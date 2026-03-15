"""Agent tool: hybrid product search — exact SKU/alias first, then semantic via Titan + pgvector."""
import json
from typing import Any

from strands import tool

from backend.agents.models import embed_text
from backend.services.sync_database import fetch_all_sync


def _row_to_result(r: dict, similarity: float) -> dict:
    """Build a result dict from a DB row, with consistent fields and similarity_score."""
    d = dict(r)
    d["aliases"] = list(d["aliases"]) if d.get("aliases") else []
    d["similarity_score"] = round(float(similarity), 4)
    for k in ("cost_price", "supplier_id", "status", "embedding"):
        d.pop(k, None)
    return d


def _dedupe_by_sku(results: list[dict], top_k: int) -> list[dict]:
    """Keep highest similarity per sku_id, sort descending, return top_k."""
    by_sku: dict[str, dict] = {}
    for row in results:
        sku = row.get("sku_id")
        if not sku:
            continue
        sim = row.get("similarity_score", 0)
        if sku not in by_sku or by_sku[sku].get("similarity_score", 0) < sim:
            by_sku[sku] = row
    sorted_rows = sorted(by_sku.values(), key=lambda x: x.get("similarity_score", 0), reverse=True)
    return sorted_rows[:top_k]


@tool
def search_products(
    query: str,
    top_k: int = 5,
    category: str | None = None,
) -> str:
    """
    Search the product catalog. Tries exact SKU and alias matches first (fast), then
    semantic search only if needed. Use for every product mention in an order.

    Args:
        query: Product identifier or natural language (e.g. "SAL-001", "king salmon").
        top_k: Maximum number of results (default 5).
        category: Optional category filter (e.g. 'Seafood', 'Produce').

    Returns:
        JSON string: list of dicts with sku_id, name, aliases, category, subcategory,
        unit_of_measure, case_size, unit_price, shelf_life_days, storage_type, similarity_score.
    """
    if not query or not query.strip():
        return json.dumps([])
    query = query.strip()
    select_cols = (
        "sku_id, name, aliases, category, subcategory, unit_of_measure, case_size, "
        "unit_price, shelf_life_days, storage_type"
    )
    all_results: list[dict] = []

    # Step 1 — Exact SKU
    if category:
        q1 = f"SELECT {select_cols} FROM products WHERE sku_id = $1 AND status = 'active' AND category = $2"
        rows1 = fetch_all_sync(q1, query, category)
    else:
        q1 = f"SELECT {select_cols} FROM products WHERE sku_id = $1 AND status = 'active'"
        rows1 = fetch_all_sync(q1, query)
    for r in rows1:
        all_results.append(_row_to_result(dict(r), 1.0))

    # Step 2 — Exact alias
    if category:
        q2 = f"SELECT {select_cols} FROM products WHERE $1 = ANY(aliases) AND status = 'active' AND category = $2"
        rows2 = fetch_all_sync(q2, query, category)
    else:
        q2 = f"SELECT {select_cols} FROM products WHERE $1 = ANY(aliases) AND status = 'active'"
        rows2 = fetch_all_sync(q2, query)
    for r in rows2:
        all_results.append(_row_to_result(dict(r), 0.99))

    # Step 3 — Fuzzy alias (ILIKE)
    fuzzy_pattern = f"%{query}%"
    if category:
        q3 = f"""
            SELECT {select_cols} FROM products
            WHERE EXISTS (
                SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS a
                WHERE a ILIKE $1
            ) AND status = 'active' AND category = $2
        """
        rows3 = fetch_all_sync(q3, fuzzy_pattern, category)
    else:
        q3 = f"""
            SELECT {select_cols} FROM products
            WHERE EXISTS (
                SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS a
                WHERE a ILIKE $1
            ) AND status = 'active'
        """
        rows3 = fetch_all_sync(q3, fuzzy_pattern)
    for r in rows3:
        all_results.append(_row_to_result(dict(r), 0.90))

    # Dedupe and check if we need semantic
    deduped = _dedupe_by_sku(all_results, top_k)
    if len(deduped) >= top_k:
        return json.dumps(deduped, default=str)

    # Step 4 — Semantic (only if we have fewer than top_k)
    vec = embed_text(query)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    if category:
        q4 = f"""
            SELECT {select_cols},
                   1 - (embedding <=> $1::vector) AS similarity_score
            FROM products WHERE status = 'active' AND embedding IS NOT NULL AND category = $2
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """
        rows4 = fetch_all_sync(q4, vec_str, category, top_k)
    else:
        q4 = f"""
            SELECT {select_cols},
                   1 - (embedding <=> $1::vector) AS similarity_score
            FROM products WHERE status = 'active' AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $2
        """
        rows4 = fetch_all_sync(q4, vec_str, top_k)
    for r in rows4:
        d = dict(r)
        sim = float(d.pop("similarity_score", 0))
        all_results.append(_row_to_result(d, sim))

    final = _dedupe_by_sku(all_results, top_k)
    return json.dumps(final, default=str)
