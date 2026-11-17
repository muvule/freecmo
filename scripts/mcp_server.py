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
from calculators.mer import compute_blended_mer
from connectors.ad_platform_sync import sync_all_platforms
from connectors.env_loader import load_dotenv_file
from connectors.utm_governance import build_governed_utm_url
from scripts.next_action import generate_next_actions


MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "freecmo_unit_economics",
        "description": "Compute gross-profit LTV, break-even ROAS, allowable CAC, and payback period.",
        "inputSchema": {
            "type": "object",
            "required": ["aov_usd", "gross_margin_pct"],
            "properties": {
                "aov_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "repeat_orders": {"type": "number", "default": 1.0},
                "target_payback_months": {"type": "number", "default": 3.0},
                "monthly_orders_per_customer": {"type": "number", "default": 1.0},
                "actual_spend_usd": {"type": "number"},
                "new_customers": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_promo_breakeven",
        "description": "Compute post-discount gross profit erosion and required volume lift % to break even on a promo.",
        "inputSchema": {
            "type": "object",
            "required": ["aov_usd", "gross_margin_pct", "discount_pct"],
            "properties": {
                "aov_usd": {"type": "number"},
                "gross_margin_pct": {"type": "number"},
                "discount_pct": {"type": "number"},
            },
        },
    },
    {
        "name": "freecmo_creator_commission_cap",
        "description": "Compute maximum affiliate/creator payout per conversion within allowable CAC.",
        "inputSchema": {
            "type": "object",
            "required": ["allowable_cac_usd"],
            "properties": {
                "allowable_cac_usd": {"type": "number"},
                "paid_whitelisting_cpa_usd": {"type": "number", "default": 0.0},
                "creator_flat_fee_usd": {"type": "number", "default": 0.0},
                "expected_conversions": {"type": "number", "default": 10},
            },
        },
    },
    {
        "name": "freecmo_blended_mer",
        "description": "Compute Blended Marketing Efficiency Ratio (MER) separating organic, branded, and cold paid.",
        "inputSchema": {
            "type": "object",
            "required": ["total_revenue_usd", "total_marketing_spend_usd"],
            "properties": {
                "total_revenue_usd": {"type": "number"},
                "total_marketing_spend_usd": {"type": "number"},
                "non_branded_organic_revenue_usd": {"type": "number"},
                "branded_search_revenue_usd": {"type": "number"},
                "paid_cold_revenue_usd": {"type": "number"},
                "paid_cold_spend_usd": {"type": "number"},
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


def dispatch_tool_call(name: str, arguments: dict[str, Any], repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Execute an MCP tool call deterministically and return JSON-serializable output."""
    if arguments is None:
        args: dict[str, Any] = {}
    elif not isinstance(arguments, dict):
        raise ValueError("MCP tool arguments must be a JSON object")
    else:
        args = arguments

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
            target = pathlib.Path(str(sp)).resolve()
            if not target.is_relative_to(repo_root.resolve()):
                raise ValueError("state_path must reside inside repository workspace")
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
