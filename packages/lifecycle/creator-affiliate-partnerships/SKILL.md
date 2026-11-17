---
name: creator-affiliate-partnerships
description: Cap creator flat fees and affiliate commissions within allowable CAC, draft UGC briefs, and enforce FTC #ad rules.
category: lifecycle-cro
tier: 1
last_updated: 2026-11-16
calculators:
  - cac_ltv
  - experiment_math
---

# creator-affiliate-partnerships

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/brand-truth.md` (`status: locked`), `.agents/visual-dna.json`, `allowable_cac_usd` (from `unit-economics-floors`), `creator_flat_fee_usd`, `paid_whitelisting_cpa_usd`, `expected_conversions`, and destination URL for `connectors/utm_governance.py` (`utm_medium=creator_ugc` or `affiliate`).
- Missing-data rule: If a creator's past 10-post median views or audience geography is missing, mark `expected_conversions` conservative (`<= 0.1%` of median views) or `unknown` and propose performance-only affiliate terms (`creator_flat_fee_usd = 0`).

## Stage Preconditions & Disagreement Table
- Precondition: Run `calculators/cac_ltv.py --mode creator_cap` before signing any flat-fee sponsorship or setting affiliate commission tiers.
- Disagreement table: When a high-follower creator demands a flat sponsorship fee whose amortized cost exceeds `allowable_cac_usd`, **allowable CAC ceiling governs**—counter with a lower base fee + capped CPA bonus or walk away.

## Deterministic Calculations
```bash
python3 -m calculators.cac_ltv --mode creator_cap --input data/offload/creator_deal.json
```

## Flash Points
- **SPEND FLASH POINT**: Stacking a `25%` recurring affiliate commission on top of a `$1,500` flat creator fee and Meta Partnership Ad whitelisting spend frequently pushes blended CPA above `2x` gross-margin LTV.
- **COMPLIANCE FLASH POINT**: Every gifted product, affiliate link, or paid UGC post on Instagram, Facebook, TikTok, YouTube, LinkedIn, or blogs MUST carry an unmistakable upfront `#ad` or platform `Paid partnership` label per FTC Endorsement Guides (`16 CFR Part 255`).

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_creator_commission_cap
inputs:
  allowable_cac_usd: 90
  paid_whitelisting_cpa_usd: 25
  creator_flat_fee_usd: 200
  expected_conversions: 10
steps:
  - amortized_flat_fee = 200 / 10 = 20.0
  - max_affiliate_payout_usd = 90 - 25 - 20 = 45.0 -> viable_partnership=true
expected:
  status: ok
  amortized_flat_fee_per_conv_usd: 20.0
  max_affiliate_payout_usd: 45.0
  viable_partnership: true
```

```cmo-check
calculator: cac_ltv
function: compute_creator_commission_cap
inputs:
  allowable_cac_usd: 50
  paid_whitelisting_cpa_usd: 30
  creator_flat_fee_usd: 300
  expected_conversions: 10
steps:
  - amortized_flat_fee = 30.0; 50 - 30 - 30 = -10.0 -> viable_partnership=false
expected:
  status: ok
  amortized_flat_fee_per_conv_usd: 30.0
  max_affiliate_payout_usd: 0.0
  viable_partnership: false
```

## Output Contract & Source Receipts
Outputs Creator Deal Economics Check, 3-beat UGC Brief (`schemas/storyboard.schema.json`), governed UTM tracking link (`connectors/utm_governance.py`), and FTC disclosure checklist inside `schemas/worker_output.schema.json`.

## Sources
- FTC Endorsement Guides — Disclosures 101 for Social Media Influencers (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers
- Instagram Branded Content & Paid Partnership Label Policies (read 2026-11-16): https://help.instagram.com/116947042301556
- Meta Partnership Ads (Formerly Branded Content Ads) Help (read 2026-11-16): https://www.facebook.com/business/help/530570508280672
