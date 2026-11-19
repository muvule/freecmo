"""Deterministic churn, NRR, customer ceiling, cash runway simulation, and referral economics."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
from typing import Any

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from calculators import ok_result, to_float, unknown_result


def compute_churn_and_nrr(
    starting_mrr_usd: Any,
    monthly_logo_churn_pct: Any,
    monthly_revenue_churn_pct: Any,
    monthly_expansion_pct: Any = 0.0,
    new_customers_per_month: Any = None,
) -> dict[str, Any]:
    """Compute monthly GRR, NRR, annualized NRR, implied lifetime, and steady-state customer ceiling."""
    mrr = to_float(starting_mrr_usd)
    logo_churn = to_float(monthly_logo_churn_pct)
    rev_churn = to_float(monthly_revenue_churn_pct)

    missing: list[str] = []
    if mrr is None:
        missing.append("starting_mrr_usd")
    if logo_churn is None:
        missing.append("monthly_logo_churn_pct")
    if rev_churn is None:
        missing.append("monthly_revenue_churn_pct")

    trace = (
        "monthly_grr_pct = round(max(0.0, 100.0 - monthly_revenue_churn_pct), 2); "
        "monthly_nrr_pct = round(max(0.0, 100.0 - monthly_revenue_churn_pct + monthly_expansion_pct), 2); "
        "annualized_nrr_pct = round(((monthly_nrr_pct / 100.0) ** 12) * 100.0, 2); "
        "implied_lifetime_months = 100.0 / monthly_logo_churn_pct; "
        "net_mrr_after_1m_usd = round(starting_mrr_usd * (monthly_nrr_pct / 100.0), 2); "
        "steady_state_customer_ceiling = new_customers_per_month / (monthly_logo_churn_pct / 100.0)"
    )

    if missing:
        return unknown_result(missing, trace)

    assert mrr is not None and logo_churn is not None and rev_churn is not None

    if mrr < 0 or logo_churn < 0 or logo_churn > 100 or rev_churn < 0 or rev_churn > 100:
        raise ValueError(
            f"Invalid inputs: starting_mrr_usd ({mrr}) must be >= 0, churn percentages must be between 0 and 100"
        )

    exp = to_float(monthly_expansion_pct) or 0.0
    if exp < 0:
        raise ValueError(f"monthly_expansion_pct ({exp}) cannot be negative")

    monthly_grr_pct = round(max(0.0, 100.0 - rev_churn), 2)
    monthly_nrr_pct = round(max(0.0, 100.0 - rev_churn + exp), 2)
    annualized_nrr_pct = round(((monthly_nrr_pct / 100.0) ** 12) * 100.0, 2)
    implied_lifetime_months: float | str = round(100.0 / logo_churn, 2) if logo_churn > 0 else "infinite"
    net_mrr_after_1m_usd = round(mrr * (monthly_nrr_pct / 100.0), 2)

    new_cust = to_float(new_customers_per_month)
    if new_cust is not None and new_cust < 0:
        raise ValueError(f"new_customers_per_month ({new_cust}) cannot be negative")

    steady_state_customer_ceiling = (
        round(new_cust / (logo_churn / 100.0), 1) if (new_cust is not None and logo_churn > 0) else None
    )
    leaky_bucket_alert = bool(logo_churn >= 8.0 or monthly_nrr_pct < 95.0)

    return {
        "status": "ok",
        "monthly_grr_pct": monthly_grr_pct,
        "monthly_nrr_pct": monthly_nrr_pct,
        "annualized_nrr_pct": annualized_nrr_pct,
        "implied_lifetime_months": implied_lifetime_months,
        "net_mrr_after_1m_usd": net_mrr_after_1m_usd,
        "steady_state_customer_ceiling": steady_state_customer_ceiling,
        "leaky_bucket_alert": leaky_bucket_alert,
    }


def simulate_cash_flow_runway(
    available_cash_usd: Any,
    monthly_ad_spend_usd: Any,
    allowable_cac_usd: Any,
    monthly_gross_profit_per_customer_usd: Any,
    monthly_logo_churn_pct: Any = 3.0,
    horizon_months: int = 12,
    fixed_marketing_ops_usd: Any = 0.0,
) -> dict[str, Any]:
    """Simulate month-by-month cash trough, minimum cash balance, breakeven, and runway safety."""
    cash = to_float(available_cash_usd)
    spend = to_float(monthly_ad_spend_usd)
    cac = to_float(allowable_cac_usd)
    gp_per_cust = to_float(monthly_gross_profit_per_customer_usd)
    churn = to_float(monthly_logo_churn_pct)
    fixed_ops = to_float(fixed_marketing_ops_usd)

    trace = (
        "new_cohort = spend / cac; "
        "active_customers = active_prev * (1 - churn/100) + new_cohort; "
        "monthly_gp = active_customers * gp_per_cust; "
        "monthly_outflow = spend + fixed_ops; "
        "monthly_net = monthly_gp - monthly_outflow"
    )

    missing: list[str] = []
    if cash is None:
        missing.append("available_cash_usd")
    if spend is None:
        missing.append("monthly_ad_spend_usd")
    if cac is None:
        missing.append("allowable_cac_usd")
    if gp_per_cust is None:
        missing.append("monthly_gross_profit_per_customer_usd")

    if missing:
        return unknown_result(missing, trace)

    if churn is None:
        churn = 3.0
    if fixed_ops is None:
        fixed_ops = 0.0

    assert cash is not None and spend is not None and cac is not None and gp_per_cust is not None

    h_months = int(horizon_months)
    if (
        cac <= 0
        or h_months < 1
        or h_months > 120
        or churn < 0
        or churn > 100
        or cash < 0
        or spend < 0
        or fixed_ops < 0
        or gp_per_cust < 0
    ):
        raise ValueError(
            "Invalid inputs: allowable_cac_usd > 0, 1 <= horizon_months <= 120, 0 <= churn <= 100, cash >= 0, spend >= 0, fixed_ops >= 0, gp_per_cust >= 0 required"
        )

    new_cohort = spend / cac
    active = 0.0
    cumulative_net = 0.0
    min_cumulative_net = 0.0
    monthly_breakeven_month: int | str = "beyond_horizon"
    cumulative_payback_month: int | str = "beyond_horizon"
    schedule: list[dict[str, Any]] = []

    for month in range(1, h_months + 1):
        active = active * (1.0 - churn / 100.0) + new_cohort
        monthly_gp = active * gp_per_cust
        monthly_outflow = spend + fixed_ops
        monthly_net = monthly_gp - monthly_outflow
        cumulative_net += monthly_net
        min_cumulative_net = min(min_cumulative_net, cumulative_net)

        if monthly_breakeven_month == "beyond_horizon" and monthly_net >= 0:
            monthly_breakeven_month = month
        if cumulative_payback_month == "beyond_horizon" and cumulative_net >= 0:
            cumulative_payback_month = month

        schedule.append(
            {
                "month": month,
                "active_customers": round(active, 2),
                "monthly_gross_profit_usd": round(monthly_gp, 2),
                "monthly_outflow_usd": round(monthly_outflow, 2),
                "monthly_net_usd": round(monthly_net, 2),
                "cumulative_net_usd": round(cumulative_net, 2),
            }
        )

    max_cash_trough_usd = round(max(0.0, -min_cumulative_net), 2)
    min_cash_balance_usd = round(cash - max_cash_trough_usd, 2)
    runway_safe = bool(min_cash_balance_usd >= (spend + fixed_ops))

    return {
        "status": "ok",
        "new_customers_per_month": round(new_cohort, 2),
        "max_cash_trough_usd": max_cash_trough_usd,
        "min_cash_balance_usd": min_cash_balance_usd,
        "monthly_breakeven_month": monthly_breakeven_month,
        "cumulative_payback_month": cumulative_payback_month,
        "runway_safe": runway_safe,
        "monthly_schedule": schedule,
    }


def compute_referral_and_review_economics(
    paid_cac_usd: Any,
    allowable_cac_usd: Any,
    referral_invite_rate: Any,
    referral_conversion_rate: Any,
    referrer_reward_usd: Any,
    friend_discount_cost_usd: Any,
    current_reviews: Any = None,
    current_rating: Any = None,
    target_rating: Any = None,
    competitor_reviews: Any = None,
) -> dict[str, Any]:
    """Compute viral k-factor, effective blended CAC with referral loop, and review overtaking targets."""
    paid_cac = to_float(paid_cac_usd)
    allowable_cac = to_float(allowable_cac_usd)
    inv_rate = to_float(referral_invite_rate)
    conv_rate = to_float(referral_conversion_rate)
    ref_reward = to_float(referrer_reward_usd)
    friend_cost = to_float(friend_discount_cost_usd)

    trace = (
        "k_factor = referral_invite_rate * referral_conversion_rate; "
        "effective_blended_cac_usd = paid_cac_usd / (1 + k_factor); "
        "total_referral_reward_usd = referrer_reward_usd + friend_discount_cost_usd; "
        "five_star_reviews_needed = ceil((target_rating*c_rev - current_rating*c_rev) / (5.0 - target_rating))"
    )

    missing: list[str] = []
    if paid_cac is None:
        missing.append("paid_cac_usd")
    if allowable_cac is None:
        missing.append("allowable_cac_usd")
    if inv_rate is None:
        missing.append("referral_invite_rate")
    if conv_rate is None:
        missing.append("referral_conversion_rate")
    if ref_reward is None:
        missing.append("referrer_reward_usd")
    if friend_cost is None:
        missing.append("friend_discount_cost_usd")

    if missing:
        return unknown_result(missing, trace)

    assert (
        paid_cac is not None
        and allowable_cac is not None
        and inv_rate is not None
        and conv_rate is not None
        and ref_reward is not None
        and friend_cost is not None
    )

    if (
        paid_cac < 0
        or allowable_cac < 0
        or inv_rate < 0
        or inv_rate > 10.0
        or conv_rate < 0
        or conv_rate > 1.0
        or ref_reward < 0
        or friend_cost < 0
    ):
        raise ValueError(
            "Invalid inputs: rates must be in range (inv_rate 0..10, conv_rate 0..1) and costs >= 0"
        )

    k_factor = round(inv_rate * conv_rate, 4)
    effective_blended_cac_usd = round(paid_cac / (1.0 + k_factor), 2)
    total_referral_reward_usd = round(ref_reward + friend_cost, 2)
    reward_within_cac_ceiling = bool(total_referral_reward_usd <= allowable_cac)

    # Optional review velocity
    c_rev = to_float(current_reviews)
    c_rating = to_float(current_rating)
    t_rating = to_float(target_rating)
    comp_rev = to_float(competitor_reviews)

    five_star_reviews_needed: int | None = None
    if (
        c_rev is not None
        and c_rating is not None
        and t_rating is not None
        and 0 < t_rating < 5.0
        and c_rev >= 0
    ):
        if c_rating >= t_rating:
            five_star_reviews_needed = 0
        else:
            five_star_reviews_needed = max(
                0, int(math.ceil((t_rating * c_rev - c_rating * c_rev) / (5.0 - t_rating)))
            )

    reviews_to_overtake_competitor: int | None = None
    if c_rev is not None and comp_rev is not None:
        reviews_to_overtake_competitor = max(0, int(comp_rev - c_rev + 1))

    return {
        "status": "ok",
        "k_factor": k_factor,
        "effective_blended_cac_usd": effective_blended_cac_usd,
        "total_referral_reward_usd": total_referral_reward_usd,
        "reward_within_cac_ceiling": reward_within_cac_ceiling,
        "five_star_reviews_needed": five_star_reviews_needed,
        "reviews_to_overtake_competitor": reviews_to_overtake_competitor,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute churn/NRR, cash runway simulation, and referral economics."
    )
    parser.add_argument(
        "--mode",
        choices=["churn_nrr", "cash_runway", "referral_loop"],
        default="churn_nrr",
    )
    parser.add_argument("--input", help="JSON input file path")

    # Arguments for churn_nrr
    parser.add_argument("--starting-mrr-usd", type=float)
    parser.add_argument("--monthly-logo-churn-pct", type=float)
    parser.add_argument("--monthly-revenue-churn-pct", type=float)
    parser.add_argument("--monthly-expansion-pct", type=float, default=0.0)
    parser.add_argument("--new-customers-per-month", type=float)

    # Arguments for cash_runway
    parser.add_argument("--available-cash-usd", type=float)
    parser.add_argument("--monthly-ad-spend-usd", type=float)
    parser.add_argument("--allowable-cac-usd", type=float)
    parser.add_argument("--monthly-gross-profit-per-customer-usd", type=float)
    parser.add_argument("--horizon-months", type=int, default=12)
    parser.add_argument("--fixed-marketing-ops-usd", type=float, default=0.0)

    # Arguments for referral_loop
    parser.add_argument("--paid-cac-usd", type=float)
    parser.add_argument("--referral-invite-rate", type=float)
    parser.add_argument("--referral-conversion-rate", type=float)
    parser.add_argument("--referrer-reward-usd", type=float)
    parser.add_argument("--friend-discount-cost-usd", type=float)
    parser.add_argument("--current-reviews", type=float)
    parser.add_argument("--current-rating", type=float)
    parser.add_argument("--target-rating", type=float)
    parser.add_argument("--competitor-reviews", type=float)

    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if args.mode == "cash_runway":
            out = simulate_cash_flow_runway(**payload)
        elif args.mode == "referral_loop":
            out = compute_referral_and_review_economics(**payload)
        else:
            out = compute_churn_and_nrr(**payload)
    elif args.mode == "cash_runway":
        out = simulate_cash_flow_runway(
            available_cash_usd=args.available_cash_usd,
            monthly_ad_spend_usd=args.monthly_ad_spend_usd,
            allowable_cac_usd=args.allowable_cac_usd,
            monthly_gross_profit_per_customer_usd=args.monthly_gross_profit_per_customer_usd,
            monthly_logo_churn_pct=args.monthly_logo_churn_pct if args.monthly_logo_churn_pct is not None else 3.0,
            horizon_months=args.horizon_months,
            fixed_marketing_ops_usd=args.fixed_marketing_ops_usd,
        )
    elif args.mode == "referral_loop":
        out = compute_referral_and_review_economics(
            paid_cac_usd=args.paid_cac_usd,
            allowable_cac_usd=args.allowable_cac_usd,
            referral_invite_rate=args.referral_invite_rate,
            referral_conversion_rate=args.referral_conversion_rate,
            referrer_reward_usd=args.referrer_reward_usd,
            friend_discount_cost_usd=args.friend_discount_cost_usd,
            current_reviews=args.current_reviews,
            current_rating=args.current_rating,
            target_rating=args.target_rating,
            competitor_reviews=args.competitor_reviews,
        )
    else:
        out = compute_churn_and_nrr(
            starting_mrr_usd=args.starting_mrr_usd,
            monthly_logo_churn_pct=args.monthly_logo_churn_pct,
            monthly_revenue_churn_pct=args.monthly_revenue_churn_pct,
            monthly_expansion_pct=args.monthly_expansion_pct,
            new_customers_per_month=args.new_customers_per_month,
        )

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
