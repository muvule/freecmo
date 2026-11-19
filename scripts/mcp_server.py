"""Zero-dependency Model Context Protocol (MCP) JSON-RPC 2.0 stdio server for FreeCMO.

Exposes deterministic unit economics, promo break-even, creator commission caps,
blended MER, UTM governance, automated platform sync, and Weekly Composer's Brief
generation directly to Claude Desktop, Claude Code, Cursor, Codex, Gemini CLI, and Antigravity.
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculators import validate_json_schema
from calculators.cac_ltv import (
    compute_cac_ltv,
    compute_creator_commission_cap,
    compute_promo_breakeven,
)
from calculators.creative_fatigue import compute_launch_pacing_guard, detect_creative_fatigue
from calculators.fanout_audit import audit_page_fanout_readiness
from calculators.local_channels import (
    compute_offline_channel_economics,
    evaluate_low_bandwidth_readiness,
)
from calculators.mer import compute_blended_mer
from calculators.runway_churn import (
    compute_churn_and_nrr,
    compute_referral_and_review_economics,
    simulate_cash_flow_runway,
)
from connectors.ad_platform_sync import sync_all_platforms
from connectors.env_loader import load_dotenv_file
from connectors.utm_governance import build_governed_utm_url
from scripts.next_action import generate_next_actions


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "freecmo_unit_economics",
        "description": "Compute gross-profit LTV, break-even ROAS, allowable CAC, and payback period in any currency.",
        "inputSchema": {
            "type": "object",
            "required": ["gross_margin_pct"],
            "properties": {
                "currency": {"type": "string", "default": "USD"},
                "aov": {"type": "number"},
                "aov_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "repeat_orders": {"type": "number", "default": 1.0},
                "target_payback_months": {"type": "number", "default": 3.0},
                "monthly_orders_per_customer": {"type": "number", "default": 1.0},
                "actual_spend": {"type": "number"},
                "actual_spend_usd": {"type": "number"},
                "new_customers": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_promo_breakeven",
        "description": "Compute post-discount gross profit erosion and required volume lift % to break even on a promo in any currency.",
        "inputSchema": {
            "type": "object",
            "required": ["gross_margin_pct", "discount_pct"],
            "properties": {
                "currency": {"type": "string", "default": "USD"},
                "aov": {"type": "number"},
                "aov_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "discount_pct": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_creator_commission_cap",
        "description": "Compute maximum affiliate/creator payout per conversion within allowable CAC in any currency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "default": "USD"},
                "allowable_cac": {"type": "number"},
                "allowable_cac_usd": {"type": "number"},
                "paid_whitelisting_cpa": {"type": "number"},
                "paid_whitelisting_cpa_usd": {"type": "number", "default": 0.0},
                "creator_flat_fee": {"type": "number"},
                "creator_flat_fee_usd": {"type": "number", "default": 0.0},
                "expected_conversions": {"type": "number", "default": 10},
            },
        },
    },
    {
        "name": "freecmo_blended_mer",
        "description": "Compute Blended Marketing Efficiency Ratio (MER) separating organic, branded, and cold paid in any currency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "currency": {"type": "string", "default": "USD"},
                "total_revenue": {"type": "number"},
                "total_revenue_usd": {"type": "number"},
                "total_ad_spend": {"type": "number"},
                "total_ad_spend_usd": {"type": "number"},
                "branded_paid_revenue": {"type": "number"},
                "branded_paid_revenue_usd": {"type": "number"},
                "branded_paid_spend": {"type": "number"},
                "branded_paid_spend_usd": {"type": "number"},
                "non_branded_paid_revenue": {"type": "number"},
                "non_branded_paid_revenue_usd": {"type": "number"},
                "non_branded_paid_spend": {"type": "number"},
                "non_branded_paid_spend_usd": {"type": "number"},
                "organic_revenue": {"type": "number"},
                "organic_revenue_usd": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_utm_builder",
        "description": "Build a governed UTM-tagged URL matching FreeCMO IdentityResolver attribution taxonomy.",
        "inputSchema": {
            "type": "object",
            "required": ["destination_url", "utm_source", "utm_medium", "utm_campaign"],
            "properties": {
                "destination_url": {"type": "string"},
                "utm_source": {"type": "string"},
                "utm_medium": {"type": "string"},
                "utm_campaign": {"type": "string"},
                "utm_content": {"type": "string"},
                "utm_term": {"type": "string"},
            },
        },
    },
    {
        "name": "freecmo_validate_creative_spec",
        "description": "Validate a Social (IG/FB/LinkedIn/X), Display (IAB), or Native creative brief against creative_asset_spec.schema.json.",
        "inputSchema": {
            "type": "object",
            "required": ["spec"],
            "properties": {
                "spec": {"type": "object"},
            },
        },
    },
    {
        "name": "freecmo_sync_platforms",
        "description": "Sync Google Ads, Meta/IG/FB, LinkedIn, TikTok, GA4, GSC, Stripe, & Shopify into data/exports/ and emit Weekly Brief.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "demo_fixture": {"type": "boolean", "default": False},
                "lookback_days": {"type": "integer", "default": 30},
                "allowable_cac_usd": {"type": "number", "default": 100.0},
                "monthly_budget_usd": {"type": "number", "default": 2500.0},
                "gross_margin_pct": {"type": "number", "default": 65.0},
                "site_load_sec": {"type": "number", "default": 2.1},
                "emit_brief": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "freecmo_churn_and_runway",
        "description": "Compute SaaS/SMB churn & NRR, 12-month J-curve cash runway trough, or referral k-factor & review targets in any currency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["churn_nrr", "cash_runway", "referral_loop"],
                    "default": "churn_nrr",
                },
                "currency": {"type": "string", "default": "USD"},
                "starting_mrr": {"type": "number"},
                "starting_mrr_usd": {"type": "number"},
                "monthly_logo_churn_pct": {"type": "number"},
                "monthly_revenue_churn_pct": {"type": "number"},
                "monthly_expansion_pct": {"type": "number"},
                "new_customers_per_month": {"type": "number"},
                "available_cash": {"type": "number"},
                "available_cash_usd": {"type": "number"},
                "monthly_ad_spend": {"type": "number"},
                "monthly_ad_spend_usd": {"type": "number"},
                "allowable_cac": {"type": "number"},
                "allowable_cac_usd": {"type": "number"},
                "monthly_gross_profit_per_customer": {"type": "number"},
                "monthly_gross_profit_per_customer_usd": {"type": "number"},
                "horizon_months": {"type": "integer", "default": 12},
                "fixed_marketing_ops": {"type": "number"},
                "fixed_marketing_ops_usd": {"type": "number"},
                "paid_cac": {"type": "number"},
                "paid_cac_usd": {"type": "number"},
                "referral_invite_rate": {"type": "number"},
                "referral_conversion_rate": {"type": "number"},
                "referrer_reward": {"type": "number"},
                "referrer_reward_usd": {"type": "number"},
                "friend_discount_cost": {"type": "number"},
                "friend_discount_cost_usd": {"type": "number"},
                "current_reviews": {"type": "number"},
                "current_rating": {"type": "number"},
                "target_rating": {"type": "number"},
                "competitor_reviews": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_creative_fatigue",
        "description": "Detect ad creative fatigue (frequency saturation + CTR decay / CPA inflation) or evaluate T-21..T+7 launch budget pacing in any currency.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["fatigue", "launch_pacing"],
                    "default": "fatigue",
                },
                "currency": {"type": "string", "default": "USD"},
                "creatives": {"type": "array", "items": {"type": "object"}},
                "max_frequency": {"type": "number", "default": 3.2},
                "ctr_drop_threshold_pct": {"type": "number", "default": 20.0},
                "cpa_inflation_threshold_pct": {"type": "number", "default": 25.0},
                "min_spend_floor": {"type": "number"},
                "launch_budget": {"type": "number"},
                "launch_budget_usd": {"type": "number"},
                "days_elapsed": {"type": "number"},
                "total_launch_days": {"type": "number"},
                "spend_to_date": {"type": "number"},
                "spend_to_date_usd": {"type": "number"},
                "revenue_to_date": {"type": "number"},
                "revenue_to_date_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "target_mer": {"type": "number", "default": 2.5},
            },
        },
    },
    {
        "name": "freecmo_ai_search_fanout_audit",
        "description": "Audit HTML or Markdown pages for Google AI Mode (Gemini 4 Hydrogen) Query Fan-Out readiness, comparison tables, schema, and crawler access.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "file_path": {"type": "string"},
                "primary_query": {"type": "string", "default": ""},
                "content_format": {"type": "string", "enum": ["auto", "html", "markdown", "md"], "default": "auto"},
                "robots_txt": {"type": "string"},
            },
        },
    },
    {
        "name": "freecmo_offline_local_channel",
        "description": "Compute local-currency unit economics or validate GSM-7 SMS, WhatsApp Business broadcast, community FM radio, print flyer, bulletin board, and 2G/3G payload readiness.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["economics", "readiness"],
                    "default": "economics",
                },
                "currency": {"type": "string", "default": "USD"},
                "channel": {"type": "string", "default": "whatsapp_broadcast"},
                "recipients_or_reach": {"type": "number"},
                "total_campaign_cost": {"type": "number"},
                "total_campaign_cost_usd": {"type": "number"},
                "response_or_redemption_rate_pct": {"type": "number"},
                "aov": {"type": "number"},
                "aov_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "allowable_cac": {"type": "number"},
                "allowable_cac_usd": {"type": "number"},
                "message_text": {"type": "string"},
                "include_opt_out": {"type": "boolean", "default": True},
                "html_payload_kb": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_weekly_brief",
        "description": "Generate Dual Readout Weekly Composer's Brief from latest synced telemetry state.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state_path": {"type": "string"},
            },
        },
    },
]


def _resolve_safe_workspace_file(
    raw_path: str,
    repo_root: pathlib.Path,
    allowed_suffixes: tuple[str, ...],
) -> pathlib.Path:
    ws_root = repo_root.resolve()
    candidate = pathlib.Path(raw_path)
    raw_target = (ws_root / candidate) if not candidate.is_absolute() else candidate
    if raw_target.is_symlink():
        raise ValueError("Symlink file access is disallowed in MCP tools")
    resolved = raw_target.resolve()
    if not resolved.is_relative_to(ws_root):
        raise ValueError("Path must reside inside repository workspace")
    rel_parts = resolved.relative_to(ws_root).parts
    if any(part.startswith(".") for part in rel_parts):
        raise ValueError("Hidden/dotfile paths (such as .env or .git) are disallowed in MCP tools")
    if resolved.suffix.lower() not in allowed_suffixes:
        raise ValueError(f"Unsupported file extension {resolved.suffix!r}; allowed={allowed_suffixes}")
    return resolved


def dispatch_tool_call(name: str, arguments: dict[str, Any], repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Execute an MCP tool call deterministically and return JSON-serializable output."""
    if arguments is None:
        args: dict[str, Any] = {}
    elif not isinstance(arguments, dict):
        raise ValueError("MCP tool arguments must be a JSON object")
    else:
        args = dict(arguments)

    if name == "freecmo_unit_economics":
        return compute_cac_ltv(**args)
    if name == "freecmo_promo_breakeven":
        return compute_promo_breakeven(**args)
    if name == "freecmo_creator_commission_cap":
        return compute_creator_commission_cap(**args)
    if name == "freecmo_blended_mer":
        return compute_blended_mer(**args)
    if name == "freecmo_utm_builder":
        return build_governed_utm_url(**args)
    if name == "freecmo_churn_and_runway":
        mode = str(args.pop("mode", "churn_nrr"))
        if mode == "cash_runway":
            return simulate_cash_flow_runway(**args)
        if mode == "referral_loop":
            return compute_referral_and_review_economics(**args)
        if mode == "churn_nrr":
            return compute_churn_and_nrr(**args)
        raise ValueError(f"Unsupported freecmo_churn_and_runway mode: {mode!r}")
    if name == "freecmo_creative_fatigue":
        mode = str(args.pop("mode", "fatigue"))
        if mode == "launch_pacing":
            return compute_launch_pacing_guard(**args)
        if mode == "fatigue":
            return detect_creative_fatigue(**args)
        raise ValueError(f"Unsupported freecmo_creative_fatigue mode: {mode!r}")
    if name == "freecmo_ai_search_fanout_audit":
        fp = args.pop("file_path", None)
        content = args.pop("content", None)
        if fp:
            target = _resolve_safe_workspace_file(
                str(fp),
                repo_root,
                allowed_suffixes=(".html", ".htm", ".md", ".markdown", ".txt"),
            )
            content = target.read_text(encoding="utf-8")
        return audit_page_fanout_readiness(content=content, **args)
    if name == "freecmo_offline_local_channel":
        mode = str(args.pop("mode", "economics"))
        if mode == "readiness":
            return evaluate_low_bandwidth_readiness(**args)
        if mode == "economics":
            return compute_offline_channel_economics(**args)
        raise ValueError(f"Unsupported freecmo_offline_local_channel mode: {mode!r}")
    if name == "freecmo_validate_creative_spec":
        spec = args.get("spec")
        if not isinstance(spec, dict):
            raise ValueError("freecmo_validate_creative_spec requires a 'spec' JSON object")
        schema_dir = repo_root / "schemas"
        schema = json.loads((schema_dir / "creative_asset_spec.schema.json").read_text(encoding="utf-8"))
        errors = validate_json_schema(spec, schema, schema_dir)
        return {
            "valid": len(errors) == 0,
            "asset_id": spec.get("asset_id"),
            "errors": errors,
        }
    if name == "freecmo_sync_platforms":
        emit_brief = bool(args.get("emit_brief", True))
        env = load_dotenv_file(repo_root / ".env")
        sync_res = sync_all_platforms(
            repo_root=repo_root,
            lookback_days=int(args.get("lookback_days", 30)),
            env=env,
            demo_fixture=bool(args.get("demo_fixture", False)),
            allowable_cac_usd=float(args.get("allowable_cac_usd", 100.0)),
            monthly_budget_usd=float(args.get("monthly_budget_usd", 2500.0)),
            gross_margin_pct=float(args.get("gross_margin_pct", 65.0)),
            site_load_sec=float(args.get("site_load_sec", 2.1)),
        )
        out: dict[str, Any] = {
            "synced_platforms": sync_res["synced_platforms"],
            "sync_errors": sync_res["sync_errors"],
            "written_exports": sync_res["written_exports"],
            "unified_customer_records": sync_res["unified_customer_records"],
        }
        if emit_brief:
            out["composers_brief"] = generate_next_actions(sync_res["orchestrator_state"], repo_root=repo_root)
        return out
    if name == "freecmo_weekly_brief":
        sp = args.get("state_path")
        if sp:
            target = _resolve_safe_workspace_file(str(sp), repo_root, allowed_suffixes=(".json",))
        else:
            target = repo_root / "data" / "latest_sync_state.json"
        state = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
        return generate_next_actions(state, repo_root=repo_root)
    raise ValueError(f"Unknown MCP tool: {name!r}")


def handle_jsonrpc_message(msg: dict[str, Any], repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any] | None:
    """Process a single MCP JSON-RPC 2.0 message; return response dict or None for notifications."""
    method = msg.get("method", "")
    msg_id = msg.get("id")

    # Notifications have no id and expect no response
    if msg_id is None:
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "freecmo-mcp", "version": "0.2.0"},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": MCP_TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        t_name = str(params.get("name") or "")
        t_args = params.get("arguments") or {}
        try:
            res = dispatch_tool_call(t_name, t_args, repo_root=repo_root)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(res, indent=2, sort_keys=True)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> int:
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle_jsonrpc_message(msg, repo_root=REPO_ROOT)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
