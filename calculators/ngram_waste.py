"""Deterministic search-term n-gram waste clustering for negative keyword mining."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict
from typing import Any

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from calculators import ok_result, to_float, unknown_result


_STOPWORDS = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


def mine_ngram_waste(
    search_terms: list[dict[str, Any]],
    allowable_cac_usd: Any,
    min_waste_spend_usd: Any = None,
    min_clicks: int = 10,
    max_ngram: int = 2,
) -> dict[str, Any]:
    """Cluster zero-conversion or over-CAC spend by 1-gram and 2-gram tokens."""
    n_cap = int(max_ngram)
    if n_cap < 1 or n_cap > 5:
        raise ValueError("max_ngram must be between 1 and 5")
    cac = to_float(allowable_cac_usd)
    trace = "aggregate spend/clicks/conversions per 1..max_ngram; flag ngrams with conversions==0 and spend>=min_waste_spend_usd"
    if not search_terms or cac is None or cac <= 0:
        return unknown_result(["search_terms", "allowable_cac_usd(>0)"], trace)

    waste_floor = to_float(min_waste_spend_usd)
    if waste_floor is None:
        waste_floor = round(cac * 1.0, 2)

    clusters: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ngram": "", "n": 1, "spend_usd": 0.0, "clicks": 0, "conversions": 0, "terms_count": 0}
    )
    total_waste_spend = 0.0

    for row in search_terms:
        term = str(row.get("search_term", "")).strip().lower()
        spend = to_float(row.get("spend_usd"))
        clicks = to_float(row.get("clicks"))
        convs = to_float(row.get("conversions"))
        if not term or spend is None or clicks is None or convs is None:
            continue
        if convs == 0:
            total_waste_spend += spend

        tokens = [t for t in re.findall(r"[a-z0-9]+", term) if t not in _STOPWORDS]
        seen_in_row: set[str] = set()
        for n in range(1, max_ngram + 1):
            for i in range(len(tokens) - n + 1):
                ng = " ".join(tokens[i : i + n])
                if ng in seen_in_row:
                    continue
                seen_in_row.add(ng)
                c = clusters[ng]
                c["ngram"] = ng
                c["n"] = n
                c["spend_usd"] = round(c["spend_usd"] + spend, 2)
                c["clicks"] += int(clicks)
                c["conversions"] += int(convs)
                c["terms_count"] += 1

    flagged: list[dict[str, Any]] = []
    for c in clusters.values():
        if c["conversions"] == 0 and c["spend_usd"] >= waste_floor and c["clicks"] >= min_clicks:
            c["suggested_match_type"] = "negative_phrase" if c["n"] > 1 else "negative_exact_or_phrase"
            flagged.append(c)

    flagged.sort(key=lambda x: (-x["spend_usd"], -x["clicks"], -x["n"], x["ngram"]))
    return ok_result(
        {
            "waste_floor_usd": waste_floor,
            "total_zero_conv_spend_usd": round(total_waste_spend, 2),
            "flagged_ngrams": flagged[:25],
            "flagged_count": len(flagged),
        },
        trace,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Search term n-gram waste miner.")
    parser.add_argument("--input", required=True, help="JSON input file path")
    args = parser.parse_args(argv)
    with open(args.input, "r", encoding="utf-8") as f:
        payload = json.load(f)
    out = mine_ngram_waste(**payload)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
