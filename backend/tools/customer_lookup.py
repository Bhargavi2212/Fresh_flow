"""Agent tools: customer order history and preferences."""
import json
from collections import Counter
from decimal import Decimal
from typing import Any

from strands import tool

from backend.services.sync_database import fetch_all_sync, fetch_one_sync


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


@tool
def get_customer_history(customer_id: str, limit: int = 10) -> str:
    """
    Get a customer's order history for resolving "the usual" or "same as last time".
    Returns recent orders with items, plus most_frequently_ordered_items (top 10 SKUs),
    average_order_value, and typical_order_frequency (orders per week). Call this when
    the customer says "the usual", "regular order", or "same as last time".

    Args:
        customer_id: The customer's ID.
        limit: Maximum number of recent orders to include (default 10).

    Returns:
        JSON string with: recent_orders (list of {order_id, created_at, items: [{sku_id, name, quantity}], total_amount}),
        most_frequently_ordered_items (list of {sku_id, name, order_count}), average_order_value,
        typical_order_frequency (orders per week from history).
    """
    cust = fetch_one_sync(
        "SELECT customer_id, name, avg_order_value FROM customers WHERE customer_id = $1",
        customer_id,
    )
    if not cust:
        return json.dumps({"error": "Customer not found", "recent_orders": [], "most_frequently_ordered_items": []})

    orders = fetch_all_sync(
        """SELECT o.order_id, o.created_at, o.total_amount
           FROM orders o WHERE o.customer_id = $1 ORDER BY o.created_at DESC LIMIT $2""",
        customer_id, limit,
    )
    recent = []
    all_sku_counts: Counter[str] = Counter()
    total_val = 0.0
    for o in orders:
        items = fetch_all_sync(
            """SELECT oi.sku_id, p.name, oi.quantity
               FROM order_items oi JOIN products p ON p.sku_id = oi.sku_id
               WHERE oi.order_id = $1""",
            o["order_id"],
        )
        item_list = [
            {"sku_id": r["sku_id"], "name": r["name"], "quantity": float(r["quantity"]) if r["quantity"] else 0}
            for r in items
        ]
        for r in items:
            all_sku_counts[r["sku_id"]] += 1
        total_val += float(o["total_amount"] or 0)
        recent.append({
            "order_id": o["order_id"],
            "created_at": _serialize(o["created_at"]),
            "items": item_list,
            "total_amount": float(o["total_amount"] or 0),
        })

    # Most frequently ordered: top 10 SKUs
    mfo = []
    for sku_id, count in all_sku_counts.most_common(10):
        name_row = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
        mfo.append({"sku_id": sku_id, "name": name_row["name"] if name_row else sku_id, "order_count": count})

    # Orders per week: from all-time order count
    all_time = fetch_one_sync(
        "SELECT COUNT(*)::int AS c, MIN(created_at) AS first_at, MAX(created_at) AS last_at FROM orders WHERE customer_id = $1",
        customer_id,
    )
    orders_per_week = 0.0
    if all_time and all_time["c"] and all_time["first_at"] and all_time["last_at"]:
        days = (all_time["last_at"] - all_time["first_at"]).days or 1
        orders_per_week = (all_time["c"] * 7.0) / days

    out = {
        "recent_orders": recent,
        "most_frequently_ordered_items": mfo,
        "average_order_value": round(total_val / len(recent), 2) if recent else float(cust.get("avg_order_value") or 0),
        "typical_order_frequency": round(orders_per_week, 2),
    }
    return json.dumps(_serialize(out))


@tool
def get_customer_preferences(customer_id: str) -> str:
    """
    Get a customer's product preferences: substitution rules, exclusions, and profile.
    Use when the customer makes a vague request (e.g. "whatever white fish you got")
    or when suggesting substitutions for out-of-stock items.

    Args:
        customer_id: The customer's ID.

    Returns:
        JSON string with: profile (name, type, delivery_days), preferences (list of
        {preference_type, description, product_sku, substitute_sku}). preference_type
        can be 'substitution', 'exclusion', 'preference', 'always_organic'.
    """
    cust = fetch_one_sync(
        "SELECT customer_id, name, type, delivery_days FROM customers WHERE customer_id = $1",
        customer_id,
    )
    if not cust:
        return json.dumps({"error": "Customer not found", "profile": {}, "preferences": []})

    prefs = fetch_all_sync(
        """SELECT preference_type, description, product_sku, substitute_sku
           FROM customer_preferences WHERE customer_id = $1""",
        customer_id,
    )
    profile = {
        "name": cust["name"],
        "type": cust["type"],
        "delivery_days": list(cust["delivery_days"]) if cust.get("delivery_days") else [],
    }
    preferences = [
        {
            "preference_type": r["preference_type"],
            "description": r["description"],
            "product_sku": r["product_sku"],
            "substitute_sku": r["substitute_sku"],
        }
        for r in prefs
    ]
    return json.dumps(_serialize({"profile": profile, "preferences": preferences}))
