---
name: search-term-negative-miner
description: Mine Google Ads search term reports via n-gram clustering to cut zero-conversion waste spend.
category: search-paid
tier: 1
last_updated: 2026-11-16
calculators:
  - ngram_waste
---

# search-term-negative-miner

## Required Inputs & Missing-Data Rules
- Required inputs: normalized Search Terms CSV (`search_term`, `spend_usd`, `clicks`, `conversions`), `allowable_cac_usd`.
- Missing-data rule: Rows with missing spend or conversions are skipped and noted as `unknown`; never infer conversions from clicks.

## Stage Preconditions & Disagreement Table
- Precondition: Requires >=14 days of search term data and `allowable_cac_usd > 0`.
- Disagreement table: When single-word broad negatives risk blocking profitable exact queries, **2-gram negative phrase matches govern** unless the 1-gram has zero conversions across >=3 terms.

## Deterministic Calculations
```bash
python3 -m calculators.ngram_waste --input data/offload/search_terms.json
```

## Flash Points
- **SPEND FLASH POINT**: Broad match + PMax search themes routinely bleed 20–40% of SMB spend on `"free"`, `"login"`, `"jobs"`, and competitor support queries.
- **COMPLIANCE FLASH POINT**: Verify proposed negative keywords do not inadvertently block brand-safety or legally required product terms.

## Worked Examples

```cmo-check
calculator: ngram_waste
function: mine_ngram_waste
inputs:
  search_terms:
    - search_term: free invoice template
      spend_usd: 75
      clicks: 20
      conversions: 0
    - search_term: free invoice pdf
      spend_usd: 55
      clicks: 15
      conversions: 0
  allowable_cac_usd: 100
steps:
  - "free invoice" spend = 130 >= 100, clicks = 35 >= 10, conv = 0
expected:
  status: ok
  total_zero_conv_spend_usd: 130.0
  flagged_count: 3
```

```cmo-check
calculator: ngram_waste
function: mine_ngram_waste
inputs:
  search_terms:
    - search_term: enterprise accounting software
      spend_usd: 120
      clicks: 12
      conversions: 2
  allowable_cac_usd: 100
steps:
  - conversions == 2 -> total_zero_conv_spend_usd = 0, flagged_count = 0
expected:
  status: ok
  total_zero_conv_spend_usd: 0.0
  flagged_count: 0
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Search Terms report CSV row numbers per proposed negative.

## Sources
- Google Ads Search Terms Report Help (read 2026-11-16): https://support.google.com/google-ads/answer/2472708
- Google Ads Negative Keywords Match Types (read 2026-11-16): https://support.google.com/google-ads/answer/2453972
