"""
Order intake via Bedrock Converse API (tools + system prompt).
Final response is parsed with parse_agent_json (fences, last {...}, key validation).
"""
import json
import logging
from typing import Any

import boto3

from backend.agents.output_parser import parse_agent_json
from backend.config import get_settings
from backend.tools import get_customer_history, get_customer_preferences, get_usual_order, search_products

logger = logging.getLogger(__name__)

MODEL_ID = "us.amazon.nova-2-lite-v1:0"
MAX_CONVERSE_ROUNDS = 15

SYSTEM_PROMPT = """You are an order parsing specialist for FreshFlow (seafood and produce distributor). Convert raw order messages into structured line items matched to real products.

RULES:
- You MUST call search_products for every product or ingredient mentioned (e.g. "salmon", "2 cases salmon", "shrimp", "lettuce"). Never output order_items without having called search_products first for each product.
- If the customer says "the usual" or "same as last time", call get_usual_order(customer_id) and use those items with confidence 0.95.
- Use get_customer_preferences for vague requests; use get_customer_history when helpful.
- Handle corrections (e.g. "3 cases — actually 5" → quantity 5).
- Convert units to SKU units (e.g. 20 lbs when SKU is 10lb case → quantity 2).
- Ground confidence in search_products similarity_score: >=0.85 use as-is; 0.70-0.85 subtract 0.05; <0.70 use 0.50 and add to items_needing_review.
- Your final response must be a single JSON object with keys: customer_id, order_items, total_amount, items_needing_review, parsing_notes. Use double quotes for all keys and strings.
- order_items must be an array of objects with: sku_id, product_name, quantity, unit_price, line_total (and optionally confidence). Never return an empty order_items when the message clearly mentions products."""

# Bedrock Converse tool definitions (toolSpec with inputSchema as JSON schema).
def _tool_specs() -> list[dict]:
    return [
        {
            "toolSpec": {
                "name": "search_products",
                "description": "Search the product catalog. Use for every product mention. Args: query (string), top_k (optional int, default 5), category (optional string). Returns JSON list with sku_id, name, unit_price, similarity_score, etc.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Product name or natural language"},
                            "top_k": {"type": "integer", "description": "Max results", "default": 5},
                            "category": {"type": "string", "description": "Optional category filter"},
                        },
                        "required": ["query"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_usual_order",
                "description": "Get customer's usual order (items in 40%+ of recent orders). Use when they say 'the usual' or 'regular order'. Args: customer_id.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string"}},
                        "required": ["customer_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_customer_history",
                "description": "Get customer order history and frequent items. Args: customer_id, limit (optional, default 10).",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "customer_id": {"type": "string"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["customer_id"],
                    }
                },
            }
        },
        {
            "toolSpec": {
                "name": "get_customer_preferences",
                "description": "Get customer preferences (substitutions, exclusions). Use for vague requests. Args: customer_id.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {"customer_id": {"type": "string"}},
                        "required": ["customer_id"],
                    }
                },
            }
        },
    ]


def _get_client():
    s = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=s.aws_default_region,
        aws_access_key_id=s.aws_access_key_id or None,
        aws_secret_access_key=s.aws_secret_access_key or None,
    )


def _run_tool(name: str, input_obj: dict, customer_id: str) -> str:
    """Execute a tool by name; input_obj is the model's tool input (dict). Returns JSON string."""
    try:
        if name == "search_products":
            query = (input_obj.get("query") or "").strip()
            top_k = int(input_obj.get("top_k", 5))
            category = input_obj.get("category")
            return search_products(query=query, top_k=top_k, category=category)
        if name == "get_usual_order":
            return get_usual_order(customer_id=customer_id)
        if name == "get_customer_history":
            limit = int(input_obj.get("limit", 10))
            return get_customer_history(customer_id=customer_id, limit=limit)
        if name == "get_customer_preferences":
            return get_customer_preferences(customer_id=customer_id)
    except Exception as e:
        logger.warning("Tool %s failed: %s", name, e)
        return json.dumps({"error": str(e)})
    return json.dumps({"error": f"Unknown tool: {name}"})


def _extract_text_from_message(content: list[dict]) -> str | None:
    """Concatenate all text blocks from assistant message content (order JSON may be in a later block)."""
    parts = []
    for block in content or []:
        if "text" in block:
            parts.append(block["text"])
    return "\n".join(parts) if parts else None


def _has_tool_use(content: list[dict]) -> bool:
    return any("toolUse" in block for block in (content or []))


def parse_order(raw_text: str, customer_id: str) -> dict:
    """
    Parse order using Bedrock Converse with outputConfig (JSON schema).
    Returns dict with customer_id, order_items, total_amount, items_needing_review, parsing_notes.
    On failure returns {"error": str, "agent_name": "parse_order"}.
    """
    client = _get_client()
    messages: list[dict] = [
        {"role": "user", "content": [{"text": f'Parse this order from customer {customer_id}:\n\n"{raw_text}"\n\nYou MUST call search_products for each product or ingredient in the message (e.g. salmon, shrimp, cases of X) before replying. Then output exactly one JSON object with keys: customer_id, order_items, total_amount, items_needing_review, parsing_notes. order_items must list each item with sku_id, product_name, quantity, unit_price, line_total. Use double quotes only.'}]}
    ]
    inference_config = {"maxTokens": 4096, "temperature": 0}
    request_kwargs: dict[str, Any] = {
        "modelId": MODEL_ID,
        "messages": messages,
        "system": [{"text": SYSTEM_PROMPT}],
        "inferenceConfig": inference_config,
        "toolConfig": {"tools": _tool_specs(), "toolChoice": {"auto": {}}},
        "additionalModelRequestFields": {
            "reasoningConfig": {"type": "enabled", "maxReasoningEffort": "low"},
        },
    }
    settings = get_settings()
    if settings.bedrock_guardrail_id:
        request_kwargs["guardrailConfig"] = {
            "guardrailIdentifier": settings.bedrock_guardrail_id,
            "guardrailVersion": settings.bedrock_guardrail_version or "DRAFT",
        }

    for round_num in range(MAX_CONVERSE_ROUNDS):
        try:
            response = client.converse(**request_kwargs)
        except Exception as e:
            logger.exception("Converse failed")
            return {"error": str(e), "agent_name": "parse_order"}
        output = response.get("output") or {}
        msg = output.get("message") or {}
        content = msg.get("content") or []
        stop_reason = output.get("stopReason", "")

        if _has_tool_use(content):
            # Append assistant message and tool results, then send again (no outputConfig for tool rounds).
            messages.append({"role": "assistant", "content": content})
            tool_results = []
            for block in content:
                if "toolUse" not in block:
                    continue
                tu = block["toolUse"]
                tool_id = tu.get("toolUseId", "")
                tool_name = tu.get("name", "")
                tool_input = tu.get("input") or {}
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except Exception:
                        tool_input = {}
                result_text = _run_tool(tool_name, tool_input, customer_id)
                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_id,
                        "content": [{"text": result_text}],
                    }
                })
            messages.append({"role": "user", "content": tool_results})
            request_kwargs["messages"] = messages
            continue

        # No tool use: this is the final response. Use parse_agent_json to strip fences, find last {...}, validate keys.
        text = _extract_text_from_message(content)
        if text and stop_reason != "tool_use":
            try:
                obj = parse_agent_json(
                    text,
                    ["customer_id", "order_items", "total_amount", "items_needing_review", "parsing_notes"],
                    "parse_order",
                )
                order_items = obj.get("order_items") or []
                logger.info(
                    "order_intake_converse: final parse order_items_count=%s keys=%s",
                    len(order_items),
                    list(obj.keys()) if isinstance(obj, dict) else None,
                )
            except ValueError as e:
                return {"error": str(e), "agent_name": "parse_order"}
            return obj

    return {"error": "parse_order: max Converse rounds exceeded", "agent_name": "parse_order"}
