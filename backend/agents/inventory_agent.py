"""Inventory Agent: checks parsed order items against stock and suggests substitutions."""
from strands import Agent, tool

from backend.agents.models import get_bedrock_model
from backend.agents.output_parser import parse_agent_json_with_retry
from backend.tools import check_stock, find_substitutions, get_expiring_items

CHECK_ORDER_INVENTORY_EXPECTED_KEYS = ["checked_items", "procurement_signals", "summary"]

INVENTORY_AGENT_SYSTEM_PROMPT = """You are an inventory management specialist for FreshFlow food distributor. You receive a list of parsed order items (already matched to SKUs with quantities) and your job is to check availability for each item against current stock levels.

RULES:
- For each item, use check_stock to get current levels. If the item is available in full, mark it "available." If partially available (some stock but not enough), mark it "partial" and include how much is available vs how much was requested. If out of stock (zero quantity), mark it "out_of_stock."
- For any item that is partial or out_of_stock, use find_substitutions to suggest alternatives based on customer preferences.
- Check expiration using get_expiring_items — if the only available stock expires within 2 days, note this as a warning.
- Flag any item where current stock after this order would fall below the reorder_point — these are procurement signals for Phase 3.

Output format: Return a single JSON object with these exact keys:
- checked_items (array; each item includes all original fields from the order plus: availability_status, available_quantity, shortfall_quantity, expiration_warning, suggested_substitutions, triggers_reorder)
- procurement_signals (array of objects with sku_id, current_quantity, reorder_point for items that need reordering)
- summary (object with counts: available, partial, out_of_stock)

Return only valid JSON, no markdown or extra text."""

_inventory_model = get_bedrock_model("low")
inventory_agent = Agent(
    model=_inventory_model,
    system_prompt=INVENTORY_AGENT_SYSTEM_PROMPT,
    tools=[check_stock, get_expiring_items, find_substitutions],
)


@tool
def check_order_inventory(order_items_json: str, customer_id: str) -> dict:
    """
    Check inventory availability for all items in a parsed order. Use after parse_order.
    For each line item, calls check_stock; for shortfalls uses find_substitutions;
    uses get_expiring_items for 2-day expiration warnings. Flags items below reorder_point.

    Args:
        order_items_json: JSON string of parsed order items from Order Intake Agent
          (order_items array with sku_id, quantity, etc.).
        customer_id: Customer ID for substitution preferences.

    Returns:
        Dict with checked_items, procurement_signals, summary.
        On parse failure after retry, returns dict with "error" and "agent_name" keys.
    """
    prompt = f"""Check inventory for these order items (customer {customer_id}):

{order_items_json}

Use check_stock for each item. Use find_substitutions for any partial or out_of_stock. Use get_expiring_items for items expiring within 2 days. Return a single JSON object only (no markdown)."""
    return parse_agent_json_with_retry(
        inventory_agent,
        prompt,
        CHECK_ORDER_INVENTORY_EXPECTED_KEYS,
        "check_order_inventory",
        max_retries=1,
    )
