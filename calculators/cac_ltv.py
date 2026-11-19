"""Deterministic unit economics, allowable CAC, break-even ROAS, payback, and cohort LTV."""

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
    ok_result,
    resolve_amount,
    round_money,
    to_float,
    unknown_result,
)


def compute_cac_ltv(
    aov_usd: Any = None,
    gross_margin_pct: Any = None,
    repeat_orders: Any = 1.0,
    target_payback_months: Any = 3.0,
    monthly_orders_per_customer: Any = 1.0,
    actual_spend_usd: Any = None,
    new_customers: Any = None,
    aov: Any = None,
    actual_spend: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compute gross-margin LTV, allowable CAC, break-even ROAS, and payback period in any currency."""
    cur = normalize_currency(currency)
    aov_val = resolve_amount(aov, aov_usd)
    gm = to_float(gross_margin_pct)
    rep = to_float(repeat_orders)
    target_pb = to_float(target_payback_months)
    m_orders = to_float(monthly_orders_per_customer)

    missing: list[str] = []
    if aov_val is None:
        missing.append("aov_usd" if cur == "USD" else "aov")
    if gm is None:
        missing.append("gross_margin_pct")
    if rep is None:
        missing.append("repeat_orders")
    if target_pb is None:
        missing.append("target_payback_months")
    if m_orders is None:
        missing.append("monthly_orders_per_customer")

    trace = (
        "gross_profit_per_order = aov * (gross_margin_pct / 100); "
        "ltv_gross_profit = gross_profit_per_order * repeat_orders; "
        "break_even_roas = 100 / gross_margin_pct; "
        "allowable_cac = min(ltv_gross_profit, gross_profit_per_order * monthly_orders_per_customer * target_payback_months)"
    )

    if missing:
        return unknown_result(missing, trace, {"currency": cur})

    assert aov_val is not None and gm is not None and rep is not None and target_pb is not None and m_orders is not None
    if aov_val <= 0 or gm <= 0 or gm > 100 or rep <= 0 or target_pb <= 0 or m_orders <= 0:
        return unknown_result(["valid_positive_unit_economics"], trace, {"currency": cur, "error": "Inputs must be > 0 and gross_margin_pct <= 100"})

    gm_ratio = gm / 100.0
    gp_per_order = round(aov_val * gm_ratio, 4)
    ltv_gross_profit = round(gp_per_order * rep, 4)
    break_even_roas = round(1.0 / gm_ratio, 4)
    payback_window_gp = gp_per_order * m_orders * target_pb
    allowable_cac_raw = min(ltv_gross_profit, payback_window_gp)
    gp_rounded = round_money(gp_per_order, cur)
    ltv_rounded = round_money(ltv_gross_profit, cur)
    allowable_cac_val = round_money(allowable_cac_raw, cur)

    result: dict[str, Any] = {
        "currency": cur,
        "currency_symbol": currency_symbol(cur),
        "gross_profit_per_order": gp_rounded,
        "gross_profit_per_order_formatted": format_money(gp_per_order, cur),
        "gross_profit_per_order_usd": round(gp_per_order, 2),
        "ltv_gross_profit": ltv_rounded,
        "ltv_gross_profit_formatted": format_money(ltv_gross_profit, cur),
        "ltv_gross_profit_usd": round(ltv_gross_profit, 2),
        "break_even_roas": break_even_roas,
        "allowable_cac": allowable_cac_val,
        "allowable_cac_formatted": format_money(allowable_cac_raw, cur),
        "allowable_cac_usd": round(allowable_cac_raw, 2),
        "actual_cac": "unknown",
        "actual_cac_usd": "unknown",
        "payback_months": "unknown",
        "ltv_to_cac_ratio": "unknown",
        "payback_gate_pass": "unknown",
    }

    spend = resolve_amount(actual_spend, actual_spend_usd)
    cust = to_float(new_customers)
    if spend is not None and cust is not None and cust > 0:
        actual_cac = spend / cust
        monthly_gp = gp_per_order * m_orders
        payback_months = actual_cac / monthly_gp if monthly_gp > 0 else None
        result["actual_cac"] = round_money(actual_cac, cur)
        result["actual_cac_formatted"] = format_money(actual_cac, cur)
        result["actual_cac_usd"] = round(actual_cac, 2)
        if payback_months is not None:
            result["payback_months"] = round(payback_months, 2)
            result["payback_gate_pass"] = payback_months <= target_pb
        if actual_cac > 0:
            result["ltv_to_cac_ratio"] = round(ltv_gross_profit / actual_cac, 2)

    return ok_result(result, trace)


def compute_promo_breakeven(
    aov_usd: Any = None,
    gross_margin_pct: Any = None,
    discount_pct: Any = None,
    aov: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compute gross-profit erosion and required volume lift % to break even on a discount/promo."""
    cur = normalize_currency(currency)
    aov_val = resolve_amount(aov, aov_usd)
    gm = to_float(gross_margin_pct)
    disc = to_float(discount_pct)
    trace = (
        "cogs = aov * (1 - gross_margin_pct/100); "
        "discounted_gp = aov*(1 - discount_pct/100) - cogs; "
        "required_volume_lift_pct = ((baseline_gp / discounted_gp) - 1) * 100"
    )
    aov_label = "aov_usd" if cur == "USD" else "aov"
    missing = [k for k, v in [(aov_label, aov_val), ("gross_margin_pct", gm), ("discount_pct", disc)] if v is None]
    if missing:
        return unknown_result(missing, trace, {"currency": cur})

    assert aov_val is not None and gm is not None and disc is not None
    if aov_val <= 0 or gm <= 0 or gm > 100 or disc < 0 or disc >= 100:
        return unknown_result(["valid_promo_inputs"], trace, {"currency": cur})

    baseline_gp = aov_val * (gm / 100.0)
    cogs = aov_val - baseline_gp
    discounted_price = aov_val * (1.0 - disc / 100.0)
    discounted_gp = discounted_price - cogs
    if discounted_gp <= 0:
        return ok_result(
            {
                "currency": cur,
                "currency_symbol": currency_symbol(cur),
                "profitable_unit_margin": False,
                "baseline_gp": round_money(baseline_gp, cur),
                "baseline_gp_formatted": format_money(baseline_gp, cur),
                "baseline_gp_usd": round(baseline_gp, 2),
                "discounted_gp": round_money(discounted_gp, cur),
                "discounted_gp_formatted": format_money(discounted_gp, cur),
                "discounted_gp_usd": round(discounted_gp, 2),
                "required_volume_lift_pct": "impossible_negative_margin",
            },
            trace,
        )

    vol_lift_pct = ((baseline_gp / discounted_gp) - 1.0) * 100.0
    return ok_result(
        {
            "currency": cur,
            "currency_symbol": currency_symbol(cur),
            "profitable_unit_margin": True,
            "baseline_gp": round_money(baseline_gp, cur),
            "baseline_gp_formatted": format_money(baseline_gp, cur),
            "baseline_gp_usd": round(baseline_gp, 2),
            "discounted_gp": round_money(discounted_gp, cur),
            "discounted_gp_formatted": format_money(discounted_gp, cur),
            "discounted_gp_usd": round(discounted_gp, 2),
            "post_discount_margin_pct": round((discounted_gp / discounted_price) * 100.0, 2),
            "required_volume_lift_pct": round(vol_lift_pct, 2),
        },
        trace,
    )


def compute_creator_commission_cap(
    allowable_cac_usd: Any = None,
    paid_whitelisting_cpa_usd: Any = 0.0,
    creator_flat_fee_usd: Any = 0.0,
    expected_conversions: Any = 10,
    allowable_cac: Any = None,
    paid_whitelisting_cpa: Any = None,
    creator_flat_fee: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compute maximum affiliate/creator payout per conversion without breaching allowable CAC."""
    cur = normalize_currency(currency)
    cac = resolve_amount(allowable_cac, allowable_cac_usd)
    paid_cpa = resolve_amount(paid_whitelisting_cpa, paid_whitelisting_cpa_usd)
    flat_fee = resolve_amount(creator_flat_fee, creator_flat_fee_usd)
    convs = to_float(expected_conversions)
    trace = "max_affiliate_payout = allowable_cac - paid_whitelisting_cpa - (creator_flat_fee / expected_conversions)"
    missing = [
        k
        for k, v in [
            ("allowable_cac" if cur != "USD" else "allowable_cac_usd", cac),
            ("paid_whitelisting_cpa_usd", paid_cpa),
            ("creator_flat_fee_usd", flat_fee),
            ("expected_conversions", convs),
        ]
        if v is None
    ]
    if missing:
        return unknown_result(missing, trace, {"currency": cur})

    assert cac is not None and paid_cpa is not None and flat_fee is not None and convs is not None
    if cac <= 0 or convs <= 0 or paid_cpa < 0 or flat_fee < 0:
        return unknown_result(["valid_creator_economics"], trace, {"currency": cur})

    amortized_fee = flat_fee / convs
    max_payout_raw = cac - paid_cpa - amortized_fee
    max_payout = round(max_payout_raw, 2)
    return ok_result(
        {
            "currency": cur,
            "currency_symbol": currency_symbol(cur),
            "amortized_flat_fee_per_conv": round_money(amortized_fee, cur),
            "amortized_flat_fee_per_conv_usd": round(amortized_fee, 2),
            "max_affiliate_payout": max(0.0, round_money(max_payout_raw, cur)),
            "max_affiliate_payout_formatted": format_money(max(0.0, max_payout_raw), cur),
            "max_affiliate_payout_usd": max(0.0, max_payout),
            "viable_partnership": max_payout >= 0.0,
        },
        trace,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute CAC, LTV, promo break-even, and creator caps in any currency.")
    parser.add_argument("--mode", choices=["unit", "promo", "creator_cap"], default="unit")
    parser.add_argument("--input", help="JSON input file path")
    parser.add_argument("--currency", default="USD", help="ISO-4217 currency code (e.g. USD, KES, IDR, MXN)")
    parser.add_argument("--aov", "--aov-usd", dest="aov_usd", type=float)
    parser.add_argument("--gross-margin-pct", type=float)
    parser.add_argument("--discount-pct", type=float)
    parser.add_argument("--repeat-orders", type=float, default=1.0)
    parser.add_argument("--target-payback-months", type=float, default=3.0)
    parser.add_argument("--monthly-orders-per-customer", type=float, default=1.0)
    parser.add_argument("--actual-spend", "--actual-spend-usd", dest="actual_spend_usd", type=float)
    parser.add_argument("--new-customers", type=float)
    parser.add_argument("--allowable-cac", "--allowable-cac-usd", dest="allowable_cac_usd", type=float)
    parser.add_argument("--paid-whitelisting-cpa", "--paid-whitelisting-cpa-usd", dest="paid_whitelisting_cpa_usd", type=float, default=0.0)
    parser.add_argument("--creator-flat-fee", "--creator-flat-fee-usd", dest="creator_flat_fee_usd", type=float, default=0.0)
    parser.add_argument("--expected-conversions", type=float, default=10.0)
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if args.mode == "promo":
            out = compute_promo_breakeven(**payload)
        elif args.mode == "creator_cap":
            out = compute_creator_commission_cap(**payload)
        else:
            out = compute_cac_ltv(**payload)
    elif args.mode == "promo":
        out = compute_promo_breakeven(
            aov_usd=args.aov_usd,
            gross_margin_pct=args.gross_margin_pct,
            discount_pct=args.discount_pct,
            currency=args.currency,
        )
    elif args.mode == "creator_cap":
        out = compute_creator_commission_cap(
            allowable_cac_usd=args.allowable_cac_usd,
            paid_whitelisting_cpa_usd=args.paid_whitelisting_cpa_usd,
            creator_flat_fee_usd=args.creator_flat_fee_usd,
            expected_conversions=args.expected_conversions,
            currency=args.currency,
        )
    else:
        out = compute_cac_ltv(
            aov_usd=args.aov_usd,
            gross_margin_pct=args.gross_margin_pct,
            repeat_orders=args.repeat_orders,
            target_payback_months=args.target_payback_months,
            monthly_orders_per_customer=args.monthly_orders_per_customer,
            actual_spend_usd=args.actual_spend_usd,
            new_customers=args.new_customers,
            currency=args.currency,
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
