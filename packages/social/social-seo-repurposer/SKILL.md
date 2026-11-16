---
name: social-seo-repurposer
description: Turn /cmo run-with-this assets and customer wins into visual-dna social SEO & storyboard drafts.
category: social
tier: 1
last_updated: 2026-11-16
calculators:
  - experiment_math
---

# social-seo-repurposer

## Required Inputs & Missing-Data Rules
- Required inputs: raw `/cmo run-with-this` note/photo/milestone, `.agents/visual-dna.json`, `.agents/brand-truth.md` (`locked`), target channel keywords.
- Missing-data rule: If a customer win lacks explicit permission or quantitative proof, anonymize client identifiers and mark missing figures `unknown`.

## Stage Preconditions & Disagreement Table
- Precondition: Requires locked `brand-truth.md`. Only posts beating 30-day median save/watch-time by `>= 2x` graduate to `meta-ads-smb-audit` paid seeding.
- Disagreement table: When chasing viral trend audio conflicts with searchable buyer-intent keywords in captions/hooks, **buyer-intent social SEO keywords govern**.

## Deterministic Calculations
```bash
python3 -m calculators.experiment_math --mode mwu --input data/offload/social_watch_mwu.json
```

## Flash Points
- **SPEND FLASH POINT**: Boosting organic posts that have NOT beaten the 30-day median engagement by `>= 2x` subsidizes weak creative with paid media.
- **COMPLIANCE FLASH POINT**: Append `(Disclosure: I built/work on <Brand>)` automatically on community cross-posts and tag synthetic/edited visuals cleanly.

## Worked Examples

```cmo-check
calculator: experiment_math
function: mann_whitney_u
inputs:
  sample_a: [12.0, 14.0, 15.0, 13.0]
  sample_b: [35.0, 40.0, 38.0, 42.0]
  alpha: 0.05
steps:
  - non-parametric watch-time comparison shows clear separation -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

```cmo-check
calculator: experiment_math
function: evaluate_disproof_condition
inputs:
  disproof_condition: "save_rate < 0.01 after 1000 impressions"
  observed_metrics:
    save_rate: 0.004
    impressions: 1200
steps:
  - save_rate 0.004 < 0.01 after 1200 impressions -> killed=true
expected:
  status: ok
  killed: true
```

## Output Contract & Source Receipts
Conforms to `schemas/storyboard.schema.json` (`9:16` / `1:1` / `16:9`) and `schemas/worker_output.schema.json`.

## Sources
- YouTube Shorts & Search Discovery Help (read 2026-11-16): https://support.google.com/youtube/answer/10059070
- LinkedIn Page Best Practices (read 2026-11-16): https://www.linkedin.com/help/linkedin/answer/a547380
