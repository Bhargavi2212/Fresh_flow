"""Seed inventory: 30-40 low stock, 10-15 zero; multiple lots; FIFO scenarios."""
import asyncio
import random
from decimal import Decimal
from datetime import date, timedelta

from backend.services.database import execute, get_pool


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE inventory CASCADE")
        products = await conn.fetch("SELECT sku_id, storage_type, shelf_life_days FROM products ORDER BY sku_id")
    product_list = [(r["sku_id"], r["storage_type"] or "ambient", int(r["shelf_life_days"] or 30)) for r in products]
    random.seed(45)
    low_count = 0
    zero_count = 0
    for sku_id, storage, shelf_days in product_list:
        if zero_count < 15 and random.random() < 0.025:
            qty = Decimal("0")
            reorder_p = Decimal("10")
            reorder_q = Decimal("20")
            zero_count += 1
        elif low_count < 40 and random.random() < 0.07:
            qty = Decimal(str(round(random.uniform(1, 15), 2)))
            reorder_p = Decimal(str(round(random.uniform(15, 30), 2)))
            reorder_q = Decimal(str(round(random.uniform(20, 50), 2)))
            low_count += 1
        else:
            qty = Decimal(str(round(random.uniform(50, 500), 2)))
            reorder_p = Decimal(str(round(random.uniform(10, 30), 2)))
            reorder_q = Decimal(str(round(random.uniform(20, 100), 2)))
        zone = storage if storage in ("frozen", "refrigerated", "ambient") else "ambient"
        # 1-2 lots per product; some expiring soon for FIFO
        num_lots = 1 if random.random() < 0.6 else 2
        for lot_idx in range(num_lots):
            received = date.today() - timedelta(days=random.randint(1, 60))
            if zone == "refrigerated" and random.random() < 0.2:
                expiration = date.today() + timedelta(days=random.randint(1, 3))
            elif zone == "frozen":
                expiration = date.today() + timedelta(days=random.randint(90, 365))
            else:
                expiration = received + timedelta(days=min(shelf_days, 30))
            lot_qty = qty / num_lots if num_lots > 1 else qty
            await execute(
                """INSERT INTO inventory (sku_id, quantity, reorder_point, reorder_quantity, lot_number, received_date, expiration_date, warehouse_zone)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                sku_id, lot_qty, reorder_p, reorder_q, f"LOT-{sku_id}-{lot_idx+1}", received, expiration, zone,
            )
    print(f"Seeded inventory ({len(product_list)} products, {low_count} low, {zero_count} zero).")


if __name__ == "__main__":
    asyncio.run(run_seed())
