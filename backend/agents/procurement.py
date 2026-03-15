"""Procurement Agent: generates purchase orders from inventory signals using supplier/demand tools."""
from strands import Agent, tool

from backend.agents.models import get_bedrock_model
from backend.agents.output_parser import parse_agent_json_with_retry
from backend.tools import (
    create_purchase_order,
    get_demand_forecast,
    get_suppliers_for_product,
)

GENERATE_PURCHASE_ORDERS_EXPECTED_KEYS = [
    "purchase_orders",
    "total_procurement_cost",
    "items_not_sourced",
]

PROCUREMENT_SYSTEM_PROMPT = """You are a procurement specialist for FreshFlow food distributor. You receive procurement signals (items that need reordering: sku_id, current_quantity, reorder_point) and create purchase orders by selecting suppliers and quantities.

SUPPLIER SELECTION RULES (follow exactly):
- Prefer lowest price first.
- If two suppliers are within 5% on price, prefer the one with shorter lead time.
- If the shorter-lead-time supplier is more than 10% more expensive, still take the cheaper one unless the item is urgently needed (e.g. out of stock, not just low).
- Compare at least 2 suppliers per product using get_suppliers_for_product.
- Respect each supplier's min_order_qty.
- Consolidate line items per supplier into one PO per supplier when possible.
- For perishables (shelf_life_days < 7), order at most 5 days of projected demand; use get_demand_forecast to get avg_daily_quantity and projected_demand_for_period.

WORKFLOW:
1. For each sku_id in the procurement signals, call get_suppliers_for_product(sku_id) and get_demand_forecast(sku_id, days=7).
2. Apply the supplier selection rules above. For each product, choose supplier and quantity (respect min_order_qty; cap perishables at 5 days demand).
3. Group items by supplier and call create_purchase_order(supplier_id, items_json, triggered_by, reasoning) for each supplier. items_json must be a JSON string array of objects with sku_id and quantity. You MUST pass a reasoning parameter (short explanation of why this supplier and these quantities — e.g. lowest price, within 5% so chose shorter lead time, urgency override).
4. Compute expected_delivery_date for each PO as today + supplier lead_time_days (from get_suppliers_for_product).

OUTPUT FORMAT: Return a single JSON object with these exact keys:
- purchase_orders: array of objects, each with: po_id, supplier_id, supplier_name, items (array with sku_id, product_name, quantity, unit_price, line_total), po_total, expected_delivery_date (YYYY-MM-DD), reasoning (short explanation of why this supplier and quantity).
- total_procurement_cost: sum of all PO totals.
- items_not_sourced: array of sku_ids that could not be sourced (no supplier or invalid).

Return only valid JSON, no markdown or extra text."""

_procurement_model = get_bedrock_model("high")
procurement_agent = Agent(
    model=_procurement_model,
    system_prompt=PROCUREMENT_SYSTEM_PROMPT,
    tools=[get_suppliers_for_product, get_demand_forecast, create_purchase_order],
)


@tool
def generate_purchase_orders(procurement_signals_json: str, triggered_by_order_id: str) -> dict:
    """
    Generate purchase orders from procurement signals (e.g. from Inventory Agent).
    For each signal (sku_id, current_quantity, reorder_point), finds suppliers, compares price/lead time,
    respects min order qty and perishable caps, and creates POs. Returns each PO with expected_delivery_date and reasoning.

    Args:
        procurement_signals_json: JSON string array of objects with sku_id, current_quantity, reorder_point
          (from Inventory Agent's procurement_signals).
        triggered_by_order_id: Order ID that triggered this procurement (for traceability).

    Returns:
        Dict with purchase_orders, total_procurement_cost, items_not_sourced.
        On parse failure after retry, returns dict with "error" and "agent_name" keys.
    """
    prompt = f"""Create purchase orders for these procurement signals. Triggered by order: {triggered_by_order_id}.

{procurement_signals_json}

Use get_suppliers_for_product and get_demand_forecast for each product. Apply the 5%/10%/urgency supplier rules. Call create_purchase_order per supplier. Return a single JSON object with purchase_orders (each with expected_delivery_date and reasoning), total_procurement_cost, and items_not_sourced. No markdown."""
    return parse_agent_json_with_retry(
        procurement_agent,
        prompt,
        GENERATE_PURCHASE_ORDERS_EXPECTED_KEYS,
        "generate_purchase_orders",
        max_retries=1,
    )
