"""Agent tool: send order confirmation SMS via Twilio (for Orchestrator)."""
import json
import logging

from strands import tool

from backend.services.twilio_service import send_sms

logger = logging.getLogger(__name__)

NEEDS_REVIEW_MESSAGE = (
    "Got your order, but we need to confirm a few items — your rep will follow up in the morning."
)


@tool
def send_order_confirmation(
    order_id: str,
    customer_phone: str,
    customer_name: str,
    status: str,
    items_summary: str,
    total_amount: float,
    special_notes: str = "",
) -> str:
    """
    Send an order confirmation SMS to the customer. Use after save_confirmed_order.
    If customer_phone is empty or Twilio is not configured, returns sent: false without raising.
    On Twilio API failure, logs and returns sent: false; does not crash order processing.

    Args:
        order_id: Order ID that was saved.
        customer_phone: Customer phone number (E.164).
        customer_name: Customer name for greeting.
        status: Order status ('confirmed' or 'needs_review').
        items_summary: Short summary of items (e.g. "3 items" or "Salmon, shrimp, greens").
        total_amount: Order total.
        special_notes: Optional notes to include.

    Returns:
        JSON string with sent (bool), twilio_sid (or null), message_body (string).
    """
    message_body = ""
    if not customer_phone or not str(customer_phone).strip():
        return json.dumps({
            "sent": False,
            "twilio_sid": None,
            "message_body": "No customer phone provided.",
        })

    customer_phone = str(customer_phone).strip()
    customer_name = (customer_name or "there").strip()
    status = (status or "confirmed").strip().lower()
    total_str = f"${total_amount:,.2f}" if total_amount is not None else "—"
    items_summary = (items_summary or "your items").strip()

    if status == "needs_review":
        message_body = NEEDS_REVIEW_MESSAGE
    else:
        parts = [f"Hi {customer_name}! Your order {order_id} is confirmed.", f"Items: {items_summary}. Total: {total_str}."]
        if special_notes:
            parts.append(str(special_notes).strip()[:100])
        message_body = " ".join(parts)

    if len(message_body) > 320:
        message_body = message_body[:317] + "..."

    result = send_sms(customer_phone, message_body)
    if not result.get("sent"):
        logger.warning("send_order_confirmation: Twilio did not send: %s", result.get("error"))
        return json.dumps({
            "sent": False,
            "twilio_sid": result.get("sid"),
            "message_body": message_body,
        })

    return json.dumps({
        "sent": True,
        "twilio_sid": result.get("sid"),
        "message_body": message_body,
    })
