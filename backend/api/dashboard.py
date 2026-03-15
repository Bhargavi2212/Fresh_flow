"""GET /api/dashboard/stats."""
from fastapi import APIRouter

from backend.services.database import fetch_one

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def dashboard_stats():
    total_products = await fetch_one("SELECT COUNT(*)::int AS c FROM products")
    total_customers = await fetch_one("SELECT COUNT(*)::int AS c FROM customers")
    orders_30 = await fetch_one("SELECT COUNT(*)::int AS c FROM orders WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'")
    low_stock = await fetch_one(
        "SELECT COUNT(*)::int AS c FROM inventory WHERE quantity < reorder_point"
    )
    expiring = await fetch_one(
        "SELECT COUNT(*)::int AS c FROM inventory WHERE expiration_date IS NOT NULL AND expiration_date <= CURRENT_DATE + INTERVAL '3 days'"
    )
    at_risk = await fetch_one("SELECT COUNT(*)::int AS c FROM customers WHERE account_health IN ('at_risk', 'churning')")
    po_today = await fetch_one(
        "SELECT COUNT(*)::int AS c, COALESCE(SUM(total_amount), 0)::float AS total FROM purchase_orders WHERE created_at >= CURRENT_DATE"
    )
    orders_confirmed_today = await fetch_one(
        "SELECT COUNT(*)::int AS c FROM orders WHERE status = 'confirmed' AND created_at >= CURRENT_DATE"
    )
    orders_review_today = await fetch_one(
        "SELECT COUNT(*)::int AS c FROM orders WHERE status = 'needs_review' AND created_at >= CURRENT_DATE"
    )
    orders_today_row = await fetch_one(
        "SELECT COUNT(*)::int AS c, COALESCE(SUM(total_amount), 0)::float AS revenue FROM orders WHERE created_at >= CURRENT_DATE"
    )
    active_alerts = await fetch_one(
        "SELECT COUNT(*)::int AS c FROM customer_alerts WHERE acknowledged = false"
    )
    return {
        "data": {
            "total_products": total_products["c"] if total_products else 0,
            "total_customers": total_customers["c"] if total_customers else 0,
            "orders_last_30_days": orders_30["c"] if orders_30 else 0,
            "low_stock_count": low_stock["c"] if low_stock else 0,
            "expiring_soon_count": expiring["c"] if expiring else 0,
            "at_risk_customer_count": at_risk["c"] if at_risk else 0,
            "purchase_orders_today": po_today["c"] if po_today else 0,
            "purchase_orders_total_value_today": float(po_today["total"]) if po_today and po_today.get("total") is not None else 0.0,
            "orders_auto_confirmed_today": orders_confirmed_today["c"] if orders_confirmed_today else 0,
            "orders_needing_review_today": orders_review_today["c"] if orders_review_today else 0,
            "orders_today": orders_today_row["c"] if orders_today_row else 0,
            "revenue_today": float(orders_today_row["revenue"]) if orders_today_row and orders_today_row.get("revenue") is not None else 0.0,
            "active_alerts_count": active_alerts["c"] if active_alerts else 0,
        }
    }
