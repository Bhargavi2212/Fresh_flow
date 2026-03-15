"""GET /api/inventory, GET /api/inventory/{sku_id}."""
from fastapi import APIRouter, HTTPException, Query

from backend.services.database import fetch_all, fetch_one

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("")
async def list_inventory(
    warehouse_zone: str | None = None,
    low_stock: bool | None = None,
    expiring_soon: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conditions = ["1=1"]
    params: list = []
    if warehouse_zone:
        params.append(warehouse_zone)
        conditions.append(f"warehouse_zone = ${len(params)}")
    if low_stock is True:
        conditions.append("quantity < reorder_point")
    if expiring_soon is True:
        conditions.append("expiration_date IS NOT NULL AND expiration_date <= CURRENT_DATE + INTERVAL '3 days'")
    where = " AND ".join(conditions)
    total = await fetch_one(f"SELECT COUNT(*)::int AS c FROM inventory WHERE {where}", *params)
    total_count = total["c"] if total else 0
    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT id, sku_id, quantity, reorder_point, reorder_quantity, lot_number, received_date, expiration_date, warehouse_zone, updated_at
            FROM inventory WHERE {where} ORDER BY sku_id, id LIMIT ${n+1} OFFSET ${n+2}""",
        *params,
    )
    data = [dict(r) for r in rows]
    return {"data": data, "meta": {"total": total_count, "limit": limit, "offset": offset}}


@router.get("/{sku_id}")
async def get_inventory(sku_id: str):
    rows = await fetch_all(
        """SELECT id, sku_id, quantity, reorder_point, reorder_quantity, lot_number, received_date, expiration_date, warehouse_zone, updated_at
           FROM inventory WHERE sku_id = $1 ORDER BY expiration_date NULLS LAST""",
        sku_id,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="No inventory found for this product")
    return {"data": [dict(r) for r in rows]}
