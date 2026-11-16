---
name: email-deliverability-flows
description: Audit SPF/DKIM/DMARC sender health, retention flow ROI, and VIP relationship exclusions.
category: lifecycle-cro
tier: 1
last_updated: 2026-11-16
calculators:
  - mer
  - experiment_math
---

# email-deliverability-flows

## Required Inputs & Missing-Data Rules
- Required inputs: DNS auth status (`SPF`, `DKIM`, `DMARC`), spam complaint rate, cohort segment ROI (`calculators/mer.py`), `.agents/guardrails.yaml` VIP list.
- Missing-data rule: If spam rate or DMARC alignment is unverified, mark deliverability `unknown` and block bulk promotional sends.

## Stage Preconditions & Disagreement Table
- Precondition: Requires verified `SPF + DKIM + DMARC` and one-click unsubscribe headers (RFC 8058) per Gmail/Yahoo bulk sender rules.
- Disagreement table: When outbound cold sequences conflict with retention lifecycle flows or VIP exclusions, **retention flows and VIP guardrails govern**.

## Deterministic Calculations
```bash
python3 -m calculators.mer --mode allocate --input data/offload/retention_alloc.json
```

## Flash Points
- **SPEND FLASH POINT**: Scaling cold acquisition while post-purchase/win-back flows are broken leaves the highest-ROI revenue uncaptured.
- **COMPLIANCE FLASH POINT**: Never cold-pitch `protected_relationships` (`vip_domains`, `vip_contacts_csv`, `never_cold_pitch_segments`), enforce one-click unsubscribe, and stay below Gmail/Yahoo `0.3%` spam complaint threshold.

## Worked Examples

```cmo-check
calculator: mer
function: allocate_acquisition_vs_retention
inputs:
  segments:
    - segment_name: Winback_Seg_A
      motion: retention
      cost_usd: 200
      incremental_gross_profit_usd: 900
    - segment_name: Cold_Seg_C
      motion: cold_acquisition
      cost_usd: 500
      incremental_gross_profit_usd: 750
  reallocation_pool_usd: 200
steps:
  - Winback_Seg_A ROI = 350% vs Cold_Seg_C ROI = 50% -> shift $200
expected:
  status: ok
```

```cmo-check
calculator: experiment_math
function: two_proportion_z_test
inputs:
  control_conversions: 25
  control_trials: 1000
  variant_conversions: 55
  variant_trials: 1000
steps:
  - plain-text win-back lifted order rate from 2.5% to 5.5% -> statistically_significant=true
expected:
  status: ok
  statistically_significant: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` citing Klaviyo/ESP flow exports, DNS records, and VIP exclusion checks.

## Sources
- Gmail Email Sender Guidelines (read 2026-11-16): https://support.google.com/a/answer/81126
- IETF RFC 8058 One-Click Unsubscribe (read 2026-11-16): https://datatracker.ietf.org/doc/html/rfc8058
- Klaviyo Deliverability & Authentication Docs (read 2026-11-16): https://help.klaviyo.com/hc/en-us/articles/115005077547
