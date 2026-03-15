"""Agent tool: demand forecast from recent order history (for procurement)."""
import json

from strands import tool

from backend.services.sync_database import fetch_one_sync


@tool
def get_demand_forecast(sku_id: str, days: int = 7) -> str:
    """
    Get demand forecast for a product based on order history (last 30 days).
    Use to decide how much to order when creating purchase orders.

    Args:
        sku_id: Product SKU to forecast.
        days: Projection period in days (default 7). Used for projected_demand_for_period.

    Returns:
        JSON string with avg_daily_quantity, projected_demand_for_period,
        total_orders_last_30_days.
    """
    if not sku_id or not str(sku_id).strip():
        return json.dumps({
            "avg_daily_quantity": 0.0,
            "projected_demand_for_period": 0.0,
            "total_orders_last_30_days": 0,
        })
    sku_id = str(sku_id).strip()
    if days is None or days < 1:
        days = 7
    row = fetch_one_sync(
        """
        SELECT COALESCE(SUM(oi.quantity), 0) AS total_qty,
               COUNT(DISTINCT oi.order_id) AS order_count
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE oi.sku_id = $1
          AND o.created_at >= NOW() - INTERVAL '30 days'
        """,
        sku_id,
    )
    if not row:
        return json.dumps({
            "avg_daily_quantity": 0.0,
            "projected_demand_for_period": 0.0,
            "total_orders_last_30_days": 0,
        })
    total_qty = float(row["total_qty"] or 0)
    order_count = int(row["order_count"] or 0)
    avg_daily = total_qty / 30.0 if total_qty else 0.0
    projected = avg_daily * days
    return json.dumps({
        "avg_daily_quantity": round(avg_daily, 2),
        "projected_demand_for_period": round(projected, 2),
        "total_orders_last_30_days": order_count,
    })
