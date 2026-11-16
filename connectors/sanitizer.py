"""Prompt-injection sanitizer, PII redactor, and VIP/relationship guardrail checker."""

from __future__ import annotations

import csv
import pathlib
import re
from typing import Any

from calculators import safe_parse_yaml


_BIDI_AND_ZW_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_CLOSING_TAG_RE = re.compile(r"<\s*/\s*untrusted_data\s*>", re.IGNORECASE)
_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"),
    re.compile(r"(?i)disregard\s+(?:system|developer|orchestrator)\s+(?:rules?|prompts?)"),
    re.compile(r"(?i)you\s+are\s+now\s+(?:in\s+)?(?:developer|admin|god|jailbreak)\s+mode"),
    re.compile(r"(?i)system\s*:\s*override"),
    re.compile(r"(?i)execute\s+shell\s+command"),
]

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_SECRET_RE = re.compile(r"\b(?:sk-[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{20,}|ghp_[A-Za-z0-9]{20,})\b")


def sanitize_untrusted_text(text: str, redact_pii: bool = False) -> str:
    """Neutralize tag breakouts, bidi chars, and prompt-injection strings, wrapping in <untrusted_data>."""
    cleaned = _BIDI_AND_ZW_RE.sub("", text or "")
    cleaned = _CLOSING_TAG_RE.sub("[ESCAPED_CLOSING_TAG]", cleaned)
    for pat in _INJECTION_PATTERNS:
        cleaned = pat.sub("[STRIPPED_INJECTION_PHRASE]", cleaned)
    if redact_pii:
        cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", cleaned)
    cleaned = _SECRET_RE.sub("[REDACTED_SECRET]", cleaned)
    return f"<untrusted_data>\n{cleaned.strip()}\n</untrusted_data>"


def load_vip_policy(guardrails_path: pathlib.Path, repo_root: pathlib.Path | None = None) -> dict[str, Any]:
    """Load protected_relationships from guardrails.yaml and optional vip_contacts_csv."""
    if not guardrails_path.exists():
        return {"vip_domains": set(), "vip_emails": set(), "never_cold_pitch_segments": set()}
    data = safe_parse_yaml(guardrails_path.read_text(encoding="utf-8")) or {}
    rel = data.get("protected_relationships", {}) or {}
    vip_domains = {str(d).strip().lower() for d in rel.get("vip_domains", []) if d}
    segments = {str(s).strip().lower() for s in rel.get("never_cold_pitch_segments", []) if s}
    vip_emails: set[str] = set()

    csv_rel = rel.get("vip_contacts_csv")
    if csv_rel and repo_root is not None:
        csv_path = (repo_root / csv_rel).resolve()
        if csv_path.is_relative_to(repo_root.resolve()) and csv_path.exists():
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    email = (row.get("email") or "").strip().lower()
                    if email:
                        vip_emails.add(email)
                    domain = (row.get("domain") or "").strip().lower()
                    if domain:
                        vip_domains.add(domain)

    return {
        "vip_domains": vip_domains,
        "vip_emails": vip_emails,
        "never_cold_pitch_segments": segments,
    }


def check_vip_violations(
    target_entities: list[str],
    vip_policy: dict[str, Any],
    outbound_text: str = "",
) -> list[str]:
    """Return deterministic VIP/relationship violation descriptions if any protected target is touched."""
    violations: list[str] = []
    vip_domains = vip_policy.get("vip_domains", set())
    vip_emails = vip_policy.get("vip_emails", set())
    blocked_segments = vip_policy.get("never_cold_pitch_segments", set())

    candidates = list(target_entities)
    for m in _EMAIL_RE.finditer(outbound_text or ""):
        candidates.append(m.group(0))

    for raw in candidates:
        item = str(raw).strip().lower()
        if not item:
            continue
        if item in vip_emails:
            violations.append(f"vip_email_blocked:{item}")
        if "@" in item:
            dom = item.split("@", 1)[1]
            if dom in vip_domains:
                violations.append(f"vip_domain_blocked:{dom}")
        elif item in vip_domains:
            violations.append(f"vip_domain_blocked:{item}")
        if item in blocked_segments:
            violations.append(f"protected_segment_blocked:{item}")

    return sorted(set(violations))
