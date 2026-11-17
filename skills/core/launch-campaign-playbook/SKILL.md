---
name: launch-campaign-playbook
description: Orchestrate T-21 to T+7 product, seasonal, and promo launches with pacing and margin circuit breakers.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - creative_fatigue
  - cac_ltv
---

# launch-campaign-playbook

## Required Inputs & Missing-Data Rules
- Required inputs: `launch_budget_usd`, `days_elapsed`, `total_launch_days`, `spend_to_date_usd`, `revenue_to_date_usd`, `gross_margin_pct`, `aov_usd`, `discount_pct`, and destination launch URLs for `connectors/utm_governance.py`.
- Optional inputs: `target_mer` (default `2.5`), list of active ad creatives with frequency and CTR telemetry for fatigue evaluation.
- Missing-data rule: If `launch_budget_usd`, `gross_margin_pct`, or `total_launch_days` is missing or `<= 0`, return `unknown` and halt automated spend scaling until unit margin floors and pacing horizons are validated.

## Stage Preconditions & Disagreement Table
- Precondition: Run `calculators/creative_fatigue.py --mode launch_pacing` and `calculators/cac_ltv.py --mode promo` before launch release and at daily check-ins (T+1 through T+7). Verify tracking QA and waitlist warm-up at T-21.
- Disagreement table: When marketing teams push to accelerate ad spend due to strong top-line revenue but pacing variance exceeds +20% and observed MER is below target, **circuit breaker pacing and unit margin floors govern**—throttle spend and rotate fatigued hooks immediately.

## Deterministic Calculations
```bash
python3 -m calculators.creative_fatigue --mode launch_pacing --launch-budget-usd 5000 --days-elapsed 4 --total-launch-days 10 --spend-to-date-usd 2600 --revenue-to-date-usd 4680 --gross-margin-pct 60 --target-mer 2.5
python3 -m calculators.cac_ltv --mode promo --aov-usd 150 --gross-margin-pct 60 --discount-pct 15
```

## Flash Points
- **SPEND FLASH POINT**: Launch campaigns overspending their daily pacing run rate while failing minimum gross-margin MER burn launch capital rapidly without recovering acquisition overhead.
- **COMPLIANCE FLASH POINT**: All promotional discount claims, countdown timers, and strike-through pricing must comply with FTC Guides Against Deceptive Pricing (`16 CFR Part 233`) and platform advertising policies.

## Worked Examples

```cmo-check
calculator: creative_fatigue
function: compute_launch_pacing_guard
inputs:
  launch_budget_usd: 5000
  days_elapsed: 4
  total_launch_days: 10
  spend_to_date_usd: 2600
  revenue_to_date_usd: 4680
  gross_margin_pct: 60
  target_mer: 2.5
steps:
  - expected_spend_to_date_usd = 5000 * (4 / 10) = 2000.0
  - pace_variance_pct = ((2600 - 2000) / 2000) * 100 = 30.0
  - observed_mer = 4680 / 2600 = 1.8
  - gross_profit_to_date_usd = 4680 * 0.60 = 2808.0
  - net_contribution_usd = 2808.0 - 2600 = 208.0
  - observed_mer < 2.5 and pace_variance_pct > 20 -> circuit_breaker_action = throttle_spend
expected:
  status: ok
  expected_spend_to_date_usd: 2000.0
  pace_variance_pct: 30.0
  observed_mer: 1.8
  gross_profit_to_date_usd: 2808.0
  net_contribution_usd: 208.0
  circuit_breaker_action: throttle_spend
```

```cmo-check
calculator: cac_ltv
function: compute_promo_breakeven
inputs:
  aov_usd: 150
  gross_margin_pct: 60
  discount_pct: 15
steps:
  - baseline_gp = 150 * 0.60 = 90.0
  - discounted_price = 150 * 0.85 = 127.5
  - discounted_gp = 127.5 - 60.0 = 67.5
  - required_volume_lift_pct = ((90.0 / 67.5) - 1.0) * 100 = 33.33
expected:
  status: ok
  baseline_gp_usd: 90.0
  discounted_gp_usd: 67.5
  required_volume_lift_pct: 33.33
  profitable_unit_margin: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` delivering T-21 to T+7 launch schedule milestones, pacing circuit breaker assessments, discount elasticity bounds, and ad platform reporting receipts.

## Sources
- Google Ads Campaign Budget and Pacing Guidelines (read 2026-11-16): https://support.google.com/google-ads/answer/2472708
- Meta Ads Delivery and Budget Pacing Systems (read 2026-11-16): https://www.facebook.com/business/help/1738164643098669
- Shopify Manual Discounts and Promotion Rules (read 2026-11-16): https://help.shopify.com/en/manual/discounts
