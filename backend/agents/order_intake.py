"""Order Intake Agent: parses raw natural language orders into structured line items."""
from strands import Agent, tool

from backend.agents.models import get_bedrock_model
from backend.agents.output_parser import parse_agent_json_with_retry
from backend.tools import get_customer_history, get_customer_preferences, get_usual_order, search_products

PARSE_ORDER_EXPECTED_KEYS = [
    "customer_id",
    "order_items",
    "total_amount",
    "items_needing_review",
    "parsing_notes",
]

ORDER_INTAKE_SYSTEM_PROMPT = """You are an order parsing specialist for a seafood and produce food distributor called FreshFlow. You receive raw order messages from restaurant customers (sent via text, email, or voice) and your job is to convert them into structured line items matched to real products in the catalog.

RULES:
- For every product mention in the message, use the search_products tool to find matching SKUs. Never guess a SKU — always search.
- If the customer says "the usual" or "same as last time" or "regular order," call get_usual_order(customer_id) and use the returned items directly. Assign confidence 0.95 to each of these items. Do not re-interpret or substitute — use the sku_id and median_quantity from get_usual_order as the line items.
- For other history-based phrasing (when not clearly "the usual"), you may use get_customer_history to look up recent orders.
- If the customer says something vague like "whatever white fish you got" or "some good fish," use get_customer_preferences to check if they have a preference, then use search_products with the category to find what's available.
- Handle mid-message corrections: if someone says "3 cases salmon — actually make that 5," the final quantity should be 5, not 3 or 8.
- Convert between natural units and SKU units. If the customer says "20 lbs of salmon" and the SKU is a 10lb case, the quantity should be 2 cases. If they say "a dozen eggs" and the SKU is "Eggs, Case of 15 dozen," figure out the right quantity.
- Confidence must be grounded in search_products' similarity_score. Use these rules exactly:
  - similarity_score >= 0.85 with clear match → confidence = similarity_score
  - similarity_score 0.70-0.85 → confidence = similarity_score - 0.05
  - similarity_score < 0.70 → confidence = 0.50 and flag for review (include in items_needing_review)
  - Preference-based or "the usual" (from get_usual_order) → use 0.95 (or reduce by 0.10 if combined with vague wording)
  - Vague request (e.g. "whatever white fish") → cap confidence at 0.82
  - Always include similarity_score in match_reasoning for each item

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
    tools=[search_products, get_usual_order, get_customer_history, get_customer_preferences],
)


@tool
def parse_order(raw_text: str, customer_id: str) -> dict:
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
        Dict with customer_id, order_items, total_amount, items_needing_review, parsing_notes.
        On parse failure after retry, returns dict with "error" and "agent_name" keys.
    """
    prompt = f"""Parse this order from customer {customer_id}:

"{raw_text}"

Use search_products for every product mentioned. If they say \"the usual\" or \"same as last time\" or \"regular order,\" call get_usual_order(customer_id) and use those items with confidence 0.95. Use get_customer_preferences for vague requests like \"whatever white fish.\" Return a single JSON object only (no markdown)."""
    return parse_agent_json_with_retry(
        order_intake_agent,
        prompt,
        PARSE_ORDER_EXPECTED_KEYS,
        "parse_order",
        max_retries=1,
    )
