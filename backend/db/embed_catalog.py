"""Embed product catalog with Titan V2; store in pgvector. Idempotent unless --force."""
import argparse
import asyncio
import sys
from typing import Any

from backend.services.bedrock_service import embed_text
from backend.services.database import close_pool, execute, get_pool


def _embed_input(row: dict[str, Any]) -> str:
    name = row.get("name") or ""
    aliases = row.get("aliases") or []
    aliases_str = " ".join(aliases) if isinstance(aliases, list) else str(aliases)
    category = row.get("category") or ""
    subcategory = row.get("subcategory") or ""
    uom = row.get("unit_of_measure") or ""
    return f"{name} {aliases_str} {category} {subcategory} {uom}".strip()


async def run(force: bool = False) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if force:
            rows = await conn.fetch("SELECT sku_id, name, aliases, category, subcategory, unit_of_measure FROM products")
        else:
            rows = await conn.fetch(
                "SELECT sku_id, name, aliases, category, subcategory, unit_of_measure FROM products WHERE embedding IS NULL"
            )
    total = len(rows)
    if total == 0:
        print("No products to embed (all have embeddings; use --force to re-embed).")
        return
    print(f"Embedding {total} products...")
    for i, row in enumerate(rows):
        sku_id = row["sku_id"]
        text = _embed_input(dict(row))
        vec = embed_text(text)
        # asyncpg accepts list for vector type
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        await execute(
            "UPDATE products SET embedding = $1::vector WHERE sku_id = $2",
            vec_str,
            sku_id,
        )
        if (i + 1) % 100 == 0:
            print(f"Embedded {i+1}/{total} products...")
    print(f"Embedded {total} products.")
    await close_pool()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Re-embed products that already have embeddings")
    args = ap.parse_args()
    asyncio.run(run(force=args.force))
    sys.exit(0)


if __name__ == "__main__":
    main()
