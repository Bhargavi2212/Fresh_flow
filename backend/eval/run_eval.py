"""
Phase 5 evaluation: run test_orders.json through the pipeline, compare SKU/quantity/status.
Target: 85%+ SKU accuracy. Run: python -m backend.eval.run_eval
"""
import json
import os
import time
from pathlib import Path

from backend.agents.orchestrator import run_orchestrator
from backend.services.sync_database import fetch_all_sync, fetch_one_sync


def _load_tests() -> list[dict]:
    path = Path(__file__).resolve().parent / "test_orders.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _build_product_map() -> dict[str, str]:
    """Map product name or alias (lowercase) -> sku_id. Name takes precedence, then aliases."""
    rows = fetch_all_sync("SELECT sku_id, name, aliases FROM products WHERE status = 'active'")
    name_to_sku: dict[str, str] = {}
    for r in rows:
        sku = r["sku_id"]
        name = (r["name"] or "").strip().lower()
        if name and name not in name_to_sku:
            name_to_sku[name] = sku
        for a in (r["aliases"] or []):
            key = (a or "").strip().lower()
            if key and key not in name_to_sku:
                name_to_sku[key] = sku
    return name_to_sku


def _resolve_product(product_key: str, name_to_sku: dict[str, str]) -> str | None:
    key = (product_key or "").strip().lower()
    if not key:
        return None
    if key in name_to_sku:
        return name_to_sku[key]
    for k, sku in name_to_sku.items():
        if key in k or k in key:
            return sku
    return None


def _quantity_within_tolerance(actual: float, expected: float, tolerance_pct: float = 10.0) -> bool:
    if expected == 0:
        return actual == 0
    pct = abs(actual - expected) / expected * 100
    return pct <= tolerance_pct


def run_eval() -> dict:
    tests = _load_tests()
    name_to_sku = _build_product_map()
    results: list[dict] = []
    total_expected_items = 0
    total_sku_matches = 0
    total_quantity_matches = 0
    status_correct = 0
    total_time_sec = 0.0

    for t in tests:
        test_id = t.get("test_id", "?")
        customer_id = t.get("customer_id", "")
        raw_message = t.get("raw_message", "")
        expected_items = t.get("expected_items") or []
        expected_status = t.get("expected_status", "confirmed")
        start = time.perf_counter()
        try:
            _, summary = run_orchestrator(raw_message, customer_id, "eval", "")
        except Exception as e:
            summary = {"order_id": "", "status": "needs_review"}
            results.append({
                "test_id": test_id,
                "pass": False,
                "error": str(e),
                "time_sec": time.perf_counter() - start,
            })
            total_time_sec += time.perf_counter() - start
            if summary.get("status") == expected_status:
                status_correct += 1
            continue
        elapsed = time.perf_counter() - start
        total_time_sec += elapsed
        order_id = (summary.get("order_id") or "").strip()
        actual_status = summary.get("status", "")

        actual_items: list[dict] = []
        if order_id and order_id != "pending":
            rows = fetch_all_sync(
                "SELECT sku_id, quantity, line_total FROM order_items WHERE order_id = $1",
                order_id,
            )
            for r in rows:
                actual_items.append({
                    "sku_id": r["sku_id"],
                    "quantity": float(r["quantity"] or 0),
                })

        sku_matches = 0
        qty_matches = 0
        for exp in expected_items:
            product_key = exp.get("product") or exp.get("product_name_or_alias") or ""
            exp_qty = float(exp.get("quantity") or 0)
            expected_sku = _resolve_product(product_key, name_to_sku)
            if not expected_sku:
                continue
            total_expected_items += 1
            for act in actual_items:
                if act["sku_id"] == expected_sku:
                    sku_matches += 1
                    if _quantity_within_tolerance(act["quantity"], exp_qty):
                        qty_matches += 1
                    break

        total_sku_matches += sku_matches
        total_quantity_matches += qty_matches
        if actual_status == expected_status:
            status_correct += 1

        # For "usual" tests expected_items may be empty; pass if status matches
        if not expected_items:
            pass_test = actual_status == expected_status
        else:
            pass_test = (
                sku_matches == len(expected_items)
                and _quantity_within_tolerance(sku_matches, len(expected_items), 0)
                and actual_status == expected_status
            )
        results.append({
            "test_id": test_id,
            "pass": pass_test,
            "status_ok": actual_status == expected_status,
            "sku_matches": sku_matches,
            "expected_items": len(expected_items),
            "actual_items": len(actual_items),
            "time_sec": round(elapsed, 2),
        })

    n = len(tests)
    sku_accuracy = (total_sku_matches / total_expected_items * 100) if total_expected_items else 0.0
    qty_accuracy = (total_quantity_matches / total_expected_items * 100) if total_expected_items else 0.0
    status_accuracy = (status_correct / n * 100) if n else 0.0

    report = {
        "total_tests": n,
        "passed": sum(1 for r in results if r.get("pass")),
        "sku_accuracy_pct": round(sku_accuracy, 1),
        "quantity_accuracy_pct": round(qty_accuracy, 1),
        "status_accuracy_pct": round(status_accuracy, 1),
        "total_time_sec": round(total_time_sec, 2),
        "avg_time_sec": round(total_time_sec / n, 2) if n else 0,
        "results": results,
    }
    return report


def main() -> None:
    os.chdir(Path(__file__).resolve().parents[2])
    report = run_eval()
    print("=== Phase 5 Eval Report ===")
    print(f"Tests: {report['total_tests']} total, {report['passed']} passed")
    print(f"SKU accuracy: {report['sku_accuracy_pct']}% (target 85%+)")
    print(f"Quantity accuracy (within 10%): {report['quantity_accuracy_pct']}%")
    print(f"Status accuracy: {report['status_accuracy_pct']}%")
    print(f"Total time: {report['total_time_sec']}s, avg: {report['avg_time_sec']}s per test")
    print("\nPer-test:")
    for r in report["results"]:
        status = "PASS" if r.get("pass") else "FAIL"
        print(f"  {r['test_id']}: {status} (sku {r.get('sku_matches', 0)}/{r.get('expected_items', 0)}, {r.get('time_sec', 0)}s)")
    if report["sku_accuracy_pct"] >= 85:
        print("\nTarget met: SKU accuracy >= 85%")
    else:
        print(f"\nTarget not met: SKU accuracy {report['sku_accuracy_pct']}% < 85%")


if __name__ == "__main__":
    main()
