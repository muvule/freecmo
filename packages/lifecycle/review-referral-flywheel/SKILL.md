---
name: review-referral-flywheel
description: Engineer compliant customer review velocity and CAC-capped double-sided referral loops.
category: lifecycle-cro
tier: 1
last_updated: 2026-11-16
calculators:
  - runway_churn
---

# review-referral-flywheel

## Required Inputs & Missing-Data Rules
- Required inputs: `paid_cac_usd`, `allowable_cac_usd`, `referral_invite_rate`, `referral_conversion_rate`, `referrer_reward_usd`, `friend_discount_cost_usd`, and customer happiness moment triggers (e.g., post-delivery satisfaction survey).
- Optional inputs: `current_reviews`, `current_rating`, `target_rating`, `competitor_reviews` for review acceleration goals.
- Missing-data rule: If `paid_cac_usd` or `allowable_cac_usd` is missing or `<= 0`, return `unknown` and halt referral program incentive deployment until unit CAC bounds are defined.

## Stage Preconditions & Disagreement Table
- Precondition: Run `calculators/runway_churn.py --mode referral_loop` before launching or amending customer referral incentives. Confirm review request emails and SMS sequences do not filter or suppress negative feedback.
- Disagreement table: When growth teams request higher referral reward tiers that exceed `allowable_cac_usd`, **unit economics and CAC ceiling govern**—cap the combined double-sided reward at or below allowable CAC.

## Deterministic Calculations
```bash
python3 -m calculators.runway_churn --mode referral_loop --paid-cac-usd 90 --allowable-cac-usd 80 --referral-invite-rate 0.5 --referral-conversion-rate 0.3 --referrer-reward-usd 25 --friend-discount-cost-usd 25 --current-reviews 40 --current-rating 4.3 --target-rating 4.7 --competitor-reviews 95
python3 -m calculators.runway_churn --mode referral_loop --paid-cac-usd 100 --allowable-cac-usd 60 --referral-invite-rate 0.2 --referral-conversion-rate 0.25 --referrer-reward-usd 40 --friend-discount-cost-usd 35
```

## Flash Points
- **SPEND FLASH POINT**: Double-sided referral incentives exceeding allowable CAC subsidize unprofitable customers and inflate blended customer acquisition costs.
- **COMPLIANCE FLASH POINT**: Review-gating—selectively screening unhappy customers before asking for public reviews or incentivizing positive reviews—is strictly prohibited under FTC Trade Regulation Rule on Reviews and Testimonials (`16 CFR Part 465`).

## Worked Examples

```cmo-check
calculator: runway_churn
function: compute_referral_and_review_economics
inputs:
  paid_cac_usd: 90
  allowable_cac_usd: 80
  referral_invite_rate: 0.5
  referral_conversion_rate: 0.3
  referrer_reward_usd: 25
  friend_discount_cost_usd: 25
  current_reviews: 40
  current_rating: 4.3
  target_rating: 4.7
  competitor_reviews: 95
steps:
  - k_factor = 0.5 * 0.3 = 0.15
  - effective_blended_cac_usd = 90 / 1.15 = 78.26
  - total_referral_reward_usd = 25 + 25 = 50.0 <= 80 -> reward_within_cac_ceiling = true
  - five_star_reviews_needed = ceil((4.7*40 - 4.3*40) / (5.0 - 4.7)) = 54
  - reviews_to_overtake_competitor = 95 - 40 + 1 = 56
expected:
  status: ok
  k_factor: 0.15
  effective_blended_cac_usd: 78.26
  total_referral_reward_usd: 50.0
  reward_within_cac_ceiling: true
  five_star_reviews_needed: 54
  reviews_to_overtake_competitor: 56
```

```cmo-check
calculator: runway_churn
function: compute_referral_and_review_economics
inputs:
  paid_cac_usd: 100
  allowable_cac_usd: 60
  referral_invite_rate: 0.2
  referral_conversion_rate: 0.25
  referrer_reward_usd: 40
  friend_discount_cost_usd: 35
steps:
  - k_factor = 0.2 * 0.25 = 0.05
  - effective_blended_cac_usd = 100 / 1.05 = 95.24
  - total_referral_reward_usd = 40 + 35 = 75.0 > 60 -> reward_within_cac_ceiling = false
expected:
  status: ok
  k_factor: 0.05
  effective_blended_cac_usd: 95.24
  total_referral_reward_usd: 75.0
  reward_within_cac_ceiling: false
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` providing referral program incentive caps, viral k-factor models, review pacing targets, and FTC endorsement compliance audit logs.

## Sources
- FTC Trade Regulation Rule on the Use of Consumer Reviews and Testimonials (read 2026-11-16): https://www.ftc.gov/legal-library/browse/rules/trade-regulation-rule-use-consumer-reviews-testimonials
- Google Business Profile Customer Reviews Policy (read 2026-11-16): https://support.google.com/business/answer/3474122
- FTC Endorsement Guides FAQs and What People Are Asking (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking
