---
name: blended-mer-reconciler
description: Reconcile blended MER, separate branded vs non-branded ROAS, and evaluate stop-loss triggers.
category: analytics
tier: 1
last_updated: 2026-11-16
calculators:
  - mer
---

# blended-mer-reconciler

## Required Inputs & Missing-Data Rules
- Required inputs: `total_revenue_usd`, `total_ad_spend_usd`.
- Optional split inputs: `branded_paid_revenue_usd`, `branded_paid_spend_usd`, `non_branded_paid_revenue_usd`, `non_branded_paid_spend_usd`, `organic_revenue_usd`.
- Missing-data rule: If `total_ad_spend_usd <= 0` or revenue is absent, return `unknown`. Never blend platform-claimed conversions without reconciling against Shopify/Stripe revenue.

## Stage Preconditions & Disagreement Table
- Precondition: Requires reconciled order revenue (Shopify/Stripe) and ad spend CSVs/MCPs covering the identical date window.
- Disagreement table: When Meta/Google platform ROAS contradicts storewide blended MER, **storewide gross revenue divided by total ad spend governs**.

## Deterministic Calculations
```bash
python3 -m calculators.mer --mode mer --input data/offload/mer_input.json
```

## Flash Points
- **SPEND FLASH POINT**: Branded search ROAS (`8x–15x`) masks unprofitable cold acquisition (`1.1x`) when blended into a single account ROAS number.
- **COMPLIANCE FLASH POINT**: Report exact date-window attribution discrepancies verbatim with `[STONE]` source receipts.

## Worked Examples

```cmo-check
calculator: mer
function: compute_blended_mer
inputs:
  total_revenue_usd: 40000
  total_ad_spend_usd: 10000
  branded_paid_revenue_usd: 10000
  branded_paid_spend_usd: 1000
  non_branded_paid_revenue_usd: 18000
  non_branded_paid_spend_usd: 9000
  organic_revenue_usd: 12000
steps:
  - blended_mer = 40000 / 10000 = 4.0
  - branded_roas = 10000 / 1000 = 10.0
  - non_branded_roas = 18000 / 9000 = 2.0
  - organic_revenue_share_pct = 12000 / 40000 * 100 = 30.0
expected:
  status: ok
  blended_mer: 4.0
  branded_roas: 10.0
  non_branded_roas: 2.0
  organic_revenue_share_pct: 30.0
```

```cmo-check
calculator: mer
function: evaluate_stop_losses
inputs:
  rules:
    - id: sl_14d
      channel: paid_social
      condition: "roas < 1.0 after_days >= 14 and spend >= 150"
      action: stage_pause
  campaigns:
    - campaign_id: camp_a
      channel: paid_social
      roas: 0.8
      days: 15
      spend: 200
steps:
  - 0.8 < 1.0, days 15 >= 14, spend 200 >= 150 -> alert_count = 1
expected:
  status: ok
  alert_count: 1
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` referencing revenue & spend export row ranges.

## Sources
- Google Analytics 4 Attribution Overview (read 2026-11-16): https://support.google.com/analytics/answer/10596866
- Stripe Revenue Analytics Docs (read 2026-11-16): https://docs.stripe.com/billing/revenue-recognition
