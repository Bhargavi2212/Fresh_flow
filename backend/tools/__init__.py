# Re-export all @tool functions for agents and ingest.
from backend.tools.product_search import search_products
from backend.tools.customer_lookup import get_customer_history, get_customer_preferences
from backend.tools.inventory_check import check_stock, get_expiring_items
from backend.tools.substitutions import find_substitutions
from backend.tools.supplier_lookup import get_suppliers_for_product
from backend.tools.demand_forecast import get_demand_forecast
from backend.tools.po_writer import create_purchase_order

__all__ = [
    "search_products",
    "get_customer_history",
    "get_customer_preferences",
    "check_stock",
    "get_expiring_items",
    "find_substitutions",
    "get_suppliers_for_product",
    "get_demand_forecast",
    "create_purchase_order",
]
