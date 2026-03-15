"""Run all seed scripts in order: suppliers -> products -> supplier_products -> customers -> customer_preferences -> inventory -> orders."""
import asyncio
import sys

from backend.services.database import close_pool, get_pool

# Import run_seed from each module
from backend.db.seeds.seed_suppliers import run_seed as seed_suppliers
from backend.db.seeds.seed_products import run_seed as seed_products
from backend.db.seeds.seed_supplier_products import run_seed as seed_supplier_products
from backend.db.seeds.seed_customers import run_seed as seed_customers
from backend.db.seeds.seed_customer_preferences import run_seed as seed_customer_preferences
from backend.db.seeds.seed_inventory import run_seed as seed_inventory
from backend.db.seeds.seed_orders import run_seed as seed_orders


async def main() -> None:
    await get_pool()
    try:
        await seed_suppliers()
        await seed_products()
        await seed_supplier_products()
        await seed_customers()
        await seed_customer_preferences()
        await seed_inventory()
        await seed_orders()
        print("All seeds completed.")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
