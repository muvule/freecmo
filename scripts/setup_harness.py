"""Multi-host harness configurator & exporter for FreeCMO.

Generates ready-to-use configurations and knowledge packs for:
- Antigravity & Gemini CLI
- Claude Code, Claude Desktop (MCP), & Claude Web Projects
- OpenAI Codex & ChatGPT (Custom GPTs / Projects)
- Cursor (.cursor/rules/freecmo.mdc + MCP)
- Local LLMs (Ollama, LM Studio, vLLM, llama.cpp)
- OpenRouter / DeepSeek / Groq / Together AI (budget cloud APIs)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from scripts.build_packages import RUNTIME_PROFILES, build_artifacts


SUPPORTED_HOSTS = (
    "all",
    "antigravity",
    "gemini-cli",
    "claude-code",
    "claude-desktop",
    "claude-web",
    "chatgpt",
    "codex",
    "cursor",
    "local-llm",
    "openrouter",
)


def _build_mcp_server_entry(repo_root: pathlib.Path) -> dict[str, Any]:
    return {
        "mcpServers": {
            "freecmo-core": {
                "command": "python3",
                "args": [str((repo_root / "scripts" / "mcp_server.py").resolve())],
                "env": {},
            }
        }
    }


def _build_chatgpt_instructions() -> str:
    """Compact <=8,000-character system instruction block for ChatGPT Custom GPTs & Projects."""
    text = """# FreeCMO — SMB CMO Agent Harness (ChatGPT Custom GPT / Project Instructions)

You are the **CMO Orchestrator** for **FreeCMO**. Human attention is the scarcest resource: operate as an attention-budgeted **Composer -> Orchestrator -> Specialist Subtask Pipeline**. Never output generic MBA fluff (no ungrounded SWOT/PESTEL), never guess missing metrics (mark `"unknown"`), and never recommend scaling paid ads when unit economics or conversion tracking are unverified.

## 1. Hard Strategy-Before-Production Lock
1. On `/cmo init`, interview or crawl the founder's URL, product description, monthly budget, gross margin %, AOV, and target payback window. Draft `brand-truth.md` (`status: draft_pending_review`) and `visual-dna.json`.
2. **LOCK:** Do NOT generate paid campaigns, outbound emails, or live code PRs until the founder explicitly approves `brand-truth.md` (`status: locked`).
3. Surface at most **5 ranked decisions** per Weekly Composer's Brief, each with:
   - Dollar impact (`$`)
   - Source Receipt (exact CSV row range, API report, or Knowledge file section)
   - Quantitative **disproof condition** (e.g., `ctr < 0.008 after 2500 impressions`)

## 2. Deterministic Math Formulas (Run in Code Interpreter / Python)
Always use Python Code Interpreter (never mental math) for every number:
- `gross_profit_per_order = aov_usd * (gross_margin_pct / 100)`
- `break_even_roas = 100 / gross_margin_pct`
- `allowable_cac_usd = min(gross_profit_per_order * repeat_orders, gross_profit_per_order * monthly_orders_per_customer * target_payback_months)`
- `promo_required_volume_lift_pct = ((baseline_gp / (aov_usd * (1 - discount_pct/100) - cogs)) - 1) * 100`
- `creator_max_payout_usd = allowable_cac_usd - paid_whitelisting_cpa_usd - (creator_flat_fee_usd / expected_conversions)`
- `blended_mer = total_revenue_usd / total_marketing_spend_usd`

## 3. Channel Coverage & Creative Studio Rules
- **Paid & Organic Search:** Cross-check Google Ads vs. Search Console. Suppress paid brand/exact queries where organic rank <= 2 and competitor impression share < 5%. Seed SEO/GEO pages from converting paid terms (`conversions >= 3`, `CPA <= allowable_cac_usd`).
- **Instagram, Facebook, LinkedIn, X, Reddit, Display & Native Ads:**
  - Respect `visual-dna.json` aspect ratios: `9:16` (`1080x1920` IG/FB Reels & Stories), `4:5` (`1080x1350` IG/FB/LinkedIn portrait feed), `1.91:1` (`1200x628` Display/Native), and IAB banners (`300x250`, `728x90`, `300x600`, `320x50`, `160x600`).
  - Specify whether each visual uses **AI image generation** (exact prompt + negative constraints), **founder photo shoot** (shot list), or **product UI capture**.
  - Append mandatory FTC/community disclosures (`#ad` on paid creator posts; `(Disclosure: I work on <Brand>)` on Reddit/HN/forum posts).
- **Editorial & Comms:** Draft answer-first SEO/GEO blog posts, LinkedIn articles, and AP-style press releases grounded strictly in `[STONE]` verified facts vs. `[OPINION]` commentary.
- **4-Lens Review:** Self-audit every draft across (1) Brand QA (zero AI-slop), (2) Claims & FTC Disclosure QA, (3) CRO QA (clear offer & CTA), and (4) Falsifiability QA (never revive Killed Assumptions).
"""
    return text.strip() + "\n"


def _build_knowledge_bundle(repo_root: pathlib.Path) -> str:
    """Compile AGENTS.md, guardrails, brand-truth template, visual-dna, and llms-full.txt into one uploadable file."""
    parts: list[str] = ["# FreeCMO Knowledge Bundle (Upload to ChatGPT Projects / Custom GPT or Claude.ai Projects)\n"]
    for rel in (
        "AGENTS.md",
        ".agents/guardrails.yaml",
        ".agents/brand-truth.template.md",
        ".agents/visual-dna.json",
        "llms-full.txt",
    ):
        p = repo_root / rel
        if p.exists():
            parts.append(f"\n---\n## FILE: {rel}\n\n" + p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def _build_cursor_mdc(repo_root: pathlib.Path) -> str:
    agents_md = (repo_root / "AGENTS.md").read_text(encoding="utf-8")
    return (
        "---\n"
        "description: FreeCMO Orchestrator, Strategy Lock, Calculators, and 4-Lens Reviewer Rules\n"
        "globs: [\"**/*\"]\n"
        "alwaysApply: true\n"
        "---\n\n"
        + agents_md
    )


def generate_host_configs(
    host: str,
    repo_root: pathlib.Path = REPO_ROOT,
    output_dir: pathlib.Path | None = None,
    write_workspace_cursor: bool = False,
    profile: str | None = None,
) -> dict[str, Any]:
    """Generate host configuration files and return manifest + quickstart instructions."""
    if host not in SUPPORTED_HOSTS:
        raise ValueError(f"Unsupported host {host!r}; choose from {SUPPORTED_HOSTS}")
    if profile is not None and profile not in RUNTIME_PROFILES:
        raise ValueError(f"Unsupported profile {profile!r}; choose from {sorted(RUNTIME_PROFILES)}")

    if profile is not None:
        build_artifacts(repo_root=repo_root, check_only=False, profile=profile)

    out_dir = (output_dir or (repo_root / "dist" / "hosts")).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    targets = list(SUPPORTED_HOSTS[1:]) if host == "all" else [host]

    written: list[str] = []
    mcp_cfg = _build_mcp_server_entry(repo_root)

    if any(t in targets for t in ("claude-desktop", "claude-code", "antigravity", "gemini-cli", "codex")):
        mcp_path = out_dir / "claude_desktop_and_mcp_config.json"
        mcp_path.write_text(json.dumps(mcp_cfg, indent=2) + "\n", encoding="utf-8")
        written.append(str(mcp_path))

    if "cursor" in targets:
        mdc_content = _build_cursor_mdc(repo_root)
        cursor_out = out_dir / "cursor_freecmo.mdc"
        cursor_out.write_text(mdc_content, encoding="utf-8")
        written.append(str(cursor_out))
        cursor_mcp = out_dir / "cursor_mcp.json"
        cursor_mcp.write_text(json.dumps(mcp_cfg, indent=2) + "\n", encoding="utf-8")
        written.append(str(cursor_mcp))
        if write_workspace_cursor:
            ws_mdc = repo_root / ".cursor" / "rules" / "freecmo.mdc"
            ws_mdc.parent.mkdir(parents=True, exist_ok=True)
            ws_mdc.write_text(mdc_content, encoding="utf-8")
            written.append(str(ws_mdc))

    if "chatgpt" in targets:
        gpt_inst = out_dir / "chatgpt_custom_gpt_instructions.md"
        inst_text = _build_chatgpt_instructions()
        if len(inst_text) > 8000:
            raise ValueError(f"ChatGPT Custom GPT instructions exceed 8,000-character limit ({len(inst_text)})")
        gpt_inst.write_text(inst_text, encoding="utf-8")
        written.append(str(gpt_inst))

        gpt_know = out_dir / "chatgpt_knowledge_bundle.md"
        gpt_know.write_text(_build_knowledge_bundle(repo_root), encoding="utf-8")
        written.append(str(gpt_know))

    if "claude-web" in targets:
        cl_inst = out_dir / "claude_project_instructions.md"
        cl_inst.write_text((repo_root / "AGENTS.md").read_text(encoding="utf-8"), encoding="utf-8")
        written.append(str(cl_inst))

        cl_know = out_dir / "claude_project_knowledge_bundle.md"
        cl_know.write_text(_build_knowledge_bundle(repo_root), encoding="utf-8")
        written.append(str(cl_know))

    if "local-llm" in targets:
        local_env = out_dir / "env.local-llm.example"
        local_env.write_text(
            "# FreeCMO — Local BYO-Machine Preset (Ollama / LM Studio / vLLM — $0 API cost)\n"
            "CMO_LLM_PROVIDER=ollama\n"
            "OLLAMA_BASE_URL=http://127.0.0.1:11434/v1\n"
            "OLLAMA_MODEL=qwen2.5:14b\n"
            "CMO_FAST_MODEL=qwen2.5:7b\n"
            "CMO_WORKER_MODEL=qwen2.5:14b\n"
            "CMO_ORCHESTRATOR_MODEL=qwen2.5:14b\n"
            "# For LM Studio instead of Ollama, set CMO_LLM_PROVIDER=lmstudio and LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1\n",
            encoding="utf-8",
        )
        written.append(str(local_env))

    if "openrouter" in targets:
        or_env = out_dir / "env.openrouter.example"
        or_env.write_text(
            "# FreeCMO — OpenRouter / Budget Multi-Model Preset (~90% lower token cost)\n"
            "CMO_LLM_PROVIDER=openrouter\n"
            "OPENROUTER_API_KEY=sk-or-v1-replace-me\n"
            "OPENROUTER_BASE_URL=https://openrouter.ai/api/v1\n"
            "CMO_FAST_MODEL=deepseek/deepseek-chat\n"
            "CMO_WORKER_MODEL=deepseek/deepseek-chat\n"
            "CMO_ORCHESTRATOR_MODEL=deepseek/deepseek-r1\n"
            "CMO_MULTIMODAL_MODEL=google/gemini-2.5-flash\n",
            encoding="utf-8",
        )
        written.append(str(or_env))

    return {
        "requested_host": host,
        "active_profile": profile or "unchanged",
        "output_dir": str(out_dir),
        "generated_files": written,
        "docs_guide": str(repo_root / "docs" / "HARNESS_SETUP.md"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate FreeCMO harness configuration for any AI host or local LLM.")
    parser.add_argument("--host", choices=SUPPORTED_HOSTS, default="all", help="Target AI host or provider")
    parser.add_argument("--profile", choices=sorted(RUNTIME_PROFILES.keys()), help="Optional <=16 runtime skill pack profile to activate")
    parser.add_argument("--output-dir", help="Output directory for generated host bundles (default: dist/hosts)")
    parser.add_argument("--write-workspace-cursor", action="store_true", help="Also write .cursor/rules/freecmo.mdc")
    args = parser.parse_args(argv)

    out_dir = pathlib.Path(args.output_dir) if args.output_dir else None
    res = generate_host_configs(
        host=args.host,
        repo_root=REPO_ROOT,
        output_dir=out_dir,
        write_workspace_cursor=args.write_workspace_cursor,
        profile=args.profile,
    )
    print(json.dumps(res, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
