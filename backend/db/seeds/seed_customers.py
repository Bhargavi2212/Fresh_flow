"""Seed 75 customers: fine_dining, casual, fast_casual, institutional, grocery. Unique phones."""
import asyncio
import random
from decimal import Decimal
from datetime import datetime, timedelta

from backend.services.database import execute, get_pool


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE customer_alerts CASCADE")
        await conn.execute("TRUNCATE TABLE order_items CASCADE")
        await conn.execute("TRUNCATE TABLE orders CASCADE")
        await conn.execute("TRUNCATE TABLE customer_preferences CASCADE")
        await conn.execute("TRUNCATE TABLE customers CASCADE")

    # 20 fine_dining, 25 casual, 10 fast_casual, 10 institutional, 10 grocery = 75
    # 5-10 at_risk or churning
    types_count = [("fine_dining", 20), ("casual", 25), ("fast_casual", 10), ("institutional", 10), ("grocery", 10)]
    payment_terms = ["NET15", "NET30", "COD"]
    delivery_days_options = [["Mon", "Wed", "Fri"], ["Tue", "Thu"], ["Mon", "Tue", "Wed", "Thu", "Fri"]]
    at_risk_indices = set(random.sample(range(75), random.randint(5, 10)))

    idx = 0
    for cust_type, count in types_count:
        for i in range(count):
            cid = f"CUST-{(idx+1):03d}"
            name = f"Customer {idx+1} {cust_type.replace('_', ' ').title()}"
            phone = f"+1212555{3000 + idx:04d}"
            email = f"contact{cid}@example.com"
            delivery = random.choice(delivery_days_options)
            terms = random.choice(payment_terms)
            if cust_type == "fine_dining":
                credit = Decimal(random.randint(5000, 15000))
                avg = Decimal(random.randint(500, 1500))
            elif cust_type == "casual":
                credit = Decimal(random.randint(2000, 8000))
                avg = Decimal(random.randint(200, 600))
            elif cust_type == "fast_casual":
                credit = Decimal(random.randint(1000, 4000))
                avg = Decimal(random.randint(100, 300))
            elif cust_type == "institutional":
                credit = Decimal(random.randint(10000, 25000))
                avg = Decimal(random.randint(800, 2000))
            else:
                credit = Decimal(random.randint(3000, 10000))
                avg = Decimal(random.randint(300, 800))
            health = "churning" if idx in at_risk_indices and random.random() < 0.3 else ("at_risk" if idx in at_risk_indices else "active")
            days_since = random.randint(0, 14) if health == "active" else random.randint(15, 45)
            created = datetime.now() - timedelta(days=365)
            await execute(
                """INSERT INTO customers (customer_id, name, type, phone, email, delivery_days, payment_terms, credit_limit, avg_order_value, account_health, days_since_last_order, created_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)""",
                cid, name, cust_type, phone, email, delivery, terms, credit, avg, health, days_since, created,
            )
            idx += 1
    print("Seeded 75 customers.")


if __name__ == "__main__":
    asyncio.run(run_seed())
