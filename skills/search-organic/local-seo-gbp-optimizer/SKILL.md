---
name: local-seo-gbp-optimizer
description: Optimize Google Business Profile categories, LocalBusiness schema, and review velocity.
category: search-organic
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - experiment_math
---

# local-seo-gbp-optimizer

## Required Inputs & Missing-Data Rules
- Required inputs: primary business category, service-area/address eligibility, NAP consistency audit, `site_load_sec`, `tracking_verified`.
- Missing-data rule: Businesses without an eligible physical storefront or in-person service area must mark GBP eligibility `unknown` or ineligible—never fabricate addresses.

## Stage Preconditions & Disagreement Table
- Precondition: Only run for brick-and-mortar or verified local service-area SMBs (`brand-truth.md` `[STONE]`).
- Disagreement table: When keyword-stuffing GBP business names conflicts with Google guidelines, **exact legal brand name governs** to avoid suspension.

## Deterministic Calculations
```bash
python3 -m calculators.budget_gate --input data/offload/local_seo_gate.json
```

## Flash Points
- **SPEND FLASH POINT**: Running Local Services Ads or radius-targeted paid ads before GBP categories, hours, and call tracking are verified wastes mobile map clicks.
- **COMPLIANCE FLASH POINT**: Incentivizing positive reviews or gating negative reviews violates FTC Endorsement Guides and Google GBP policies.

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: seo_geo
  tracking_verified: true
  site_load_sec: 2.3
  payback_months: 1.0
  monthly_budget_usd: 0
steps:
  - tracking_verified=true and site_load_sec < 4.0 -> unlocked=true
expected:
  status: ok
  unlocked: true
```

```cmo-check
calculator: experiment_math
function: two_proportion_z_test
inputs:
  control_conversions: 30
  control_trials: 1000
  variant_conversions: 58
  variant_trials: 1000
steps:
  - map pack call CTR lifted from 3.0% to 5.8% -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing GBP profile fields and `LocalBusiness` JSON-LD paths.

## Sources
- Google Business Profile Guidelines (read 2026-11-16): https://support.google.com/business/answer/3038177
- Schema.org LocalBusiness Specification (read 2026-11-16): https://schema.org/LocalBusiness
- FTC Consumer Reviews Rule (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking
