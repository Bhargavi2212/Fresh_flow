"""Agent tool: persist confirmed order and items (for Orchestrator)."""
import json
import logging
from datetime import datetime, timezone

from strands import tool

from backend.services.sync_database import execute_sync, fetch_all_sync, fetch_one_sync, fetch_val_sync
from backend.services.websocket_manager import get_ws_manager

logger = logging.getLogger(__name__)


def deduct_inventory(sku_id: str, quantity: float) -> dict:
    """
    Deduct quantity from inventory for sku_id using FIFO (earliest expiration first).
    Fetches lots ordered by expiration_date ASC, subtracts from each until fulfilled.
    Returns total_deducted, lots_modified, remaining_to_deduct.
    """
    remaining = float(quantity)
    total_deducted = 0.0
    lots_modified = 0
    lots = fetch_all_sync(
        """SELECT id, quantity, expiration_date FROM inventory
           WHERE sku_id = $1 AND quantity > 0
           ORDER BY expiration_date ASC NULLS LAST, id ASC""",
        sku_id,
    )
    for row in lots:
        if remaining <= 0:
            break
        lot_id = row["id"]
        lot_qty = float(row["quantity"] or 0)
        deduct = min(remaining, lot_qty)
        if deduct <= 0:
            continue
        new_qty = lot_qty - deduct
        execute_sync(
            "UPDATE inventory SET quantity = $1, updated_at = NOW() WHERE id = $2",
            new_qty,
            lot_id,
        )
        total_deducted += deduct
        remaining -= deduct
        lots_modified += 1
    if remaining > 0:
        logger.warning(
            "deduct_inventory: sku_id=%s requested=%.2f total_deducted=%.2f remaining_to_deduct=%.2f",
            sku_id, quantity, total_deducted, remaining,
        )
    return {
        "total_deducted": total_deducted,
        "lots_modified": lots_modified,
        "remaining_to_deduct": remaining,
    }


@tool
def save_confirmed_order(order_data: str) -> str:
    """
    Save a confirmed order and its line items to the database. Call after parsing and
    inventory check (and optional procurement). order_data must be a JSON string with
    customer_id, channel, raw_message, status, confidence_score, items (array with
    sku_id, quantity, unit_price, line_total, etc.), and agent_trace (full trace for storage).

    Args:
        order_data: JSON string with customer_id, channel, raw_message, status,
          confidence_score, items[], agent_trace.

    Returns:
        JSON string with order_id and status.
    """
    try:
        data = json.loads(order_data) if isinstance(order_data, str) else order_data
    except (json.JSONDecodeError, TypeError):
        logger.warning("order_writer: invalid order_data (not valid JSON)")
        return json.dumps({"error": "order_data must be a valid JSON string", "order_id": None, "status": None})

    customer_id = (data.get("customer_id") or "").strip()
    if not customer_id:
        logger.warning("order_writer: missing customer_id")
        return json.dumps({"error": "customer_id required", "order_id": None, "status": None})

    channel = (data.get("channel") or "web").strip()
    raw_message = data.get("raw_message") or data.get("rawMessage") or ""
    status = (data.get("status") or "confirmed").strip()
    confidence_score = data.get("confidence_score")
    if confidence_score is not None:
        confidence_score = float(confidence_score)
    else:
        confidence_score = 1.0

    items = data.get("items") or data.get("order_items") or []
    if not isinstance(items, list):
        items = []

    logger.info("order_writer: saving order customer_id=%s item_count=%s", customer_id, len(items))
    if not items:
        logger.warning("order_writer: refusing to save order with 0 items customer_id=%s", customer_id)
        return json.dumps({"error": "No items to save", "order_id": None, "status": None})

    total_amount = 0.0
    for it in items:
        lt = it.get("line_total") or it.get("lineTotal")
        if lt is not None:
            total_amount += float(lt)
        elif it.get("quantity") and it.get("unit_price"):
            total_amount += float(it.get("quantity")) * float(it.get("unit_price") or 0)
    total_amount = round(total_amount, 2)

    agent_trace = data.get("agent_trace") or {}
    if not isinstance(agent_trace, dict):
        agent_trace = {}
    trace_str = json.dumps(agent_trace, default=str)

    # Generate order_id: ORD-2026-XXXXXX (6 digits)
    count = fetch_val_sync("SELECT COUNT(*) FROM orders")
    next_num = (int(count) if count is not None else 0) + 1
    order_id = f"ORD-2026-{next_num:06d}"

    execute_sync(
        """
        INSERT INTO orders (order_id, customer_id, channel, raw_message, status, confidence_score, total_amount, agent_trace)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)
        """,
        order_id,
        customer_id,
        channel,
        raw_message[:10000] if raw_message else None,
        status,
        confidence_score,
        total_amount,
        trace_str,
    )
    logger.info("order_writer: saved order_id=%s customer_id=%s item_count=%s total_amount=%s", order_id, customer_id, len(items), total_amount)

    for it in items:
        sku_id = (it.get("sku_id") or it.get("skuId") or "").strip()
        if not sku_id:
            continue
        raw_text = (it.get("raw_text") or it.get("rawText") or "")[:200]
        qty = float(it.get("quantity") or 0)
        unit_price = it.get("unit_price") or it.get("unitPrice")
        unit_price = float(unit_price) if unit_price is not None else None
        line_total = it.get("line_total") or it.get("lineTotal")
        line_total = float(line_total) if line_total is not None else (qty * unit_price if unit_price is not None else None)
        match_conf = it.get("confidence")
        match_conf = float(match_conf) if match_conf is not None else None
        item_status = (it.get("availability_status") or it.get("availabilityStatus") or "available")[:20]
        substituted_from = (it.get("substituted_from") or it.get("substitutedFrom") or "")[:20] or None
        notes = (it.get("notes") or "")[:500] or None

        execute_sync(
            """
            INSERT INTO order_items (order_id, sku_id, raw_text, quantity, unit_price, line_total, match_confidence, status, substituted_from, notes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            order_id,
            sku_id,
            raw_text or None,
            qty,
            unit_price,
            line_total,
            match_conf,
            item_status,
            substituted_from,
            notes,
        )

    # FIFO inventory deduction for available/partial items; track before/after per sku for WebSocket
    deduction_log: dict[str, tuple[float, float]] = {}
    for it in items:
        item_status_val = (it.get("availability_status") or it.get("availabilityStatus") or "available")[:20]
        if item_status_val not in ("available", "partial"):
            continue
        sku_id = (it.get("sku_id") or it.get("skuId") or "").strip()
        if not sku_id:
            continue
        qty = float(it.get("quantity") or 0)
        if qty <= 0:
            continue
        prev_row = fetch_one_sync(
            "SELECT COALESCE(SUM(quantity), 0) AS total FROM inventory WHERE sku_id = $1",
            sku_id,
        )
        prev_qty = float(prev_row["total"]) if prev_row else 0.0
        ded = deduct_inventory(sku_id, qty)
        new_qty = prev_qty - ded["total_deducted"]
        deduction_log[sku_id] = (prev_qty, new_qty)
        if ded["remaining_to_deduct"] > 0:
            logger.warning(
                "save_confirmed_order: sku_id=%s remaining_to_deduct=%.2f",
                sku_id, ded["remaining_to_deduct"],
            )

    # Broadcast order_confirmed and inventory_update with real before/after
    try:
        cust = fetch_one_sync("SELECT name FROM customers WHERE customer_id = $1", customer_id)
        customer_name = (cust["name"] or "Customer").strip() if cust else "Customer"
        get_ws_manager().broadcast_sync({
            "type": "order_confirmed",
            "order_id": order_id,
            "customer_name": customer_name,
            "status": status,
            "item_count": len(items),
            "total_amount": total_amount,
            "confidence_score": confidence_score,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        for sku_id, (prev_qty, new_qty) in deduction_log.items():
            inv = fetch_one_sync(
                "SELECT reorder_point FROM inventory WHERE sku_id = $1 LIMIT 1",
                sku_id,
            )
            reorder = float(inv["reorder_point"]) if inv and inv.get("reorder_point") is not None else 0.0
            prod = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
            product_name = (prod["name"] or sku_id) if prod else sku_id
            get_ws_manager().broadcast_sync({
                "type": "inventory_update",
                "sku_id": sku_id,
                "product_name": product_name,
                "previous_quantity": prev_qty,
                "new_quantity": new_qty,
                "is_low_stock": new_qty <= reorder if reorder else False,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
    except Exception:
        pass

    return json.dumps({"order_id": order_id, "status": status})


@tool
def append_order_trace(order_id: str, trace_key: str, trace_value: str | dict) -> str:
    """
    Append a key to an order's agent_trace (e.g. customer_intel after analyze_customer_order).
    Call after the order exists and you have new trace data to store.

    Args:
        order_id: The order's ID (from save_confirmed_order).
        trace_key: Key to add (e.g. "customer_intel").
        trace_value: JSON string or dict to merge into agent_trace.

    Returns:
        JSON with success true/false.
    """
    order_id = (order_id or "").strip()
    trace_key = (trace_key or "").strip()
    if not order_id or not trace_key:
        return json.dumps({"success": False, "error": "order_id and trace_key required"})
    if isinstance(trace_value, dict):
        trace_value = json.dumps(trace_value, default=str)
    try:
        # Ensure trace_value is valid JSON so we can cast to jsonb
        json.loads(trace_value)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"success": False, "error": "trace_value must be valid JSON"})
    try:
        execute_sync(
            """UPDATE orders SET agent_trace = COALESCE(agent_trace, '{}'::jsonb) || jsonb_build_object($1::text, $2::jsonb) WHERE order_id = $3""",
            trace_key,
            trace_value,
            order_id,
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
    return json.dumps({"success": True, "order_id": order_id, "trace_key": trace_key})
