"""Pydantic models for API request/response. Product excludes embedding."""
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sku_id: str
    name: str
    aliases: list[str]
    category: str | None
    subcategory: str | None
    unit_of_measure: str | None
    case_size: Decimal | None
    unit_price: Decimal | None
    cost_price: Decimal | None
    shelf_life_days: int | None
    storage_type: str | None
    supplier_id: str | None
    status: str | None


class ProductSearchResult(Product):
    similarity: float


class Customer(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    customer_id: str
    name: str | None
    type: str | None
    phone: str | None
    email: str | None
    delivery_days: list[str] | None
    payment_terms: str | None
    credit_limit: Decimal | None
    avg_order_value: Decimal | None
    account_health: str | None
    days_since_last_order: int | None


class InventoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sku_id: str
    quantity: Decimal
    reorder_point: Decimal | None
    reorder_quantity: Decimal | None
    lot_number: str | None
    received_date: Any
    expiration_date: Any
    warehouse_zone: str | None


class Supplier(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    supplier_id: str
    name: str | None
    lead_time_days: int | None
    min_order_value: Decimal | None
    reliability_score: Decimal | None
    phone: str | None
    email: str | None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    database: str
    bedrock: str


class DashboardStats(BaseModel):
    total_products: int
    total_customers: int
    orders_last_30_days: int
    low_stock_count: int
    expiring_soon_count: int
    at_risk_customer_count: int
    purchase_orders_today: int = 0
    purchase_orders_total_value_today: float = 0.0
    orders_auto_confirmed_today: int = 0
    orders_needing_review_today: int = 0
    orders_today: int = 0
    revenue_today: float = 0.0
    active_alerts_count: int = 0


# --- Purchase orders (Phase 3) ---
class POItem(BaseModel):
    id: int | None = None
    sku_id: str
    quantity: float
    unit_price: float | None = None
    line_total: float | None = None


class PurchaseOrderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    po_id: str
    supplier_id: str
    status: str | None = None
    total_amount: Decimal | None = None
    triggered_by: str | None = None
    reasoning: str | None = None
    created_at: Any = None
    items: list[POItem] = []
    supplier_name: str | None = None


class PurchaseOrderListResponse(BaseModel):
    items: list[PurchaseOrderDetail]
    total: int
    limit: int
    offset: int


# --- Ingest (Phase 2) ---
class IngestWebRequest(BaseModel):
    customer_id: str
    message: str
    channel: str = "web"


class IngestWebResponse(BaseModel):
    order_id: str
    status: str
    parsed_items: list[Any]
    procurement_signals: list[Any]
    customer_insights: list[Any]
    total_amount: Decimal | None
    confidence_score: float | None


# --- Orders (Phase 2) ---
class OrderStatusUpdate(BaseModel):
    status: str  # "confirmed" | "needs_review" | "cancelled"


class OrderItemDetail(BaseModel):
    id: int | None = None
    sku_id: str
    raw_text: str | None = None
    quantity: Decimal
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    match_confidence: Decimal | None = None
    status: str | None = None
    substituted_from: str | None = None
    notes: str | None = None


class OrderDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    order_id: str
    customer_id: str
    channel: str | None
    raw_message: str | None
    status: str | None
    confidence_score: Decimal | None
    total_amount: Decimal | None
    created_at: Any = None
    confirmed_at: Any = None
    agent_trace: dict[str, Any] | None = None
    customer: Customer | None = None
    items: list[OrderItemDetail] = []


# --- Customer alerts (Phase 4) ---
class CustomerAlertDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    customer_id: str
    customer_name: str | None = None
    alert_type: str
    description: str | None = None
    severity: str | None = None
    acknowledged: bool = False
    created_at: Any = None


class CustomerAlertListResponse(BaseModel):
    items: list[CustomerAlertDetail]
    total: int
    limit: int
    offset: int


class CustomerAlertAck(BaseModel):
    acknowledged: bool = True
