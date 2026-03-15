"""Agent tool: lookup suppliers that carry a product (for procurement)."""
import json

from strands import tool

from backend.services.sync_database import fetch_all_sync


@tool
def get_suppliers_for_product(sku_id: str) -> str:
    """
    Get all suppliers that carry this product/SKU, with price and lead time.
    Use when deciding which supplier to use for a purchase order.
    Returns suppliers sorted by supplier_price ascending.

    Args:
        sku_id: Product SKU to look up (e.g. from procurement_signals or order items).

    Returns:
        JSON string: list of dicts with supplier_id, supplier_name, supplier_price,
        min_order_qty, lead_time_days, reliability_score, available.
    """
    if not sku_id or not str(sku_id).strip():
        return json.dumps([])
    sku_id = str(sku_id).strip()
    rows = fetch_all_sync(
        """
        SELECT sp.supplier_id, s.name AS supplier_name, sp.supplier_price,
               sp.min_order_qty, s.lead_time_days, s.reliability_score, sp.available
        FROM supplier_products sp
        JOIN suppliers s ON s.supplier_id = sp.supplier_id
        WHERE sp.sku_id = $1
        ORDER BY sp.supplier_price ASC
        """,
        sku_id,
    )
    out = []
    for r in rows:
        out.append({
            "supplier_id": r["supplier_id"],
            "supplier_name": r["supplier_name"] or "",
            "supplier_price": float(r["supplier_price"]) if r["supplier_price"] is not None else None,
            "min_order_qty": float(r["min_order_qty"]) if r["min_order_qty"] is not None else None,
            "lead_time_days": int(r["lead_time_days"]) if r["lead_time_days"] is not None else None,
            "reliability_score": float(r["reliability_score"]) if r["reliability_score"] is not None else None,
            "available": bool(r["available"]) if r["available"] is not None else True,
        })
    return json.dumps(out)
