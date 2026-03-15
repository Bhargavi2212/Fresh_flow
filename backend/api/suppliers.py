"""GET /api/suppliers."""
from fastapi import APIRouter

from backend.services.database import fetch_all

router = APIRouter(prefix="/api/suppliers", tags=["suppliers"])


@router.get("")
async def list_suppliers():
    rows = await fetch_all(
        "SELECT supplier_id, name, lead_time_days, min_order_value, reliability_score, phone, email FROM suppliers ORDER BY supplier_id"
    )
    return {"data": [dict(r) for r in rows]}
