"""Blended MER, branded/non-branded split, Acquisition vs. Retention allocator, and stop-losses."""

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
    round_money,
    safe_eval_condition,
    to_float,
    unknown_result,
)


def compute_blended_mer(
    total_revenue_usd: Any = None,
    total_ad_spend_usd: Any = None,
    branded_paid_revenue_usd: Any = None,
    branded_paid_spend_usd: Any = None,
    non_branded_paid_revenue_usd: Any = None,
    non_branded_paid_spend_usd: Any = None,
    organic_revenue_usd: Any = None,
    total_revenue: Any = None,
    total_ad_spend: Any = None,
    branded_paid_revenue: Any = None,
    branded_paid_spend: Any = None,
    non_branded_paid_revenue: Any = None,
    non_branded_paid_spend: Any = None,
    organic_revenue: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compute blended MER and separate Branded, Non-Branded Paid, and Organic efficiency in any currency."""
    cur = normalize_currency(currency)
    rev = resolve_amount(total_revenue, total_revenue_usd)
    spend = resolve_amount(total_ad_spend, total_ad_spend_usd)
    trace = "blended_mer = total_revenue / total_ad_spend; amer = non_branded_paid_revenue / non_branded_paid_spend"

    missing: list[str] = []
    if rev is None:
        missing.append("total_revenue_usd" if cur == "USD" else "total_revenue")
    if spend is None or spend <= 0:
        missing.append("total_ad_spend_usd(>0)" if cur == "USD" else "total_ad_spend(>0)")
    if missing:
        return unknown_result(missing, trace, {"currency": cur})

    assert rev is not None and spend is not None
    blended_mer = round(rev / spend, 4)
    metrics: dict[str, Any] = {
        "currency": cur,
        "blended_mer": blended_mer,
        "branded_roas": "unknown",
        "non_branded_roas": "unknown",
        "organic_revenue_share_pct": "unknown",
    }

    b_rev = resolve_amount(branded_paid_revenue, branded_paid_revenue_usd)
    b_spend = resolve_amount(branded_paid_spend, branded_paid_spend_usd)
    if b_rev is not None and b_spend is not None and b_spend > 0:
        metrics["branded_roas"] = round(b_rev / b_spend, 4)

    nb_rev = resolve_amount(non_branded_paid_revenue, non_branded_paid_revenue_usd)
    nb_spend = resolve_amount(non_branded_paid_spend, non_branded_paid_spend_usd)
    if nb_rev is not None and nb_spend is not None and nb_spend > 0:
        metrics["non_branded_roas"] = round(nb_rev / nb_spend, 4)

    org_rev = resolve_amount(organic_revenue, organic_revenue_usd)
    if org_rev is not None and rev > 0:
        metrics["organic_revenue_share_pct"] = round((org_rev / rev) * 100.0, 2)

    return ok_result(metrics, trace)


def allocate_acquisition_vs_retention(
    segments: list[dict[str, Any]],
    reallocation_pool_usd: Any = 0.0,
    reallocation_pool: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compare marginal ROI of retention vs. cold acquisition across segments in any currency."""
    cur = normalize_currency(currency)
    trace = "marginal_roi_pct = ((incremental_gross_profit - cost) / cost) * 100"
    pool = resolve_amount(reallocation_pool, reallocation_pool_usd)
    if not segments or pool is None:
        return unknown_result(["segments", "reallocation_pool_usd" if cur == "USD" else "reallocation_pool"], trace, {"currency": cur})

    scored: list[dict[str, Any]] = []
    for seg in segments:
        name = seg.get("segment_name")
        mode = seg.get("motion")  # "retention" or "cold_acquisition"
        cost = resolve_amount(seg.get("cost"), seg.get("cost_usd"))
        gp = resolve_amount(seg.get("incremental_gross_profit"), seg.get("incremental_gross_profit_usd"))
        if not name or mode not in ("retention", "cold_acquisition") or cost is None or cost <= 0 or gp is None:
            return unknown_result([f"segment:{name or 'unnamed'}"], trace, {"currency": cur})
        roi_pct = round(((gp - cost) / cost) * 100.0, 2)
        scored.append(
            {
                "segment_name": name,
                "motion": mode,
                "cost": round_money(cost, cur),
                "cost_usd": cost,
                "incremental_gross_profit": round_money(gp, cur),
                "incremental_gross_profit_usd": gp,
                "marginal_roi_pct": roi_pct,
            }
        )

    retention_best = max(
        (s for s in scored if s["motion"] == "retention"),
        key=lambda x: x["marginal_roi_pct"],
        default=None,
    )
    cold_worst = min(
        (s for s in scored if s["motion"] == "cold_acquisition"),
        key=lambda x: x["marginal_roi_pct"],
        default=None,
    )

    recommendation: dict[str, Any] | None = None
    if retention_best and cold_worst:
        delta = round(retention_best["marginal_roi_pct"] - cold_worst["marginal_roi_pct"], 2)
        if delta > 0:
            shift_raw = min(pool, cold_worst["cost"])
            shift_val = round_money(shift_raw, cur)
            shift_formatted = format_money(shift_raw, cur)
            recommendation = {
                "currency": cur,
                "from_segment": cold_worst["segment_name"],
                "to_segment": retention_best["segment_name"],
                "shift_amount": shift_val,
                "shift_formatted": shift_formatted,
                "shift_usd": round(shift_raw, 2),
                "marginal_roi_delta_pct": delta,
                "summary": (
                    f"{retention_best['segment_name']} (retention) outperforms "
                    f"{cold_worst['segment_name']} (cold_acquisition) by {delta}pp ROI; shift {shift_formatted}"
                ),
            }

    return ok_result(
        {
            "currency": cur,
            "scored_segments": sorted(scored, key=lambda x: x["marginal_roi_pct"], reverse=True),
            "recommendation": recommendation,
        },
        trace,
    )


def evaluate_stop_losses(
    rules: list[dict[str, Any]],
    campaigns: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate time-windowed conditional stop-loss rules without eval()."""
    trace = "safe_eval_condition(rule.condition, campaign_metrics)"
    alerts: list[dict[str, Any]] = []
    for camp in campaigns:
        camp_id = camp.get("campaign_id", "unknown")
        for rule in rules:
            if rule.get("channel") and camp.get("channel") and rule["channel"] != camp["channel"]:
                continue
            cond_res = safe_eval_condition(rule["condition"], camp)
            if cond_res["triggered"] is True:
                alerts.append(
                    {
                        "rule_id": rule.get("id", "unnamed"),
                        "campaign_id": camp_id,
                        "action": rule.get("action", "stage_pause"),
                        "condition": rule["condition"],
                    }
                )
    return ok_result({"triggered_alerts": alerts, "alert_count": len(alerts)}, trace)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blended MER, Acq-vs-Retention, and stop-loss evaluator.")
    parser.add_argument("--input", required=True, help="JSON input file path")
    parser.add_argument("--mode", choices=["mer", "allocate", "stop_loss"], default="mer")
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if args.mode == "mer":
        out = compute_blended_mer(**payload)
    elif args.mode == "allocate":
        out = allocate_acquisition_vs_retention(**payload)
    else:
        out = evaluate_stop_losses(**payload)

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
