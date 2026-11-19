"""Deterministic offline-first & low-bandwidth channel economics and readiness validator.

Supports WhatsApp Business broadcasts, GSM-7 vs UCS-2 SMS segmentation,
community FM radio spots, print flyers, neighborhood bulletin boards, and
low-data (2G/3G prepaid) page weight checks across any ISO-4217 currency.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import sys
from typing import Any

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from calculators import (
    currency_symbol,
    format_money,
    normalize_currency,
    ok_result,
    resolve_amount,
    round_money,
    to_float,
    unknown_result,
)


SUPPORTED_ECONOMICS_CHANNELS = (
    "whatsapp_broadcast",
    "sms_blast",
    "community_radio",
    "print_flyer",
    "bulletin_board",
)

SUPPORTED_READINESS_CHANNELS = (
    "whatsapp",
    "sms",
    "radio_15s",
    "radio_30s",
    "radio_60s",
    "print_flyer",
    "bulletin_board",
)

# Standard 3GPP TS 23.038 GSM 7-bit Default Alphabet + Extension Table
_GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
_GSM7_EXT = set("^{}\\[~]|€")

_RADIO_WORD_CAPS = {
    "radio_15s": (35, 15),
    "radio_30s": (70, 30),
    "radio_60s": (135, 60),
}

_OPT_OUT_RE = re.compile(r"\b(stop|opt[- ]?out|unsubscribe|cancel|reply\s+no|stopp|alto|batal|acha)\b", re.IGNORECASE)
_CTA_RE = re.compile(
    r"\b(reply|order|book|call|visit|text|whatsapp|sms|send|claim|show|bring|wa\.me|m-?pesa|upi|cash|cod)\b|\+?[0-9][0-9 \-]{5,}",
    re.IGNORECASE,
)
_PRICE_OR_OFFER_RE = re.compile(
    r"(%|free|off|discount|save|promo|deal|buy\s+\d+|[\$€£¥₹₦₱₫]|ksh|rp\b|mx\$|tsh|ush|r\$|gh₵)",
    re.IGNORECASE,
)
_PHONE_OR_CODE_RE = re.compile(r"(?:\+?\d[\d\s-]{5,}\d|\*\d{3,4}(?:\*\d+)*#?)")


def analyze_sms_segments(text: str) -> dict[str, Any]:
    """Classify SMS text as GSM-7 (160/153 chars) or UCS-2 (70/67 chars) and flag cost-doubling characters."""
    septets = 0
    non_gsm7: list[str] = []
    for ch in text:
        if ch in _GSM7_BASIC:
            septets += 1
        elif ch in _GSM7_EXT:
            septets += 2
        else:
            non_gsm7.append(ch)

    if non_gsm7:
        encoding = "UCS-2"
        char_len = len(text)
        segments = 1 if char_len <= 70 else math.ceil(char_len / 67)
        gsm7_equiv_segments = 1 if len(text) <= 160 else math.ceil(len(text) / 153)
        cost_mult = round(segments / max(1, gsm7_equiv_segments), 2)
    else:
        encoding = "GSM-7"
        char_len = septets
        segments = 1 if septets <= 160 else math.ceil(septets / 153)
        cost_mult = 1.0

    unique_bad = []
    for ch in non_gsm7:
        if ch not in unique_bad:
            unique_bad.append(ch)

    return {
        "sms_encoding": encoding,
        "sms_char_or_septet_count": char_len,
        "sms_segments": segments,
        "cost_multiplier_vs_gsm7": cost_mult,
        "non_gsm7_chars": unique_bad[:10],
    }


def compute_offline_channel_economics(
    channel: str,
    recipients_or_reach: Any = None,
    total_campaign_cost_usd: Any = None,
    response_or_redemption_rate_pct: Any = None,
    aov_usd: Any = None,
    gross_margin_pct: Any = None,
    allowable_cac_usd: Any = None,
    total_campaign_cost: Any = None,
    aov: Any = None,
    allowable_cac: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Compute unit economics, effective CAC, CPM, and ROI for offline & low-connectivity channels."""
    cur = normalize_currency(currency)
    if channel not in SUPPORTED_ECONOMICS_CHANNELS:
        raise ValueError(f"Unsupported offline channel {channel!r}; choose from {SUPPORTED_ECONOMICS_CHANNELS}")

    reach = to_float(recipients_or_reach)
    cost = resolve_amount(total_campaign_cost, total_campaign_cost_usd)
    rate_pct = to_float(response_or_redemption_rate_pct)
    aov_val = resolve_amount(aov, aov_usd)
    gm_pct = to_float(gross_margin_pct)
    allow_cac = resolve_amount(allowable_cac, allowable_cac_usd)

    trace = (
        "expected_orders = recipients_or_reach * (response_or_redemption_rate_pct / 100); "
        "gross_revenue = expected_orders * aov; "
        "gross_profit = gross_revenue * (gross_margin_pct / 100); "
        "net_contribution = gross_profit - total_campaign_cost; "
        "effective_cac = total_campaign_cost / expected_orders; "
        "cost_per_1000_reach = (total_campaign_cost / recipients_or_reach) * 1000"
    )

    missing: list[str] = []
    if reach is None:
        missing.append("recipients_or_reach")
    if cost is None:
        missing.append("total_campaign_cost_usd" if cur == "USD" else "total_campaign_cost")
    if rate_pct is None:
        missing.append("response_or_redemption_rate_pct")
    if aov_val is None:
        missing.append("aov_usd" if cur == "USD" else "aov")
    if gm_pct is None:
        missing.append("gross_margin_pct")

    if missing:
        return unknown_result(missing, trace, {"currency": cur, "channel": channel})

    assert (
        reach is not None
        and cost is not None
        and rate_pct is not None
        and aov_val is not None
        and gm_pct is not None
    )

    if reach <= 0 or cost < 0 or rate_pct < 0 or rate_pct > 100 or aov_val <= 0 or gm_pct <= 0 or gm_pct > 100:
        raise ValueError(
            "Invalid inputs: recipients_or_reach > 0, cost >= 0, 0 <= response_rate_pct <= 100, aov > 0, 0 < gross_margin_pct <= 100 required"
        )
    if allow_cac is not None and allow_cac <= 0:
        raise ValueError("allowable_cac must be > 0 when provided")

    orders_raw = reach * (rate_pct / 100.0)
    gross_rev_raw = orders_raw * aov_val
    gross_profit_raw = gross_rev_raw * (gm_pct / 100.0)
    net_contrib_raw = gross_profit_raw - cost
    cpm_raw = (cost / reach) * 1000.0

    effective_cac_val: float | str = round_money(cost / orders_raw, cur) if orders_raw > 0 else "unknown"
    effective_cac_fmt: str = format_money(cost / orders_raw, cur) if orders_raw > 0 else "unknown"
    effective_cac_usd: float | str = round(cost / orders_raw, 2) if orders_raw > 0 else "unknown"

    if cost > 0:
        roi_pct: float | str = round(((gross_profit_raw - cost) / cost) * 100.0, 2)
    else:
        roi_pct = "infinite" if gross_profit_raw > 0 else 0.0

    within_cac: bool | str = "unknown"
    if allow_cac is not None:
        if orders_raw > 0:
            within_cac = bool((cost / orders_raw) <= allow_cac)
        elif cost > 0:
            within_cac = False
        else:
            within_cac = True

    return ok_result(
        {
            "currency": cur,
            "currency_symbol": currency_symbol(cur),
            "channel": channel,
            "recipients_or_reach": int(reach) if reach.is_integer() else round(reach, 2),
            "expected_orders": round(orders_raw, 2),
            "gross_revenue": round_money(gross_rev_raw, cur),
            "gross_revenue_formatted": format_money(gross_rev_raw, cur),
            "gross_revenue_usd": round(gross_rev_raw, 2),
            "gross_profit": round_money(gross_profit_raw, cur),
            "gross_profit_formatted": format_money(gross_profit_raw, cur),
            "gross_profit_usd": round(gross_profit_raw, 2),
            "net_contribution": round_money(net_contrib_raw, cur),
            "net_contribution_formatted": format_money(net_contrib_raw, cur),
            "net_contribution_usd": round(net_contrib_raw, 2),
            "effective_cac": effective_cac_val,
            "effective_cac_formatted": effective_cac_fmt,
            "effective_cac_usd": effective_cac_usd,
            "cost_per_1000_reach": round_money(cpm_raw, cur),
            "cost_per_1000_reach_formatted": format_money(cpm_raw, cur),
            "cost_per_1000_reach_usd": round(cpm_raw, 2),
            "roi_pct": roi_pct,
            "within_allowable_cac": within_cac,
        },
        trace,
    )


def evaluate_low_bandwidth_readiness(
    message_text: Any = None,
    channel: str = "whatsapp",
    include_opt_out: bool = True,
    html_payload_kb: Any = None,
    currency: str = "USD",
) -> dict[str, Any]:
    """Validate SMS GSM-7 vs UCS-2 segments, WhatsApp broadcast compliance, radio spot timing, flyer scannability, and 2G/3G payload size."""
    cur = normalize_currency(currency)
    if channel not in SUPPORTED_READINESS_CHANNELS:
        raise ValueError(f"Unsupported readiness channel {channel!r}; choose from {SUPPORTED_READINESS_CHANNELS}")

    trace = (
        "sms: GSM-7 (160/153) vs UCS-2 (70/67); "
        "radio: words / (130 wpm / 60); "
        "whatsapp/flyer: CTA + opt-out/contact + word budget; "
        "low_data_web: html_payload_kb <= 150"
    )

    if not isinstance(message_text, str) or not message_text.strip():
        return unknown_result(["message_text"], trace, {"currency": cur, "channel": channel})

    text = message_text.strip()
    words = re.findall(r"\S+", text)
    word_count = len(words)
    char_count = len(text)

    warnings: list[str] = []
    blockers: list[str] = []
    details: dict[str, Any] = {
        "currency": cur,
        "channel": channel,
        "char_count": char_count,
        "word_count": word_count,
        "has_clear_cta": bool(_CTA_RE.search(text)),
        "has_opt_out": bool(_OPT_OUT_RE.search(text)),
    }

    score = 100

    if channel == "sms":
        sms = analyze_sms_segments(text)
        details.update(sms)
        if sms["sms_encoding"] == "UCS-2":
            score -= 25
            warnings.append(
                f"UCS-2 encoding triggered by {sms['non_gsm7_chars']} — shrinks limit from 160 to 70 chars/segment ({sms['cost_multiplier_vs_gsm7']}x SMS cost)"
            )
        if sms["sms_segments"] > 2:
            score -= 20
            warnings.append(f"Message spans {sms['sms_segments']} SMS segments; trim to <= 2 segments to avoid carrier truncation and extra per-recipient fees")
        if not details["has_clear_cta"]:
            score -= 20
            blockers.append("missing_reply_or_contact_cta: add reply keyword, phone number, or short USSD/payment code")
        if include_opt_out and not details["has_opt_out"]:
            score -= 20
            blockers.append("missing_sms_opt_out: append 'Reply STOP to opt out' (or local-language equivalent)")

    elif channel == "whatsapp":
        if char_count > 1024:
            score -= 20
            warnings.append(f"WhatsApp template body is {char_count} chars (>1024 recommendation for low-end Android screens); trim for instant preview without 'Read more' fold")
        if not details["has_clear_cta"]:
            score -= 20
            blockers.append("missing_whatsapp_cta: include reply keyword, order instruction, phone, or cash/mobile-money checkout option")
        if include_opt_out and not details["has_opt_out"]:
            score -= 20
            blockers.append("missing_whatsapp_opt_out: include clear opt-out instruction (e.g. 'Reply STOP anytime')")

    elif channel in _RADIO_WORD_CAPS:
        max_words, target_sec = _RADIO_WORD_CAPS[channel]
        est_sec = round((word_count / 130.0) * 60.0, 1)
        phone_matches = _PHONE_OR_CODE_RE.findall(text)
        details["estimated_speaking_seconds"] = est_sec
        details["target_spot_seconds"] = target_sec
        details["max_recommended_words"] = max_words
        details["contact_repetitions"] = len(phone_matches)
        if word_count > max_words:
            score -= 30
            blockers.append(
                f"radio_script_too_long: {word_count} words (~{est_sec}s at 130 wpm) exceeds {target_sec}s spot cap ({max_words} words)"
            )
        if len(phone_matches) < 2:
            score -= 20
            warnings.append("Repeat phone number, WhatsApp number, or short code at least twice in audio spots so listeners remember without writing it down")
        if not details["has_clear_cta"]:
            score -= 15
            warnings.append("Add explicit spoken action (call, text, or visit landmark)")

    else:  # print_flyer or bulletin_board
        cap = 90 if channel == "bulletin_board" else 180
        details["max_recommended_words"] = cap
        details["has_price_or_offer"] = bool(_PRICE_OR_OFFER_RE.search(text))
        if word_count > cap:
            score -= 25
            warnings.append(f"{channel} copy has {word_count} words (recommended <= {cap} words for 3-second street scannability)")
        if not details["has_clear_cta"]:
            score -= 25
            blockers.append("missing_contact_or_location_cta: include phone/WhatsApp number, street landmark, or tear-off contact")
        if not details["has_price_or_offer"]:
            score -= 15
            warnings.append("Include clear price or concrete offer so passersby immediately qualify themselves")

    kb_val = to_float(html_payload_kb)
    if kb_val is not None:
        if kb_val < 0:
            raise ValueError("html_payload_kb cannot be negative")
        details["html_payload_kb"] = round(kb_val, 2)
        details["low_data_web_pass"] = bool(kb_val <= 150.0)
        if kb_val > 150.0:
            score -= 20
            warnings.append(f"Landing page/order sheet weight {kb_val:.1f} KB exceeds 150 KB 2G/prepaid-data budget")

    score = max(0, score)
    details["readiness_score"] = score
    details["ready"] = len(blockers) == 0 and score >= 70
    details["blockers"] = blockers
    details["warnings"] = warnings
    return ok_result(details, trace)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compute offline/low-bandwidth channel economics and message readiness."
    )
    parser.add_argument("--mode", choices=["economics", "readiness"], default="economics")
    parser.add_argument("--input", help="JSON input file path")
    parser.add_argument("--currency", default="USD", help="ISO-4217 currency code (e.g. USD, KES, IDR, MXN)")
    parser.add_argument("--channel", default="whatsapp_broadcast")

    # Economics args
    parser.add_argument("--recipients-or-reach", type=float)
    parser.add_argument("--total-campaign-cost-usd", type=float)
    parser.add_argument("--total-campaign-cost", type=float)
    parser.add_argument("--response-or-redemption-rate-pct", type=float)
    parser.add_argument("--aov-usd", type=float)
    parser.add_argument("--aov", type=float)
    parser.add_argument("--gross-margin-pct", type=float)
    parser.add_argument("--allowable-cac-usd", type=float)
    parser.add_argument("--allowable-cac", type=float)

    # Readiness args
    parser.add_argument("--message-text")
    parser.add_argument("--no-opt-out", action="store_true")
    parser.add_argument("--html-payload-kb", type=float)

    args = parser.parse_args(argv)

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if args.mode == "readiness":
            out = evaluate_low_bandwidth_readiness(**payload)
        else:
            out = compute_offline_channel_economics(**payload)
    elif args.mode == "readiness":
        ch = "whatsapp" if args.channel == "whatsapp_broadcast" else args.channel
        out = evaluate_low_bandwidth_readiness(
            message_text=args.message_text,
            channel=ch,
            include_opt_out=not args.no_opt_out,
            html_payload_kb=args.html_payload_kb,
            currency=args.currency,
        )
    else:
        out = compute_offline_channel_economics(
            channel=args.channel,
            recipients_or_reach=args.recipients_or_reach,
            total_campaign_cost_usd=args.total_campaign_cost_usd,
            response_or_redemption_rate_pct=args.response_or_redemption_rate_pct,
            aov_usd=args.aov_usd,
            gross_margin_pct=args.gross_margin_pct,
            allowable_cac_usd=args.allowable_cac_usd,
            total_campaign_cost=args.total_campaign_cost,
            aov=args.aov,
            allowable_cac=args.allowable_cac,
            currency=args.currency,
        )

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
