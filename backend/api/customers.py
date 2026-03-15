"""GET /api/customers, GET /api/customers/{customer_id}."""
from fastapi import APIRouter, HTTPException, Query

from backend.services.database import fetch_all, fetch_one

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("")
async def list_customers(
    type: str | None = None,
    account_health: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    conditions = ["1=1"]
    params: list = []
    if type:
        params.append(type)
        conditions.append(f"type = ${len(params)}")
    if account_health:
        params.append(account_health)
        conditions.append(f"account_health = ${len(params)}")
    where = " AND ".join(conditions)
    total = await fetch_one(f"SELECT COUNT(*)::int AS c FROM customers WHERE {where}", *params)
    total_count = total["c"] if total else 0
    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT customer_id, name, type, phone, email, delivery_days, payment_terms, credit_limit, avg_order_value,
            account_health, days_since_last_order, created_at FROM customers WHERE {where} ORDER BY customer_id LIMIT ${n+1} OFFSET ${n+2}""",
        *params,
    )
    data = [dict(r) for r in rows]
    return {"data": data, "meta": {"total": total_count, "limit": limit, "offset": offset}}


@router.get("/{customer_id}")
async def get_customer(customer_id: str):
    row = await fetch_one(
        "SELECT customer_id, name, type, phone, email, delivery_days, payment_terms, credit_limit, avg_order_value, account_health, days_since_last_order, created_at FROM customers WHERE customer_id = $1",
        customer_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    prefs = await fetch_all(
        "SELECT id, customer_id, preference_type, description, product_sku, substitute_sku FROM customer_preferences WHERE customer_id = $1",
        customer_id,
    )
    orders = await fetch_all(
        "SELECT order_id, customer_id, channel, status, total_amount, created_at FROM orders WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 10",
        customer_id,
    )
    stats = await fetch_one(
        "SELECT COUNT(*)::int AS total_orders, COALESCE(AVG(total_amount), 0) AS avg_value, MAX(created_at) AS last_order FROM orders WHERE customer_id = $1",
        customer_id,
    )
    out = dict(row)
    out["preferences"] = [dict(p) for p in prefs]
    out["recent_orders"] = [dict(o) for o in orders]
    out["stats"] = {"total_orders": stats["total_orders"], "avg_value": float(stats["avg_value"] or 0), "last_order": str(stats["last_order"]) if stats.get("last_order") else None}
    return {"data": out}
