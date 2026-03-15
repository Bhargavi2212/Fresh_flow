"""Agent tools for Customer Intelligence: full history, similar customers, alerts, health."""
import json
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from strands import tool

from backend.services.sync_database import execute_sync, fetch_all_sync, fetch_one_sync, fetch_val_sync
from backend.services.websocket_manager import get_ws_manager


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
def get_customer_full_history(customer_id: str) -> str:
    """
    Get complete ordering history for a customer (all orders, not limited). Use for trend
    analysis: frequency, value trends, most_ordered_products, recent_orders. Required for
    Customer Intelligence Agent pattern analysis.

    Args:
        customer_id: The customer's ID.

    Returns:
        JSON with total_order_count, first_order_date, orders_last_7/30/90_days,
        avg_order_value_30d/90d, value_trend_direction, most_ordered_products (top 15),
        recent_orders (last 20), days_since_last_order, typical_order_frequency_per_week.
    """
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return json.dumps({"error": "customer_id required"})

    cust = fetch_one_sync("SELECT customer_id, name FROM customers WHERE customer_id = $1", customer_id)
    if not cust:
        return json.dumps({"error": "Customer not found"})

    # All orders for this customer (no limit)
    orders = fetch_all_sync(
        """SELECT order_id, created_at, total_amount FROM orders
           WHERE customer_id = $1 ORDER BY created_at ASC""",
        customer_id,
    )
    total_order_count = len(orders)
    if total_order_count == 0:
        first_order_date = None
        orders_last_7 = orders_last_30 = orders_last_90 = 0
        avg_30d = avg_90d = 0.0
        value_trend_direction = "stable"
        most_ordered_products = []
        recent_orders = []
        days_since_last_order = None
        typical_order_frequency_per_week = 0.0
    else:
        now = datetime.now(timezone.utc)
        first_ts = orders[0]["created_at"]
        last_ts = orders[-1]["created_at"]
        first_order_date = first_ts.isoformat() if hasattr(first_ts, "isoformat") else str(first_ts)
        last_order_dt = last_ts.replace(tzinfo=timezone.utc) if getattr(last_ts, "tzinfo", None) is None and hasattr(last_ts, "replace") else last_ts
        try:
            days_since_last_order = (now - last_order_dt).days
        except TypeError:
            days_since_last_order = None

        # Count orders in windows (compare created_at to now)
        def _parse_dt(r):
            ts = r["created_at"]
            if getattr(ts, "tzinfo", None) is None and hasattr(ts, "replace"):
                ts = ts.replace(tzinfo=timezone.utc)
            return ts

        orders_last_7 = sum(1 for o in orders if (now - _parse_dt(o)).days <= 7)
        orders_last_30 = sum(1 for o in orders if (now - _parse_dt(o)).days <= 30)
        orders_last_90 = sum(1 for o in orders if (now - _parse_dt(o)).days <= 90)

        totals_30d = [float(o["total_amount"] or 0) for o in orders if (now - _parse_dt(o)).days <= 30]
        totals_60d_31d = [float(o["total_amount"] or 0) for o in orders if 30 < (now - _parse_dt(o)).days <= 90]
        avg_30d = sum(totals_30d) / len(totals_30d) if totals_30d else 0.0
        avg_90d_list = [float(o["total_amount"] or 0) for o in orders if (now - _parse_dt(o)).days <= 90]
        avg_90d = sum(avg_90d_list) / len(avg_90d_list) if avg_90d_list else 0.0
        prev_30d_avg = sum(totals_60d_31d) / len(totals_60d_31d) if totals_60d_31d else avg_30d
        if prev_30d_avg and avg_30d > prev_30d_avg * 1.05:
            value_trend_direction = "increasing"
        elif prev_30d_avg and avg_30d < prev_30d_avg * 0.95:
            value_trend_direction = "declining"
        else:
            value_trend_direction = "stable"

        # Most ordered products (top 15 by frequency with quantities)
        sku_counts: Counter[str] = Counter()
        sku_qty: dict[str, float] = {}
        for o in orders:
            items = fetch_all_sync(
                "SELECT sku_id, quantity FROM order_items WHERE order_id = $1",
                o["order_id"],
            )
            for r in items:
                sku_id = r["sku_id"]
                q = float(r["quantity"] or 0)
                sku_counts[sku_id] += 1
                sku_qty[sku_id] = sku_qty.get(sku_id, 0) + q
        most_ordered_products = []
        for sku_id, count in sku_counts.most_common(15):
            name_row = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
            most_ordered_products.append({
                "sku_id": sku_id,
                "name": name_row["name"] if name_row else sku_id,
                "order_count": count,
                "total_quantity": round(sku_qty.get(sku_id, 0), 2),
            })

        # Recent orders (last 20 with date, items, total)
        recent_orders = []
        for o in list(orders)[-20:][::-1]:
            items = fetch_all_sync(
                """SELECT oi.sku_id, p.name, oi.quantity
                   FROM order_items oi JOIN products p ON p.sku_id = oi.sku_id
                   WHERE oi.order_id = $1""",
                o["order_id"],
            )
            item_list = [
                {"sku_id": r["sku_id"], "name": r["name"], "quantity": float(r["quantity"] or 0)}
                for r in items
            ]
            recent_orders.append({
                "order_id": o["order_id"],
                "date": _serialize(o["created_at"]),
                "items": item_list,
                "total": float(o["total_amount"] or 0),
            })

        # Typical order frequency per week
        if first_ts and last_ts and total_order_count:
            span_days = (last_ts - first_ts).days if hasattr(last_ts - first_ts, "days") else 1
            if span_days <= 0:
                span_days = 1
            typical_order_frequency_per_week = round((total_order_count * 7.0) / span_days, 2)
        else:
            typical_order_frequency_per_week = 0.0

    out = {
        "total_order_count": total_order_count,
        "first_order_date": first_order_date,
        "orders_last_7_days": orders_last_7,
        "orders_last_30_days": orders_last_30,
        "orders_last_90_days": orders_last_90,
        "avg_order_value_30d": round(avg_30d, 2) if total_order_count else 0.0,
        "avg_order_value_90d": round(avg_90d, 2) if total_order_count else 0.0,
        "value_trend_direction": value_trend_direction,
        "most_ordered_products": most_ordered_products,
        "recent_orders": recent_orders,
        "days_since_last_order": days_since_last_order,
        "typical_order_frequency_per_week": typical_order_frequency_per_week,
    }
    return json.dumps(_serialize(out))


@tool
def get_similar_customers(customer_id: str) -> str:
    """
    Find peers: same customer type and active account_health. Returns peer stats and
    commonly_ordered_products_by_peers (products ordered by at least 30% of peers) plus
    products_this_customer_doesnt_order for upsell targeting.

    Args:
        customer_id: The customer's ID.

    Returns:
        JSON with peer_count, peer_avg_order_value, peer_avg_frequency,
        commonly_ordered_products_by_peers (top 20), products_this_customer_doesnt_order.
    """
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return json.dumps({"error": "customer_id required"})

    cust = fetch_one_sync("SELECT customer_id, type FROM customers WHERE customer_id = $1", customer_id)
    if not cust:
        return json.dumps({"error": "Customer not found"})
    ctype = (cust["type"] or "").strip() or "casual"
    # Peers: same type, active account_health (exclude self)
    peers = fetch_all_sync(
        """SELECT customer_id FROM customers
           WHERE type = $1 AND account_health = 'active' AND customer_id != $2""",
        ctype,
        customer_id,
    )
    peer_ids = [r["customer_id"] for r in peers]
    peer_count = len(peer_ids)
    if peer_count == 0:
        return json.dumps({
            "peer_count": 0,
            "peer_avg_order_value": 0.0,
            "peer_avg_frequency": 0.0,
            "commonly_ordered_products_by_peers": [],
            "products_this_customer_doesnt_order": [],
        })

    # Peer order stats: avg order value and orders per week per peer
    peer_orders = fetch_all_sync(
        """SELECT customer_id, total_amount, created_at FROM orders
           WHERE customer_id = ANY($1::text[])""",
        peer_ids,
    )
    peer_totals: dict[str, list[float]] = {}
    peer_dates: dict[str, list] = {}
    for o in peer_orders:
        cid = o["customer_id"]
        if cid not in peer_totals:
            peer_totals[cid] = []
            peer_dates[cid] = []
        peer_totals[cid].append(float(o["total_amount"] or 0))
        peer_dates[cid].append(o["created_at"])
    avg_order_value_list = [sum(v) / len(v) for v in peer_totals.values() if v]
    peer_avg_order_value = sum(avg_order_value_list) / len(avg_order_value_list) if avg_order_value_list else 0.0
    orders_per_peer = [len(v) for v in peer_totals.values()]
    total_orders_peers = sum(orders_per_peer)
    span_weeks = 1
    for dates in peer_dates.values():
        if len(dates) >= 2:
            span = (max(dates) - min(dates)).days / 7.0
            if span > span_weeks:
                span_weeks = span
    peer_avg_frequency = (total_orders_peers / peer_count) / span_weeks if peer_count and span_weeks else 0.0

    # Products ordered by at least 30% of peers
    peer_order_items = fetch_all_sync(
        """SELECT oi.order_id, oi.sku_id, o.customer_id
           FROM order_items oi
           JOIN orders o ON o.order_id = oi.order_id
           WHERE o.customer_id = ANY($1::text[])""",
        peer_ids,
    )
    peer_sku_count: Counter[str] = Counter()
    for r in peer_order_items:
        peer_sku_count[r["sku_id"]] += 1
    threshold = max(1, int(peer_count * 0.3))
    common_skus = [sku for sku, cnt in peer_sku_count.most_common(20) if cnt >= threshold]
    commonly_ordered_products_by_peers = []
    for sku_id in common_skus[:20]:
        name_row = fetch_one_sync("SELECT name FROM products WHERE sku_id = $1", sku_id)
        commonly_ordered_products_by_peers.append({
            "sku_id": sku_id,
            "name": name_row["name"] if name_row else sku_id,
            "peer_order_count": peer_sku_count[sku_id],
        })

    # Products this customer has never ordered (from common list)
    this_customer_skus = fetch_all_sync(
        """SELECT DISTINCT oi.sku_id FROM order_items oi
           JOIN orders o ON o.order_id = oi.order_id
           WHERE o.customer_id = $1""",
        customer_id,
    )
    ordered_by_customer = {r["sku_id"] for r in this_customer_skus}
    products_this_customer_doesnt_order = [
        p for p in commonly_ordered_products_by_peers
        if p["sku_id"] not in ordered_by_customer
    ]

    out = {
        "peer_count": peer_count,
        "peer_avg_order_value": round(peer_avg_order_value, 2),
        "peer_avg_frequency": round(peer_avg_frequency, 2),
        "commonly_ordered_products_by_peers": commonly_ordered_products_by_peers,
        "products_this_customer_doesnt_order": products_this_customer_doesnt_order,
    }
    return json.dumps(_serialize(out))


@tool
def create_customer_alert(customer_id: str, alert_type: str, description: str, severity: str) -> str:
    """
    Create a customer intelligence alert (churn_risk, upsell, anomaly, growth_signal, milestone).
    Writes to customer_alerts table. Call when the Customer Intelligence Agent identifies
    an actionable insight.

    Args:
        customer_id: The customer's ID.
        alert_type: One of churn_risk, upsell, anomaly, growth_signal, milestone.
        description: Plain English 1-2 sentences for the sales rep.
        severity: low, medium, or high.

    Returns:
        JSON of the created alert (id, customer_id, alert_type, description, severity, created_at).
    """
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return json.dumps({"error": "customer_id required"})
    alert_type = (alert_type or "anomaly")[:50]
    description = (description or "")[:2000]
    severity = (severity or "medium")[:20]

    aid = fetch_val_sync(
        """INSERT INTO customer_alerts (customer_id, alert_type, description, severity)
           VALUES ($1, $2, $3, $4) RETURNING id""",
        customer_id,
        alert_type,
        description,
        severity,
    )
    if aid is None:
        return json.dumps({"error": "Failed to create alert"})
    row = fetch_one_sync(
        "SELECT id, customer_id, alert_type, description, severity, created_at FROM customer_alerts WHERE id = $1",
        aid,
    )
    try:
        cust = fetch_one_sync("SELECT name FROM customers WHERE customer_id = $1", customer_id)
        customer_name = (cust["name"] or "Customer").strip() if cust else "Customer"
        get_ws_manager().broadcast_sync({
            "type": "customer_alert",
            "alert_id": row["id"],
            "customer_name": customer_name,
            "alert_type": row["alert_type"],
            "description": row["description"] or "",
            "severity": row["severity"],
            "timestamp": _serialize(row["created_at"]),
        })
    except Exception:
        pass
    out = {
        "id": row["id"],
        "customer_id": row["customer_id"],
        "alert_type": row["alert_type"],
        "description": row["description"],
        "severity": row["severity"],
        "created_at": _serialize(row["created_at"]),
    }
    return json.dumps(_serialize(out))


@tool
def update_customer_health(customer_id: str, account_health: str) -> str:
    """
    Update a customer's account_health and recompute days_since_last_order. Call after
    analyzing an order to keep the profile current.

    Args:
        customer_id: The customer's ID.
        account_health: New status (e.g. active, at_risk, churning).

    Returns:
        JSON with success and updated fields.
    """
    customer_id = (customer_id or "").strip()
    if not customer_id:
        return json.dumps({"error": "customer_id required"})
    account_health = (account_health or "active")[:20]

    # Recompute days_since_last_order from last order
    last_order = fetch_one_sync(
        "SELECT created_at FROM orders WHERE customer_id = $1 ORDER BY created_at DESC LIMIT 1",
        customer_id,
    )
    days_since = None
    if last_order and last_order["created_at"]:
        ld = last_order["created_at"]
        if hasattr(ld, "date"):
            last_date = ld.date()
        else:
            last_date = ld
        today = date.today()
        days_since = (today - last_date).days

    execute_sync(
        "UPDATE customers SET account_health = $1, days_since_last_order = $2 WHERE customer_id = $3",
        account_health,
        days_since,
        customer_id,
    )
    return json.dumps({"success": True, "customer_id": customer_id, "account_health": account_health, "days_since_last_order": days_since})
