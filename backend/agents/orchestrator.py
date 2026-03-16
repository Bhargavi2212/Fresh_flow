"""Code-driven order pipeline: parse → inventory → status → procure (if needed) → save → confirm → customer intel."""
import json
import logging
import re
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from backend.agents.order_intake import parse_order
from backend.agents.inventory_agent import check_order_inventory
from backend.agents.procurement import generate_purchase_orders
from backend.agents.customer_intel import analyze_customer_order
from backend.tools.order_writer import save_confirmed_order, append_order_trace
from backend.tools.sms_sender import send_order_confirmation
from backend.tools.customer_lookup import get_usual_order
from backend.tools import search_products
from backend.services.websocket_manager import get_ws_manager
from backend.services.sync_database import fetch_one_sync, fetch_all_sync
from backend.services.token_tracker import start_tracking, get_summary
from backend.services.input_sanitizer import validate_order_output

ORDER_ID_PLACEHOLDER = "pending"

USUAL_PHRASES = (
    "the usual",
    "usual",
    "my usual",
    "same as usual",
    "the usual please",
    "usual order",
    "my regular order",
    "regular order",
    "reorder last",
    "last order",
    "same as last time",
    "last time",
    "repeat last order",
    "same order",
)


def _normalized_message_is_usual(raw_message: str) -> bool:
    if not raw_message or not isinstance(raw_message, str):
        return False
    normalized = raw_message.strip().lower()
    return any(phrase in normalized for phrase in USUAL_PHRASES)


def _build_usual_or_last_order_items(customer_id: str) -> tuple[list[dict], float, str] | None:
    """If customer has 'usual' or last order, return (order_items, total_amount, parsing_notes). Else None."""
    try:
        usual_raw = get_usual_order(customer_id=customer_id)
        usual_data = json.loads(usual_raw) if isinstance(usual_raw, str) else usual_raw
        items = usual_data.get("items") or []
        notes = "Usual order"
        if not items:
            # Fallback: last order's items
            row = fetch_one_sync(
                "SELECT order_id FROM orders WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 1",
                customer_id,
            )
            if not row:
                return None
            rows = fetch_all_sync(
                """SELECT oi.sku_id, oi.quantity, oi.unit_price, oi.line_total
                   FROM order_items oi WHERE oi.order_id = $1""",
                row["order_id"],
            )
            if not rows:
                return None
            # Use last order's line items directly (unit_price from order_items so we don't drop inactive products)
            order_items = []
            total_amount = 0.0
            for r in rows:
                sku_id = (r.get("sku_id") or "").strip()
                if not sku_id:
                    continue
                qty = float(r.get("quantity") or 0)
                if qty <= 0:
                    continue
                unit_price = float(r.get("unit_price") or 0)
                line_total = float(r.get("line_total") or 0) if r.get("line_total") is not None else round(qty * unit_price, 2)
                total_amount += line_total
                name_row = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
                order_items.append({
                    "sku_id": sku_id,
                    "product_name": (name_row["name"] if name_row else sku_id),
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "confidence": 0.95,
                })
            if not order_items:
                return None
            return (order_items, round(total_amount, 2), "Last order (no usual pattern yet)")
        order_items = []
        total_amount = 0.0
        for it in items:
            sku_id = (it.get("sku_id") or "").strip()
            if not sku_id:
                continue
            qty = float(it.get("median_quantity") or it.get("quantity") or 0)
            if qty <= 0:
                continue
            prod = fetch_one_sync("SELECT name, unit_price FROM products WHERE sku_id = $1 AND status = 'active'", sku_id)
            if not prod:
                continue
            unit_price = float(prod["unit_price"] or 0)
            line_total = round(qty * unit_price, 2)
            total_amount += line_total
            order_items.append({
                "sku_id": sku_id,
                "product_name": (prod.get("name") or sku_id),
                "quantity": qty,
                "unit_price": unit_price,
                "line_total": line_total,
                "confidence": 0.95,
            })
        if not order_items:
            return None
        return (order_items, round(total_amount, 2), notes)
    except Exception:
        return None


def _build_free_text_order_items(raw_message: str, customer_id: str) -> tuple[list[dict], float, str] | None:
    """
    When Converse returns 0 items or an error, try to resolve at least one product from free text:
    use the message (or a product-like substring) as search_products query and take the top hit.
    """
    if not raw_message or not isinstance(raw_message, str):
        return None
    text = raw_message.strip()
    if len(text) < 2:
        return None
    stopwords = {
        "please", "pls", "thanks", "thank", "you", "need", "want", "order", "for", "me", "just", "the",
    }

    def _clean_phrase(phrase: str) -> str:
        phrase = re.sub(r"\s+", " ", (phrase or "").strip())
        phrase = re.sub(r"^[^a-zA-Z0-9]+|[^a-zA-Z0-9]+$", "", phrase)
        if not phrase:
            return ""
        words = [w for w in phrase.split() if w.lower() not in stopwords]
        return " ".join(words).strip()

    def try_query(query: str, quantity: float = 1.0) -> tuple[dict, float] | None:
        query = _clean_phrase(query)
        if not query or len(query) < 2:
            return None
        try:
            result_json = search_products(query=query[:120], top_k=3)
            results = json.loads(result_json) if isinstance(result_json, str) else result_json
            if not results or not isinstance(results, list):
                return None
            best = results[0]
            sku_id = (best.get("sku_id") or "").strip()
            if not sku_id:
                return None
            sim = float(best.get("similarity_score") or 0)
            if sim < 0.35:
                return None
            unit_price = float(best.get("unit_price") or 0)
            product_name = best.get("name") or sku_id
            qty = max(1.0, float(quantity or 1.0))
            line_total = round(qty * unit_price, 2)
            return (
                {
                    "sku_id": sku_id,
                    "product_name": product_name,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "line_total": line_total,
                    "confidence": round(sim, 2),
                },
                line_total,
            )
        except Exception:
            return None

    def _extract_candidates(message: str) -> list[tuple[str, float]]:
        candidates: list[tuple[str, float]] = []
        # Pattern like: "2 cases salmon", "3 shrimp", "1.5 lb cod"
        pattern = re.compile(
            r"(?P<qty>\d+(?:\.\d+)?)\s*(?:cases?|lbs?|lb|pounds?|x|\*)?\s+(?P<name>[a-zA-Z][^,;\n]+?)(?=(?:\s*(?:,|;|\band\b|&)\s*)|$)",
            re.IGNORECASE,
        )
        for m in pattern.finditer(message):
            name = _clean_phrase(m.group("name"))
            if not name:
                continue
            qty = max(1.0, float(m.group("qty")))
            candidates.append((name, qty))

        if candidates:
            return candidates

        parts = re.split(r"(?:,|;|\band\b|\n|&)", message, flags=re.IGNORECASE)
        for p in parts:
            p = (p or "").strip()
            if not p:
                continue
            qty = 1.0
            m = re.match(r"^(\d+(?:\.\d+)?)\s*(?:cases?|lbs?|lb|pounds?|x|\*)?\s+(.*)$", p, re.IGNORECASE)
            if m:
                qty = max(1.0, float(m.group(1)))
                p = m.group(2)
            name = _clean_phrase(p)
            if name:
                candidates.append((name, qty))
        return candidates[:8]

    order_items: list[dict] = []
    total = 0.0
    by_sku: dict[str, int] = {}
    for candidate, qty in _extract_candidates(text):
        resolved = try_query(candidate, qty)
        if not resolved:
            continue
        item, line_total = resolved
        sku = item["sku_id"]
        existing_idx = by_sku.get(sku)
        if existing_idx is not None:
            existing = order_items[existing_idx]
            existing["quantity"] = round(float(existing.get("quantity") or 0) + float(item.get("quantity") or 0), 3)
            existing["line_total"] = round(float(existing.get("line_total") or 0) + line_total, 2)
            existing["confidence"] = max(float(existing.get("confidence") or 0), float(item.get("confidence") or 0))
        else:
            by_sku[sku] = len(order_items)
            order_items.append(item)
        total = round(total + line_total, 2)

    if order_items:
        return (order_items, total, "Parsed from free text (fallback)")

    # Try full message first, then product-only (strip leading numbers and unit words)
    out = try_query(text)
    if out is not None:
        item, line_total = out
        return ([item], line_total, "Parsed from free text (fallback)")
    product_part = re.sub(r"\b\d+(?:\.\d+)?\s*(?:cases?|lbs?|lb|pounds?|x|\*)?\s*", "", text, flags=re.IGNORECASE).strip()
    if product_part and product_part != text:
        out = try_query(product_part)
        if out is not None:
            item, line_total = out
            return ([item], line_total, "Parsed from free text (fallback)")
    return None


def _broadcast(order_id: str, agent_name: str, status: str, summary: str, duration_ms: int | None = None):
    try:
        get_ws_manager().broadcast_sync({
            "type": "agent_activity",
            "order_id": order_id,
            "agent_name": agent_name,
            "status": status,
            "summary": summary,
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass


def run_orchestrator(
    raw_message: str,
    customer_id: str,
    channel: str,
    customer_phone: str = "",
) -> tuple[object, dict | None]:
    """
    Run the full order pipeline in code: no LLM for routing. Each step is a Python call
    with try/except; WebSocket events at each step. Returns (None, summary_dict).
    summary_dict has order_id, status, customer_name, channel, item_count, total_amount,
    items_confirmed, items_needing_review, substitutions_made, purchase_orders_generated,
    confirmation_sent. On parse failure returns early with status needs_review.
    """
    customer_phone = (customer_phone or "").strip()
    order_id = ORDER_ID_PLACEHOLDER
    customer_name = "Customer"
    try:
        row = fetch_one_sync("SELECT name FROM customers WHERE customer_id = $1", customer_id)
        if row and row.get("name"):
            customer_name = (row["name"] or "Customer").strip()
    except Exception:
        pass

    start_tracking()
    _broadcast(order_id, "orchestrator", "started", "Processing order", None)
    start_total = time.perf_counter()

    # --- Fast path: "the usual" / "last order" ---
    parse_result = None
    if _normalized_message_is_usual(raw_message):
        built = _build_usual_or_last_order_items(customer_id)
        if built:
            order_items_built, total_amount_built, parsing_notes = built
            parse_result = {
                "customer_id": customer_id,
                "order_items": order_items_built,
                "total_amount": total_amount_built,
                "items_needing_review": [],
                "parsing_notes": parsing_notes,
            }

    # --- Step 1: Parse order (unless fast path filled parse_result) ---
    t0 = time.perf_counter()
    _broadcast(order_id, "order_intake", "started", "Parsing order", None)
    if parse_result is None:
        try:
            parse_result = parse_order(raw_message, customer_id)
        except Exception as e:
            _broadcast(order_id, "order_intake", "failed", str(e), int((time.perf_counter() - t0) * 1000))
            summary = {
                "order_id": "",
                "status": "needs_review",
                "customer_name": customer_name,
                "channel": channel or "web",
                "item_count": 0,
                "total_amount": 0,
                "items_confirmed": 0,
                "items_needing_review": 0,
                "substitutions_made": 0,
                "purchase_orders_generated": 0,
                "confirmation_sent": False,
                "parsed_items": [],
                "message": "Order processing failed. Please try again or contact your sales rep.",
            }
            return None, summary
    if isinstance(parse_result, dict) and parse_result.get("error"):
        # Try free-text fallback before giving up: often Converse fails but the message is clear (e.g. "2 cases salmon").
        built = _build_free_text_order_items(raw_message, customer_id)
        if built:
            order_items_built, total_amount_built, parsing_notes = built
            parse_result = {
                "customer_id": customer_id,
                "order_items": order_items_built,
                "total_amount": total_amount_built,
                "items_needing_review": [],
                "parsing_notes": parsing_notes,
            }
            logger.info("order_writer: parse had error, used free-text fallback, now %s items", len(order_items_built))
        else:
            _broadcast(order_id, "order_intake", "failed", parse_result.get("error", "Parse failed"), int((time.perf_counter() - t0) * 1000))
            summary = {
                "order_id": "",
                "status": "needs_review",
                "customer_name": customer_name,
                "channel": channel or "web",
                "item_count": 0,
                "total_amount": float(parse_result.get("total_amount", 0) or 0),
                "items_confirmed": 0,
                "items_needing_review": 0,
                "substitutions_made": 0,
                "purchase_orders_generated": 0,
                "confirmation_sent": False,
                "parsed_items": [],
                "message": "We couldn't parse your order. Please list the items you need or try 'Reorder last order'.",
            }
            return None, summary
    valid, security_note = validate_order_output(parse_result, customer_id)
    if not valid:
        _broadcast(order_id, "order_intake", "failed", security_note or "Output validation failed", int((time.perf_counter() - t0) * 1000))
        summary = {
            "order_id": "",
            "status": "needs_review",
            "customer_name": customer_name,
            "channel": channel or "web",
            "item_count": 0,
            "total_amount": 0,
            "items_confirmed": 0,
            "items_needing_review": 0,
            "substitutions_made": 0,
            "purchase_orders_generated": 0,
            "confirmation_sent": False,
            "security_note": security_note or "Output validation failed",
            "parsed_items": [],
            "message": security_note or "Order validation failed. Please check and try again.",
        }
        return None, summary
    _broadcast(order_id, "order_intake", "completed", "Parsed", int((time.perf_counter() - t0) * 1000))

    order_items = parse_result.get("order_items") or []
    logger.info(
        "order_writer: parse_result order_items_count=%s has_error=%s parsing_notes=%s",
        len(order_items),
        bool(parse_result.get("error")),
        (parse_result.get("parsing_notes") or "")[:200],
    )
    total_amount = float(parse_result.get("total_amount") or 0)
    # Fallback: if parse returned 0 items but message suggests "usual" or "last order", try usual/last
    if not order_items and _normalized_message_is_usual(raw_message):
        built = _build_usual_or_last_order_items(customer_id)
        if built:
            order_items_built, total_amount_built, parsing_notes = built
            parse_result = {
                "customer_id": customer_id,
                "order_items": order_items_built,
                "total_amount": total_amount_built,
                "items_needing_review": [],
                "parsing_notes": f"{parse_result.get('parsing_notes') or ''}; {parsing_notes}".strip("; "),
            }
            order_items = order_items_built
            total_amount = total_amount_built
            logger.info("order_writer: used usual/last fallback after parse returned 0 items, now %s items", len(order_items))
    if not order_items:
        built = _build_free_text_order_items(raw_message, customer_id)
        if built:
            order_items_built, total_amount_built, parsing_notes = built
            parse_result = {
                "customer_id": customer_id,
                "order_items": order_items_built,
                "total_amount": total_amount_built,
                "items_needing_review": [],
                "parsing_notes": f"{parse_result.get('parsing_notes') or ''}; {parsing_notes}".strip("; "),
            }
            order_items = order_items_built
            total_amount = total_amount_built
            logger.info("order_writer: used free-text fallback, now %s items", len(order_items))
    order_items_json = json.dumps(order_items, default=str)

    # --- Step 2: Check inventory ---
    t1 = time.perf_counter()
    _broadcast(order_id, "inventory", "started", "Checking inventory", None)
    try:
        inv_result = check_order_inventory(order_items_json, customer_id)
    except Exception as e:
        _broadcast(order_id, "inventory", "failed", str(e), int((time.perf_counter() - t1) * 1000))
        inv_result = {"checked_items": order_items, "procurement_signals": [], "summary": {}}
    if isinstance(inv_result, dict) and inv_result.get("error"):
        inv_result = {"checked_items": order_items, "procurement_signals": [], "summary": {}}
    _broadcast(order_id, "inventory", "completed", "Checked", int((time.perf_counter() - t1) * 1000))

    checked_items = inv_result.get("checked_items") or order_items
    procurement_signals = inv_result.get("procurement_signals") or []
    inv_summary = inv_result.get("summary") or {}

    # --- Step 3: Decide status in code ---
    confidences = [float(i.get("confidence", 0)) for i in checked_items if i.get("confidence") is not None]
    min_confidence = min(confidences) if confidences else 0.0
    all_available = all(
        (i.get("availability_status") or i.get("availabilityStatus") or "available") == "available"
        for i in checked_items
    )
    any_out_of_stock_no_sub = any(
        (i.get("availability_status") or i.get("availabilityStatus")) == "out_of_stock"
        and not (i.get("suggested_substitutions") or i.get("substituted_from"))
        for i in checked_items
    )
    if min_confidence >= 0.9 and all_available:
        status = "confirmed"
    elif min_confidence < 0.8 or any_out_of_stock_no_sub:
        status = "needs_review"
    else:
        status = "confirmed"  # with notes

    # --- Step 4: Procurement if needed ---
    purchase_orders_generated = 0
    proc_result = {}
    if procurement_signals:
        t2 = time.perf_counter()
        _broadcast(order_id, "procurement", "started", "Creating POs", None)
        try:
            proc_result = generate_purchase_orders(json.dumps(procurement_signals, default=str), "orchestrator")
        except Exception:
            proc_result = {"purchase_orders": [], "total_procurement_cost": 0, "items_not_sourced": []}
        if isinstance(proc_result, dict) and not proc_result.get("error"):
            purchase_orders_generated = len(proc_result.get("purchase_orders") or [])
        _broadcast(order_id, "procurement", "completed", f"{purchase_orders_generated} POs", int((time.perf_counter() - t2) * 1000))

    # --- Step 5: Build order_data, save, get order_id ---
    agent_trace = {
        "order_intake": parse_result,
        "inventory": inv_result,
        "procurement": proc_result if procurement_signals else None,
    }
    confidence_score = min_confidence if confidences else 1.0
    order_data = {
        "customer_id": customer_id,
        "channel": channel or "web",
        "raw_message": raw_message,
        "status": status,
        "confidence_score": confidence_score,
        "items": checked_items,
        "agent_trace": agent_trace,
    }
    t3 = time.perf_counter()
    num_parsed = len(order_items)
    num_checked = len(checked_items)
    _broadcast(order_id, "order_writer", "started", "Saving order", None)
    logger.info(
        "order_writer: parsed_items=%s checked_items=%s inv_summary=%s",
        num_parsed, num_checked, inv_summary,
    )
    if not checked_items:
        if num_parsed == 0:
            skip_reason = "Parse returned 0 items (no line items could be identified from the message)."
            if _normalized_message_is_usual(raw_message):
                user_message = (
                    "We don't have a usual or last order on file for you yet. "
                    "Please list the items you need (e.g. '2 cases salmon, 1 flat strawberries')."
                )
            else:
                user_message = (
                    "We couldn't identify any items in your order. "
                    "Please list the items you need (e.g. product names and quantities), or try 'Reorder last order' to repeat your previous order."
                )
        else:
            skip_reason = f"Parse returned {num_parsed} item(s) but inventory check produced 0 items to save (e.g. all out of stock with no substitutions)."
            user_message = (
                "Your items couldn't be fulfilled from current stock (out of stock or unavailable). "
                "Your sales rep can suggest alternatives or restock dates."
            )
        logger.warning(
            "order_writer: skipping order — %s customer_id=%s raw_message_len=%s",
            skip_reason, customer_id, len(raw_message or ""),
        )
        broadcast_summary = f"No items to save: {skip_reason}"
        _broadcast(ORDER_ID_PLACEHOLDER, "order_writer", "failed", broadcast_summary, int((time.perf_counter() - t3) * 1000))
        summary = {
            "order_id": "",
            "status": "needs_review",
            "customer_name": customer_name,
            "channel": channel or "web",
            "item_count": 0,
            "total_amount": total_amount,
            "items_confirmed": 0,
            "items_needing_review": 0,
            "substitutions_made": 0,
            "purchase_orders_generated": purchase_orders_generated,
            "confirmation_sent": False,
            "parsed_items": [],
            "message": user_message,
        }
        return None, summary
    try:
        save_raw = save_confirmed_order(json.dumps(order_data, default=str))
        save_out = json.loads(save_raw) if isinstance(save_raw, str) else save_raw
        order_id = (save_out.get("order_id") or "").strip() or ORDER_ID_PLACEHOLDER
    except Exception as e:
        _broadcast(ORDER_ID_PLACEHOLDER, "order_writer", "failed", str(e), int((time.perf_counter() - t3) * 1000))
        summary = {
            "order_id": "",
            "status": "needs_review",
            "customer_name": customer_name,
            "channel": channel or "web",
            "item_count": len(checked_items),
            "total_amount": total_amount,
            "items_confirmed": inv_summary.get("available", 0),
            "items_needing_review": inv_summary.get("partial", 0) + inv_summary.get("out_of_stock", 0),
            "substitutions_made": 0,
            "purchase_orders_generated": purchase_orders_generated,
            "confirmation_sent": False,
            "parsed_items": checked_items,
        }
        return None, summary
    _broadcast(order_id, "order_writer", "completed", f"Saved {order_id}", int((time.perf_counter() - t3) * 1000))

    # --- Step 6: Send confirmation ---
    items_summary = f"{len(checked_items)} items"
    if checked_items:
        names = [i.get("product_name") or i.get("name") or i.get("sku_id") for i in checked_items[:5]]
        items_summary = ", ".join(n for n in names if n)[:80] or items_summary
    special_notes = (parse_result.get("parsing_notes") or "")[:200] or ""
    try:
        conf_out = send_order_confirmation(
            order_id,
            customer_phone,
            customer_name,
            status,
            items_summary,
            total_amount,
            special_notes,
        )
        conf_obj = json.loads(conf_out) if isinstance(conf_out, str) else conf_out
        confirmation_sent = conf_obj.get("sent", False)
    except Exception:
        confirmation_sent = False

    # --- Step 7: Analyze customer, append trace ---
    order_summary_json = json.dumps({
        "order_id": order_id,
        "customer_id": customer_id,
        "item_count": len(checked_items),
        "total_amount": total_amount,
        "status": status,
    }, default=str)
    try:
        intel_result = analyze_customer_order(customer_id, order_summary_json)
        append_order_trace(order_id, "customer_intel", intel_result)
    except Exception:
        pass
    try:
        append_order_trace(order_id, "token_usage", get_summary())
    except Exception:
        pass

    # --- Step 8: Summary ---
    items_confirmed = int(inv_summary.get("available", 0))
    items_needing_review = int(inv_summary.get("partial", 0)) + int(inv_summary.get("out_of_stock", 0))
    substitutions_made = sum(1 for i in checked_items if i.get("substituted_from") or i.get("substitutedFrom"))

    duration_ms = int((time.perf_counter() - start_total) * 1000)
    _broadcast(order_id, "orchestrator", "completed", f"Order {order_id} {status}", duration_ms)

    summary = {
        "order_id": order_id,
        "status": status,
        "customer_name": customer_name,
        "channel": channel or "web",
        "item_count": len(checked_items),
        "total_amount": total_amount,
        "items_confirmed": items_confirmed,
        "items_needing_review": items_needing_review,
        "substitutions_made": substitutions_made,
        "purchase_orders_generated": purchase_orders_generated,
        "confirmation_sent": confirmation_sent,
        "parsed_items": checked_items,
    }
    return None, summary
