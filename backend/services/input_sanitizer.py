"""Input sanitization and output validation for prompt-injection protection."""
import re
import logging
from typing import Any

from backend.services.sync_database import fetch_one_sync

logger = logging.getLogger(__name__)

MAX_ORDER_INPUT_LEN = 2000

# Lines containing these (case-insensitive) are stripped as injection patterns
INJECTION_PATTERNS = re.compile(
    r"^.*(ignore|disregard|system\s*prompt|instructions|you\s+are|act\s+as|return\s+json|output\s+format).*$",
    re.MULTILINE | re.IGNORECASE,
)
# XML-like tags and markdown code fences to strip
XML_OR_FENCE = re.compile(r"</?[a-zA-Z][^>]*>|```[a-z]*\n?|```", re.MULTILINE)


def sanitize_order_input(raw_text: str) -> str:
    """
    Strip injection patterns (lines with ignore, disregard, system prompt, etc.),
    truncate to 2000 chars, strip non-printable. Returns sanitized string.
    """
    if not raw_text or not isinstance(raw_text, str):
        return ""
    text = raw_text
    lines = text.split("\n")
    kept = []
    for line in lines:
        if INJECTION_PATTERNS.match(line.strip()):
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = XML_OR_FENCE.sub("", text)
    text = "".join(c for c in text if c.isprintable() or c in "\n\r\t")
    text = text.strip()
    if len(text) > MAX_ORDER_INPUT_LEN:
        text = text[:MAX_ORDER_INPUT_LEN]
    return text


def validate_order_output(parsed_json: dict, customer_id: str) -> tuple[bool, str | None]:
    """
    Validate parsed order output: total_amount in range, quantities 0.1-1000,
    each sku_id exists in products, customer_id matches. Returns (valid, security_note).
    If invalid, security_note is set for needs_review.
    """
    if not isinstance(parsed_json, dict):
        return False, "Invalid parse result"
    if parsed_json.get("error"):
        return False, parsed_json.get("error", "Parse error")

    customer_id = (customer_id or "").strip()
    if parsed_json.get("customer_id", "").strip() != customer_id:
        return False, "customer_id mismatch"

    total = parsed_json.get("total_amount")
    if total is not None:
        try:
            t = float(total)
            if t < 0 or t > 50000:
                return False, "total_amount out of range [0, 50000]"
        except (TypeError, ValueError):
            return False, "total_amount invalid"

    items = parsed_json.get("order_items") or []
    if not isinstance(items, list):
        return False, "order_items invalid"
    for it in items:
        qty = it.get("quantity")
        if qty is not None:
            try:
                q = float(qty)
                if q < 0.1 or q > 1000:
                    return False, f"quantity out of range 0.1-1000: {q}"
            except (TypeError, ValueError):
                return False, "quantity invalid"
        sku = (it.get("sku_id") or "").strip()
        if sku:
            row = fetch_one_sync("SELECT 1 FROM products WHERE sku_id = $1 AND status = 'active'", sku)
            if not row:
                return False, f"sku_id not found or inactive: {sku}"

    return True, None
