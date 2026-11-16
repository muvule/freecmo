---
name: aeo-entity-readiness
description: Score 10-prompt AI citation share, entity gaps, and answer-first page priorities for GEO/AEO.
category: search-organic
tier: 1
last_updated: 2026-11-16
calculators:
  - experiment_math
  - budget_gate
---

# aeo-entity-readiness

## Required Inputs & Missing-Data Rules
- Required inputs: `brand_name`, `brand_domain`, competitor list, 10-prompt benchmark output (`scripts/geo_benchmark.py`).
- Missing-data rule: Never claim an AI model cites the brand without verbatim prompt/response logs; missing model results stay `unknown`.

## Stage Preconditions & Disagreement Table
- Precondition: Requires locked `brand-truth.md` `[STONE]` facts and `scripts/geo_benchmark.py` score `< 5/10`.
- Disagreement table: When long-form narrative prose conflicts with structured answer-first blocks + comparison tables, **answer-first 40–60 word definitions + cited comparison tables govern**.

## Deterministic Calculations
```bash
python3 scripts/geo_benchmark.py --fixture data/offload/geo_fixture.json
python3 -m calculators.experiment_math --mode ztest --input data/offload/geo_ztest.json
```

## Flash Points
- **SPEND FLASH POINT**: Paying PR agencies for generic backlinks while `robots.txt` blocks `GPTBot`/`ClaudeBot`/`PerplexityBot` wastes GEO budget.
- **COMPLIANCE FLASH POINT**: Every competitor comparison cell must cite primary pricing/docs URLs or mark unverified competitor features `unknown`.

## Worked Examples

```cmo-check
calculator: experiment_math
function: two_proportion_z_test
inputs:
  control_conversions: 2
  control_trials: 40
  variant_conversions: 16
  variant_trials: 40
steps:
  - citation share jumped from 2/40 (5%) to 16/40 (40%) -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: seo_geo
  tracking_verified: true
  site_load_sec: 1.5
  payback_months: 1.0
  monthly_budget_usd: 0
steps:
  - fast site + verified tracking -> seo_geo unlocked=true
expected:
  status: ok
  unlocked: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing `geo_benchmark.py` prompt/response logs and competitor URLs.

## Sources
- Google Search AI Features & Structured Data Docs (read 2026-11-16): https://developers.google.com/search/docs/appearance/ai-features
- Schema.org FAQPage Specification (read 2026-11-16): https://schema.org/FAQPage
