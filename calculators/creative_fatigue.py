"""Deterministic creative fatigue detection and launch pacing circuit breaker."""

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
    currency_symbol,
    format_money,
    normalize_currency,
    resolve_amount,
    round_money,
    to_float,
    unknown_result,
    usd_equivalent_floor,
)


def detect_creative_fatigue(
    creatives: Any,
    max_frequency: float = 3.2,
    ctr_drop_threshold_pct: float = 20.0,
    cpa_inflation_threshold_pct: float = 25.0,
    currency: str = "USD",
    min_spend_floor: Any = None,
) -> dict[str, Any]:
    """Detect fatigued ad creatives breaching frequency, CTR decay, or CPA inflation thresholds in any currency."""
    cur = normalize_currency(currency)
    spend_floor = to_float(min_spend_floor)
    if spend_floor is None:
        spend_floor = usd_equivalent_floor(75.0, cur)
    trace = (
        "enough_volume = impressions >= 2000 or (spend_floor is not None and spend >= spend_floor); "
        "ctr_drop_pct = ((peak_ctr - current_ctr) / peak_ctr) * 100.0; "
        "cpa_inflation_pct = ((curr_cpa - base_cpa) / base_cpa) * 100.0; "
        "fatigued if enough_volume and ((freq >= max_freq and ctr_drop_pct >= ctr_thresh) or ctr_drop_pct >= 35.0 or (freq >= max_freq and cpa_inflation_pct >= cpa_thresh))"
    )

    if not isinstance(creatives, list) or len(creatives) == 0:
        return unknown_result(["creatives"], trace, {"currency": cur})

    fatigued: list[dict[str, Any]] = []
    watch: list[dict[str, Any]] = []
    healthy: list[dict[str, Any]] = []

    max_freq = float(max_frequency)
    ctr_thresh = float(ctr_drop_threshold_pct)
    cpa_thresh = float(cpa_inflation_threshold_pct)

    for item in creatives:
        if not isinstance(item, dict):
            continue

        item_cur = normalize_currency(item.get("currency") or cur)
        item_floor = spend_floor if item_cur == cur else usd_equivalent_floor(75.0, item_cur)
        ad_id = str(item.get("ad_id") or item.get("creative_id") or item.get("campaign_id") or "unknown_ad")
        freq = to_float(item.get("frequency")) or 1.0
        peak_ctr = to_float(item.get("peak_ctr")) or 0.0
        curr_ctr = to_float(item.get("current_ctr")) or 0.0
        base_cpa = resolve_amount(item.get("baseline_cpa"), item.get("baseline_cpa_usd"))
        curr_cpa = resolve_amount(item.get("current_cpa"), item.get("current_cpa_usd"))
        impr = to_float(item.get("impressions")) or 0.0
        spend = resolve_amount(item.get("spend"), item.get("spend_usd")) or 0.0

        if peak_ctr > 0:
            ctr_drop_pct = round(((peak_ctr - curr_ctr) / peak_ctr) * 100.0, 2)
        else:
            ctr_drop_pct = 0.0

        if base_cpa is not None and curr_cpa is not None and base_cpa > 0:
            cpa_inflation_pct = round(((curr_cpa - base_cpa) / base_cpa) * 100.0, 2)
        else:
            cpa_inflation_pct = 0.0

        enough_volume = bool(impr >= 2000 or (item_floor is not None and spend >= item_floor))

        record = {
            "ad_id": ad_id,
            "currency": item_cur,
            "frequency": round(freq, 2),
            "peak_ctr": peak_ctr,
            "current_ctr": curr_ctr,
            "ctr_drop_pct": ctr_drop_pct,
            "cpa_inflation_pct": cpa_inflation_pct,
            "impressions": int(impr),
            "spend": round_money(spend, item_cur),
            "spend_formatted": format_money(spend, item_cur),
            "spend_usd": round(spend, 2),
            "enough_volume": enough_volume,
        }

        is_fatigued = False
        is_watch = False

        if enough_volume:
            if (
                (freq >= max_freq and ctr_drop_pct >= ctr_thresh)
                or ctr_drop_pct >= 35.0
                or (freq >= max_freq and cpa_inflation_pct >= cpa_thresh)
            ):
                is_fatigued = True
            elif (freq >= max_freq * 0.85) or (ctr_drop_pct >= ctr_thresh):
                is_watch = True

        if is_fatigued:
            record["status"] = "fatigued"
            fatigued.append(record)
        elif is_watch:
            record["status"] = "watch"
            watch.append(record)
        else:
            record["status"] = "healthy"
            healthy.append(record)

    return {
        "status": "ok",
        "currency": cur,
        "currency_symbol": currency_symbol(cur),
        "fatigued_count": len(fatigued),
        "watch_count": len(watch),
        "healthy_count": len(healthy),
        "fatigued_creatives": fatigued,
        "watch_creatives": watch,
        "healthy_creatives": healthy,
        "recommended_hook_rotations": len(fatigued),
    }


def compute_launch_pacing_guard(
    launch_budget_usd: Any = None,
    days_elapsed: Any = None,
    total_launch_days: Any = None,
    spend_to_date_usd: Any = None,
    revenue_to_date_usd: Any = None,
    gross_margin_pct: Any = None,
    target_mer: Any = 2.5,
    launch_budget: Any = None,
    spend_to_date: Any = None,
    revenue_to_date: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Circuit breaker and budget pacing evaluator for campaign and product launches in any currency."""
    cur = normalize_currency(currency)
    trace = (
        "expected_spend = budget * min(1.0, days_elapsed / total_launch_days); "
        "pace_variance_pct = ((spend - expected_spend) / expected_spend) * 100.0; "
        "observed_mer = revenue / spend; "
        "gross_profit = revenue * (gross_margin_pct / 100.0); "
        "net_contribution = gross_profit - spend"
    )

    budget = resolve_amount(launch_budget, launch_budget_usd)
    d_elapsed = to_float(days_elapsed)
    d_total = to_float(total_launch_days)
    spend = resolve_amount(spend_to_date, spend_to_date_usd)
    rev = resolve_amount(revenue_to_date, revenue_to_date_usd)
    gm = to_float(gross_margin_pct)
    t_mer = to_float(target_mer) if target_mer is not None else 2.5

    missing: list[str] = []
    if budget is None:
        missing.append("launch_budget_usd" if cur == "USD" else "launch_budget")
    if d_elapsed is None:
        missing.append("days_elapsed")
    if d_total is None:
        missing.append("total_launch_days")
    if spend is None:
        missing.append("spend_to_date_usd" if cur == "USD" else "spend_to_date")
    if rev is None:
        missing.append("revenue_to_date_usd" if cur == "USD" else "revenue_to_date")
    if gm is None:
        missing.append("gross_margin_pct")

    if missing:
        return unknown_result(missing, trace, {"currency": cur})

    assert (
        budget is not None
        and d_elapsed is not None
        and d_total is not None
        and spend is not None
        and rev is not None
        and gm is not None
    )

    if d_total <= 0 or d_elapsed < 0 or budget < 0 or spend < 0 or rev < 0 or gm <= 0 or gm > 100:
        raise ValueError(
            "Invalid inputs: total_launch_days > 0, days_elapsed >= 0, launch_budget >= 0, spend_to_date >= 0, revenue_to_date >= 0, 0 < gross_margin_pct <= 100 required"
        )

    expected_raw = budget * min(1.0, d_elapsed / d_total)
    expected_spend_to_date_usd = round(expected_raw, 2)
    if expected_raw > 0:
        pace_variance_pct = round(((spend - expected_raw) / expected_raw) * 100.0, 2)
    else:
        pace_variance_pct = 0.0

    observed_mer: float | str = round(rev / spend, 2) if spend > 0 else "unknown"
    gross_profit_raw = rev * (gm / 100.0)
    net_contribution_raw = gross_profit_raw - spend
    gross_profit_to_date_usd = round(gross_profit_raw, 2)
    net_contribution_usd = round(net_contribution_raw, 2)

    if isinstance(observed_mer, float) and observed_mer < 1.0 and d_elapsed >= 2:
        action = "pause_unprofitable_channels"
    elif isinstance(observed_mer, float) and t_mer is not None and observed_mer < t_mer and pace_variance_pct > 20.0:
        action = "throttle_spend"
    else:
        action = "hold_or_scale"

    return {
        "status": "ok",
        "currency": cur,
        "currency_symbol": currency_symbol(cur),
        "expected_spend_to_date": round_money(expected_raw, cur),
        "expected_spend_to_date_formatted": format_money(expected_raw, cur),
        "expected_spend_to_date_usd": expected_spend_to_date_usd,
        "pace_variance_pct": pace_variance_pct,
        "observed_mer": observed_mer,
        "gross_profit_to_date": round_money(gross_profit_raw, cur),
        "gross_profit_to_date_formatted": format_money(gross_profit_raw, cur),
        "gross_profit_to_date_usd": gross_profit_to_date_usd,
        "net_contribution": round_money(net_contribution_raw, cur),
        "net_contribution_formatted": format_money(net_contribution_raw, cur),
        "net_contribution_usd": net_contribution_usd,
        "circuit_breaker_action": action,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect creative fatigue and compute launch pacing guardrails in any currency."
    )
    parser.add_argument(
        "--mode",
        choices=["fatigue", "launch_pacing"],
        default="fatigue",
    )
    parser.add_argument("--currency", default="USD", help="ISO-4217 currency code (e.g. USD, KES, IDR, MXN)")
    parser.add_argument("--input", help="JSON input file path")

    # Arguments for fatigue
    parser.add_argument("--max-frequency", type=float, default=3.2)
    parser.add_argument("--ctr-drop-threshold-pct", type=float, default=20.0)
    parser.add_argument("--cpa-inflation-threshold-pct", type=float, default=25.0)
    parser.add_argument("--min-spend-floor", type=float)

    # Arguments for launch_pacing
    parser.add_argument("--launch-budget-usd", type=float)
    parser.add_argument("--launch-budget", type=float)
    parser.add_argument("--days-elapsed", type=float)
    parser.add_argument("--total-launch-days", type=float)
    parser.add_argument("--spend-to-date-usd", type=float)
    parser.add_argument("--spend-to-date", type=float)
    parser.add_argument("--revenue-to-date-usd", type=float)
    parser.add_argument("--revenue-to-date", type=float)
    parser.add_argument("--gross-margin-pct", type=float)
    parser.add_argument("--target-mer", type=float, default=2.5)

    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if args.mode == "launch_pacing":
            out = compute_launch_pacing_guard(**payload)
        else:
            if isinstance(payload, list):
                out = detect_creative_fatigue(
                    creatives=payload,
                    max_frequency=args.max_frequency,
                    ctr_drop_threshold_pct=args.ctr_drop_threshold_pct,
                    cpa_inflation_threshold_pct=args.cpa_inflation_threshold_pct,
                    currency=args.currency,
                    min_spend_floor=args.min_spend_floor,
                )
            else:
                out = detect_creative_fatigue(**payload)
    elif args.mode == "launch_pacing":
        out = compute_launch_pacing_guard(
            launch_budget_usd=args.launch_budget_usd,
            days_elapsed=args.days_elapsed,
            total_launch_days=args.total_launch_days,
            spend_to_date_usd=args.spend_to_date_usd,
            revenue_to_date_usd=args.revenue_to_date_usd,
            gross_margin_pct=args.gross_margin_pct,
            target_mer=args.target_mer,
            launch_budget=args.launch_budget,
            spend_to_date=args.spend_to_date,
            revenue_to_date=args.revenue_to_date,
            currency=args.currency,
        )
    else:
        out = detect_creative_fatigue(
            creatives=[],
            max_frequency=args.max_frequency,
            ctr_drop_threshold_pct=args.ctr_drop_threshold_pct,
            cpa_inflation_threshold_pct=args.cpa_inflation_threshold_pct,
            currency=args.currency,
            min_spend_floor=args.min_spend_floor,
        )

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
