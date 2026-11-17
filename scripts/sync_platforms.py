"""CLI entrypoint for automated ad, social, analytics, and revenue sync + Weekly Brief generation."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from connectors.ad_platform_sync import SUPPORTED_PLATFORMS, sync_all_platforms
from connectors.env_loader import load_dotenv_file
from scripts.next_action import generate_next_actions


def append_shift_ledger(repo_root: pathlib.Path, entry: dict) -> None:
    ledger = repo_root / "data" / "shift_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Automated read-only sync from ad/analytics/revenue platforms into data/exports/ + Weekly Brief."
    )
    parser.add_argument(
        "--platforms",
        help=f"Comma-separated platforms ({','.join(SUPPORTED_PLATFORMS)}). Omit to auto-detect configured credentials.",
    )
    parser.add_argument("--lookback-days", type=int, default=30, help="Lookback window in days (default: 30)")
    parser.add_argument("--demo-fixture", action="store_true", help="Run deterministic multi-platform demo sync offline")
    parser.add_argument("--allowable-cac-usd", type=float, default=100.0)
    parser.add_argument("--monthly-budget-usd", type=float, default=2500.0)
    parser.add_argument("--gross-margin-pct", type=float, default=65.0, help="Gross margin percentage (default: 65.0)")
    parser.add_argument("--site-load-sec", type=float, default=2.1, help="Observed site load seconds (default: 2.1)")
    parser.add_argument("--fail-fast", action="store_true", help="Abort immediately if any configured platform API call fails")
    parser.add_argument("--emit-brief", action="store_true", help="Immediately generate Weekly Composer's Brief")
    parser.add_argument("--output-brief", help="Optional path to write generated Weekly Composer's Brief JSON")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Workspace root directory")
    args = parser.parse_args(argv)

    root = pathlib.Path(args.repo_root).resolve()
    env = load_dotenv_file(root / ".env")
    plat_list = [p.strip() for p in args.platforms.split(",") if p.strip()] if args.platforms else None

    sync_res = sync_all_platforms(
        repo_root=root,
        platforms=plat_list,
        lookback_days=args.lookback_days,
        env=env,
        demo_fixture=args.demo_fixture,
        allowable_cac_usd=args.allowable_cac_usd,
        monthly_budget_usd=args.monthly_budget_usd,
        gross_margin_pct=args.gross_margin_pct,
        site_load_sec=args.site_load_sec,
        fail_fast=args.fail_fast,
    )

    result: dict = {
        "synced_platforms": sync_res["synced_platforms"],
        "sync_errors": sync_res["sync_errors"],
        "written_exports": sync_res["written_exports"],
        "unified_customer_records": sync_res["unified_customer_records"],
        "state_path": sync_res["state_path"],
    }

    if args.emit_brief:
        brief = generate_next_actions(sync_res["orchestrator_state"], repo_root=root)
        result["composers_brief"] = brief
        if args.output_brief:
            out_path = pathlib.Path(args.output_brief)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(brief, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    append_shift_ledger(
        root,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "shift_type": "automated_platform_sync",
            "demo_fixture": bool(args.demo_fixture),
            "synced_platforms": sync_res["synced_platforms"],
            "sync_error_platforms": sorted(sync_res["sync_errors"].keys()),
            "exports_count": len(sync_res["written_exports"]),
            "brief_emitted": bool(args.emit_brief),
        },
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    if sync_res["sync_errors"] and not sync_res["synced_platforms"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
