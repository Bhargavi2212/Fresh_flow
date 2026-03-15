"""Agent tool: find product substitutions based on customer preferences and similarity."""
import json
from typing import Any

from strands import tool

from backend.agents.models import embed_text
from backend.services.sync_database import fetch_all_sync, fetch_one_sync


def _serialize(obj: Any) -> Any:
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    return obj


@tool
def find_substitutions(sku_id: str, customer_id: str) -> str:
    """
    Find substitution options for a product given customer preferences. First checks
    customer_preferences for explicit substitution or exclusion rules. If no rule,
    returns up to 3 alternatives from the same subcategory (excluding customer
    exclusions), ranked by embedding similarity to the original product. Use for
    out-of-stock or partial-fulfillment suggestions.

    Args:
        sku_id: The product SKU we need a substitute for.
        customer_id: Customer ID for preference and exclusion rules.

    Returns:
        JSON string: has_explicit_preference (bool), substitutions (array of
        {sku_id, name, reason: "customer preference" | "same category alternative"}),
        excluded_products (SKUs the customer has excluded).
    """
    product = fetch_one_sync(
        "SELECT sku_id, name, subcategory FROM products WHERE sku_id = $1",
        sku_id,
    )
    if not product:
        return json.dumps({"error": "Product not found", "has_explicit_preference": False, "substitutions": [], "excluded_products": []})

    # Exclusions: SKUs this customer must not receive
    excl_rows = fetch_all_sync(
        """SELECT product_sku FROM customer_preferences
           WHERE customer_id = $1 AND preference_type = 'exclusion' AND product_sku IS NOT NULL""",
        customer_id,
    )
    excluded_skus = {r["product_sku"] for r in excl_rows}

    # Substitution rules where product_sku = our sku (explicit preferred substitute)
    sub_rows = fetch_all_sync(
        """SELECT substitute_sku FROM customer_preferences
           WHERE customer_id = $1 AND preference_type = 'substitution' AND product_sku = $2 AND substitute_sku IS NOT NULL""",
        customer_id, sku_id,
    )
    explicit_subs = []
    for r in sub_rows:
        sub_row = fetch_one_sync("SELECT sku_id, name FROM products WHERE sku_id = $1", r["substitute_sku"])
        if sub_row and sub_row["sku_id"] not in excluded_skus:
            explicit_subs.append({
                "sku_id": sub_row["sku_id"],
                "name": sub_row["name"],
                "reason": "customer preference",
            })

    if explicit_subs:
        return json.dumps(_serialize({
            "has_explicit_preference": True,
            "substitutions": explicit_subs[:5],
            "excluded_products": list(excluded_skus),
        }))

    # No explicit rule: same subcategory, exclude exclusions, rank by similarity
    subcategory = product.get("subcategory")
    if not subcategory:
        return json.dumps(_serialize({
            "has_explicit_preference": False,
            "substitutions": [],
            "excluded_products": list(excluded_skus),
        }))

    # Get original product embedding for similarity sort
    orig_row = fetch_one_sync("SELECT embedding FROM products WHERE sku_id = $1", sku_id)
    exclude_list = list(excluded_skus | {sku_id})
    if not orig_row or not orig_row.get("embedding"):
        # No embedding: get same subcategory, filter excluded, return first 3
        same_sub = fetch_all_sync(
            """SELECT sku_id, name FROM products
               WHERE subcategory = $1 AND status = 'active' AND sku_id != $2""",
            subcategory, sku_id,
        )
        same_sub = [r for r in same_sub if r["sku_id"] not in excluded_skus][:3]
        subs = [{"sku_id": r["sku_id"], "name": r["name"], "reason": "same category alternative"} for r in same_sub]
        return json.dumps(_serialize({"has_explicit_preference": False, "substitutions": subs, "excluded_products": list(excluded_skus)}))

    vec = orig_row["embedding"]
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    vec_str = "[" + ",".join(str(float(x)) for x in vec) + "]"
    # Same subcategory, not self, not excluded; order by similarity; limit 5 then filter
    similar = fetch_all_sync(
        """SELECT sku_id, name FROM products
           WHERE subcategory = $2 AND sku_id != $3 AND status = 'active' AND embedding IS NOT NULL
           ORDER BY embedding <=> $1::vector LIMIT 10""",
        vec_str, subcategory, sku_id,
    )
    similar = [r for r in similar if r["sku_id"] not in excluded_skus][:3]
    subs = [{"sku_id": r["sku_id"], "name": r["name"], "reason": "same category alternative"} for r in similar]
    return json.dumps(_serialize({
        "has_explicit_preference": False,
        "substitutions": subs,
        "excluded_products": list(excluded_skus),
    }))
