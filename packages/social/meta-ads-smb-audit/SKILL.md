---
name: meta-ads-smb-audit
description: Audit Meta Ads spend floors, Advantage+ defaults, CAPI deduplication, and 14-day stop-losses.
category: social
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - mer
---

# meta-ads-smb-audit

## Required Inputs & Missing-Data Rules
- Required inputs: Meta Ads CSV (`spend_usd`, `impressions`, `clicks`, `conversions`, `revenue_usd`), `allowable_cac_usd`, `payback_months`, `tracking_verified`.
- Missing-data rule: If CAPI event match quality or view-through vs. click-through split is absent, mark attribution `unknown`.

## Stage Preconditions & Disagreement Table
- Precondition: Requires `tracking_verified == true`, `site_load_sec < 4.0`, `payback_months <= 3.0`, and `monthly_budget_usd >= 300`.
- Disagreement table: When Meta Ads Manager 7-day click + 1-day view ROAS conflicts with blended MER or 14-day stop-loss, **blended MER and 14-day stop-loss govern**.

## Deterministic Calculations
```bash
python3 -m calculators.mer --mode stop_loss --input data/offload/meta_stoploss.json
```

## Flash Points
- **SPEND FLASH POINT**: Disable Advantage+ Audience expansion and Audience Network placements on lean SMB budgets; stage all new studies/ad sets as `PAUSED`.
- **COMPLIANCE FLASH POINT**: Housing, employment, and credit offers require Special Ad Category declarations in Meta Ads Manager.

## Worked Examples

```cmo-check
calculator: mer
function: evaluate_stop_losses
inputs:
  rules:
    - id: meta_14d
      channel: paid_social
      condition: "roas < 1.0 after_days >= 14 and spend >= 150"
      action: stage_pause
  campaigns:
    - campaign_id: spark_01
      channel: paid_social
      roas: 0.65
      days: 16
      spend: 180
steps:
  - roas 0.65 < 1.0, days 16 >= 14, spend 180 >= 150 -> alert_count = 1
expected:
  status: ok
  alert_count: 1
```

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: paid_social
  tracking_verified: true
  site_load_sec: 2.0
  payback_months: 2.5
  monthly_budget_usd: 200
steps:
  - monthly_budget_usd 200 < 300 -> unlocked=false
expected:
  status: ok
  unlocked: false
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Meta Ads CSV row ranges and `PAUSED` study payloads.

## Sources
- Meta Business Help Ad Studies & Split Testing (read 2026-11-16): https://www.facebook.com/business/help/1738164643098669
- Meta Conversions API Best Practices (read 2026-11-16): https://developers.facebook.com/docs/marketing-api/conversions-api/best-practices
