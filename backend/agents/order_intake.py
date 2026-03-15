"""Order Intake: parses raw natural language orders into structured line items via Bedrock Converse with structured output."""
from strands import tool

from backend.agents.order_intake_converse import parse_order as _parse_order_converse


@tool
def parse_order(raw_text: str, customer_id: str) -> dict:
    """
    Parse raw order message from a customer into structured line items matched to SKUs.
    Uses Bedrock Converse API with outputConfig (JSON schema) so the response is always valid JSON.

    Args:
        raw_text: The raw order message from the customer.
        customer_id: The customer's ID for history and preferences lookup.

    Returns:
        Dict with customer_id, order_items, total_amount, items_needing_review, parsing_notes.
        On failure, returns dict with "error" and "agent_name" keys.
    """
    return _parse_order_converse(raw_text, customer_id)
