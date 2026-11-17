---
name: display-native-ad-studio
description: Guide image creation, photo/UI acquisition, IAB sizing, and copywriting for Instagram, Facebook, LinkedIn, Display & Native ads.
category: social
tier: 1
last_updated: 2026-11-16
calculators:
  - budget_gate
  - experiment_math
---

# display-native-ad-studio

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/visual-dna.json`, `.agents/brand-truth.md` (`status: locked`), target `channel_family` (`instagram_facebook_social`, `linkedin_x_social`, `google_display_iab`, or `native_discovery`), landing page URL, and unit-economics `allowable_cac_usd`.
- Missing-data rule: If product screenshots or licensed customer photos do not exist, explicitly select `ai_image_generation` or `founder_photo_shoot` with a concrete shot list; never fabricate fake UI screens or unverified before/after transformations.

## Stage Preconditions & Disagreement Table
- Precondition: Paid Display, Native, and Paid Social placements require `budget_gate.evaluate_budget_gate` (`tracking_verified == True`, `site_load_sec < 4.0`, `payback_months <= max_payback_months`) and launch strictly in `PAUSED` / `validate_only=True` state.
- Image Creation vs. Image Acquisition Decision Protocol:
  1. **Product UI Capture (`product_ui_capture`):** Best for SaaS/tools—crop tightly on the single outcome screen at `2x` retina DPI with high-contrast callout (`<= 6` words overlay).
  2. **Founder / Product Photo Shoot (`founder_photo_shoot`):** Best for physical goods, local services, and high-trust founder stories—specify natural daylight, focal length (`35mm`/`50mm`), background clutter removal, and `4:5` + `9:16` framing.
  3. **Licensed UGC (`licensed_ugc_asset`):** Best for Instagram/Facebook Reels & Feed social proof—verify written usage rights before paid boosting.
  4. **AI Image Generation (`ai_image_generation`):** Best for conceptual metaphors, editorial illustrations, and clean background scenes—lock palette to `.agents/visual-dna.json` (`#18222D`, `#2D5A4C`, `#F9F8F6`), enforce `negative_constraints` (no garbled text, no uncanny hands, no neon stock clichés), and keep text overlays separate in design layers.
- Placement Sizing & Copy Limits:
  - **Instagram & Facebook:** `9:16` (`1080x1920`, top `14%` & bottom `20%` UI-free safe zones) for Reels/Stories; `4:5` (`1080x1350`) for Portrait Feed & Carousels; `1.91:1` (`1200x628`) for Right-Column/Link shares. Hook visible in first `125` chars.
  - **Google Responsive Display & IAB Banners:** `1.91:1` (`1200x628`) + `1:1` (`1200x1200`) + static IAB sizes (`300x250`, `728x90`, `300x600`, `320x50`, `160x600`); short headline `<= 30` chars, long headline `<= 90` chars, description `<= 90` chars.
  - **Native Discovery (Taboola / Outbrain / Reddit Promoted):** `1.91:1` (`1200x628`) or `4:5` editorial photo with zero text burned into the image, curiosity-grounded factual headline (`<= 65` chars), and mandatory `Sponsored` label.
- Disagreement table: When clever visual puns conflict with instant 1.5-second offer comprehension on mobile feeds, **clear focal subject and offer legibility govern**.

## Deterministic Calculations
```bash
python3 -m calculators.budget_gate --input data/offload/display_gate.json
python3 -m calculators.experiment_math --mode sample_size --baseline-rate 0.012 --relative-mde 0.30
```

## Flash Points
- **SPEND FLASH POINT**: Launching Google Display Network or Native discovery campaigns without excluding mobile-app gaming placements (`adsenseformobileapps.com`) and setting a `2.0x allowable_cac_usd` stop-loss drains SMB budgets on accidental fat-finger clicks.
- **COMPLIANCE FLASH POINT**: Native ads and paid social posts MUST display clear `Sponsored` / `#ad` disclosures and match landing-page offer terms (FTC deceptive-doorway prohibition).

## Worked Examples

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: "paid_social"
  tracking_verified: true
  site_load_sec: 2.2
  payback_months: 1.9
  max_payback_months: 3.0
  monthly_conversions: 45
  monthly_budget_usd: 3000
steps:
  - tracking verified, load 2.2s < 4.0s, payback 1.9m <= 3.0m -> unlocked=true
expected:
  status: ok
  unlocked: true
  bidding_mode: "conversion_bidding_eligible"
```

```cmo-check
calculator: experiment_math
function: required_sample_size_per_arm
inputs:
  baseline_rate: 0.012
  relative_mde: 0.30
  alpha: 0.05
  power: 0.80
steps:
  - creative CTR split test from 1.2% to 1.56% requires 16484 impressions per arm
expected:
  status: ok
  n_per_arm: 16484
  total_sample_size: 32968
```

## Output Contract & Source Receipts
Outputs validated `schemas/creative_asset_spec.schema.json` JSON + Markdown production sheet (image generation prompt or acquisition shot list, crop dimensions, character-counted copy variants, and `connectors/utm_governance.py` URLs) inside `schemas/worker_output.schema.json`.

## Sources
- Meta Ads Guide — Instagram & Facebook Image and Video Specifications (read 2026-11-16): https://www.facebook.com/business/ads-guide/image
- Google Ads Responsive Display Ad Specifications (read 2026-11-16): https://support.google.com/google-ads/answer/7005917
- IAB New Standard Ad Unit Portfolio Specification (read 2026-11-16): https://www.iab.com/wp-content/uploads/2017/08/IABNewAdPortfolio_FINAL_2017.pdf
- FTC Native Advertising Guide for Businesses (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/native-advertising-guide-businesses
