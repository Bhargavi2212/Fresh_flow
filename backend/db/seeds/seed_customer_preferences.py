"""Seed 2-5 preferences per customer: substitution, exclusion, always_organic."""
import asyncio
import random

from backend.services.database import execute, get_pool


PREF_TEMPLATES = [
    ("substitution", "if no halibut, substitute with cod", None, None),
    ("substitution", "if no king salmon, substitute atlantic salmon", None, None),
    ("exclusion", "never substitute farmed salmon", None, None),
    ("exclusion", "no shellfish - allergy", None, None),
    ("preference", "prefer wild over farmed when available", None, None),
    ("always_organic", "always organic for produce", None, None),
    ("substitution", "if no branzino, substitute sea bass", None, None),
    ("exclusion", "no tilapia", None, None),
]


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE customer_preferences CASCADE")
        customers = await conn.fetch("SELECT customer_id FROM customers ORDER BY customer_id")
        products = await conn.fetch("SELECT sku_id FROM products LIMIT 100")
    customer_ids = [r["customer_id"] for r in customers]
    product_skus = [r["sku_id"] for r in products]

    random.seed(44)
    count = 0
    for cid in customer_ids:
        n = random.randint(2, 5)
        used = set()
        for _ in range(n):
            pref_type, desc, psku, subsku = random.choice(PREF_TEMPLATES)
            psku = random.choice(product_skus) if psku is None else psku
            subsku = random.choice(product_skus) if pref_type == "substitution" else None
            key = (pref_type, desc[:30])
            if key in used:
                continue
            used.add(key)
            await execute(
                """INSERT INTO customer_preferences (customer_id, preference_type, description, product_sku, substitute_sku)
                   VALUES ($1, $2, $3, $4, $5)""",
                cid, pref_type, desc, psku, subsku,
            )
            count += 1
    print(f"Seeded {count} customer preferences.")


if __name__ == "__main__":
    asyncio.run(run_seed())
