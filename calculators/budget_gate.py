"""Stage precondition and channel budget gate evaluator (About-Intelligence/OpenCMO pattern)."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from calculators import (
    format_money,
    normalize_currency,
    ok_result,
    resolve_amount,
    to_float,
    unknown_result,
    usd_equivalent_floor,
)


def evaluate_budget_gate(
    channel: str,
    tracking_verified: Any,
    site_load_sec: Any,
    payback_months: Any,
    max_payback_months: Any = 3.0,
    monthly_conversions: Any = 0,
    monthly_budget_usd: Any = 0,
    retention_margin_ready: Any = True,
    monthly_budget: Any = None,
    currency: str = "USD",
    min_paid_budget: Any = None,
) -> dict[str, Any]:
    """Deterministically decide whether a marketing channel is unlocked or blocked by hard preconditions."""
    cur = normalize_currency(currency)
    load_s = to_float(site_load_sec)
    pb = to_float(payback_months)
    max_pb = to_float(max_payback_months)
    convs = to_float(monthly_conversions)
    budget = resolve_amount(monthly_budget, monthly_budget_usd)

    trace = (
        "require tracking_verified==True; site_load_sec < 4.0; payback_months <= max_payback_months; "
        "paid channels require monthly_budget >= min_paid_budget; automated bidding requires monthly_conversions >= 30"
    )

    if tracking_verified is None or load_s is None or budget is None or max_pb is None:
        missing = []
        if tracking_verified is None:
            missing.append("tracking_verified")
        if load_s is None:
            missing.append("site_load_sec")
        if budget is None:
            missing.append("monthly_budget_usd" if cur == "USD" else "monthly_budget")
        if max_pb is None:
            missing.append("max_payback_months")
        return unknown_result(missing, trace, {"currency": cur})

    assert load_s is not None and budget is not None and max_pb is not None
    blockers: list[str] = []
    warnings: list[str] = []

    if tracking_verified is not True:
        blockers.append("tracking_unverified: fix analytics/conversion events before scaling")
    if load_s >= 4.0:
        blockers.append(f"site_load_too_slow: {load_s}s >= 4.0s threshold")

    floor_val = to_float(min_paid_budget)
    if floor_val is None:
        floor_val = usd_equivalent_floor(300.0, cur)

    if channel in ("paid_search", "paid_social"):
        if pb is None:
            blockers.append("payback_months_unknown: verify unit economics before paid spend")
        elif pb > max_pb:
            blockers.append(f"payback_too_long: {pb}m > {max_pb}m limit")
        if floor_val is not None and budget < floor_val:
            blockers.append(
                f"budget_below_learning_floor: {format_money(budget, cur)} < {format_money(floor_val, cur)}/mo minimum"
            )
        if not retention_margin_ready:
            warnings.append("retention_not_ready: prioritize lifecycle retention flows before scaling cold paid")
        if convs is not None and convs < 30:
            warnings.append(f"low_conversion_volume: {int(convs)}/mo < 30; block automated Target ROAS/CPA bidding")

    return ok_result(
        {
            "currency": cur,
            "channel": channel,
            "learning_floor": floor_val,
            "unlocked": len(blockers) == 0,
            "blockers": blockers,
            "warnings": warnings,
            "bidding_mode": "manual_or_max_clicks" if (convs is None or convs < 30) else "conversion_bidding_eligible",
        },
        trace,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate stage preconditions and budget gate.")
    parser.add_argument("--input", required=True, help="JSON input file path")
    args = parser.parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out = evaluate_budget_gate(**payload)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
