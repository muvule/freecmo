---
name: google-ads-smb-audit
description: Audit SMB Google Ads campaigns for budget floors, conversion volume, and auto-apply traps.
category: search-paid
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - cac_ltv
---

# google-ads-smb-audit

## Required Inputs & Missing-Data Rules
- Required inputs: `tracking_verified`, `site_load_sec`, `payback_months`, `monthly_conversions`, `monthly_budget_usd`, `aov_usd`, `gross_margin_pct`.
- Missing-data rule: Missing Auction Insights or conversion lag must be marked `unknown`.

## Stage Preconditions & Disagreement Table
- Precondition: Requires `tracking_verified == true`, `site_load_sec < 4.0`, and `monthly_budget_usd >= 300`.
- Disagreement table: When Google Ads recommends Target CPA/ROAS with `< 30` monthly conversions, **the 30-conversion floor governs** (`bidding_mode = manual_or_max_clicks`).

## Deterministic Calculations
```bash
python3 -m calculators.budget_gate --input data/offload/gads_gate.json
```

## Flash Points
- **SPEND FLASH POINT**: Disable Google Ads Search Partners, Display Expansion on Search campaigns, and Auto-Apply Recommendations (`AAR`) which quietly add broad match keywords and raise budgets.
- **COMPLIANCE FLASH POINT**: All staged mutations must default to `validate_only=True` via `connectors/platform_adapters.py`.

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: paid_search
  tracking_verified: true
  site_load_sec: 1.9
  payback_months: 2.2
  max_payback_months: 3.0
  monthly_conversions: 18
  monthly_budget_usd: 900
steps:
  - unlocked=true, conversions 18 < 30 -> manual_or_max_clicks
expected:
  status: ok
  unlocked: true
  bidding_mode: manual_or_max_clicks
```

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 200
  gross_margin_pct: 50
  repeat_orders: 1.5
  target_payback_months: 3
  monthly_orders_per_customer: 1
steps:
  - gp = 100, ltv = 150, break_even_roas = 2.0
expected:
  status: ok
  allowable_cac_usd: 150.0
  break_even_roas: 2.0
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Google Ads campaign export CSV row ranges.

## Sources
- Google Ads Smart Bidding Best Practices (read 2026-11-16): https://support.google.com/google-ads/answer/7065882
- Google Ads API ExperimentService Docs (read 2026-11-16): https://developers.google.com/google-ads/api/docs/campaigns/experiments/overview
