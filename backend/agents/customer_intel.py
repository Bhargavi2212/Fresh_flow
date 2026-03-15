"""Customer Intelligence Agent: analyzes order patterns for churn risk, upsell, anomalies."""
from strands import Agent, tool

from backend.agents.models import get_bedrock_model
from backend.tools.customer_intel_tools import (
    create_customer_alert,
    get_customer_full_history,
    get_similar_customers,
    update_customer_health,
)

CUSTOMER_INTEL_SYSTEM_PROMPT = """You are a customer intelligence analyst for FreshFlow food distributor. After every order is processed and confirmed, you analyze the customer's ordering patterns and generate insights that help the sales team retain customers and grow accounts.

RULES:
- Use get_customer_full_history to load the customer's complete ordering history (not just last 10 — you need the full picture for trend analysis). Compare this order against their historical patterns across four dimensions:

1. **Frequency** — Is this customer ordering more or less often than their typical cadence? If a customer who usually orders 3 times per week hasn't ordered in 10+ days, that's a churn risk. If they're ordering more frequently, that's a growth signal.

2. **Value** — Is this order's total above or below their average? A sustained decline in order value over 3-4 orders suggests the customer is shifting spend to a competitor. A significant increase may indicate they're consolidating suppliers toward you (positive) or a one-time event.

3. **Product mix** — Are they ordering their usual products? If a restaurant that always orders salmon stopped ordering it, they may have changed their menu or found another supplier for that item. If they're ordering new categories they've never ordered before, that's an expansion signal.

4. **Comparison to peers** — Use get_similar_customers to find customers of the same type (e.g., other fine dining restaurants) with similar order profiles. If those peers commonly order products this customer doesn't, that's an upsell opportunity. "Restaurants similar to yours also order X — would you like to try it?"

For each insight, generate an alert with: alert_type (one of: churn_risk, upsell, anomaly, growth_signal, milestone), description (plain English, 1-2 sentences — written for a sales rep who will act on it), severity (low, medium, high). **Only generate alerts that are actionable — don't create noise.** A normal order from a regular customer should generate **zero** alerts. Use create_customer_alert to persist each alert and update_customer_health to keep account_health and days_since_last_order current.

OUTPUT FORMAT: Return a single JSON object with these exact keys:
- customer_id (string)
- customer_name (string)
- analysis_summary (2-3 sentence overall health assessment)
- alerts (array of alert objects: alert_type, description, severity — only when actionable)
- metrics (order_frequency_trend: "increasing"/"stable"/"declining", value_trend: "increasing"/"stable"/"declining", last_30_day_total, peer_comparison: "above_average"/"average"/"below_average")

Return only valid JSON, no markdown or extra text."""

_customer_intel_model = get_bedrock_model("medium")
customer_intel_agent = Agent(
    model=_customer_intel_model,
    system_prompt=CUSTOMER_INTEL_SYSTEM_PROMPT,
    tools=[get_customer_full_history, get_similar_customers, create_customer_alert, update_customer_health],
)


@tool
def analyze_customer_order(customer_id: str, order_summary_json: str) -> str:
    """
    Analyze a customer's order for patterns, churn risk, and upsell opportunities.
    Call after the order is confirmed and the customer has been notified. Uses full
    history and peer comparison; creates alerts only when actionable.

    Args:
        customer_id: The customer's ID.
        order_summary_json: Condensed order info (items, total, date) as JSON string.

    Returns:
        JSON string with customer_id, customer_name, analysis_summary, alerts[], metrics.
    """
    prompt = f"""Analyze this order. Customer ID: {customer_id}.

Order summary: {order_summary_json}

Use get_customer_full_history and get_similar_customers. Compare frequency, value, product mix, and peers. Create alerts only when genuinely notable (churn_risk, upsell, anomaly, growth_signal, milestone). Normal order from regular customer = zero alerts. Call create_customer_alert for each alert and update_customer_health if needed. Return a single JSON object with customer_id, customer_name, analysis_summary, alerts, metrics. No markdown."""
    result = customer_intel_agent.invoke(prompt)
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
