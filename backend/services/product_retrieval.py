"""Retrieval data-prep and ranking utilities for product matching."""
import re
from collections import defaultdict

from backend.agents.models import embed_text
from backend.services.sync_database import fetch_all_sync

TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(TOKEN_RE.findall((text or "").lower()))


def _build_pack_text(case_size, unit_of_measure: str | None) -> str:
    uom = (unit_of_measure or "").strip()
    if case_size is None:
        return uom
    return f"{case_size} {uom}".strip()


def _get_customer_recent_counts(customer_id: str | None) -> dict[str, int]:
    if not customer_id:
        return {}
    rows = fetch_all_sync(
        """
        SELECT oi.sku_id, COUNT(*)::int AS cnt
        FROM order_items oi
        JOIN orders o ON o.order_id = oi.order_id
        WHERE o.customer_id = $1
        GROUP BY oi.sku_id
        ORDER BY MAX(o.created_at) DESC
        LIMIT 50
        """,
        customer_id,
    )
    return {str(r.get("sku_id")): int(r.get("cnt") or 0) for r in rows if r.get("sku_id")}


def _get_historical_aliases() -> dict[str, list[str]]:
    rows = fetch_all_sync(
        """
        SELECT sku_id, raw_text
        FROM order_items
        WHERE raw_text IS NOT NULL AND LENGTH(TRIM(raw_text)) >= 2
        """
    )
    by_sku: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        sku = (r.get("sku_id") or "").strip()
        alias = (r.get("raw_text") or "").strip()
        if sku and alias:
            by_sku[sku].add(alias)
    return {sku: sorted(vals)[:15] for sku, vals in by_sku.items()}


def _fetch_semantic_candidates(query_text: str, top_n: int) -> dict[str, float]:
    vec = embed_text(query_text)
    vec_str = "[" + ",".join(str(x) for x in vec) + "]"
    rows = fetch_all_sync(
        """
        SELECT sku_id, 1 - (embedding <=> $1::vector) AS semantic_score
        FROM products
        WHERE LOWER(status) = 'active' AND embedding IS NOT NULL
        ORDER BY embedding <=> $1::vector
        LIMIT $2
        """,
        vec_str,
        top_n,
    )
    return {str(r.get("sku_id")): max(0.0, min(1.0, float(r.get("semantic_score") or 0))) for r in rows if r.get("sku_id")}


def _fetch_candidate_rows(query_text: str, semantic_skus: set[str], cap: int) -> list[dict]:
    like_q = f"%{query_text}%"
    token_rows = fetch_all_sync(
        """
        SELECT sku_id, name, category, case_size, unit_of_measure, aliases
        FROM products
        WHERE LOWER(status) = 'active'
          AND (
            name ILIKE $1
            OR category ILIKE $1
            OR EXISTS (
                SELECT 1 FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS a
                WHERE a ILIKE $1
            )
          )
        LIMIT $2
        """,
        like_q,
        cap,
    )
    if semantic_skus:
        sem_rows = fetch_all_sync(
            """
            SELECT sku_id, name, category, case_size, unit_of_measure, aliases
            FROM products
            WHERE LOWER(status) = 'active' AND sku_id = ANY($1::text[])
            """,
            list(semantic_skus),
        )
    else:
        sem_rows = []

    by_sku: dict[str, dict] = {}
    for r in token_rows + sem_rows:
        sku_id = (r.get("sku_id") or "").strip()
        if sku_id:
            by_sku[sku_id] = dict(r)
    return list(by_sku.values())


def retrieve_products(query_text: str, customer_id: str | None = None, top_k: int = 10) -> list[dict]:
    """Retrieve and rank product candidates with explicit component scores."""
    query_text = (query_text or "").strip()
    if not query_text:
        return []

    semantic_scores = _fetch_semantic_candidates(query_text, top_n=max(50, top_k * 6))
    candidate_rows = _fetch_candidate_rows(query_text, set(semantic_scores.keys()), cap=max(50, top_k * 8))
    historical_aliases = _get_historical_aliases()
    recent_counts = _get_customer_recent_counts(customer_id)
    max_count = max(recent_counts.values(), default=0)
    q_tokens = _tokenize(query_text)

    ranked: list[dict] = []
    for row in candidate_rows:
        sku_id = (row.get("sku_id") or "").strip()
        if not sku_id:
            continue
        aliases = [a for a in (row.get("aliases") or []) if a]
        alias_terms = sorted(set(aliases + historical_aliases.get(sku_id, [])))
        pack_text = _build_pack_text(row.get("case_size"), row.get("unit_of_measure"))
        doc_text = " ".join([row.get("name") or "", row.get("category") or "", pack_text, " ".join(alias_terms)])

        d_tokens = _tokenize(doc_text)
        overlap = len(q_tokens & d_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0
        semantic = semantic_scores.get(sku_id, 0.0)

        history_boost = 0.0
        if max_count and sku_id in recent_counts:
            history_boost = 0.15 * (recent_counts[sku_id] / max_count)

        final_score = (0.65 * semantic) + (0.25 * overlap) + history_boost
        ranked.append(
            {
                "sku_id": sku_id,
                "name": row.get("name") or sku_id,
                "category": row.get("category") or "",
                "pack_unit_text": pack_text,
                "alias_terms": alias_terms,
                "semantic_score": round(semantic, 4),
                "exact_token_overlap": round(overlap, 4),
                "customer_history_boost": round(history_boost, 4),
                "final_score": round(final_score, 4),
            }
        )

    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    return ranked[: max(1, int(top_k))]
