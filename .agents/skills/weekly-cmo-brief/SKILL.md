---
name: weekly-cmo-brief
description: Synthesize weekly shift ledger, stop-losses, and cohort reallocations into max 5 Composer decisions.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - mer
  - experiment_math
---

# weekly-cmo-brief

## Required Inputs & Missing-Data Rules
- Required inputs: `brand-truth.md` lock status, `experiments/ledger.jsonl`, `data/shift_ledger.jsonl`, cohort segment ROI metrics, active campaign metrics.
- Missing-data rule: Absent channel metrics remain `unknown` and cannot be used to justify budget increases.

## Stage Preconditions & Disagreement Table
- Precondition: Outputs Dual Readout (`schemas/composers_brief.schema.json`) capped at **5 ranked decisions** for human review.
- Disagreement table: When cold paid acquisition conflicts with retention win-back ROI in `calculators/mer.py`, **higher marginal segment ROI governs** and triggers dollar reallocation.

## Deterministic Calculations
```bash
python3 scripts/next_action.py --input data/offload/weekly_state.json
```

## Flash Points
- **SPEND FLASH POINT**: Never approve a weekly budget scale without checking conditional stop-losses and `Killed Assumptions` non-resurrection.
- **COMPLIANCE FLASH POINT**: Every proposed test must declare a quantitative `disproof_condition` and link verbatim `source_receipts`.

## Worked Examples

```cmo-check
calculator: mer
function: allocate_acquisition_vs_retention
inputs:
  segments:
    - segment_name: Retention_VIP
      motion: retention
      cost_usd: 500
      incremental_gross_profit_usd: 2000
    - segment_name: Cold_Broad
      motion: cold_acquisition
      cost_usd: 500
      incremental_gross_profit_usd: 1000
  reallocation_pool_usd: 300
steps:
  - Retention_VIP ROI = (2000 - 500)/500 * 100 = 300%
  - Cold_Broad ROI = (1000 - 500)/500 * 100 = 100%
  - Delta = 200pp; shift $300
expected:
  status: ok
```

```cmo-check
calculator: experiment_math
function: evaluate_disproof_condition
inputs:
  disproof_condition: "ctr < 0.005 after 2500 impressions"
  observed_metrics:
    ctr: 0.003
    impressions: 3000
steps:
  - ctr 0.003 < 0.005 and impressions 3000 >= 2500 -> killed=true
expected:
  status: ok
  killed: true
```

## Output Contract & Source Receipts
Must validate against `schemas/composers_brief.schema.json` (max 5 Human Readout decisions + machine-readable Agent Brief).

## Sources
- Google Ads Experiments Overview (read 2026-11-16): https://developers.google.com/google-ads/api/docs/campaigns/experiments/overview
- Meta Experiments & A/B Testing Docs (read 2026-11-16): https://www.facebook.com/business/help/1738164643098669
