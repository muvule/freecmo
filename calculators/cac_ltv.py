"""Deterministic unit economics, allowable CAC, break-even ROAS, payback, and cohort LTV."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from calculators import ok_result, to_float, unknown_result


def compute_cac_ltv(
    aov_usd: Any,
    gross_margin_pct: Any,
    repeat_orders: Any = 1.0,
    target_payback_months: Any = 3.0,
    monthly_orders_per_customer: Any = 1.0,
    actual_spend_usd: Any = None,
    new_customers: Any = None,
) -> dict[str, Any]:
    """Compute gross-margin LTV, allowable CAC, break-even ROAS, and payback period."""
    aov = to_float(aov_usd)
    gm = to_float(gross_margin_pct)
    rep = to_float(repeat_orders)
    target_pb = to_float(target_payback_months)
    m_orders = to_float(monthly_orders_per_customer)

    missing: list[str] = []
    if aov is None:
        missing.append("aov_usd")
    if gm is None:
        missing.append("gross_margin_pct")
    if rep is None:
        missing.append("repeat_orders")
    if target_pb is None:
        missing.append("target_payback_months")
    if m_orders is None:
        missing.append("monthly_orders_per_customer")

    trace = (
        "gross_profit_per_order = aov_usd * (gross_margin_pct / 100); "
        "ltv_gross_profit = gross_profit_per_order * repeat_orders; "
        "break_even_roas = 100 / gross_margin_pct; "
        "allowable_cac_usd = min(ltv_gross_profit, gross_profit_per_order * monthly_orders_per_customer * target_payback_months)"
    )

    if missing:
        return unknown_result(missing, trace)

    assert aov is not None and gm is not None and rep is not None and target_pb is not None and m_orders is not None
    if aov <= 0 or gm <= 0 or gm > 100 or rep <= 0 or target_pb <= 0 or m_orders <= 0:
        return unknown_result(["valid_positive_unit_economics"], trace, {"error": "Inputs must be > 0 and gross_margin_pct <= 100"})

    gm_ratio = gm / 100.0
    gp_per_order = round(aov * gm_ratio, 4)
    ltv_gross_profit = round(gp_per_order * rep, 4)
    break_even_roas = round(1.0 / gm_ratio, 4)
    payback_window_gp = gp_per_order * m_orders * target_pb
    allowable_cac_usd = round(min(ltv_gross_profit, payback_window_gp), 2)

    result: dict[str, Any] = {
        "gross_profit_per_order_usd": round(gp_per_order, 2),
        "ltv_gross_profit_usd": round(ltv_gross_profit, 2),
        "break_even_roas": break_even_roas,
        "allowable_cac_usd": allowable_cac_usd,
        "actual_cac_usd": "unknown",
        "payback_months": "unknown",
        "ltv_to_cac_ratio": "unknown",
        "payback_gate_pass": "unknown",
    }

    spend = to_float(actual_spend_usd)
    cust = to_float(new_customers)
    if spend is not None and cust is not None and cust > 0:
        actual_cac = spend / cust
        monthly_gp = gp_per_order * m_orders
        payback_months = actual_cac / monthly_gp if monthly_gp > 0 else None
        result["actual_cac_usd"] = round(actual_cac, 2)
        if payback_months is not None:
            result["payback_months"] = round(payback_months, 2)
            result["payback_gate_pass"] = payback_months <= target_pb
        if actual_cac > 0:
            result["ltv_to_cac_ratio"] = round(ltv_gross_profit / actual_cac, 2)

    return ok_result(result, trace)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compute CAC, LTV, break-even ROAS, and payback.")
    parser.add_argument("--input", help="JSON input file path")
    parser.add_argument("--aov-usd", type=float)
    parser.add_argument("--gross-margin-pct", type=float)
    parser.add_argument("--repeat-orders", type=float, default=1.0)
    parser.add_argument("--target-payback-months", type=float, default=3.0)
    parser.add_argument("--monthly-orders-per-customer", type=float, default=1.0)
    parser.add_argument("--actual-spend-usd", type=float)
    parser.add_argument("--new-customers", type=float)
    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        out = compute_cac_ltv(**payload)
    else:
        out = compute_cac_ltv(
            aov_usd=args.aov_usd,
            gross_margin_pct=args.gross_margin_pct,
            repeat_orders=args.repeat_orders,
            target_payback_months=args.target_payback_months,
            monthly_orders_per_customer=args.monthly_orders_per_customer,
            actual_spend_usd=args.actual_spend_usd,
            new_customers=args.new_customers,
        )
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
