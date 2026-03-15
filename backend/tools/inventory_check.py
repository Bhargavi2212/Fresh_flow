"""Agent tools: check stock levels and items expiring soon."""
import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from strands import tool

from backend.services.sync_database import fetch_all_sync, fetch_one_sync


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


@tool
def check_stock(sku_id: str, requested_quantity: float) -> str:
    """
    Check current inventory for a SKU. Use for every order line to see if we can fulfill.
    Returns total quantity, lot-level details (FIFO by expiration), reorder_point,
    and flags for below reorder or out of stock. In Phase 2 available_quantity equals
    total (no committed-unshipped). If requested exceeds available, shortfall is included.

    Args:
        sku_id: Product SKU to check.
        requested_quantity: Quantity the customer requested.

    Returns:
        JSON string: current_total_quantity, available_quantity, lot_details (array of
        {lot_number, quantity, received_date, expiration_date} sorted by expiration ASC),
        reorder_point, is_below_reorder, is_out_of_stock, shortfall (if requested > available).
    """
    product = fetch_one_sync("SELECT sku_id, name FROM products WHERE sku_id = $1", sku_id)
    if not product:
        return json.dumps({"error": "Product not found", "sku_id": sku_id, "current_total_quantity": 0, "is_out_of_stock": True})

    lots = fetch_all_sync(
        """SELECT id, lot_number, quantity, reorder_point, received_date, expiration_date
           FROM inventory WHERE sku_id = $1 ORDER BY expiration_date ASC NULLS LAST""",
        sku_id,
    )
    total = sum(float(r["quantity"] or 0) for r in lots)
    reorder_point = 0.0
    for r in lots:
        rp = r.get("reorder_point")
        if rp is not None:
            reorder_point = max(reorder_point, float(rp))
    available = total  # Phase 2: no committed tracking
    is_out = total == 0
    is_below = total < reorder_point if reorder_point else False
    shortfall = max(0.0, requested_quantity - available) if requested_quantity > available else None

    lot_details = [
        {
            "lot_number": r["lot_number"],
            "quantity": float(r["quantity"] or 0),
            "received_date": _serialize(r["received_date"]),
            "expiration_date": _serialize(r["expiration_date"]),
        }
        for r in lots
    ]

    out = {
        "sku_id": sku_id,
        "current_total_quantity": round(total, 2),
        "available_quantity": round(available, 2),
        "lot_details": lot_details,
        "reorder_point": reorder_point,
        "is_below_reorder": is_below,
        "is_out_of_stock": is_out,
    }
    if shortfall is not None:
        out["shortfall"] = round(shortfall, 2)
    return json.dumps(_serialize(out))


@tool
def get_expiring_items(sku_id: str | None = None, days_threshold: int = 3) -> str:
    """
    List inventory items expiring within the given number of days. Use to warn when
    the only stock for an order line expires soon (e.g. within 2 days). If sku_id
    is provided, filter to that SKU only.

    Args:
        sku_id: Optional SKU to limit results; if None, all SKUs are checked.
        days_threshold: Number of days from today (default 3).

    Returns:
        JSON string: list of {sku_id, name, lot_number, quantity, expiration_date, days_until_expiry}.
    """
    cutoff = date.today() + timedelta(days=days_threshold)
    if sku_id:
        rows = fetch_all_sync(
            """SELECT i.sku_id, p.name, i.lot_number, i.quantity, i.expiration_date
               FROM inventory i JOIN products p ON p.sku_id = i.sku_id
               WHERE i.sku_id = $1 AND i.expiration_date IS NOT NULL AND i.expiration_date <= $2 AND i.quantity > 0""",
            sku_id, cutoff,
        )
    else:
        rows = fetch_all_sync(
            """SELECT i.sku_id, p.name, i.lot_number, i.quantity, i.expiration_date
               FROM inventory i JOIN products p ON p.sku_id = i.sku_id
               WHERE i.expiration_date IS NOT NULL AND i.expiration_date <= $1 AND i.quantity > 0
               ORDER BY i.expiration_date ASC""",
            cutoff,
        )
    today = date.today()
    out = []
    for r in rows:
        exp = r["expiration_date"]
        days = (exp - today).days if exp else None
        out.append({
            "sku_id": r["sku_id"],
            "name": r["name"],
            "lot_number": r["lot_number"],
            "quantity": float(r["quantity"] or 0),
            "expiration_date": _serialize(exp),
            "days_until_expiry": days,
        })
    return json.dumps(_serialize(out))
