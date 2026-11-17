---
name: comms-press-release-writer
description: Draft AP-style press releases, launch announcements, media pitches, and incident comms grounded in verified facts.
category: content-comms
tier: 2
last_updated: 2026-11-16
calculators:
  - experiment_math
  - cac_ltv
---

# comms-press-release-writer

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/brand-truth.md` (`status: locked`), announcement milestone (product release, funding, partnership, benchmark study, or customer/security update), dateline city/date, embargo status (`FOR IMMEDIATE RELEASE` vs. `EMBARGOED UNTIL <UTC timestamp>`), approved spokesperson name/title, and media contact email.
- Missing-data rule: Every financial figure, customer logo, security certification, or performance claim MUST have a verified `[STONE]` receipt. If partner sign-off or metric verification is pending, mark `[PENDING PARTNER/LEGAL VERIFICATION — DO NOT DISTRIBUTE]` and `unknown`.

## Stage Preconditions & Disagreement Table
- Precondition: Tier 2 public communications require 4-Lens Reviewer (`Claims & Disclosure QA`) and explicit Composer sign-off (`connectors/approval_gate.py`) before wire distribution or journalist outreach. Never contact journalists listed in `protected_relationships` without Composer approval.
- Mandatory AP-style structure:
  1. **Release Header:** `FOR IMMEDIATE RELEASE` or explicit embargo timestamp.
  2. **Headline (`<= 100` chars) & Subheadline:** Concrete news verb; zero superlatives ("revolutionary", "world-first", "game-changing").
  3. **Dateline & Factual Lead Paragraph:** `CITY — Month Day, Year —` answering Who, What, When, Where, and Why it matters to customers in 2–3 sentences.
  4. **Proof Body (`[STONE]`):** Verified product capabilities, pricing/availability, or methodology-backed data.
  5. **Executive & Customer Quotes (`[OPINION]`):** Human perspective (never robotic restatements of the lead); customer quotes require written approval.
  6. **Boilerplate, Press Kit Links (`utm_medium=press_release`), & Media Contact (`###` end mark).**
- Disagreement table: When promotional hype conflicts with journalistic verifiability, **journalistic verifiability and AP factual restraint govern**.

## Deterministic Calculations
```bash
python3 -m calculators.cac_ltv --aov-usd 150 --gross-margin-pct 75 --repeat-orders 2
```

## Flash Points
- **SPEND FLASH POINT**: Paying `$500–$1,500+` for paid newswire distribution on minor UI tweaks with no newsworthy hook, customer proof, or targeted reporter pitch wastes comms budget with near-zero earned pickups.
- **COMPLIANCE FLASH POINT**: Naming enterprise customers, partners, investors, or revenue growth percentages without written permission and `[STONE]` verification creates severe legal, FTC, and contractual exposure.

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 150
  gross_margin_pct: 75
  repeat_orders: 2
  target_payback_months: 3
  monthly_orders_per_customer: 1
steps:
  - gp_per_order = 150 * 0.75 = 112.50
  - ltv_gross_profit_usd = 112.50 * 2 = 225.0
  - verify PR wire spend cap against allowable_cac_usd = 225.0
expected:
  status: ok
  gross_profit_per_order_usd: 112.5
  ltv_gross_profit_usd: 225.0
  allowable_cac_usd: 225.0
```

```cmo-check
calculator: experiment_math
function: evaluate_disproof_condition
inputs:
  disproof_condition: "media_reply_rate < 0.05 and pitches >= 40"
  observed_metrics:
    media_reply_rate: 0.02
    pitches: 45
steps:
  - media_reply_rate 0.02 < 0.05 and pitches 45 >= 40 -> angle killed=true
expected:
  status: ok
  killed: true
```

## Output Contract & Source Receipts
Outputs AP-style Press Release Markdown, 3-sentence personalized journalist pitch email, and FAQ Q&A sheet conforming to `schemas/worker_output.schema.json` with `[STONE]` receipts per factual claim.

## Sources
- Associated Press Stylebook Official Reference (read 2026-11-16): https://www.apstylebook.com/
- FTC Truth in Advertising & Substantiation Guidance (read 2026-11-16): https://www.ftc.gov/business-guidance/advertising-marketing/truth-advertising
- SEC Regulation FD Fair Disclosure Overview (read 2026-11-16): https://www.sec.gov/rules-regulations/2000/08/selective-disclosure-insider-trading
