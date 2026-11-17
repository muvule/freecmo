"""Experiment sample size power, two-proportion z-test, Mann-Whitney U, and disproof evaluation."""

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

from calculators import ok_result, safe_eval_condition, to_float, unknown_result


def _norm_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """Acklam rational approximation for inverse standard normal CDF (0 < p < 1)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("Probability must be strictly between 0 and 1")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
        ) / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def required_sample_size_per_arm(
    baseline_rate: Any,
    relative_mde: Any,
    alpha: Any = 0.05,
    power: Any = 0.80,
) -> dict[str, Any]:
    """Compute minimum sample size per variant arm for a two-proportion experiment."""
    p1 = to_float(baseline_rate)
    mde = to_float(relative_mde)
    al = to_float(alpha)
    pw = to_float(power)
    trace = "n_per_arm = ceil(((z_alpha*sqrt(2*p_bar*(1-p_bar)) + z_beta*sqrt(p1*(1-p1)+p2*(1-p2)))**2) / (p2-p1)**2)"

    missing = [k for k, v in [("baseline_rate", p1), ("relative_mde", mde), ("alpha", al), ("power", pw)] if v is None]
    if missing:
        return unknown_result(missing, trace)

    assert p1 is not None and mde is not None and al is not None and pw is not None
    p2 = p1 * (1.0 + mde)
    if not (0.0 < p1 < 1.0) or not (0.0 < p2 < 1.0) or p1 == p2 or not (0.0 < al < 0.5) or not (0.5 < pw < 1.0):
        return unknown_result(["valid_rate_and_mde"], trace)

    p_bar = 0.5 * (p1 + p2)
    z_alpha = _norm_ppf(1.0 - al / 2.0)
    z_beta = _norm_ppf(pw)
    num = (z_alpha * math.sqrt(2.0 * p_bar * (1.0 - p_bar)) + z_beta * math.sqrt(p1 * (1.0 - p1) + p2 * (1.0 - p2))) ** 2
    den = (p2 - p1) ** 2
    n_arm = math.ceil(num / den)
    return ok_result(
        {
            "baseline_rate": round(p1, 6),
            "target_rate": round(p2, 6),
            "n_per_arm": n_arm,
            "total_sample_size": n_arm * 2,
        },
        trace,
    )


def two_proportion_z_test(
    control_conversions: Any,
    control_trials: Any,
    variant_conversions: Any,
    variant_trials: Any,
    alpha: Any = 0.05,
) -> dict[str, Any]:
    """Two-sided pooled two-proportion z-test."""
    c_conv = to_float(control_conversions)
    c_n = to_float(control_trials)
    v_conv = to_float(variant_conversions)
    v_n = to_float(variant_trials)
    al = to_float(alpha)
    trace = "z = (p_v - p_c) / sqrt(p_pool*(1-p_pool)*(1/n_c + 1/n_v)); p_value = 2*(1-norm_cdf(|z|))"

    missing = [
        k
        for k, v in [
            ("control_conversions", c_conv),
            ("control_trials", c_n),
            ("variant_conversions", v_conv),
            ("variant_trials", v_n),
            ("alpha", al),
        ]
        if v is None
    ]
    if missing:
        return unknown_result(missing, trace)

    assert c_conv is not None and c_n is not None and v_conv is not None and v_n is not None and al is not None
    if c_n <= 0 or v_n <= 0 or c_conv < 0 or v_conv < 0 or c_conv > c_n or v_conv > v_n:
        return unknown_result(["valid_trial_counts"], trace)

    p_c = c_conv / c_n
    p_v = v_conv / v_n
    p_pool = (c_conv + v_conv) / (c_n + v_n)
    se = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / c_n + 1.0 / v_n))
    if se == 0.0:
        return unknown_result(["nonzero_variance"], trace)

    z = (p_v - p_c) / se
    p_val = 2.0 * (1.0 - _norm_cdf(abs(z)))
    rel_lift = ((p_v - p_c) / p_c * 100.0) if p_c > 0 else "unknown"
    return ok_result(
        {
            "control_rate": round(p_c, 6),
            "variant_rate": round(p_v, 6),
            "relative_lift_pct": round(rel_lift, 2) if isinstance(rel_lift, float) else "unknown",
            "z_score": round(z, 4),
            "p_value": round(p_val, 6),
            "statistically_significant": p_val < al,
        },
        trace,
    )


def mann_whitney_u(sample_a: list[float], sample_b: list[float], alpha: float = 0.05) -> dict[str, Any]:
    """Two-sided Mann-Whitney U test with normal approximation & tie correction."""
    trace = "U_a = R_a - n_a*(n_a+1)/2; z = (U - mu_U) / sigma_U_tie_corrected"
    if not sample_a or not sample_b or len(sample_a) < 3 or len(sample_b) < 3:
        return unknown_result(["sample_a(>=3)", "sample_b(>=3)"], trace)

    n1 = len(sample_a)
    n2 = len(sample_b)
    combined = sorted([(val, 0) for val in sample_a] + [(val, 1) for val in sample_b], key=lambda x: x[0])

    ranks_a = 0.0
    tie_corr = 0.0
    i = 0
    n = n1 + n2
    while i < n:
        j = i
        while j + 1 < n and combined[j + 1][0] == combined[i][0]:
            j += 1
        t = j - i + 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            if combined[k][1] == 0:
                ranks_a += avg_rank
        if t > 1:
            tie_corr += t**3 - t
        i = j + 1

    u1 = ranks_a - n1 * (n1 + 1) / 2.0
    u2 = n1 * n2 - u1
    u = min(u1, u2)
    mu = n1 * n2 / 2.0
    var = (n1 * n2 / 12.0) * ((n + 1) - tie_corr / (n * (n - 1))) if n > 1 else 0.0
    if var <= 0.0:
        return unknown_result(["nonzero_rank_variance"], trace)
    z = (u - mu) / math.sqrt(var)
    p_val = 2.0 * (1.0 - _norm_cdf(abs(z)))
    return ok_result(
        {
            "u_stat": round(u, 4),
            "z_score": round(z, 4),
            "p_value": round(p_val, 6),
            "statistically_significant": p_val < alpha,
        },
        trace,
    )


def evaluate_disproof_condition(disproof_condition: str, observed_metrics: dict[str, Any]) -> dict[str, Any]:
    """Deterministically check whether an experiment's disproof condition has triggered."""
    res = safe_eval_condition(disproof_condition, observed_metrics)
    return ok_result(
        {
            "killed": res["triggered"] is True,
            "triggered": res["triggered"],
            "missing_inputs": res["missing_inputs"],
            "disproof_condition": disproof_condition,
        },
        "safe_eval_condition(disproof_condition, observed_metrics)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Experiment math and disproof condition evaluator.")
    parser.add_argument("--input", required=True, help="JSON input file path")
    parser.add_argument("--mode", choices=["power", "ztest", "mwu", "disproof"], required=True)
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)

    if args.mode == "power":
        out = required_sample_size_per_arm(**payload)
    elif args.mode == "ztest":
        out = two_proportion_z_test(**payload)
    elif args.mode == "mwu":
        out = mann_whitney_u(**payload)
    else:
        out = evaluate_disproof_condition(**payload)

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
