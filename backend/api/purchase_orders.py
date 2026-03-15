"""GET /api/purchase-orders and GET /api/purchase-orders/{po_id}."""
from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import POItem, PurchaseOrderDetail, PurchaseOrderListResponse
from backend.services.database import fetch_all, fetch_one

router = APIRouter(prefix="/api/purchase-orders", tags=["purchase-orders"])


@router.get("", response_model=PurchaseOrderListResponse)
async def list_purchase_orders(
    status: str | None = None,
    supplier_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List purchase orders with optional filters. Sorted by created_at DESC."""
    conditions = ["1=1"]
    params: list = []
    if status:
        params.append(status)
        conditions.append(f"status = ${len(params)}")
    if supplier_id:
        params.append(supplier_id)
        conditions.append(f"supplier_id = ${len(params)}")
    if created_after:
        params.append(created_after)
        conditions.append(f"created_at >= ${len(params)}::timestamp")
    if created_before:
        params.append(created_before)
        conditions.append(f"created_at <= ${len(params)}::timestamp")

    where = " AND ".join(conditions)
    total_row = await fetch_one(f"SELECT COUNT(*)::int AS c FROM purchase_orders WHERE {where}", *params)
    total = total_row["c"] if total_row else 0

    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT po_id, supplier_id, status, total_amount, triggered_by, created_at
            FROM purchase_orders WHERE {where} ORDER BY created_at DESC LIMIT ${n + 1} OFFSET ${n + 2}""",
        *params,
    )
    items = []
    for r in rows:
        items.append(
            PurchaseOrderDetail(
                po_id=r["po_id"],
                supplier_id=r["supplier_id"],
                status=r["status"],
                total_amount=r["total_amount"],
                triggered_by=r["triggered_by"],
                created_at=r["created_at"],
                items=[],
                supplier_name=None,
            )
        )
    return PurchaseOrderListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{po_id}", response_model=PurchaseOrderDetail)
async def get_purchase_order(po_id: str):
    """Get one purchase order with line items and triggering order_id."""
    row = await fetch_one(
        """SELECT po.po_id, po.supplier_id, po.status, po.total_amount, po.triggered_by, po.reasoning, po.created_at, s.name AS supplier_name
           FROM purchase_orders po
           LEFT JOIN suppliers s ON s.supplier_id = po.supplier_id
           WHERE po.po_id = $1""",
        po_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    item_rows = await fetch_all(
        "SELECT id, sku_id, quantity, unit_price, line_total FROM po_items WHERE po_id = $1 ORDER BY id",
        po_id,
    )
    items = [
        POItem(
            id=r["id"],
            sku_id=r["sku_id"],
            quantity=float(r["quantity"]) if r["quantity"] is not None else 0,
            unit_price=float(r["unit_price"]) if r["unit_price"] is not None else None,
            line_total=float(r["line_total"]) if r["line_total"] is not None else None,
        )
        for r in item_rows
    ]
    return PurchaseOrderDetail(
        po_id=row["po_id"],
        supplier_id=row["supplier_id"],
        status=row["status"],
        total_amount=row["total_amount"],
        triggered_by=row["triggered_by"],
        reasoning=row.get("reasoning"),
        created_at=row["created_at"],
        items=items,
        supplier_name=row["supplier_name"],
    )
