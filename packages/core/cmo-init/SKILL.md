---
name: cmo-init
description: Initialize brand-truth.md and visual-dna.json from URL or repo with draft_pending_review lock.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - cac_ltv
  - budget_gate
---

# cmo-init

## Required Inputs & Missing-Data Rules
- Required inputs: `website_url` or `repo_path`, `company_description`, `primary_goals`, `monthly_budget_usd`, `aov_usd`, `gross_margin_pct`.
- Missing-data rule: Any absent economic figure (`aov_usd`, `gross_margin_pct`, `repeat_orders`) MUST resolve to `unknown` inside `.agents/brand-truth.md`. Never substitute industry averages.

## Stage Preconditions & Disagreement Table
- Precondition: Run first on any new workspace before unlocking production skills. Stages `.agents/brand-truth.md` in `status: draft_pending_review` and extracts `.agents/visual-dna.json`.
- Disagreement table: If founder intuition on target CAC conflicts with 3-month cash payback (`calculators/cac_ltv.py`), **3-month cash payback governs** for SMBs without external venture runway.

## Deterministic Calculations
```bash
python3 -m calculators.cac_ltv --aov-usd 120 --gross-margin-pct 75 --repeat-orders 2 --target-payback-months 3
python3 -m calculators.budget_gate --input data/offload/gate_input.json
```

## Flash Points
- **SPEND FLASH POINT**: Launching paid creative or outbound while `brand-truth.md` is `draft_pending_review` burns cash on unverified ICP positioning.
- **COMPLIANCE FLASH POINT**: Every `[STONE]` claim in `brand-truth.md` must cite a verbatim repository file or live webpage URL; unverified claims stay `[OPINION]`.

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 120
  gross_margin_pct: 75
  repeat_orders: 2
  target_payback_months: 3
  monthly_orders_per_customer: 1
steps:
  - gross_profit_per_order = 120 * 0.75 = 90
  - ltv_gross_profit = 90 * 2 = 180
  - break_even_roas = 1 / 0.75 = 1.3333
  - allowable_cac_usd = min(180, 90 * 1 * 3) = 180
expected:
  status: ok
  allowable_cac_usd: 180.0
  break_even_roas: 1.3333
```

```cmo-check
calculator: budget_gate
function: evaluate_budget_gate
inputs:
  channel: paid_search
  tracking_verified: false
  site_load_sec: 2.2
  payback_months: 2.0
  monthly_budget_usd: 800
steps:
  - tracking_verified is false -> blocked before launch
expected:
  status: ok
  unlocked: false
```

## Output Contract & Source Receipts
Must emit JSON + Markdown matching `schemas/worker_output.schema.json` with verbatim URL/repo receipts and `disproof_condition` for every initial bet.

## Sources
- Agent Skills Open Specification (read 2026-11-16): https://agentskills.io/specification
- FTC Endorsement Guides (read 2026-11-16): https://www.ftc.gov/business-guidance/resources/ftcs-endorsement-guides-what-people-are-asking
