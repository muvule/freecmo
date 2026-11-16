"""Tier 0 CSV dropzone normalizer for Google Ads, Meta Ads, GA4, GSC, and Shopify/Stripe exports."""

from __future__ import annotations

import csv
import pathlib
from typing import Any


_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def neutralize_csv_cell(value: str) -> str:
    """Prevent spreadsheet formula injection while preserving negative numbers."""
    s = (value or "").strip()
    if not s:
        return ""
    if s[0] in _FORMULA_PREFIXES:
        # Allow legitimate negative numbers like -12.50
        if s[0] == "-" and s[1:].replace(".", "", 1).isdigit():
            return s
        return "'" + s
    return s


def _parse_num(raw: str | None) -> float | None:
    if raw is None:
        return None
    cleaned = raw.strip().replace("$", "").replace(",", "").replace("%", "")
    if not cleaned or cleaned in ("--", "-", "N/A", "n/a", "unknown"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


_COLUMN_ALIASES: dict[str, str] = {
    # Search / Ads
    "search term": "search_term",
    "query": "search_term",
    "top queries": "search_term",
    "campaign": "campaign_name",
    "campaign name": "campaign_name",
    "ad set name": "ad_set_name",
    "cost": "spend_usd",
    "amount spent (usd)": "spend_usd",
    "spend": "spend_usd",
    "impr.": "impressions",
    "impressions": "impressions",
    "clicks": "clicks",
    "link clicks": "clicks",
    "conversions": "conversions",
    "purchases": "conversions",
    "results": "conversions",
    "conv. value": "revenue_usd",
    "purchase conversion value": "revenue_usd",
    "total revenue": "revenue_usd",
    "gross sales": "revenue_usd",
    "position": "avg_position",
    "ctr": "ctr",
    "email": "email",
    "customer email": "email",
    "utm_source": "first_touch_utm",
    "first_touch_utm": "first_touch_utm",
    "segment": "crm_segment",
    "orders": "orders_count",
    "ltv": "ltv_usd",
}


def normalize_csv_export(csv_path: pathlib.Path, source_platform: str = "auto") -> dict[str, Any]:
    """Parse and normalize a Tier 0 CSV export with formula neutralization and source receipts."""
    path = csv_path.resolve()
    rows: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        raw_headers = reader.fieldnames or []
        for idx, raw_row in enumerate(reader, start=2):
            norm: dict[str, Any] = {"_row_number": idx}
            for col, val in raw_row.items():
                if col is None:
                    continue
                canonical = _COLUMN_ALIASES.get(col.strip().lower(), col.strip().lower().replace(" ", "_"))
                safe_val = neutralize_csv_cell(val or "")
                if canonical in (
                    "spend_usd",
                    "impressions",
                    "clicks",
                    "conversions",
                    "revenue_usd",
                    "avg_position",
                    "ctr",
                    "orders_count",
                    "ltv_usd",
                ):
                    num = _parse_num(safe_val)
                    norm[canonical] = num if num is not None else "unknown"
                else:
                    norm[canonical] = safe_val
            rows.append(norm)

    return {
        "source_platform": source_platform,
        "file_path": str(path),
        "raw_headers": raw_headers,
        "row_count": len(rows),
        "row_range": f"2-{len(rows) + 1}" if rows else "empty",
        "rows": rows,
    }
