"""GET /api/products, /api/products/search?q=, /api/products/{sku_id}."""
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import PaginationMeta, Product, ProductSearchResult
from backend.services.bedrock_service import embed_text
from backend.services.database import fetch_all, fetch_one, get_pool

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("")
async def list_products(
    category: str | None = None,
    subcategory: str | None = None,
    storage_type: str | None = None,
    status: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    conditions = ["1=1"]
    params: list = []
    if category:
        conditions.append("category = $1")
        params.append(category)
    if subcategory:
        conditions.append(f"subcategory = ${len(params)+1}")
        params.append(subcategory)
    if storage_type:
        conditions.append(f"storage_type = ${len(params)+1}")
        params.append(storage_type)
    if status:
        conditions.append(f"status = ${len(params)+1}")
        params.append(status)
    where = " AND ".join(conditions)
    total = await fetch_one(f"SELECT COUNT(*)::int AS c FROM products WHERE {where}", *params)
    total_count = total["c"] if total else 0
    n = len(params)
    params.extend([limit, offset])
    rows = await fetch_all(
        f"""SELECT sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, unit_price, cost_price,
            shelf_life_days, storage_type, supplier_id, status FROM products WHERE {where} ORDER BY sku_id LIMIT ${n+1} OFFSET ${n+2}""",
        *params,
    )
    data = [Product.model_validate(dict(r)) for r in rows]
    return {"data": data, "meta": PaginationMeta(total=total_count, limit=limit, offset=offset)}


@router.get("/search")
async def search_products(q: str = Query(..., min_length=1)):
    if not q.strip():
        return {"data": [], "meta": {"query": q}}
    vec = embed_text(q.strip())
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, unit_price, cost_price,
                shelf_life_days, storage_type, supplier_id, status,
                1 - (embedding <=> $1::vector) AS similarity
               FROM products WHERE status = 'active' AND embedding IS NOT NULL ORDER BY embedding <=> $1::vector LIMIT 10""",
            vec_str,
        )
    data = []
    for r in rows:
        d = dict(r)
        sim = float(d.pop("similarity", 0))
        data.append(ProductSearchResult(**d, similarity=round(sim, 4)))
    return {"data": data}


@router.get("/{sku_id}")
async def get_product(sku_id: str):
    row = await fetch_one(
        """SELECT sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, unit_price, cost_price,
           shelf_life_days, storage_type, supplier_id, status FROM products WHERE sku_id = $1""",
        sku_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Product not found")
    inv = await fetch_one("SELECT COALESCE(SUM(quantity), 0) AS total FROM inventory WHERE sku_id = $1", sku_id)
    out = dict(row)
    out["current_inventory"] = float(inv["total"]) if inv else 0
    return {"data": out}
