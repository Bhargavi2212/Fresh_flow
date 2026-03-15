"""Link products to 2-3 suppliers each; cheapest supplier has longer lead time or higher min."""
import asyncio
import random
from decimal import Decimal

from backend.services.database import execute, get_pool


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE supplier_products CASCADE")
        suppliers = await conn.fetch("SELECT supplier_id, lead_time_days, min_order_value FROM suppliers ORDER BY supplier_id")
        products = await conn.fetch("SELECT sku_id, cost_price FROM products ORDER BY sku_id")
    supplier_list = [(s["supplier_id"], int(s["lead_time_days"] or 0), float(s["min_order_value"] or 0)) for s in suppliers]
    product_list = [(p["sku_id"], float(p["cost_price"] or 0)) for p in products]

    random.seed(43)
    for sku_id, cost_price in product_list:
        n = random.randint(2, min(3, len(supplier_list)))
        chosen = random.sample(supplier_list, n)
        chosen.sort(key=lambda x: (-x[1], -x[2]))
        for i, (sup_id, _lead, _min_val) in enumerate(chosen):
            margin = 1.0 + (0.05 * (i + 1)) + random.uniform(0, 0.10)
            supplier_price = round(cost_price * margin, 2)
            min_order_qty = round(random.uniform(1, 20), 2)
            await execute(
                """INSERT INTO supplier_products (supplier_id, sku_id, supplier_price, min_order_qty, available)
                   VALUES ($1, $2, $3, $4, true)""",
                sup_id, sku_id, Decimal(str(supplier_price)), Decimal(str(min_order_qty)),
            )
    print(f"Seeded supplier_products ({len(product_list)} products x 2-3 suppliers).")


if __name__ == "__main__":
    asyncio.run(run_seed())
