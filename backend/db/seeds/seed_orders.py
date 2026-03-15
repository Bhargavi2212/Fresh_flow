"""Seed 8k-12k historical orders (Oct 2025 - Mar 2026); at_risk declining in last 6 weeks."""
import asyncio
import random
from decimal import Decimal
from datetime import datetime, timedelta

from backend.services.database import execute, get_pool


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE order_items CASCADE")
        await conn.execute("TRUNCATE TABLE orders CASCADE")
        customers = await conn.fetch("SELECT customer_id, type, avg_order_value, account_health FROM customers")
        products = await conn.fetch("SELECT sku_id, unit_price FROM products")
    customer_list = [(r["customer_id"], r["type"], float(r["avg_order_value"] or 300)) for r in customers]
    product_list = [(r["sku_id"], float(r["unit_price"] or 10)) for r in products]
    at_risk = {r["customer_id"] for r in customers if r["account_health"] in ("at_risk", "churning")}

    # Orders per week by type; target ~10k total over 26 weeks
    orders_per_week = {"fine_dining": 3.5, "casual": 3, "fast_casual": 2.5, "institutional": 3, "grocery": 2}
    start = datetime(2025, 10, 1)
    end = datetime(2026, 3, 31)
    cutoff_decline = end - timedelta(weeks=6)

    random.seed(46)
    order_id_num = 1
    total_orders = 0
    for cid, ctype, avg_val in customer_list:
        per_week = orders_per_week.get(ctype, 2)
        is_at_risk = cid in at_risk
        current = start
        while current <= end:
            # At-risk: fewer orders in last 6 weeks
            if is_at_risk and current >= cutoff_decline:
                if random.random() > 0.4:
                    current += timedelta(days=1)
                    continue
            # Otherwise 2-4 orders per week depending on type
            n_this_week = max(0, int(per_week) + random.randint(-1, 1))
            for _ in range(n_this_week):
                if current > end:
                    break
                oid = f"ORD-2025-{order_id_num:06d}"
                total_amt = round(avg_val * random.uniform(0.7, 1.3), 2)
                channel = random.choice(["sms", "email", "phone", "web"])
                status = random.choice(["confirmed", "fulfilled", "fulfilled", "fulfilled"])
                created = current.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
                await execute(
                    """INSERT INTO orders (order_id, customer_id, channel, raw_message, status, confidence_score, total_amount, created_at, confirmed_at, agent_trace)
                       VALUES ($1, $2, $3, NULL, $4, NULL, $5, $6, $6, NULL)""",
                    oid, cid, channel, status, Decimal(str(total_amt)), created,
                )
                # 4-12 line items
                n_items = random.randint(4, 12)
                remaining = total_amt
                chosen = random.sample(product_list, min(n_items, len(product_list)))
                for i, (sku, up) in enumerate(chosen):
                    if i == len(chosen) - 1:
                        qty = max(0.5, round(remaining / up, 2))
                    else:
                        qty = round(random.uniform(0.5, 10), 2)
                    line_total = round(float(qty) * up, 2)
                    remaining -= line_total
                    await execute(
                        """INSERT INTO order_items (order_id, sku_id, raw_text, quantity, unit_price, line_total, match_confidence, status, substituted_from, notes)
                           VALUES ($1, $2, NULL, $3, $4, $5, NULL, 'available', NULL, NULL)""",
                        oid, sku, Decimal(str(qty)), Decimal(str(up)), Decimal(str(line_total)),
                    )
                order_id_num += 1
                total_orders += 1
            current += timedelta(days=7)
    print(f"Seeded {total_orders} orders with line items.")


if __name__ == "__main__":
    asyncio.run(run_seed())
