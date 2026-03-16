"""Deterministic + retrieval-based order parser used as first pass before LLM refinement."""

from __future__ import annotations

import json
import logging
import re
from typing import Callable

from backend.tools import search_products

logger = logging.getLogger(__name__)

EXPECTED_KEYS = ["customer_id", "order_items", "total_amount", "items_needing_review", "parsing_notes"]

FILLER_WORDS = {
    "please",
    "pls",
    "need",
    "wanna",
    "want",
    "would",
    "like",
    "get",
    "send",
    "me",
    "us",
    "thanks",
    "thank",
    "you",
    "can",
    "i",
}

SPLIT_PATTERN = re.compile(r"\s*(?:,|\band\b|\bplus\b|\bwith\b|\balso\b|\&|\+)\s*", re.IGNORECASE)
QUANTITY_FIRST_PATTERN = re.compile(
    r"(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>cases?|case|lbs?|lb|pounds?|x|boxes?|bags?|flats?)?\s*(?:of\s+)?(?P<item>[a-z][a-z\s\-]{1,})",
    re.IGNORECASE,
)
ITEM_FIRST_PATTERN = re.compile(
    r"(?P<item>[a-z][a-z\s\-]{1,}?)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>cases?|case|lbs?|lb|pounds?|x|boxes?|bags?|flats?)?",
    re.IGNORECASE,
)

HIGH_CONFIDENCE = 0.85
REVIEW_CONFIDENCE = 0.70



def _normalize_text(raw_text: str) -> str:
    text = (raw_text or "").lower()
    text = text.replace("—", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9,\.\s&+]", " ", text)
    tokens = [tok for tok in text.split() if tok not in FILLER_WORDS]
    cleaned = " ".join(tokens)
    return re.sub(r"\s+", " ", cleaned).strip()



def _extract_candidate_phrases(normalized_text: str) -> list[dict]:
    segments = [seg.strip(" .") for seg in SPLIT_PATTERN.split(normalized_text) if seg.strip(" .")]
    candidates: list[dict] = []

    for seg in segments:
        match = QUANTITY_FIRST_PATTERN.search(seg) or ITEM_FIRST_PATTERN.search(seg)
        if match:
            item_phrase = re.sub(r"\s+", " ", (match.group("item") or "").strip())
            qty = float(match.group("qty"))
        else:
            item_phrase = re.sub(r"\s+", " ", seg)
            qty = 1.0

        item_phrase = re.sub(r"\b(of|the|a|an)\b", " ", item_phrase)
        item_phrase = re.sub(r"\s+", " ", item_phrase).strip()
        if len(item_phrase) < 2:
            continue

        candidates.append({
            "phrase": item_phrase,
            "quantity": max(1.0, qty),
            "source_segment": seg,
        })

    # de-duplicate by phrase, keeping largest quantity observed
    merged: dict[str, dict] = {}
    for candidate in candidates:
        phrase = candidate["phrase"]
        if phrase not in merged or candidate["quantity"] > merged[phrase]["quantity"]:
            merged[phrase] = candidate

    return list(merged.values())



def _search_candidates(
    phrase: str,
    top_k: int,
    retrieval_adapter: Callable[..., str],
) -> list[dict]:
    try:
        raw = retrieval_adapter(query=phrase, top_k=top_k)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except Exception:
        logger.exception("RAG order parser: retrieval failed for phrase=%s", phrase)
        return []



def parse_order_rag(
    raw_text: str,
    customer_id: str,
    retrieval_adapter: Callable[..., str] = search_products,
) -> dict:
    """Parse order text using deterministic extraction + retrieval matching."""
    normalized = _normalize_text(raw_text)
    candidates = _extract_candidate_phrases(normalized)

    order_items: list[dict] = []
    review_items: list[dict] = []

    for candidate in candidates:
        phrase = candidate["phrase"]
        quantity = candidate["quantity"]
        matches = _search_candidates(phrase=phrase, top_k=5, retrieval_adapter=retrieval_adapter)

        if not matches:
            review_items.append({
                "requested_phrase": phrase,
                "requested_quantity": quantity,
                "reason": "no_retrieval_results",
                "confidence": 0.0,
            })
            continue

        best = matches[0]
        confidence = float(best.get("similarity_score") or 0.0)
        item = {
            "sku_id": best.get("sku_id"),
            "product_name": best.get("name") or phrase,
            "quantity": quantity,
            "unit_price": float(best.get("unit_price") or 0),
            "line_total": round(quantity * float(best.get("unit_price") or 0), 2),
            "confidence": round(confidence, 4),
        }

        if confidence >= HIGH_CONFIDENCE:
            order_items.append(item)
        elif confidence >= REVIEW_CONFIDENCE:
            order_items.append(item)
            review_items.append({
                "requested_phrase": phrase,
                "requested_quantity": quantity,
                "matched_sku_id": best.get("sku_id"),
                "matched_name": best.get("name"),
                "confidence": round(confidence, 4),
                "reason": "low_confidence_match",
            })
        else:
            review_items.append({
                "requested_phrase": phrase,
                "requested_quantity": quantity,
                "matched_sku_id": best.get("sku_id"),
                "matched_name": best.get("name"),
                "confidence": round(confidence, 4),
                "reason": "below_threshold",
            })

    total_amount = round(sum(float(i.get("line_total") or 0) for i in order_items), 2)
    if order_items:
        notes = "RAG parser resolved items"
    elif review_items:
        notes = "RAG parser found candidate items requiring review"
    else:
        notes = "RAG parser could not identify candidate items"

    out = {
        "customer_id": customer_id,
        "order_items": order_items,
        "total_amount": total_amount,
        "items_needing_review": review_items,
        "parsing_notes": notes,
    }
    return {k: out.get(k) for k in EXPECTED_KEYS}
