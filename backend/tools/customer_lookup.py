"""Agent tools: customer order history and preferences."""
import json
from collections import Counter
from decimal import Decimal
from statistics import median
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


@tool
def get_usual_order(customer_id: str) -> str:
    """
    Get the customer's "usual" order: items that appear in 40%+ of their orders over the last 90 days,
    with median quantity per item. Use when the customer says "the usual" or "my regular order".
    Return items sorted by frequency (most often ordered first). Use these items directly with confidence 0.95.

    Args:
        customer_id: The customer's ID.

    Returns:
        JSON string with: items (list of {sku_id, product_name, median_quantity, order_count, frequency_pct}),
        total_orders_in_window (number of orders in last 90 days).
    """
    orders = fetch_all_sync(
        """SELECT order_id FROM orders
           WHERE customer_id = $1 AND created_at >= (CURRENT_DATE - INTERVAL '90 days')
           ORDER BY created_at DESC""",
        customer_id,
    )
    total_orders = len(orders)
    if total_orders == 0:
        return json.dumps({"items": [], "total_orders_in_window": 0})

    # sku_id -> list of quantities (one per order where this sku appeared)
    sku_quantities: dict[str, list[float]] = {}
    for o in orders:
        items = fetch_all_sync(
            """SELECT oi.sku_id, oi.quantity FROM order_items oi WHERE oi.order_id = $1""",
            o["order_id"],
        )
        for r in items:
            sku = r["sku_id"]
            qty = float(r["quantity"]) if r["quantity"] else 0
            if sku not in sku_quantities:
                sku_quantities[sku] = []
            sku_quantities[sku].append(qty)

    # Include only items in >= 40% of orders; median quantity; sort by frequency desc
    threshold = max(1, int(0.4 * total_orders))
    result_items = []
    for sku_id, quantities in sku_quantities.items():
        order_count = len(quantities)
        if order_count < threshold:
            continue
        med_qty = median(quantities)
        name_row = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
        product_name = name_row["name"] if name_row else sku_id
        result_items.append({
            "sku_id": sku_id,
            "product_name": product_name,
            "median_quantity": round(med_qty, 2),
            "order_count": order_count,
            "frequency_pct": round(100.0 * order_count / total_orders, 1),
        })
    result_items.sort(key=lambda x: x["order_count"], reverse=True)

    out = {"items": result_items, "total_orders_in_window": total_orders}
    return json.dumps(_serialize(out))
