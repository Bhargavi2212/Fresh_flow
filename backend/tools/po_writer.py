"""Agent tool: create purchase orders (for Procurement Agent)."""
import json
from datetime import datetime, timezone

from strands import tool

from backend.services.sync_database import execute_sync, fetch_one_sync, fetch_val_sync
from backend.services.websocket_manager import get_ws_manager


@tool
def create_purchase_order(supplier_id: str, items: str, triggered_by: str, reasoning: str = "") -> str:
    """
    Create a purchase order for a supplier with the given line items.
    Items must be a JSON string: array of objects with sku_id and quantity.
    Unit prices are looked up from supplier_products. PO id is generated as PO-2026-XXXXXX.
    Provide reasoning (why this supplier and quantity) for visibility.

    Args:
        supplier_id: Supplier to order from.
        items: JSON string array of {sku_id, quantity} (e.g. [{"sku_id":"SAL-001","quantity":10}]).
        triggered_by: Order ID or reason that triggered this PO (e.g. order_id for traceability).
        reasoning: Short explanation of why this supplier and quantity (stored for dashboard).

    Returns:
        JSON string of the created PO: po_id, supplier_id, status, total_amount, triggered_by,
        reasoning, items (with sku_id, quantity, unit_price, line_total).
    """
    if not supplier_id or not str(supplier_id).strip():
        return json.dumps({"error": "supplier_id required"})
    supplier_id = str(supplier_id).strip()
    triggered_by = (triggered_by or "").strip() or "manual"
    reasoning = (reasoning or "").strip()[:2000] or None
    try:
        item_list = json.loads(items) if isinstance(items, str) else items
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"error": "items must be a JSON array of {sku_id, quantity}"})
    if not isinstance(item_list, list) or not item_list:
        return json.dumps({"error": "items must be a non-empty array"})

    # Resolve unit_price per sku from supplier_products for this supplier
    line_items = []
    total_amount = 0.0
    for entry in item_list:
        sku_id = (entry.get("sku_id") or "").strip()
        qty = float(entry.get("quantity") or 0)
        if not sku_id or qty <= 0:
            continue
        row = fetch_one_sync(
            "SELECT supplier_price FROM supplier_products WHERE supplier_id = $1 AND sku_id = $2 AND available = true",
            supplier_id,
            sku_id,
        )
        if not row:
            continue
        unit_price = float(row["supplier_price"] or 0)
        line_total = round(unit_price * qty, 2)
        total_amount += line_total
        line_items.append({
            "sku_id": sku_id,
            "quantity": qty,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    if not line_items:
        return json.dumps({"error": "No valid items found for this supplier"})

    # Generate PO id: PO-2026-XXXXXX (6 digits)
    count = fetch_val_sync("SELECT COUNT(*) FROM purchase_orders")
    next_num = (int(count) if count is not None else 0) + 1
    po_id = f"PO-2026-{next_num:06d}"

    execute_sync(
        """
        INSERT INTO purchase_orders (po_id, supplier_id, status, total_amount, triggered_by, reasoning)
        VALUES ($1, $2, 'draft', $3, $4, $5)
        """,
        po_id,
        supplier_id,
        round(total_amount, 2),
        triggered_by,
        reasoning,
    )
    for li in line_items:
        execute_sync(
            """
            INSERT INTO po_items (po_id, sku_id, quantity, unit_price, line_total)
            VALUES ($1, $2, $3, $4, $5)
            """,
            po_id,
            li["sku_id"],
            li["quantity"],
            li["unit_price"],
            li["line_total"],
        )

    try:
        sup = fetch_one_sync("SELECT name FROM suppliers WHERE supplier_id = $1", supplier_id)
        supplier_name = (sup["name"] or supplier_id) if sup else supplier_id
        get_ws_manager().broadcast_sync({
            "type": "purchase_order_created",
            "po_id": po_id,
            "supplier_name": supplier_name,
            "item_count": len(line_items),
            "total_amount": round(total_amount, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    return json.dumps({
        "po_id": po_id,
        "supplier_id": supplier_id,
        "status": "draft",
        "total_amount": round(total_amount, 2),
        "triggered_by": triggered_by,
        "reasoning": reasoning,
        "items": line_items,
    })
