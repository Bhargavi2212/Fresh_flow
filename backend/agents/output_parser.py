"""Structured output validation for agent responses: strip markdown, parse JSON, validate keys."""
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


def parse_agent_json(raw_output: str, expected_keys: list[str], agent_name: str) -> dict:
    """
    Strip markdown fences, find last JSON object via regex, parse, validate expected keys.
    Raises ValueError if invalid or missing keys.
    """
    if not raw_output or not isinstance(raw_output, str):
        raise ValueError(f"{agent_name}: empty or non-string output")

    text = raw_output.strip()
    # Strip markdown code fences
    m = MARKDOWN_FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    raw = _find_last_json_object(text)
    if not raw:
        raise ValueError(f"{agent_name}: no JSON object found in output")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"{agent_name}: invalid JSON: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError(f"{agent_name}: root is not a JSON object")
    missing = [k for k in expected_keys if k not in obj]
    if missing:
        raise ValueError(f"{agent_name}: missing keys: {missing}")
    return obj


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
