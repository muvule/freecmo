---
name: offline-local-channels
description: Plan & write currency-aware WhatsApp broadcasts, GSM-7 SMS, community FM radio spots, flyers, and bulletin boards for low-connectivity & 7B-local workflows.
category: social
tier: 2
last_updated: 2026-11-18
calculators:
  - local_channels
  - cac_ltv
---

# offline-local-channels

## Required Inputs & Missing-Data Rules
- Required inputs: `.agents/brand-truth.md` (`status: locked`, including local `currency` ISO-4217 code), target offline channel (`whatsapp_broadcast`, `sms_blast`, `community_radio`, `print_flyer`, or `bulletin_board`), `aov`, `gross_margin_pct`, `total_campaign_cost`, `recipients_or_reach`, and expected `response_or_redemption_rate_pct`.
- Missing-data rule: If `aov`, `gross_margin_pct`, or `total_campaign_cost` is missing, return `"unknown"` and compute allowable CAC floors before spending cash on airtime, print runs, or carrier SMS credits.

## Stage Preconditions & Disagreement Table
- Precondition: Run `cac_ltv.compute_cac_ltv` in the founder's native `currency` (`KES`, `IDR`, `MXN`, `NGN`, `INR`, `USD`, etc.) first, then verify channel ROI via `local_channels.compute_offline_channel_economics` and message readiness via `local_channels.evaluate_low_bandwidth_readiness`.
- Channel Production Protocols (Optimized for 7B Local LLMs & Zero-Cloud Execution):
  1. **WhatsApp Business Broadcasts (`whatsapp`):** Keep under `500` chars (`1024` max) so the full offer fits above the fold on budget Android phones; state local price, cash-on-delivery / mobile-money (`M-Pesa`, `UPI`, `QRIS`, `OXXO`) option, clear reply CTA, and `Reply STOP` opt-out.
  2. **SMS Blasts (`sms`):** Enforce strict **GSM-7** ASCII encoding (`<= 160` chars per segment, `<= 2` segments). Reject curly quotes (`’`, `“`), em-dashes (`—`), and emojis—one non-GSM-7 glyph triggers **UCS-2** (`70` chars/segment) and doubles or triples SMS bills.
  3. **Community FM Radio (`radio_15s` / `radio_30s` / `radio_60s`):** Pace at `130` WPM (`<= 35` words for `15s`, `<= 70` words for `30s`, `<= 135` words for `60s`), anchor with a recognizable street landmark, and **repeat the phone/WhatsApp number or USSD code at least twice**.
  4. **Print Flyers & Community Bulletin Boards (`print_flyer` / `bulletin_board`):** Use `<= 90` words for bulletin cards (`<= 180` for flyers) with bold local price/offer, street directions, and tear-off/WhatsApp contact. Keep companion web order pages `<= 150 KB` (`html_payload_kb <= 150`) for 2G/prepaid mobile data.
- Disagreement table: When persuasive storytelling conflicts with 1-segment GSM-7 SMS limits or twice-spoken phone numbers on radio, **encoding cost control and instant contact recall govern**.

## Deterministic Calculations
```bash
python3 -m calculators.local_channels --mode economics --currency KES --channel whatsapp_broadcast --recipients-or-reach 800 --total-campaign-cost 4000 --response-or-redemption-rate-pct 3.5 --aov 1800 --gross-margin-pct 55 --allowable-cac 990
python3 -m calculators.local_channels --mode readiness --currency IDR --channel sms --message-text "Kopi Nusantara: Diskon 20% paket 1kg hari ini, bayar QRIS/COD. Balas PESAN atau kunjungi Jl. Malioboro 14. Balas STOP untuk berhenti."
```

## Flash Points
- **SPEND FLASH POINT**: Sending an SMS blast with smart curly quotes or a single emoji silently switches carrier encoding from GSM-7 (`160` chars) to UCS-2 (`70` chars), doubling or tripling per-recipient SMS spend for identical copy.
- **COMPLIANCE FLASH POINT**: WhatsApp Business broadcasts and bulk SMS blasts MUST go only to opt-in customers and include a working local-language opt-out command (`Reply STOP` / `Balas STOP` / `Jibu STOP`); unconsented blasts trigger carrier filtering and WhatsApp Business account bans.

## Worked Examples

```cmo-check
calculator: local_channels
function: compute_offline_channel_economics
inputs:
  channel: "whatsapp_broadcast"
  recipients_or_reach: 800
  total_campaign_cost: 4000
  response_or_redemption_rate_pct: 3.5
  aov: 1800
  gross_margin_pct: 55
  allowable_cac: 990
  currency: "KES"
steps:
  - expected_orders = 800 * 0.035 = 28
  - gross_revenue = 28 * 1800 = 50400 KES
  - gross_profit = 50400 * 0.55 = 27720 KES
  - net_contribution = 27720 - 4000 = 23720 KES
  - effective_cac = 4000 / 28 = 142.86 KES (<= 990 KES allowable CAC)
expected:
  status: ok
  currency: "KES"
  expected_orders: 28.0
  gross_revenue: 50400.0
  gross_profit: 27720.0
  net_contribution: 23720.0
  effective_cac: 142.86
  within_allowable_cac: true
```

```cmo-check
calculator: local_channels
function: evaluate_low_bandwidth_readiness
inputs:
  channel: "sms"
  currency: "MXN"
  include_opt_out: true
  message_text: "Panaderia Sol: 2x1 en pan dulce hoy hasta 7pm. Paga en efectivo o WhatsApp 5512345678. Envia STOP para cancelar."
steps:
  - pure GSM-7 characters (118 chars <= 160), includes CTA + STOP opt-out -> 1 SMS segment, ready=true
expected:
  status: ok
  channel: "sms"
  sms_encoding: "GSM-7"
  sms_segments: 1
  cost_multiplier_vs_gsm7: 1.0
  ready: true
```

```cmo-check
calculator: local_channels
function: evaluate_low_bandwidth_readiness
inputs:
  channel: "radio_30s"
  currency: "KES"
  message_text: "Need fresh solar milk cooling in Nakuru? Visit JuaKazi Depot next to Westside Mall today. Call or M-Pesa 0712345678 for same-day setup. That number again is 0712345678."
steps:
  - 27 words (~12.5s at 130 wpm <= 70 words) and repeats phone number 0712345678 twice -> ready=true
expected:
  status: ok
  channel: "radio_30s"
  word_count: 27
  contact_repetitions: 2
  ready: true
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` with verified local-currency unit economics from `calculators/local_channels.py` and `calculators/cac_ltv.py`, GSM-7 / radio / print compliance readout, and local-payment CTA checklist.

## Sources
- WhatsApp Business Platform Opt-In Policy & Guidelines (read 2026-11-18): https://developers.facebook.com/docs/whatsapp/overview/getting-opt-in
- 3GPP TS 23.038 Alphabets & Language-Specific Information (GSM-7 / UCS-2) (read 2026-11-18): https://www.3gpp.org/specifications-technologies
- FCC Consumer Guide — Rules for Political & Commercial Text Messages (Opt-Out Compliance) (read 2026-11-18): https://www.fcc.gov/consumers/guides/stop-unwanted-robocalls-and-texts
- web.dev — Fast Load Times & Low-Data Web Performance Budgets (read 2026-11-18): https://web.dev/articles/fast-load-times
