---
name: landing-page-cro-audit
description: Audit landing page speed, above-the-fold CTA clarity, offer friction, and A/B test power.
category: lifecycle-cro
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - experiment_math
---

# landing-page-cro-audit

## Required Inputs & Missing-Data Rules
- Required inputs: target URL or template path, `site_load_sec`, `tracking_verified`, baseline landing conversion rate, monthly sessions.
- Missing-data rule: Never guess baseline conversion rate or session counts; mark absent telemetry `unknown` and block A/B test launch if `n_per_arm` exceeds 60 days of traffic.

## Stage Preconditions & Disagreement Table
- Precondition: Run before scaling paid traffic if `site_load_sec >= 4.0` or landing conversion rate is below break-even CAC threshold.
- Disagreement table: When aesthetic redesign requests conflict with page load speed (`< 4.0s`) and single primary CTA clarity, **load speed `< 4.0s` and offer clarity govern**.

## Deterministic Calculations
```bash
python3 -m calculators.experiment_math --mode power --input data/offload/cro_power.json
python3 -m calculators.budget_gate --input data/offload/cro_gate.json
```

## Flash Points
- **SPEND FLASH POINT**: Sending cold paid clicks to a slow (`>= 4.0s`) multi-CTA homepage burns acquisition budget before the hero even paints.
- **COMPLIANCE FLASH POINT**: Avoid fake urgency countdowns, dark-pattern pre-checked boxes, and unverified social proof badges.

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: cro
  tracking_verified: true
  site_load_sec: 4.5
  payback_months: 2.0
  monthly_budget_usd: 0
steps:
  - site_load_sec 4.5 >= 4.0 blocks scaling -> unlocked=false
expected:
  status: ok
  unlocked: false
```

```cmo-check
calculator: experiment_math
function: two_proportion_z_test
inputs:
  control_conversions: 40
  control_trials: 1000
  variant_conversions: 70
  variant_trials: 1000
steps:
  - CVR lifted from 4.0% to 7.0% -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Core Web Vitals/Lighthouse measurements and PostHog/GA4 funnel exports.

## Sources
- Google Search Core Web Vitals Docs (read 2026-11-16): https://developers.google.com/search/docs/appearance/core-web-vitals
- PostHog Experimentation Statistical Significance Docs (read 2026-11-16): https://posthog.com/docs/experiments/statistical-significance
