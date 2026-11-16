"""Deterministic behavioral compliance exam verifying harness invariants without improvisation."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculators.cac_ltv import compute_cac_ltv
from connectors.context_offloader import build_ordered_context
from connectors.radar_store import draft_community_reply
from connectors.sanitizer import check_vip_violations, load_vip_policy
from scripts.next_action import generate_next_actions


def run_exam(repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Run deterministic behavioral scenarios against core harness invariants."""
    checks: list[dict[str, Any]] = []

    # 1. Missing-data -> 'unknown' rule (never guess defaults)
    res_missing = compute_cac_ltv(aov_usd=None, gross_margin_pct=65)
    checks.append(
        {
            "exam": "missing_data_returns_unknown",
            "passed": res_missing["status"] == "unknown" and res_missing["value"] == "unknown",
        }
    )

    # 2. Prefix-cache stability rejects volatile timestamps in static prefix
    prefix_rejected = False
    try:
        build_ordered_context("Now: 2026-11-16T12:00:00", {}, "", "", "", {})
    except ValueError:
        prefix_rejected = True
    checks.append({"exam": "prefix_cache_rejects_volatile_ts", "passed": prefix_rejected})

    # 3. VIP exclusion blocks investor/protected domain outreach
    policy = load_vip_policy(repo_root / ".agents/guardrails.yaml", repo_root)
    viols = check_vip_violations(["active_customers"], policy, "Pitching founder@example-investor.com")
    checks.append(
        {
            "exam": "vip_guardrail_blocks_protected_outreach",
            "passed": len(viols) >= 2,
        }
    )

    # 4. Strategy-before-production lock blocks production skills while draft_pending_review
    with tempfile.TemporaryDirectory() as tmp:
        bt = pathlib.Path(tmp) / "bt.md"
        bt.write_text("---\nstatus: draft_pending_review\n---\n", encoding="utf-8")
        brief = generate_next_actions({"brand_truth_path": str(bt)}, repo_root=repo_root)
        checks.append(
            {
                "exam": "strategy_lock_blocks_production",
                "passed": brief["strategy_lock_status"] == "draft_pending_review"
                and all(s["skill_names"][0] in ("cmo-init", "unit-economics-floors") for s in brief["agent_brief"]["subtasks"]),
            }
        )

    # 5. Community reply FTC disclosure enforced
    reply = draft_community_reply("Try indexing your comparison tables.", "OpenCMO")
    checks.append(
        {
            "exam": "community_reply_ftc_disclosure",
            "passed": "(Disclosure: I built/work on OpenCMO)" in reply,
        }
    )

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "total_exams": len(checks),
        "passed": passed_count,
        "failed": len(checks) - passed_count,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic behavioral compliance exam.")
    parser.parse_args(argv)
    report = run_exam(REPO_ROOT)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if report["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
