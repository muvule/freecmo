---
name: unit-economics-floors
description: Compute allowable CAC, break-even ROAS, payback months, and cohort LTV floors before spend.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - cac_ltv
---

# unit-economics-floors

## Required Inputs & Missing-Data Rules
- Required inputs: `aov_usd`, `gross_margin_pct`, `repeat_orders`, `target_payback_months`, `monthly_orders_per_customer`.
- Optional inputs for actuals: `actual_spend_usd`, `new_customers`.
- Missing-data rule: If `aov_usd` or `gross_margin_pct` is missing or `<= 0`, return `unknown` and block paid scaling.

## Stage Preconditions & Disagreement Table
- Precondition: Always run prior to `google-ads-smb-audit` or `meta-ads-smb-audit` budget increases.
- Disagreement table: When revenue-based ROAS looks profitable but gross-margin payback exceeds `target_payback_months`, **cash payback months governs** and caps `allowable_cac_usd`.

## Deterministic Calculations
```bash
python3 -m calculators.cac_ltv --aov-usd 80 --gross-margin-pct 60 --repeat-orders 3 --target-payback-months 3 --monthly-orders-per-customer 1
```

## Flash Points
- **SPEND FLASH POINT**: Bidding to revenue ROAS (`1.5x`) on a `40%` gross margin product guarantees negative unit cash flow (`break_even_roas = 2.5x`).
- **COMPLIANCE FLASH POINT**: Never include unverified projected repeat rates in `[STONE]` financial tables; tag forecasts `[OPINION]`.

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 80
  gross_margin_pct: 60
  repeat_orders: 3
  target_payback_months: 3
  monthly_orders_per_customer: 1
  actual_spend_usd: 1200
  new_customers: 10
steps:
  - gp_per_order = 80 * 0.60 = 48
  - ltv_gp = 48 * 3 = 144
  - actual_cac = 1200 / 10 = 120
  - payback_months = 120 / 48 = 2.5
expected:
  status: ok
  allowable_cac_usd: 144.0
  actual_cac_usd: 120.0
  payback_months: 2.5
  payback_gate_pass: true
```

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 100
  gross_margin_pct: 40
  repeat_orders: 1
  target_payback_months: 3
  monthly_orders_per_customer: 1
steps:
  - break_even_roas = 1 / 0.40 = 2.5
  - allowable_cac_usd = 40.0
expected:
  status: ok
  break_even_roas: 2.5
  allowable_cac_usd: 40.0
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Shopify/Stripe CSV row ranges or accounting exports.

## Sources
- Stripe Billing & Revenue Metrics Docs (read 2026-11-16): https://docs.stripe.com/billing
- Shopify Analytics Reports Reference (read 2026-11-16): https://help.shopify.com/en/manual/reports-and-analytics/shopify-reports
