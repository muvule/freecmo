---
name: ad-creative-angle-matrix
description: Build visual-dna timed storyboards (0-4s/4-10s/CTA) and falsifiable ad angles from winners.
category: social
tier: 1
last_updated: 2026-11-16
calculators:
  - experiment_math
---

# ad-creative-angle-matrix

## Required Inputs & Missing-Data Rules
- Required inputs: locked `.agents/brand-truth.md`, `.agents/visual-dna.json`, `.agents/instincts.md`, competitor ad/organic winner receipts.
- Missing-data rule: Never invent customer testimonials or benchmark statistics; tag unverified angle hypotheses `[OPINION]`.

## Stage Preconditions & Disagreement Table
- Precondition: Hard-blocked while `brand-truth.md` is `draft_pending_review`. Must check `Killed Assumptions` before proposing any angle.
- Disagreement table: When generic benefit copy conflicts with timed visual proof (`0–4s` hook / `4–10s` proof / `10–15s` CTA matching `schemas/storyboard.schema.json`), **timed visual storyboard governs**.

## Deterministic Calculations
```bash
python3 -m calculators.experiment_math --mode power --input data/offload/creative_power.json
```

## Flash Points
- **SPEND FLASH POINT**: Testing 12 unpowered creative variants on a $20/day budget starves statistical power; cap tests to 2–3 distinct hooks meeting `required_sample_size_per_arm`.
- **COMPLIANCE FLASH POINT**: Reject any `visual-dna.json` forbidden tropes, AI-generated fake testimonials, or unsubstantiated superlatives.

## Worked Examples

```cmo-check
calculator: experiment_math
function: required_sample_size_per_arm
inputs:
  baseline_rate: 0.015
  relative_mde: 0.30
  alpha: 0.05
  power: 0.80
steps:
  - baseline CTR 1.5%, +30% MDE (to 1.95%) -> n_per_arm = 13141
expected:
  status: ok
  n_per_arm: 13141
```

```cmo-check
calculator: experiment_math
function: evaluate_disproof_condition
inputs:
  disproof_condition: "ctr < 0.008 after 2500 impressions"
  observed_metrics:
    ctr: 0.012
    impressions: 3000
steps:
  - ctr 0.012 >= 0.008 -> killed=false
expected:
  status: ok
  killed: false
```

## Output Contract & Source Receipts
Every creative angle MUST conform to `schemas/storyboard.schema.json` and `schemas/worker_output.schema.json` with `disproof_condition`.

## Sources
- Meta Creative Best Practices for Video Ads (read 2026-11-16): https://www.facebook.com/business/help/1009998509088829
- FTC Advertising Substantiation Policy (read 2026-11-16): https://www.ftc.gov/business-guidance/advertising-marketing
