"""Check primary platform documentation URLs across skills/ for reachability and drift."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.geo_benchmark import safe_urlopen, validate_endpoint_url
from scripts.validate_skills import PRIMARY_SOURCE_DOMAINS


_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")


def scan_skill_sources(skills_dir: pathlib.Path, offline: bool = True) -> dict[str, Any]:
    """Scan all SKILL.md ## Sources URLs for domain compliance and optional HTTP reachability."""
    results: list[dict[str, Any]] = []
    errors = 0
    for path in sorted(skills_dir.glob("*/*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        idx = text.find("## Sources")
        sec = text[idx:] if idx != -1 else ""
        urls = sorted(set(_URL_RE.findall(sec)))
        for url in urls:
            parsed = urllib.parse.urlparse(url)
            host = (parsed.hostname or "").rstrip(".").lower()
            domain_ok = (parsed.scheme == "https") and (parsed.username is None) and (host in PRIMARY_SOURCE_DOMAINS)
            status = "offline_ok" if domain_ok else "disallowed_domain"
            if not domain_ok:
                errors += 1
            elif not offline:
                try:
                    safe_url = validate_endpoint_url(url)
                    req = urllib.request.Request(safe_url, method="HEAD", headers={"User-Agent": "freecmo-source-watch/0.1"})
                    http_status, _ = safe_urlopen(req, timeout=10, max_bytes=65536)
                    status = f"http_{http_status}"
                except Exception as exc:
                    status = f"error:{exc}"
                    errors += 1
            results.append({"skill": path.parent.name, "url": url, "status": status})
    return {"checked": len(results), "errors": errors, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check primary documentation URLs for spec drift.")
    parser.add_argument("--offline", action="store_true", help="Validate URLs & primary domains without network calls.")
    args = parser.parse_args(argv)
    out = scan_skill_sources(REPO_ROOT / "skills", offline=args.offline)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 1 if out["errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
