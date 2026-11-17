---
name: editorial-blog-linkedin-writer
description: Write answer-first SEO/GEO web blog posts, Reddit/HN forum posts, and LinkedIn articles or carousels.
category: content-comms
tier: 1
last_updated: 2026-11-16
calculators:
  - experiment_math
---

# editorial-blog-linkedin-writer

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/brand-truth.md` (`status: locked`), `.agents/instincts.md`, target search/entity topic or `radar_store.py` buyer pain cluster, verified `[STONE]` product proof or customer receipts, and destination URL for `connectors/utm_governance.py`.
- Missing-data rule: Never invent customer case-study metrics, survey percentages, or benchmark numbers. Any unverified statistic MUST be marked `unknown` or omitted; subjective commentary MUST be tagged `[OPINION]`.

## Stage Preconditions & Disagreement Table
- Precondition: Hard-blocked while `brand-truth.md` is `draft_pending_review`. Check `Killed Assumptions` before drafting so disproven positioning angles are never republished.
- Channel adaptation rules:
  - **Web Blog (SEO + GEO/AEO):** Open with a 40–60 word direct answer block for AI answer engines, include comparison tables with verifiable criteria, attach `Article` / `FAQPage` JSON-LD (`schema.org`), and link with governed `utm_medium=blog`.
  - **Forums (Reddit, Hacker News, Niche Communities):** Zero marketing jargon or breathless hooks. Lead with reproducible workflow steps, trade-offs, or raw numbers, and append explicit affiliation disclosure.
  - **LinkedIn (Long-Form Post & `4:5` Document Carousel):** Concrete problem/lesson in lines 1–2 (before the fold), scannable takeaways, and zero engagement-bait ("Comment YES below").
- Disagreement table: When keyword-density targets conflict with factual clarity or human readability, **direct answer clarity and primary proof govern**.

## Deterministic Calculations
```bash
python3 -m calculators.experiment_math --mode sample_size --baseline-rate 0.025 --relative-mde 0.25
```

## Flash Points
- **SPEND FLASH POINT**: Commissioning or promoting generic "Ultimate Guide" AI-slop blog posts with zero original data, screenshots, or `[STONE]` receipts wastes crawl budget and paid content amplification dollars.
- **COMPLIANCE FLASH POINT**: Every forum post (Reddit, HN, community Slack/Discord) MUST include `(Disclosure: I work on <Brand>)` and strictly follow subreddit/forum self-promotion rules.

## Worked Examples

```cmo-check
calculator: experiment_math
function: required_sample_size_per_arm
inputs:
  baseline_rate: 0.025
  relative_mde: 0.25
  alpha: 0.05
  power: 0.80
steps:
  - blog CTA conversion test from 2.5% to 3.125% requires 10984 readers per arm
expected:
  status: ok
  n_per_arm: 10984
  total_sample_size: 21968
```

```cmo-check
calculator: experiment_math
function: evaluate_disproof_condition
inputs:
  disproof_condition: "organic_ctr < 0.015 after 2000 impressions"
  observed_metrics:
    organic_ctr: 0.009
    impressions: 2400
steps:
  - organic_ctr 0.009 < 0.015 after 2400 impressions -> headline/angle killed=true
expected:
  status: ok
  killed: true
```

## Output Contract & Source Receipts
Outputs structured Markdown drafts (Web Blog + `Article` JSON-LD, Forum post with disclosure, and LinkedIn post/carousel outline) plus `schemas/worker_output.schema.json` citing exact `brand-truth.md` or `radar.db` Source Receipts.

## Sources
- Google Search Helpful, Reliable, People-First Content Guide (read 2026-11-16): https://developers.google.com/search/docs/fundamentals/creating-helpful-content
- Schema.org Article Structured Data Specification (read 2026-11-16): https://schema.org/Article
- LinkedIn Publishing & Page Best Practices (read 2026-11-16): https://www.linkedin.com/help/linkedin/answer/a547380
- Reddit Rules on Authentic Participation & Self-Promotion (read 2026-11-16): https://support.reddithelp.com/hc/en-us/articles/360043504051-What-constitutes-spam-Am-I-a-spammer
