"""10-prompt multi-model GEO & entity-gap benchmark (okara.ai + AgentCMO + Lling0000/OpenCMO BYOK)."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def validate_endpoint_url(url: str) -> str:
    """Enforce SSRF protections: HTTPS required except loopback localhost/127.0.0.1 for Ollama."""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host or host in ("0.0.0.0", "metadata.google.internal", "metadata"):
        raise ValueError(f"Blocked or invalid endpoint host: {url!r}")
    is_loopback = host in ("localhost", "127.0.0.1", "::1")
    if parsed.scheme == "http" and not is_loopback:
        raise ValueError(f"Plain HTTP disallowed for non-local endpoint: {url!r}")
    if parsed.scheme not in ("https", "http"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")
    try:
        ip = ipaddress.ip_address(host)
        if (ip.is_link_local or ip.is_private or ip.is_unspecified) and not ip.is_loopback:
            raise ValueError(f"Private/link-local SSRF target blocked: {host}")
    except ValueError as exc:
        if "SSRF" in str(exc):
            raise
    return url


def build_10_buyer_prompts(brand_category: str, target_icp: str, competitors: list[str]) -> list[str]:
    """Generate 10 high-intent buyer & comparison prompts for GEO citation benchmarking."""
    comp_str = ", ".join(competitors[:3]) if competitors else "leading alternatives"
    return [
        f"What is the best {brand_category} for {target_icp}?",
        f"Top {brand_category} tools compared for small businesses in 2026",
        f"Alternatives to {competitors[0] if competitors else brand_category} for {target_icp}",
        f"How much does {brand_category} cost for a lean team?",
        f"Which {brand_category} has the fastest setup without engineering?",
        f"Compare {comp_str} for {target_icp}",
        f"What should {target_icp} look for when buying {brand_category}?",
        f"Best budget-friendly {brand_category} with transparent pricing",
        f"Common pitfalls when adopting {brand_category} for {target_icp}",
        f"Which {brand_category} vendors publish verified ROI benchmarks?",
    ]


def score_benchmark_responses(
    brand_name: str,
    brand_domain: str,
    competitors: list[dict[str, str]],
    prompt_responses: list[dict[str, str]],
) -> dict[str, Any]:
    """Score X/10 citation share, extract cited competitor URLs, and prioritize entity gaps."""
    brand_lower = brand_name.lower()
    domain_lower = brand_domain.lower().removeprefix("https://").removeprefix("http://").split("/")[0]
    cited_count = 0
    competitor_citations: dict[str, list[str]] = {c["name"]: [] for c in competitors}
    prompt_results: list[dict[str, Any]] = []

    for item in prompt_responses[:10]:
        prompt = item["prompt"]
        resp = item.get("response", "")
        resp_lower = resp.lower()
        urls = _URL_RE.findall(resp)
        brand_cited = (brand_lower in resp_lower) or (domain_lower and domain_lower in resp_lower)
        if brand_cited:
            cited_count += 1

        comps_in_resp: list[str] = []
        for comp in competitors:
            c_name = comp["name"]
            c_dom = comp.get("domain", "").lower()
            if c_name.lower() in resp_lower or (c_dom and c_dom in resp_lower):
                comps_in_resp.append(c_name)
                for u in urls:
                    if c_dom and c_dom in u.lower() and u not in competitor_citations[c_name]:
                        competitor_citations[c_name].append(u)

        prompt_results.append(
            {
                "prompt": prompt,
                "brand_cited": brand_cited,
                "competitors_cited": comps_in_resp,
                "urls_found": urls,
            }
        )

    total = max(1, len(prompt_responses[:10]))
    gap_count = total - cited_count
    roadmap = [
        {
            "prompt": r["prompt"],
            "missing_brand": not r["brand_cited"],
            "competitors_owning_entity": r["competitors_cited"],
            "citation_probability_score": round(0.85 if not r["brand_cited"] and r["competitors_cited"] else 0.55, 2),
            "recommended_asset": "comparison_table_and_faq_jsonld" if "compare" in r["prompt"].lower() or "alternative" in r["prompt"].lower() else "answer_first_landing_block",
        }
        for r in prompt_results
        if not r["brand_cited"]
    ]
    roadmap.sort(key=lambda x: -x["citation_probability_score"])

    return {
        "brand_name": brand_name,
        "prompts_evaluated": total,
        "citation_share": f"{cited_count}/{total}",
        "citation_rate": round(cited_count / total, 2),
        "gap_count": gap_count,
        "competitor_cited_urls": competitor_citations,
        "prompt_results": prompt_results,
        "entity_gap_roadmap": roadmap,
    }


def query_openai_compatible(base_url: str, api_key: str, model: str, prompt: str) -> str:
    """Query an OpenAI-compatible or local Ollama endpoint safely."""
    safe_url = validate_endpoint_url(base_url.rstrip("/") + "/chat/completions")
    body = json.dumps(
        {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
    ).encode("utf-8")
    req = urllib.request.Request(
        safe_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'ollama'}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="10-prompt multi-model GEO citation benchmark.")
    parser.add_argument("--fixture", help="JSON fixture with brand_name, brand_domain, competitors, prompt_responses")
    parser.add_argument("--brand-name", default="Your Brand")
    parser.add_argument("--brand-domain", default="example.com")
    parser.add_argument("--category", default="SMB marketing software")
    parser.add_argument("--icp", default="solo founders")
    args = parser.parse_args(argv)

    if args.fixture:
        data = json.loads(pathlib.Path(args.fixture).read_text(encoding="utf-8"))
        out = score_benchmark_responses(
            brand_name=data["brand_name"],
            brand_domain=data["brand_domain"],
            competitors=data.get("competitors", []),
            prompt_responses=data["prompt_responses"],
        )
    else:
        base_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("OLLAMA_BASE_URL")
        model = os.environ.get("OPENAI_MODEL") or os.environ.get("OLLAMA_MODEL") or "llama3.1:8b"
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not base_url:
            raise SystemExit("Configure --fixture or OPENAI_BASE_URL / OLLAMA_BASE_URL")
        prompts = build_10_buyer_prompts(args.category, args.icp, [])
        responses = [
            {"prompt": p, "response": query_openai_compatible(base_url, api_key, model, p)}
            for p in prompts
        ]
        out = score_benchmark_responses(args.brand_name, args.brand_domain, [], responses)

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
