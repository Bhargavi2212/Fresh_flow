"""Code-driven order pipeline: parse → inventory → status → procure (if needed) → save → confirm → customer intel."""
import json
import time
from datetime import datetime, timezone

from backend.agents.order_intake import parse_order
from backend.agents.inventory_agent import check_order_inventory
from backend.agents.procurement import generate_purchase_orders
from backend.agents.customer_intel import analyze_customer_order
from backend.tools.order_writer import save_confirmed_order, append_order_trace
from backend.tools.sms_sender import send_order_confirmation
from backend.services.websocket_manager import get_ws_manager
from backend.services.sync_database import fetch_one_sync
from backend.services.token_tracker import start_tracking, get_summary
from backend.services.input_sanitizer import validate_order_output

ORDER_ID_PLACEHOLDER = "pending"


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

    # --- Step 1: Parse order ---
    t0 = time.perf_counter()
    _broadcast(order_id, "order_intake", "started", "Parsing order", None)
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
        }
        return None, summary
    if isinstance(parse_result, dict) and parse_result.get("error"):
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
        }
        return None, summary
    _broadcast(order_id, "order_intake", "completed", "Parsed", int((time.perf_counter() - t0) * 1000))

    order_items = parse_result.get("order_items") or []
    total_amount = float(parse_result.get("total_amount") or 0)
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
    _broadcast(order_id, "order_writer", "started", "Saving order", None)
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
    }
    return None, summary
