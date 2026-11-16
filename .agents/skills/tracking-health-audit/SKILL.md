---
name: tracking-health-audit
description: Verify GA4, pixel, server-side conversion integrity, site speed, and budget gate prerequisites.
category: analytics
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - experiment_math
---

# tracking-health-audit

## Required Inputs & Missing-Data Rules
- Required inputs: `tracking_verified`, `site_load_sec`, `payback_months`, `monthly_budget_usd`.
- Missing-data rule: If purchase/lead event match rate vs. backend orders is unverified, set `tracking_verified: false` (never assume tracking works).

## Stage Preconditions & Disagreement Table
- Precondition: Must pass before unlocking `paid_search` or `paid_social` scaling.
- Disagreement table: If ad-platform conversion pixel reports higher conversions than backend Stripe/Shopify orders by >15%, **backend order count governs** and triggers a tracking Circuit Breaker.

## Deterministic Calculations
```bash
python3 -m calculators.budget_gate --input data/offload/tracking_gate.json
```

## Flash Points
- **SPEND FLASH POINT**: Broken deduplication or double-firing purchase tags trick automated bidding into 2x over-bidding.
- **COMPLIANCE FLASH POINT**: Ensure consent mode / GDPR banner blocks non-essential tracking scripts prior to user consent in EU/EEA regions.

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: paid_social
  tracking_verified: true
  site_load_sec: 4.8
  payback_months: 2.0
  monthly_budget_usd: 1000
steps:
  - site_load_sec 4.8 >= 4.0 -> unlocked=false
expected:
  status: ok
  unlocked: false
```

```cmo-check
calculator: experiment_math
function: two_proportion_z_test
inputs:
  control_conversions: 50
  control_trials: 1000
  variant_conversions: 85
  variant_trials: 1000
steps:
  - significant lift from 5.0% to 8.5% -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing tag/event logs and server order reconciliation.

## Sources
- Google Analytics 4 Event Measurement Docs (read 2026-11-16): https://developers.google.com/analytics/devguides/collection/ga4
- Meta Conversions API Deduplication Docs (read 2026-11-16): https://developers.facebook.com/docs/marketing-api/conversions-api/deduplicate-pixel-and-server-events
- EU GDPR Official Regulation Text (read 2026-11-16): https://eur-lex.europa.eu/eli/reg/2016/679/oj
