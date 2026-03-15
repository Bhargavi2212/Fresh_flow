"""GET /api/orders, GET /api/orders/{order_id}, PATCH /api/orders/{order_id}."""
from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import Customer, OrderDetail, OrderItemDetail, OrderStatusUpdate, PaginationMeta
from backend.services.database import fetch_all, fetch_one, execute

router = APIRouter(prefix="/api/orders", tags=["orders"])

VALID_STATUSES = {"pending", "confirmed", "needs_review", "fulfilled", "cancelled"}


@router.get("")
async def list_orders(
    status: str | None = None,
    channel: str | None = None,
    customer_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List orders with optional filters. Paginated, sorted by created_at DESC."""
    conditions = ["1=1"]
    params: list = []
    if status:
        conditions.append("status = $1")
        params.append(status)
    if channel:
        params.append(channel)
        conditions.append(f"channel = ${len(params)}")
    if customer_id:
        params.append(customer_id)
        conditions.append(f"customer_id = ${len(params)}")
    if created_after:
        params.append(created_after)
        conditions.append(f"created_at >= ${len(params)}::timestamp")
    if created_before:
        params.append(created_before)
        conditions.append(f"created_at <= ${len(params)}::timestamp")

    where = " AND ".join(conditions)
    total_row = await fetch_one(f"SELECT COUNT(*)::int AS c FROM orders WHERE {where}", *params)
    total = total_row["c"] if total_row else 0

    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT order_id, customer_id, channel, raw_message, status, confidence_score, total_amount, created_at, confirmed_at
            FROM orders WHERE {where} ORDER BY created_at DESC LIMIT ${n+1} OFFSET ${n+2}""",
        *params,
    )
    data = []
    for r in rows:
        data.append({
            "order_id": r["order_id"],
            "customer_id": r["customer_id"],
            "channel": r["channel"],
            "raw_message": (r["raw_message"] or "")[:200],
            "status": r["status"],
            "confidence_score": float(r["confidence_score"]) if r.get("confidence_score") is not None else None,
            "total_amount": float(r["total_amount"]) if r.get("total_amount") is not None else None,
            "created_at": r["created_at"],
            "confirmed_at": r["confirmed_at"],
        })
    return {"data": data, "meta": PaginationMeta(total=total, limit=limit, offset=offset)}


@router.get("/{order_id}")
async def get_order(order_id: str):
    """Single order with line items, agent_trace, and customer."""
    row = await fetch_one(
        """SELECT order_id, customer_id, channel, raw_message, status, confidence_score, total_amount, created_at, confirmed_at, agent_trace
           FROM orders WHERE order_id = $1""",
        order_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    customer = await fetch_one(
        "SELECT customer_id, name, type, phone, email, delivery_days, payment_terms, credit_limit, avg_order_value, account_health, days_since_last_order FROM customers WHERE customer_id = $1",
        row["customer_id"],
    )
    items = await fetch_all(
        """SELECT id, sku_id, raw_text, quantity, unit_price, line_total, match_confidence, status, substituted_from, notes
           FROM order_items WHERE order_id = $1 ORDER BY id""",
        order_id,
    )

    agent_trace = dict(row["agent_trace"]) if row.get("agent_trace") else None
    item_list = [
        OrderItemDetail(
            id=r["id"],
            sku_id=r["sku_id"],
            raw_text=r["raw_text"],
            quantity=r["quantity"],
            unit_price=r["unit_price"],
            line_total=r["line_total"],
            match_confidence=r["match_confidence"],
            status=r["status"],
            substituted_from=r["substituted_from"],
            notes=r["notes"],
        )
        for r in items
    ]
    cust = Customer.model_validate(dict(customer)) if customer else None
    return {
        "data": OrderDetail(
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            channel=row["channel"],
            raw_message=row["raw_message"],
            status=row["status"],
            confidence_score=row["confidence_score"],
            total_amount=row["total_amount"],
            created_at=row["created_at"],
            confirmed_at=row["confirmed_at"],
            agent_trace=agent_trace,
            customer=cust,
            items=item_list,
        ),
    }


@router.patch("/{order_id}")
async def update_order_status(order_id: str, body: OrderStatusUpdate):
    """Update order status (confirmed, needs_review, cancelled)."""
    if body.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(VALID_STATUSES)}")

    existing = await fetch_one("SELECT order_id FROM orders WHERE order_id = $1", order_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found")

    await execute("UPDATE orders SET status = $1 WHERE order_id = $2", body.status, order_id)
    return {"order_id": order_id, "status": body.status}
