"""Order Intake Agent: parses raw natural language orders into structured line items."""
from strands import Agent, tool

from backend.agents.models import get_bedrock_model
from backend.tools import get_customer_history, get_customer_preferences, search_products

ORDER_INTAKE_SYSTEM_PROMPT = """You are an order parsing specialist for a seafood and produce food distributor called FreshFlow. You receive raw order messages from restaurant customers (sent via text, email, or voice) and your job is to convert them into structured line items matched to real products in the catalog.

RULES:
- For every product mention in the message, use the search_products tool to find matching SKUs. Never guess a SKU — always search.
- If the customer says "the usual" or "same as last time" or "regular order," use get_customer_history to look up their most frequently ordered items and include those.
- If the customer says something vague like "whatever white fish you got" or "some good fish," use get_customer_preferences to check if they have a preference, then use search_products with the category to find what's available.
- Handle mid-message corrections: if someone says "3 cases salmon — actually make that 5," the final quantity should be 5, not 3 or 8.
- Convert between natural units and SKU units. If the customer says "20 lbs of salmon" and the SKU is a 10lb case, the quantity should be 2 cases. If they say "a dozen eggs" and the SKU is "Eggs, Case of 15 dozen," figure out the right quantity.
- Assign a confidence score (0.0 to 1.0) to each line item match. Above 0.9 means certain match. 0.7-0.9 means probable match. Below 0.7 means uncertain — flag for human review.

Output format: Return a single JSON object with these exact keys:
- customer_id (string)
- order_items (array; each item: sku_id, product_name, raw_text, quantity, unit_of_measure, unit_price, line_total, confidence, match_reasoning)
- total_amount (number)
- items_needing_review (array of items with confidence below 0.8)
- parsing_notes (string; any observations — corrections detected, vague requests resolved, etc.)

Return only valid JSON, no markdown or extra text."""

_order_intake_model = get_bedrock_model("medium")
order_intake_agent = Agent(
    model=_order_intake_model,
    system_prompt=ORDER_INTAKE_SYSTEM_PROMPT,
    tools=[search_products, get_customer_history, get_customer_preferences],
)


@tool
def parse_order(raw_text: str, customer_id: str) -> str:
    """
    Parse raw order message from a customer into structured line items matched to SKUs.
    Use this to convert natural language (SMS, email, voice) into order_items with
    sku_id, quantity, unit_price, confidence. Always uses search_products for each
    product mention; uses get_customer_history for "the usual"; uses get_customer_preferences
    for vague requests.

    Args:
        raw_text: The raw order message from the customer.
        customer_id: The customer's ID for history and preferences lookup.

    Returns:
        JSON string with customer_id, order_items (each with sku_id, product_name, raw_text,
        quantity, unit_of_measure, unit_price, line_total, confidence, match_reasoning),
        total_amount, items_needing_review, parsing_notes.
    """
    prompt = f"""Parse this order from customer {customer_id}:

"{raw_text}"

Use search_products for every product mentioned. Use get_customer_history if they say "the usual" or "same as last time." Use get_customer_preferences for vague requests like "whatever white fish." Return a single JSON object only (no markdown)."""
    result = order_intake_agent.invoke(prompt)
    # AgentResult has .content (list of content blocks) or .message
    if hasattr(result, "message") and result.message:
        return result.message if isinstance(result.message, str) else str(result.message)
    if hasattr(result, "content") and result.content:
        parts = result.content
        if isinstance(parts, list) and parts:
            first = parts[0]
            if hasattr(first, "text"):
                return first.text
            if isinstance(first, dict) and "text" in first:
                return first["text"]
            return str(first)
        return str(parts)
    return str(result)
