"""Standalone terminal runner for FreeCMO (ideal for Local Ollama/LM Studio, OpenRouter, or CI).

Lets founders and marketers run /cmo init, automated platform sync + Weekly Briefs,
and individual domain skills (blog writing, press releases, display/native ad studio,
audits) directly from the terminal using any configured LLM or --dry-run mode.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculators.cac_ltv import compute_cac_ltv
from connectors.ad_platform_sync import detect_configured_platforms, sync_all_platforms
from connectors.approval_gate import check_strategy_lock
from connectors.context_offloader import build_ordered_context
from connectors.llm_router import MODEL_TIERS, complete_prompt, resolve_llm_route
from scripts.next_action import PRODUCTION_SKILLS, generate_next_actions
from scripts.validate_skills import split_frontmatter


BOOTSTRAP_SAFE_SKILLS = {"cmo-init", "unit-economics-floors", "tracking-health-audit"}


def load_dotenv_file(dotenv_path: pathlib.Path) -> dict[str, str]:
    """Load simple KEY=VALUE lines from .env without overriding existing process env vars."""
    merged = dict(os.environ)
    if not dotenv_path.exists():
        return merged
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        val = v.strip().strip('"').strip("'")
        if key and key not in merged:
            merged[key] = val
    return merged


def _find_skill_path(skill_name: str, repo_root: pathlib.Path) -> pathlib.Path:
    matches = list((repo_root / "skills").glob(f"*/{skill_name}/SKILL.md"))
    if not matches:
        raise FileNotFoundError(f"Skill {skill_name!r} not found under skills/*/*/SKILL.md")
    return matches[0]


def cmd_status(repo_root: pathlib.Path, env: dict[str, str], provider: str | None) -> dict[str, Any]:
    routes = {tier: resolve_llm_route(model_tier=tier, provider_override=provider, env=env) for tier in MODEL_TIERS}
    return {
        "strategy_lock_status": check_strategy_lock(repo_root / ".agents" / "brand-truth.md"),
        "configured_ad_and_revenue_platforms": detect_configured_platforms(env),
        "llm_routes": routes,
    }


def cmd_init(
    repo_root: pathlib.Path,
    brand_name: str,
    website_url: str,
    aov_usd: float,
    gross_margin_pct: float,
    monthly_budget_usd: float,
    description: str,
) -> dict[str, Any]:
    econ = compute_cac_ltv(aov_usd=aov_usd, gross_margin_pct=gross_margin_pct)
    floors = econ
    bt_path = repo_root / ".agents" / "brand-truth.md"
    bt_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""---
status: draft_pending_review
brand_name: "{brand_name}"
website_url: "{website_url}"
monthly_budget_usd: {monthly_budget_usd}
---

# Brand Truth — {brand_name}

> Review the unit economics and positioning below, then change `status: draft_pending_review` to `status: locked` to unlock production skills.

## 1. Company & Offer Summary
- **Website:** {website_url}
- **Description:** {description}

## 2. Deterministic Unit Economics Floors (`calculators/cac_ltv.py`)
- **AOV:** ${aov_usd:.2f}
- **Gross Margin:** {gross_margin_pct:.1f}%
- **Gross Profit per Order:** ${floors.get('gross_profit_per_order_usd', 'unknown')}
- **Break-Even ROAS:** {floors.get('break_even_roas', 'unknown')}x
- **Allowable CAC:** ${floors.get('allowable_cac_usd', 'unknown')}

## 3. Active Strategic Bets (With Disproof Conditions)
- Bet 1: Validate primary buyer pain angle within allowable CAC (`disproof_condition: conversions == 0 after 2.0x allowable_cac_usd spend`).

## 4. Killed Assumptions
| Bet ID | Disproven Angle / Hypothesis | Quantitative Evidence | Date Killed | Resurrection Condition |
|---|---|---|---|---|
| — | None recorded yet | — | — | Requires explicit market/product shift approved by Composer |

## 5. Validated Learnings
- Initialized via `cmo_runner.py init`.
"""
    bt_path.write_text(content, encoding="utf-8")
    return {
        "brand_truth_path": str(bt_path),
        "strategy_lock_status": "draft_pending_review",
        "unit_economics": econ,
    }


def cmd_run_skill(
    repo_root: pathlib.Path,
    skill_name: str,
    brief_text: str,
    model_tier: str,
    provider: str | None,
    dry_run: bool,
    env: dict[str, str],
) -> dict[str, Any]:
    lock_status = check_strategy_lock(repo_root / ".agents" / "brand-truth.md")
    if skill_name not in BOOTSTRAP_SAFE_SKILLS and (skill_name in PRODUCTION_SKILLS or lock_status != "locked"):
        if lock_status != "locked":
            raise PermissionError(
                f"Hard Strategy-Before-Production Lock active (brand-truth.md status={lock_status!r}). "
                f"Skill {skill_name!r} is blocked until Composer sets status: locked."
            )

    skill_path = _find_skill_path(skill_name, repo_root)
    skill_raw = skill_path.read_text(encoding="utf-8")
    fm, _ = split_frontmatter(skill_raw)

    agents_rules = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    bt_md = (
        (repo_root / ".agents" / "brand-truth.md").read_text(encoding="utf-8")
        if (repo_root / ".agents" / "brand-truth.md").exists()
        else (repo_root / ".agents" / "brand-truth.template.md").read_text(encoding="utf-8")
    )
    vdna_json = (repo_root / ".agents" / "visual-dna.json").read_text(encoding="utf-8")
    instincts_md = (repo_root / ".agents" / "instincts.md").read_text(encoding="utf-8")

    ordered = build_ordered_context(
        static_system_rules=agents_rules,
        tool_or_skill_schemas={skill_name: {"frontmatter": fm, "instructions": skill_raw}},
        brand_truth_md=bt_md,
        visual_dna_json=vdna_json,
        instincts_md=instincts_md,
        volatile_slice={"skill": skill_name, "brief": brief_text},
    )
    route = resolve_llm_route(model_tier=model_tier, provider_override=provider, env=env)
    if dry_run:
        return {
            "dry_run": True,
            "skill": skill_name,
            "route": route,
            "prompt_chars": len(ordered["full_prompt"]),
            "kv_prefix_chars": len(ordered["prefix_segments"]),
        }

    completion = complete_prompt(
        system_prompt=ordered["prefix_segments"],
        user_prompt=ordered["volatile_tail"],
        model_tier=model_tier,
        provider_override=provider,
        env=env,
    )
    return {
        "dry_run": False,
        "skill": skill_name,
        "route": route,
        "output": completion["content"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FreeCMO standalone CLI runner (Local LLM, OpenRouter, or Cloud).")
    parser.add_argument("--repo-root", default=str(REPO_ROOT), help="Workspace root")
    parser.add_argument("--provider", help="Override LLM provider (ollama | lmstudio | openrouter | deepseek | groq | openai | anthropic | gemini)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show LLM provider routing, configured ad platforms, and strategy lock status")

    p_init = sub.add_parser("init", help="Bootstrap .agents/brand-truth.md and deterministic unit economics")
    p_init.add_argument("--brand-name", required=True)
    p_init.add_argument("--website-url", required=True)
    p_init.add_argument("--aov-usd", type=float, required=True)
    p_init.add_argument("--gross-margin-pct", type=float, required=True)
    p_init.add_argument("--monthly-budget-usd", type=float, default=2000.0)
    p_init.add_argument("--description", default="SMB product/service")

    p_sync = sub.add_parser("sync-brief", help="Sync ad/revenue platforms and emit Weekly Composer's Brief")
    p_sync.add_argument("--demo-fixture", action="store_true")

    p_run = sub.add_parser("run-skill", help="Execute a specialist FreeCMO skill via local or cloud LLM")
    p_run.add_argument("--skill", required=True, help="Skill folder name (e.g., editorial-blog-linkedin-writer)")
    p_run.add_argument("--brief", required=True, help="Subtask brief text or path to a file")
    p_run.add_argument("--tier", choices=MODEL_TIERS, default="balanced_worker")
    p_run.add_argument("--dry-run", action="store_true", help="Verify lock, KV-cache prompt assembly, and model route without API call")

    args = parser.parse_args(argv)
    root = pathlib.Path(args.repo_root).resolve()
    env = load_dotenv_file(root / ".env")

    if args.command == "status":
        out = cmd_status(root, env, args.provider)
    elif args.command == "init":
        out = cmd_init(
            repo_root=root,
            brand_name=args.brand_name,
            website_url=args.website_url,
            aov_usd=args.aov_usd,
            gross_margin_pct=args.gross_margin_pct,
            monthly_budget_usd=args.monthly_budget_usd,
            description=args.description,
        )
    elif args.command == "sync-brief":
        sync_res = sync_all_platforms(repo_root=root, env=env, demo_fixture=args.demo_fixture)
        brief = generate_next_actions(sync_res["orchestrator_state"], repo_root=root)
        out = {"synced_platforms": sync_res["synced_platforms"], "composers_brief": brief}
    elif args.command == "run-skill":
        brief_arg = args.brief
        p_candidate = pathlib.Path(brief_arg)
        brief_txt = p_candidate.read_text(encoding="utf-8") if p_candidate.exists() and p_candidate.is_file() else brief_arg
        out = cmd_run_skill(
            repo_root=root,
            skill_name=args.skill,
            brief_text=brief_txt,
            model_tier=args.tier,
            provider=args.provider,
            dry_run=args.dry_run,
            env=env,
        )
    else:
        raise ValueError(f"Unknown command {args.command}")

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
