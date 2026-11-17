---
name: competitor-battlecard-pricing
description: Build factual competitor comparison battlecards and calculate promo/discount gross-margin break-even lift.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - cac_ltv
---

# competitor-battlecard-pricing

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/brand-truth.md` (`status: locked`), `aov_usd`, `gross_margin_pct`, proposed `discount_pct` (if evaluating a promotion), and sanitized competitor pricing/feature pages wrapped via `connectors/sanitizer.py`.
- Missing-data rule: Any competitor limit, hidden fee, or SLA not verified on a dated primary vendor page MUST be marked `unknown`—never disparage competitors with unverified claims.

## Stage Preconditions & Disagreement Table
- Precondition: Run `calculators/cac_ltv.py --mode promo` before approving any seasonal discount, Black Friday offer, or competitive price-match campaign.
- Disagreement table: When matching a competitor's `30%` discount pushes post-discount unit gross margin `<= 0` (or requires unrealistic volume lift), **unit gross-profit preservation governs**—counter with value bundles, extended onboarding, or migration guarantees instead of margin-destroying discounts.

## Deterministic Calculations
```bash
python3 -m calculators.cac_ltv --mode promo --aov-usd 120 --gross-margin-pct 60 --discount-pct 20
```

## Flash Points
- **SPEND FLASH POINT**: Running a `20%` sitewide discount on a `30%` gross-margin product cuts unit gross profit by `66.7%`, requiring a `+200%` volume surge (`3x` baseline orders) just to make the same gross profit dollars—before counting ad spend!
- **COMPLIANCE FLASH POINT**: Comparative advertising tables MUST cite the exact date and public URL of each competitor pricing tier (`[STONE]`) to comply with FTC comparative-substantiation rules.

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_promo_breakeven
inputs:
  aov_usd: 120
  gross_margin_pct: 60
  discount_pct: 20
steps:
  - baseline_gp = 72.0, cogs = 48.0, discounted_price = 96.0, discounted_gp = 48.0
  - required_volume_lift_pct = ((72 / 48) - 1) * 100 = 50.0%
expected:
  status: ok
  profitable_unit_margin: true
  baseline_gp_usd: 72.0
  discounted_gp_usd: 48.0
  required_volume_lift_pct: 50.0
```

```cmo-check
calculator: cac_ltv
function: compute_promo_breakeven
inputs:
  aov_usd: 100
  gross_margin_pct: 25
  discount_pct: 30
steps:
  - baseline_gp = 25.0, cogs = 75.0, discounted_price = 70.0 -> discounted_gp = -5.0 (negative margin!)
expected:
  status: ok
  profitable_unit_margin: false
  discounted_gp_usd: -5.0
  required_volume_lift_pct: "impossible_negative_margin"
```

## Output Contract & Source Receipts
Outputs structured Sales/Landing-Page Battlecard Matrix + Promo Break-Even verdict conforming to `schemas/worker_output.schema.json` with dated competitor URL receipts.

## Sources
- FTC Statement of Policy Regarding Comparative Advertising (read 2026-11-16): https://www.ftc.gov/legal-library/browse/statement-policy-regarding-comparative-advertising
- Stripe Coupons & Promotion Codes Economics Docs (read 2026-11-16): https://docs.stripe.com/billing/subscriptions/coupons
