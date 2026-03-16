"""Structured output validation for agent responses: strip markdown, parse JSON, validate keys."""
import ast
import json
import re
import logging

logger = logging.getLogger(__name__)

# Match ```json ... ``` or ``` ... ``` code fences
MARKDOWN_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL | re.IGNORECASE)


def _find_last_json_object(text: str) -> str | None:
    """Find the last complete {...} JSON object in text by matching braces."""
    start = text.rfind("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _find_all_json_objects(text: str) -> list[str]:
    """Find all complete {...} JSON objects in text (left to right, by brace matching)."""
    out = []
    i = 0
    while i < len(text):
        start = text.find("{", i)
        if start == -1:
            break
        depth = 0
        end = -1
        for j in range(start, len(text)):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end >= 0:
            out.append(text[start : end + 1])
            i = end + 1
        else:
            i = start + 1
    return out


def _normalize_json_string(raw: str) -> str:
    """Fix common model output: BOM, single-quoted keys (Nova sometimes returns these despite outputConfig)."""
    raw = raw.strip()
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    raw = re.sub(r"(\{|\,\s*)'([^']*)'\s*:", r'\1"\2":', raw)
    return raw


def _extract_text_from_agent_result(result) -> str:
    """Extract raw text from a Strands agent invoke result."""
    if hasattr(result, "message") and result.message:
        msg = result.message
        return msg if isinstance(msg, str) else str(msg)
    if hasattr(result, "content") and result.content:
        parts = result.content
        if isinstance(parts, list) and parts:
            first = parts[0]
            if hasattr(first, "text"):
                return first.text
            if isinstance(first, dict) and "text" in first:
                return first["text"]
            return str(first)
        return str(parts)
    return str(result)


def _snake_to_camel(s: str) -> str:
    parts = s.split("_")
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


def _normalize_obj_keys(obj: dict, expected_keys: list[str]) -> dict:
    """Unwrap single-key wrappers and map camelCase to snake_case for expected_keys."""
    # Unwrap if model returned e.g. {"data": {...}} or {"order": {...}}
    for wrapper in ("data", "order", "result", "output", "body"):
        if wrapper in obj and isinstance(obj.get(wrapper), dict):
            inner = obj[wrapper]
            if any(k in inner or _snake_to_camel(k) in inner for k in expected_keys):
                obj = inner
                break
    # Accept camelCase equivalents (e.g. orderItems -> order_items)
    for key in expected_keys:
        if key not in obj:
            camel = _snake_to_camel(key)
            if camel in obj:
                obj[key] = obj[camel]
    return obj


def _count_matching_keys(obj: dict, expected_keys: list[str]) -> int:
    """After _normalize_obj_keys, count how many expected_keys are in obj."""
    return sum(1 for k in expected_keys if k in obj)


def parse_agent_json(raw_output: str, expected_keys: list[str], agent_name: str) -> dict:
    """
    Strip markdown fences, find JSON object(s), parse, validate expected keys.
    If multiple {...} exist, picks the one with the most expected keys (so the order
    object is chosen over trailing {"status": "done"} etc.).
    Raises ValueError if invalid or missing keys.
    """
    if not raw_output or not isinstance(raw_output, str):
        raise ValueError(f"{agent_name}: empty or non-string output")

    text = raw_output.strip()
    m = MARKDOWN_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    # Try all JSON objects and pick the one that has the most expected keys
    all_raw = _find_all_json_objects(text)
    if not all_raw:
        raise ValueError(f"{agent_name}: no JSON object found in output")
    best_obj = None
    best_count = -1
    for raw in all_raw:
        raw = _normalize_json_string(raw)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            try:
                obj = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                continue
        if not isinstance(obj, dict):
            continue
        obj = _normalize_obj_keys(obj, expected_keys)
        count = _count_matching_keys(obj, expected_keys)
        if count > best_count:
            best_count = count
            best_obj = obj
    if best_obj is None:
        raise ValueError(f"{agent_name}: invalid JSON in output")
    missing = [k for k in expected_keys if k not in best_obj]
    if missing:
        raise ValueError(f"{agent_name}: missing keys: {missing}")
    return best_obj


def parse_agent_json_with_retry(
    agent,
    prompt: str,
    expected_keys: list[str],
    agent_name: str,
    max_retries: int = 1,
) -> dict:
    """
    Invoke agent, extract text, parse with parse_agent_json.
    On failure, retry once with a correction prompt. On final failure, return fallback dict with "error" key.
    """
    correction_prompt_suffix = (
        "\n\nYour previous response was not valid JSON or was missing required keys. "
        "Return ONLY a single JSON object with the required keys, no markdown or explanation."
    )
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            result = agent(prompt)
            text = _extract_text_from_agent_result(result)
            return parse_agent_json(text, expected_keys, agent_name)
        except ValueError as e:
            last_error = e
            logger.warning("%s parse attempt %s failed: %s", agent_name, attempt + 1, e)
            if attempt < max_retries:
                prompt = prompt + correction_prompt_suffix
    return {"error": str(last_error), "agent_name": agent_name}
