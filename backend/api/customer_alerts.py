"""GET /api/customer-alerts and PATCH /api/customer-alerts/{id}."""
from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import CustomerAlertDetail, CustomerAlertListResponse
from backend.services.database import execute, fetch_all, fetch_one

router = APIRouter(prefix="/api/customer-alerts", tags=["customer-alerts"])


@router.get("", response_model=CustomerAlertListResponse)
async def list_customer_alerts(
    alert_type: str | None = None,
    severity: str | None = None,
    acknowledged: bool | None = None,
    customer_id: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List customer alerts with optional filters. Sorted by created_at DESC."""
    conditions = ["1=1"]
    params: list = []
    if alert_type:
        params.append(alert_type)
        conditions.append(f"a.alert_type = ${len(params)}")
    if severity:
        params.append(severity)
        conditions.append(f"a.severity = ${len(params)}")
    if acknowledged is not None:
        params.append(acknowledged)
        conditions.append(f"a.acknowledged = ${len(params)}")
    if customer_id:
        params.append(customer_id)
        conditions.append(f"a.customer_id = ${len(params)}")

    where = " AND ".join(conditions)
    total_row = await fetch_one(
        f"SELECT COUNT(*)::int AS c FROM customer_alerts a WHERE {where}",
        *params,
    )
    total = total_row["c"] if total_row else 0

    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT a.id, a.customer_id, c.name AS customer_name, a.alert_type, a.description, a.severity, a.acknowledged, a.created_at
            FROM customer_alerts a
            LEFT JOIN customers c ON c.customer_id = a.customer_id
            WHERE {where}
            ORDER BY a.created_at DESC
            LIMIT ${n + 1} OFFSET ${n + 2}""",
        *params,
    )
    items = [
        CustomerAlertDetail(
            id=r["id"],
            customer_id=r["customer_id"],
            customer_name=r["customer_name"],
            alert_type=r["alert_type"],
            description=r["description"],
            severity=r["severity"],
            acknowledged=r["acknowledged"] or False,
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return CustomerAlertListResponse(items=items, total=total, limit=limit, offset=offset)


@router.patch("/{alert_id}", response_model=CustomerAlertDetail)
async def acknowledge_alert(alert_id: int):
    """Set acknowledged = true for the given alert."""
    row = await fetch_one(
        """SELECT a.id, a.customer_id, c.name AS customer_name, a.alert_type, a.description, a.severity, a.acknowledged, a.created_at
           FROM customer_alerts a
           LEFT JOIN customers c ON c.customer_id = a.customer_id
           WHERE a.id = $1""",
        alert_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    await execute("UPDATE customer_alerts SET acknowledged = true WHERE id = $1", alert_id)
    return CustomerAlertDetail(
        id=row["id"],
        customer_id=row["customer_id"],
        customer_name=row["customer_name"],
        alert_type=row["alert_type"],
        description=row["description"],
        severity=row["severity"],
        acknowledged=True,
        created_at=row["created_at"],
    )
