"""Orchestrator Agent: runs the full order pipeline (parse → inventory → procure → save → confirm → customer intel)."""
import json
import re
import time
from datetime import datetime, timezone

from strands import Agent

from backend.agents.models import get_bedrock_model
from backend.agents.order_intake import parse_order
from backend.agents.inventory_agent import check_order_inventory
from backend.agents.procurement import generate_purchase_orders
from backend.agents.customer_intel import analyze_customer_order
from backend.tools.order_writer import save_confirmed_order, append_order_trace
from backend.tools.sms_sender import send_order_confirmation
from backend.services.websocket_manager import get_ws_manager

ORCHESTRATOR_SYSTEM_PROMPT = """You are the order orchestration agent for FreshFlow. You run a strict 6-step workflow. Use ONLY these tools in order; do not skip steps.

STEP 1 — PARSE: Call parse_order(raw_text, customer_id) with the raw order message and customer_id. You get back structured order_items (JSON).

STEP 2 — CHECK INVENTORY: Call check_order_inventory(order_items_json, customer_id) with the JSON string of order_items from step 1. You get back checked_items, procurement_signals, and summary.

STEP 3 — DECIDE STATUS: From the inventory result, set status to "confirmed" if all items available and confidence is high; set status to "needs_review" if any item is partial/out_of_stock or confidence is low.

STEP 4 — PROCURE (if needed): If the inventory result contains non-empty procurement_signals, call generate_purchase_orders(procurement_signals_json, triggered_by_order_id). Use the string "orchestrator" as triggered_by_order_id. Count how many POs were created.

STEP 5 — SAVE AND CONFIRM: Build order_data as a JSON string with: customer_id, channel, raw_message, status, confidence_score (from parse result), items (use the checked_items from inventory, with all fields each item needs: sku_id, quantity, unit_price, line_total, raw_text, confidence, availability_status, etc.), and agent_trace (object containing: order_intake = parse result, inventory = inventory result, procurement = procurement result if step 4 was called). Call save_confirmed_order(order_data). You get back order_id and status. Then call send_order_confirmation(order_id, customer_phone, customer_name, status, items_summary, total_amount, special_notes). If customer_phone is empty use "". For items_summary use a short line like "3 items" or list key product names. total_amount from parse result. Check the return value for confirmation_sent (sent: true/false).

STEP 6 — ANALYZE CUSTOMER: After step 5, build a short order_summary_json (e.g. order_id, customer_id, item_count, total_amount, status). Call analyze_customer_order(customer_id, order_summary_json). Then call append_order_trace(order_id, "customer_intel", <the JSON string returned by analyze_customer_order>) to store the customer intelligence result on the order.

FINAL OUTPUT: You MUST end your final response with a single JSON object (no markdown, no code fence) containing exactly these keys so the system can parse the result:
- order_id (string from save_confirmed_order)
- status (string: confirmed | needs_review)
- customer_name (string)
- channel (string: web | sms)
- item_count (number)
- total_amount (number)
- items_confirmed (number: count of items with availability available)
- items_needing_review (number: count of items partial or out_of_stock or low confidence)
- substitutions_made (number: count of items that were substituted)
- purchase_orders_generated (number: count of POs from step 4, or 0)
- confirmation_sent (boolean: from send_order_confirmation result)

Example final line: {"order_id":"ORD-2026-000001","status":"confirmed","customer_name":"Acme Cafe","channel":"sms","item_count":3,"total_amount":450.00,"items_confirmed":3,"items_needing_review":0,"substitutions_made":0,"purchase_orders_generated":0,"confirmation_sent":true}
"""

_orchestrator_model = get_bedrock_model("medium")
orchestrator_agent = Agent(
    model=_orchestrator_model,
    system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
    tools=[
        parse_order,
        check_order_inventory,
        generate_purchase_orders,
        save_confirmed_order,
        send_order_confirmation,
        analyze_customer_order,
        append_order_trace,
    ],
)


def _extract_summary_json(text: str) -> dict | None:
    """Extract the required summary JSON from agent output (last JSON object in text)."""
    if not text or not isinstance(text, str):
        return None
    # Find last {...} that looks like our summary (has order_id, status, etc.)
    candidates = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text)
    for raw in reversed(candidates):
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and "order_id" in obj and "status" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def run_orchestrator(
    raw_message: str,
    customer_id: str,
    channel: str,
    customer_phone: str = "",
) -> tuple[object, dict | None]:
    """
    Run the full Orchestrator pipeline on a raw order message.
    Returns (agent result, parsed_summary_dict). parsed_summary_dict has the exact
    summary keys (order_id, status, customer_name, channel, item_count, total_amount,
    items_confirmed, items_needing_review, substitutions_made, purchase_orders_generated,
    confirmation_sent) or None if parsing failed.
    """
    customer_phone = (customer_phone or "").strip()
    order_id_placeholder = "pending"
    try:
        get_ws_manager().broadcast_sync({
            "type": "agent_activity",
            "order_id": order_id_placeholder,
            "agent_name": "orchestrator",
            "status": "started",
            "summary": "Processing order",
            "duration_ms": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    start = time.perf_counter()
    prompt_parts = [
        f"Process this order. Customer ID: {customer_id}. Channel: {channel}.",
        f"Raw message: {raw_message!r}",
    ]
    if customer_phone:
        prompt_parts.append(f"Customer phone for SMS confirmation: {customer_phone}")
    prompt_parts.append(
        "Run all 6 steps (parse, inventory, decide status, procure if needed, save and confirm, then analyze_customer_order and append_order_trace). End your final message with the required summary JSON (single line, no markdown)."
    )
    prompt = "\n".join(prompt_parts)
    result = orchestrator_agent.invoke(prompt)
    duration_ms = int((time.perf_counter() - start) * 1000)

    # Extract summary from result
    text = ""
    if hasattr(result, "message") and result.message:
        text = result.message if isinstance(result.message, str) else str(result.message)
    elif hasattr(result, "content") and result.content:
        parts = result.content
        if isinstance(parts, list) and parts:
            first = parts[0]
            if hasattr(first, "text"):
                text = first.text
            elif isinstance(first, dict) and "text" in first:
                text = first["text"]
            else:
                text = str(first)
        else:
            text = str(parts)
    else:
        text = str(result)

    summary = _extract_summary_json(text)
    final_order_id = (summary.get("order_id") or order_id_placeholder) if summary else order_id_placeholder
    try:
        get_ws_manager().broadcast_sync({
            "type": "agent_activity",
            "order_id": final_order_id,
            "agent_name": "orchestrator",
            "status": "completed",
            "summary": f"Order {final_order_id} {summary.get('status', '')}" if summary else "Done",
            "duration_ms": duration_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass
    return result, summary
