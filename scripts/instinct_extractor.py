"""Distill Composer brief rejections and edits into .agents/instincts.md rules."""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import tempfile
from datetime import datetime, timezone
from typing import Any


def distill_feedback_to_rule(
    feedback_text: str,
    trigger_domain: str = "global",
    decision_date: str | None = None,
) -> dict[str, str]:
    """Convert raw Composer rejection/edit note into a deterministic 1-line instinct entry."""
    cleaned = re.sub(r"\s+", " ", (feedback_text or "").strip())
    # Remove leading "Reject #2:" style prefixes
    cleaned = re.sub(r"^(?:reject|edit|fix)\s*(?:#?\d+)?\s*[:\-]\s*", "", cleaned, flags=re.IGNORECASE)
    if not cleaned:
        raise ValueError("Feedback text cannot be empty")
    if len(cleaned) > 220:
        cleaned = cleaned[:217].rstrip() + "..."
    rule_id = "inst-" + hashlib.sha256(f"{trigger_domain}:{cleaned.lower()}".encode("utf-8")).hexdigest()[:6]
    date_str = decision_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "id": rule_id,
        "trigger_domain": trigger_domain.strip().lower() or "global",
        "rule": cleaned.replace("|", "/"),
        "source_decision_date": date_str,
    }


def append_instinct(
    instincts_path: pathlib.Path,
    feedback_text: str,
    trigger_domain: str = "global",
    decision_date: str | None = None,
) -> dict[str, Any]:
    """Atomically append a deduplicated rule to .agents/instincts.md."""
    entry = distill_feedback_to_rule(feedback_text, trigger_domain, decision_date)
    existing = instincts_path.read_text(encoding="utf-8") if instincts_path.exists() else (
        "# Learned Composer Instincts\n\n"
        "| id | trigger_domain | rule | source_decision_date |\n"
        "|---|---|---|---|\n"
    )
    if f"`{entry['id']}`" in existing:
        return {"added": False, "entry": entry}

    row = f"| `{entry['id']}` | `{entry['trigger_domain']}` | {entry['rule']} | `{entry['source_decision_date']}` |\n"
    updated = existing.rstrip() + "\n" + row

    instincts_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(instincts_path.parent), prefix=".tmp_", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(updated)
        os.replace(tmp_name, instincts_path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise
    return {"added": True, "entry": entry}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Distill Composer brief rejection into .agents/instincts.md")
    parser.add_argument("--instincts", default=".agents/instincts.md")
    parser.add_argument("--domain", default="global")
    parser.add_argument("--feedback", required=True)
    parser.add_argument("--date", default=None)
    args = parser.parse_args(argv)
    import json

    res = append_instinct(pathlib.Path(args.instincts), args.feedback, args.domain, args.date)
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
