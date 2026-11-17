"""Deterministic UTM governance builder & validator for clean CDP IdentityResolver attribution."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any


ALLOWED_MEDIUMS = {
    "cpc",
    "paid_social",
    "organic_social",
    "display",
    "native",
    "email",
    "press_release",
    "blog",
    "community",
    "affiliate",
    "creator_ugc",
}

_SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def normalize_utm_slug(value: str) -> str:
    """Normalize UTM token to lowercase snake/kebab case without spaces or PII."""
    s = _SLUG_RE.sub("_", (value or "").strip().lower()).strip("_")
    if not s:
        raise ValueError(f"UTM parameter cannot be empty after normalization: {value!r}")
    return s[:64]


def build_governed_utm_url(
    destination_url: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    utm_content: str | None = None,
    utm_term: str | None = None,
) -> dict[str, Any]:
    """Build a canonical UTM-tagged URL aligned with FreeCMO IdentityResolver cohort taxonomy."""
    parsed = urllib.parse.urlparse((destination_url or "").strip())
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError(f"Invalid destination URL: {destination_url!r}")

    src = normalize_utm_slug(utm_source)
    med = normalize_utm_slug(utm_medium)
    if med not in ALLOWED_MEDIUMS:
        raise ValueError(f"Unsupported utm_medium {med!r}; allowed={sorted(ALLOWED_MEDIUMS)}")
    camp = normalize_utm_slug(utm_campaign)

    existing_qs = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=False))
    existing_qs["utm_source"] = src
    existing_qs["utm_medium"] = med
    existing_qs["utm_campaign"] = camp
    if utm_content:
        existing_qs["utm_content"] = normalize_utm_slug(utm_content)
    if utm_term:
        existing_qs["utm_term"] = normalize_utm_slug(utm_term)

    encoded_query = urllib.parse.urlencode(existing_qs)
    final_url = urllib.parse.urlunparse(parsed._replace(query=encoded_query))
    return {
        "url": final_url,
        "utm_source": src,
        "utm_medium": med,
        "utm_campaign": camp,
        "utm_content": existing_qs.get("utm_content"),
        "utm_term": existing_qs.get("utm_term"),
    }
