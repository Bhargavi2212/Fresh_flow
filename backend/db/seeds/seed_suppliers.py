"""Seed 15 suppliers: seafood, produce, dairy, dry goods, paper."""
import asyncio
from decimal import Decimal

from backend.services.database import execute, fetch_all, get_pool


SUPPLIERS = [
    ("SUP-SEA-001", "Pacific Seafood", 1, Decimal("500.00"), Decimal("0.95"), "+1-503-555-1001", "orders@pacificseafood.com"),
    ("SUP-SEA-002", "Boston Fish Market", 2, Decimal("300.00"), Decimal("0.92"), "+1-617-555-1002", "sales@bostonfish.com"),
    ("SUP-SEA-003", "Ocean Pride", 1, Decimal("400.00"), Decimal("0.88"), "+1-206-555-1003", "orders@oceanpride.com"),
    ("SUP-SEA-004", "Gulf Coast Seafood", 2, Decimal("350.00"), Decimal("0.90"), "+1-504-555-1004", "info@gulfcoastseafood.com"),
    ("SUP-PRO-001", "Valley Fresh Farms", 1, Decimal("200.00"), Decimal("0.94"), "+1-559-555-2001", "orders@valleyfresh.com"),
    ("SUP-PRO-002", "Sunrise Produce", 1, Decimal("250.00"), Decimal("0.91"), "+1-408-555-2002", "sales@sunriseproduce.com"),
    ("SUP-PRO-003", "Green Valley Organics", 2, Decimal("400.00"), Decimal("0.96"), "+1-831-555-2003", "orders@greenvalley.com"),
    ("SUP-PRO-004", "Pacific Northwest Growers", 2, Decimal("300.00"), Decimal("0.89"), "+1-503-555-2004", "info@pacificnw.com"),
    ("SUP-DRY-001", "Chef's Pantry", 5, Decimal("150.00"), Decimal("0.93"), "+1-800-555-3001", "orders@chefspantry.com"),
    ("SUP-DRY-002", "Restaurant Depot Wholesale", 7, Decimal("500.00"), Decimal("0.97"), "+1-800-555-3002", "sales@restdepot.com"),
    ("SUP-DRY-003", "US Foods Direct", 5, Decimal("350.00"), Decimal("0.94"), "+1-800-555-3003", "orders@usfoods.com"),
    ("SUP-DAI-001", "Dairy Fresh Co", 2, Decimal("200.00"), Decimal("0.92"), "+1-612-555-4001", "orders@dairyfresh.com"),
    ("SUP-DAI-002", "Organic Valley Wholesale", 3, Decimal("300.00"), Decimal("0.90"), "+1-608-555-4002", "sales@organicvalley.com"),
    ("SUP-PAP-001", "Paper & More", 5, Decimal("100.00"), Decimal("0.85"), "+1-800-555-5001", "orders@paperandmore.com"),
    ("SUP-PAP-002", "Eco-Supply Co", 7, Decimal("250.00"), Decimal("0.88"), "+1-800-555-5002", "info@ecosupply.com"),
]


async def run_seed() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE order_items, orders, inventory, supplier_products, po_items, purchase_orders, products CASCADE")
        await conn.execute("TRUNCATE TABLE suppliers CASCADE")
    for row in SUPPLIERS:
        await execute(
            """INSERT INTO suppliers (supplier_id, name, lead_time_days, min_order_value, reliability_score, phone, email)
               VALUES ($1, $2, $3, $4, $5, $6, $7)""",
            *row,
        )
    print("Seeded 15 suppliers.")


if __name__ == "__main__":
    asyncio.run(run_seed())
