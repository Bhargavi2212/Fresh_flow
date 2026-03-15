"""FreshFlow FastAPI application."""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api import customer_alerts, dashboard, health, products, customers, inventory, suppliers, ingest, orders, purchase_orders, websocket as ws_router
from backend.services.database import close_pool, get_pool
from backend.services.websocket_manager import get_ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_ws_manager().set_loop(asyncio.get_running_loop())
    await get_pool()
    yield
    await close_pool()


app = FastAPI(title="FreshFlow API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

app.include_router(health.router)
app.include_router(products.router)
app.include_router(customers.router)
app.include_router(inventory.router)
app.include_router(suppliers.router)
app.include_router(dashboard.router)
app.include_router(ingest.router)
app.include_router(orders.router)
app.include_router(purchase_orders.router)
app.include_router(customer_alerts.router)
app.include_router(ws_router.router)
