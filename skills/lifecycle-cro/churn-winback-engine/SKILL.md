---
name: churn-winback-engine
description: Diagnose logo churn, NRR, J-curve ad-scaling cash troughs, and margin-safe winback sequences.
category: lifecycle-cro
tier: 1
last_updated: 2026-11-16
calculators:
  - runway_churn
  - cac_ltv
---

# churn-winback-engine

## Required Inputs & Missing-Data Rules
- Required inputs: `starting_mrr_usd`, `monthly_logo_churn_pct`, `monthly_revenue_churn_pct`, `available_cash_usd`, `monthly_ad_spend_usd`, `allowable_cac_usd`, `monthly_gross_profit_per_customer_usd`, and cancellation reason telemetry.
- Optional inputs: `monthly_expansion_pct`, `new_customers_per_month`, `horizon_months`, `fixed_marketing_ops_usd`, and `.agents/guardrails.yaml` VIP list (`vip_domains`, `vip_contacts_csv`, `never_cold_pitch_segments`).
- Missing-data rule: If `starting_mrr_usd`, churn rates, or cash runway inputs are missing or `<= 0`, return `unknown` and halt aggressive ad spend expansion until unit churn and runway metrics are quantified.

## Stage Preconditions & Disagreement Table
- Precondition: Run `calculators/runway_churn.py --mode churn_nrr` and `--mode cash_runway` before authorizing paid acquisition budget increases. Always verify cancellation save flows (offer account pause or plan downgrade before discounts).
- Disagreement table: When top-line customer acquisition growth looks high but logo churn exceeds 8%/month or cash balance breaches the J-curve trough minimum, **cash runway and retention floors govern**—freeze budget expansion and reallocate into 30/60/90-day winback cohorts and retention flows.

## Deterministic Calculations
```bash
python3 -m calculators.runway_churn --mode churn_nrr --starting-mrr-usd 20000 --monthly-logo-churn-pct 9.0 --monthly-revenue-churn-pct 7.0 --monthly-expansion-pct 2.0 --new-customers-per-month 18
python3 -m calculators.runway_churn --mode cash_runway --available-cash-usd 15000 --monthly-ad-spend-usd 4000 --allowable-cac-usd 100 --monthly-gross-profit-per-customer-usd 40 --monthly-logo-churn-pct 5.0 --horizon-months 6 --fixed-marketing-ops-usd 0
```

## Flash Points
- **SPEND FLASH POINT**: Scaling top-of-funnel ad spend into a leaky bucket (monthly logo churn `>= 8%` or monthly NRR `< 95%`) accelerates burn through the J-curve cash trough and triggers premature runway exhaustion before cohort gross profits can compound.
- **COMPLIANCE FLASH POINT**: Winback email and SMS cadences must honor FTC CAN-SPAM requirements, provide visible one-click unsubscribe headers per RFC 8058, strictly respect opt-outs within 10 business days, and exclude all VIP accounts listed in `.agents/guardrails.yaml`.

## Worked Examples

```cmo-check
calculator: runway_churn
function: compute_churn_and_nrr
inputs:
  starting_mrr_usd: 20000
  monthly_logo_churn_pct: 9.0
  monthly_revenue_churn_pct: 7.0
  monthly_expansion_pct: 2.0
  new_customers_per_month: 18
steps:
  - monthly_grr_pct = 100.0 - 7.0 = 93.0
  - monthly_nrr_pct = 100.0 - 7.0 + 2.0 = 95.0
  - net_mrr_after_1m_usd = 20000 * 0.95 = 19000.0
  - steady_state_customer_ceiling = 18 / 0.09 = 200.0
  - logo_churn >= 8.0 -> leaky_bucket_alert = true
expected:
  status: ok
  monthly_grr_pct: 93.0
  monthly_nrr_pct: 95.0
  net_mrr_after_1m_usd: 19000.0
  steady_state_customer_ceiling: 200.0
  leaky_bucket_alert: true
```

```cmo-check
calculator: runway_churn
function: simulate_cash_flow_runway
inputs:
  available_cash_usd: 15000
  monthly_ad_spend_usd: 4000
  allowable_cac_usd: 100
  monthly_gross_profit_per_customer_usd: 40
  monthly_logo_churn_pct: 5.0
  horizon_months: 6
  fixed_marketing_ops_usd: 0
steps:
  - new_cohort = 4000 / 100 = 40 customers/month
  - month 1 active 40.0 net -2400.0 cum -2400.0
  - month 2 active 78.0 net -880.0 cum -3280.0 (trough)
  - month 3 active 114.1 net +564.0 (monthly breakeven) cum -2716.0
  - month 5 cumulative net +2458.81 (cumulative payback)
  - max cash trough = 3280.0, min cash balance = 11720.0 >= 4000 -> runway safe
expected:
  status: ok
  max_cash_trough_usd: 3280.0
  min_cash_balance_usd: 11720.0
  monthly_breakeven_month: 3
  cumulative_payback_month: 5
  runway_safe: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` delivering subscription churn diagnostics, J-curve cash-runway projection tables, 30/60/90-day winback sequencing recommendations, and Stripe/payment processor receipts.

## Sources
- Stripe Billing Subscriptions Cancellation & Retention (read 2026-11-16): https://docs.stripe.com/billing/subscriptions/cancel
- FTC CAN-SPAM Act Compliance Guide for Business (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- IETF RFC 8058 Signaling One-Click Functionality for List-Unsubscribe (read 2026-11-16): https://datatracker.ietf.org/doc/html/rfc8058
