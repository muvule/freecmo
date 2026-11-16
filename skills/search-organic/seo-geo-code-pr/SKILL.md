---
name: seo-geo-code-pr
description: Stage isolated git branch PRs adding canonicals, meta tags, FAQPage JSON-LD, and AI robots.txt.
category: search-organic
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - experiment_math
---

# seo-geo-code-pr

## Required Inputs & Missing-Data Rules
- Required inputs: local website repository path, approved entity-gap roadmap from `aeo-entity-readiness`, `tracking_verified`, `site_load_sec`, base commit SHA.
- Missing-data rule: If framework/template routing cannot be verified cleanly in the repo, mark target paths `unknown` and abort PR staging.

## Stage Preconditions & Disagreement Table
- Precondition: Requires `brand-truth.md` `status: locked`, clean git working tree, non-`main` branch (`cmo/seo-geo-fixes-<date>`), and `allowed_paths` scoped strictly to content/SEO/robots files.
- Disagreement table: If an existing page has high paid conversion volume (`>= 3`) and thin organic meta/schema, **enrich existing canonical URL rather than creating duplicate doorway pages**.

## Deterministic Calculations
```bash
python3 -m calculators.budget_gate --input data/offload/seo_pr_gate.json
```

## Flash Points
- **SPEND FLASH POINT**: Publishing duplicate comparison URLs splits internal PageRank and cannibalizes paid landing quality scores.
- **COMPLIANCE FLASH POINT**: Never commit directly to `main`/`master`, never touch `.env*`, auth, or billing files, and verify `FAQPage` JSON-LD matches visible page text verbatim.

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: seo_geo
  tracking_verified: true
  site_load_sec: 1.4
  payback_months: 1.5
  monthly_budget_usd: 0
steps:
  - site_load_sec 1.4 < 4.0 and tracking_verified=true -> unlocked=true
expected:
  status: ok
  unlocked: true
```

```cmo-check
calculator: experiment_math
function: required_sample_size_per_arm
inputs:
  baseline_rate: 0.03
  relative_mde: 0.30
  alpha: 0.05
  power: 0.80
steps:
  - organic CTR test from 3.0% to 3.9% requires deterministic sample per arm
expected:
  status: ok
  n_per_arm: 6455
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing git branch name, base SHA, modified file paths, and `data/rollbacks/<action_id>.json`.

## Sources
- Google Search Central Robots.txt Specification (read 2026-11-16): https://developers.google.com/search/docs/crawling-indexing/robots/intro
- Google Search Central Structured Data Policies (read 2026-11-16): https://developers.google.com/search/docs/appearance/structured-data/sd-policies
- Google Search Central Canonicalization Docs (read 2026-11-16): https://developers.google.com/search/docs/crawling-indexing/canonicalization
