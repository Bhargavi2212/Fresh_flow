"""Agent tool: product retrieval with explicit score components."""
import json

from strands import tool

from backend.services.product_retrieval import retrieve_products
from backend.services.sync_database import fetch_all_sync


def _load_product_details(sku_ids: list[str]) -> dict[str, dict]:
    if not sku_ids:
        return {}
    rows = fetch_all_sync(
        """
        SELECT sku_id, subcategory, unit_of_measure, case_size, unit_price, shelf_life_days, storage_type
        FROM products
        WHERE sku_id = ANY($1::text[])
        """,
        sku_ids,
    )
    return {str(r.get("sku_id")): dict(r) for r in rows if r.get("sku_id")}


@tool
def search_products(
    query: str,
    top_k: int = 5,
    category: str | None = None,
    customer_id: str | None = None,
) -> str:
    """Search product candidates and return explicit scoring fields for ranking."""
    query = (query or "").strip()
    if not query:
        return json.dumps([])

    results = retrieve_products(query_text=query, customer_id=customer_id, top_k=top_k)
    if category:
        results = [r for r in results if (r.get("category") or "").lower() == category.lower()]

    details_by_sku = _load_product_details([r["sku_id"] for r in results])
    hydrated = []
    for r in results:
        d = details_by_sku.get(r["sku_id"], {})
        item = dict(r)
        item["aliases"] = item.pop("alias_terms", [])
        item["subcategory"] = d.get("subcategory")
        item["unit_of_measure"] = d.get("unit_of_measure")
        item["case_size"] = d.get("case_size")
        item["unit_price"] = d.get("unit_price")
        item["shelf_life_days"] = d.get("shelf_life_days")
        item["storage_type"] = d.get("storage_type")
        item["similarity_score"] = item.get("final_score", 0)
        hydrated.append(item)

    return json.dumps(hydrated[: max(1, int(top_k))], default=str)
