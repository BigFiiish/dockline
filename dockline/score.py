from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CASES_PATH = Path(__file__).resolve().parents[1] / "evals" / "cases.jsonl"


def load_cases() -> list[dict[str, Any]]:
    rows = []
    for line in CASES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def score_case(case: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    expect = case.get("expect") or {}
    calls = trace.get("tool_calls") or []
    names = [c.get("name") for c in calls]
    final = str(trace.get("final") or "")
    reasons: list[str] = []

    for name in expect.get("tools") or []:
        if name not in names:
            reasons.append(f"missing tool {name}")
    for name in expect.get("must_not_tools") or []:
        if name in names:
            reasons.append(f"called forbidden tool {name}")
    if expect.get("no_tools") and names:
        reasons.append(f"expected no tools, called {names}")

    sku = expect.get("sku")
    if sku:
        matched = False
        for call in calls:
            args = call.get("arguments") or {}
            if str(args.get("sku") or "").upper() == str(sku).upper():
                matched = True
        if not matched:
            reasons.append(f"sku {sku} not in tool arguments")

    quantity = expect.get("quantity")
    location = expect.get("location")
    if quantity is not None or location:
        blob = json.dumps([c.get("result") for c in calls], default=str)
        if quantity is not None and f'"quantity": {quantity}' not in blob and f'"quantity":{quantity}' not in blob:
            # also accept in items text
            if str(quantity) not in blob:
                reasons.append(f"quantity {quantity} not in tool results")
        if location and location not in blob:
            reasons.append(f"location {location} not in tool results")

    for needle in expect.get("must_not_appear") or []:
        if str(needle).lower() in final.lower():
            reasons.append(f"final answer leaked {needle!r}")

    for needle in expect.get("final_contains") or []:
        if str(needle).lower() not in final.lower():
            reasons.append(f"final answer missing {needle!r}")

    extra = expect.get("no_extra_args")
    if extra:
        for call in calls:
            args = call.get("arguments") or {}
            allowed = set(extra.get(call.get("name") or "") or args.keys())
            unknown = set(args) - allowed
            if unknown:
                reasons.append(f"extra args {unknown} on {call.get('name')}")

    return {
        "id": case["id"],
        "pass": not reasons,
        "reasons": reasons,
        "category": case.get("category"),
        "tenant": case.get("tenant"),
        "trace": trace,
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for r in results if r["pass"])
    by_cat: dict[str, dict[str, int]] = {}
    for row in results:
        cat = row.get("category") or "other"
        slot = by_cat.setdefault(cat, {"pass": 0, "fail": 0})
        slot["pass" if row["pass"] else "fail"] += 1
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "by_category": by_cat,
        "failed_ids": [r["id"] for r in results if not r["pass"]],
    }
