"""Agent tool: semantic product search via Titan embeddings and pgvector."""
import json
from typing import Any

from strands import tool

from backend.agents.models import embed_text
from backend.services.sync_database import fetch_all_sync


@tool
def search_products(
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> str:
    """
    Search the product catalog by natural language. Use this for every product mention
    in an order to find matching SKUs. Embeds the query with Titan V2 and returns
    the top_k most similar products by cosine similarity. Optionally filter by category
    (e.g. 'Seafood', 'Produce').

    Args:
        query: Natural language product description (e.g. "king salmon", "jumbo shrimp").
        top_k: Maximum number of results to return (default 5).
        category: Optional category filter to narrow results.

    Returns:
        JSON string: list of dicts with sku_id, name, aliases, category, subcategory,
        unit_of_measure, case_size, unit_price, shelf_life_days, storage_type, similarity_score.
        Use for matching customer order lines to real SKUs. Never guess a SKU without calling this.
    """
    if not query or not query.strip():
        return json.dumps([])
    vec = embed_text(query.strip())
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    conditions = ["status = 'active'", "embedding IS NOT NULL"]
    params: list[Any] = [vec_str]
    if category:
        conditions.append("category = $2")
        params.append(category)
    params.append(top_k)
    where = " AND ".join(conditions)
    q = f"""
        SELECT sku_id, name, aliases, category, subcategory, unit_of_measure, case_size,
               unit_price, shelf_life_days, storage_type,
               1 - (embedding <=> $1::vector) AS similarity_score
        FROM products WHERE {where}
        ORDER BY embedding <=> $1::vector
        LIMIT ${len(params)}
    """
    rows = fetch_all_sync(q, *params)
    out = []
    for r in rows:
        d = dict(r)
        d["aliases"] = list(d["aliases"]) if d.get("aliases") else []
        d["similarity_score"] = round(float(d.get("similarity_score", 0)), 4)
        for k in ("cost_price", "supplier_id", "status"):
            d.pop(k, None)
        out.append(d)
    return json.dumps(out, default=str)
