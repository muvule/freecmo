import json
import pathlib
import shutil
import tempfile
import unittest
import urllib.request
from typing import Any

from calculators import validate_json_schema
from calculators.cac_ltv import compute_creator_commission_cap, compute_promo_breakeven
from connectors.ad_platform_sync import (
    detect_configured_platforms,
    fetch_google_ads,
    fetch_meta_ads_and_social,
    fetch_shopify_orders,
    fetch_stripe_revenue,
    sync_all_platforms,
)
from connectors.llm_router import complete_prompt, resolve_llm_route
from connectors.utm_governance import build_governed_utm_url
from scripts.cmo_runner import cmd_init, cmd_run_skill, cmd_status
from scripts.mcp_server import handle_jsonrpc_message
from scripts.next_action import generate_next_actions
from scripts.setup_harness import generate_host_configs


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestV020Features(unittest.TestCase):
    def test_promo_breakeven_and_creator_commission_caps(self) -> None:
        ok_promo = compute_promo_breakeven(aov_usd=120, gross_margin_pct=60, discount_pct=20)
        self.assertEqual(ok_promo["status"], "ok")
        self.assertTrue(ok_promo["profitable_unit_margin"])
        self.assertAlmostEqual(ok_promo["required_volume_lift_pct"], 50.0)

        bad_promo = compute_promo_breakeven(aov_usd=100, gross_margin_pct=25, discount_pct=30)
        self.assertEqual(bad_promo["status"], "ok")
        self.assertFalse(bad_promo["profitable_unit_margin"])
        self.assertEqual(bad_promo["required_volume_lift_pct"], "impossible_negative_margin")

        unk_promo = compute_promo_breakeven(aov_usd="unknown", gross_margin_pct=50, discount_pct=10)
        self.assertEqual(unk_promo["status"], "unknown")

        ok_creator = compute_creator_commission_cap(
            allowable_cac_usd=90,
            paid_whitelisting_cpa_usd=25,
            creator_flat_fee_usd=200,
            expected_conversions=10,
        )
        self.assertTrue(ok_creator["viable_partnership"])
        self.assertAlmostEqual(ok_creator["max_affiliate_payout_usd"], 45.0)

        bad_creator = compute_creator_commission_cap(
            allowable_cac_usd=40,
            paid_whitelisting_cpa_usd=20,
            creator_flat_fee_usd=300,
            expected_conversions=10,
        )
        self.assertFalse(bad_creator["viable_partnership"])
        self.assertEqual(bad_creator["max_affiliate_payout_usd"], 0.0)

    def test_utm_governance_and_creative_schemas(self) -> None:
        utm = build_governed_utm_url(
            destination_url="https://nordicdesk.example/standing?ref=nav",
            utm_source="Instagram Reels",
            utm_medium="paid_social",
            utm_campaign="Spring Launch 2026!",
            utm_content="4x5 Carousel A",
        )
        self.assertIn("utm_source=instagram_reels", utm["url"])
        self.assertIn("utm_medium=paid_social", utm["url"])
        self.assertIn("utm_campaign=spring_launch_2026", utm["url"])
        self.assertIn("ref=nav", utm["url"])

        with self.assertRaises(ValueError):
            build_governed_utm_url("https://example.com", "ig", "invalid_medium", "camp")

        schema_dir = REPO_ROOT / "schemas"
        creative_schema = json.loads((schema_dir / "creative_asset_spec.schema.json").read_text(encoding="utf-8"))
        valid_spec = {
            "asset_id": "ig-display-01",
            "channel_family": "instagram_facebook_social",
            "visual_dna_ref": ".agents/visual-dna.json",
            "image_acquisition_mode": "ai_image_generation",
            "image_direction": {
                "aspect_ratio": "4:5",
                "iab_banner_sizes": ["300x250", "728x90"],
                "focal_subject": "Minimalist oak standing desk in daylight studio",
                "generation_prompt_or_shot_list": "Scandinavian oak desk, soft morning daylight, warm alabaster wall, zero text",
                "negative_constraints": ["no neon gradients", "no garbled text"],
                "safe_zone_note": "Keep top 14% and bottom 20% clear for Reels/Feed UI",
            },
            "copy_variants": [
                {
                    "short_headline": "Built for 8-Hour Focus",
                    "long_headline": "Solid oak standing desks engineered for quiet home offices.",
                    "primary_text": "Stop wobbling mid-call. Tested to 120kg with a 30-day studio trial.",
                    "cta_label": "See Dimensions",
                }
            ],
            "compliance_disclosure": "Sponsored",
            "utm_tagged_url": utm["url"],
            "disproof_condition": "ctr < 0.009 after 2500 impressions",
        }
        self.assertEqual(validate_json_schema(valid_spec, creative_schema, schema_dir), [])

        # Over-length short_headline (>30 chars) must fail schema validation
        invalid_spec = json.loads(json.dumps(valid_spec))
        invalid_spec["copy_variants"][0]["short_headline"] = "This short headline is way over thirty characters long"
        self.assertTrue(len(validate_json_schema(invalid_spec, creative_schema, schema_dir)) > 0)

    def test_automated_platform_sync_mock_and_demo_pipeline(self) -> None:
        env = {
            "GOOGLE_ADS_CUSTOMER_ID": "123-456-7890",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "dev-tok",
            "GOOGLE_ADS_ACCESS_TOKEN": "ya29.test",
            "META_ACCESS_TOKEN": "EAAB-test",
            "META_AD_ACCOUNT_ID": "act_998877",
            "IG_BUSINESS_ACCOUNT_ID": "1784140000",
            "FB_PAGE_ID": "100200300",
            "STRIPE_RESTRICTED_KEY": "rk_live_secret",
            "SHOPIFY_STORE_DOMAIN": "nordic.myshopify.com",
            "SHOPIFY_ADMIN_TOKEN": "shpat_secret",
        }
        configured = detect_configured_platforms(env)
        self.assertEqual(configured, ["google_ads", "meta_ads", "stripe", "shopify"])

        def fake_transport(req: urllib.request.Request) -> dict[str, Any]:
            u = req.full_url
            if "googleads.googleapis.com" in u:
                return {
                    "batches": [
                        {
                            "results": [
                                {
                                    "campaign": {"id": "11", "name": "Search Core"},
                                    "metrics": {
                                        "costMicros": "250000000",
                                        "impressions": "1200",
                                        "clicks": "95",
                                        "conversions": "5",
                                        "conversionsValue": "900",
                                    },
                                    "searchTermView": {"searchTerm": "oak standing desk"},
                                }
                            ]
                        }
                    ]
                }
            if "/act_998877/insights" in u:
                return {
                    "data": [
                        {
                            "campaign_id": "22",
                            "campaign_name": "IG Reels Prospecting",
                            "publisher_platform": "instagram",
                            "spend": "180.50",
                            "impressions": "9400",
                            "clicks": "140",
                            "actions": [{"action_type": "purchase", "value": "3"}],
                            "action_values": [{"action_type": "purchase", "value": "540.0"}],
                        }
                    ]
                }
            if "/1784140000/media" in u:
                return {
                    "data": [
                        {"id": "ig1", "media_type": "REELS", "caption": "Desk cable tray", "saved": 120, "plays": 9000, "reach": 8500},
                        {"id": "ig2", "media_type": "CAROUSEL_ALBUM", "caption": "Wood grain", "saved": 10, "plays": 400, "reach": 500},
                    ]
                }
            if "/100200300/posts" in u:
                return {"data": [{"id": "fb1", "message": "Studio tour", "shares": {"count": 4}}]}
            if "api.stripe.com" in u:
                return {
                    "data": [
                        {
                            "id": "ch_1",
                            "paid": True,
                            "refunded": False,
                            "amount": 24000,
                            "billing_details": {"email": "alice@private-customer.com"},
                            "metadata": {"utm_source": "instagram_reels"},
                        }
                    ]
                }
            if "myshopify.com" in u:
                return {
                    "orders": [
                        {
                            "id": 501,
                            "email": "bob@private-customer.com",
                            "total_price": "310.00",
                            "landing_site": "/products/desk?utm_source=google_cpc",
                        }
                    ]
                }
            return {}

        gads = fetch_google_ads(env, transport=fake_transport)
        self.assertEqual(gads["rows"][0]["spend_usd"], 250.0)
        meta = fetch_meta_ads_and_social(env, transport=fake_transport)
        self.assertEqual(len(meta["organic_social_posts"]), 3)
        self.assertGreaterEqual(meta["organic_social_posts"][0]["save_or_watch_multiplier"], 2.0)

        stripe_res = fetch_stripe_revenue(env, transport=fake_transport)
        shopify_res = fetch_shopify_orders(env, transport=fake_transport)
        # Ensure raw emails were hashed and never appear in normalized rows
        self.assertNotIn("alice@private-customer.com", json.dumps(stripe_res))
        self.assertNotIn("bob@private-customer.com", json.dumps(shopify_res))

        # Full end-to-end demo sync + locked brief generation in isolated workspace
        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp)
            (ws / ".agents").mkdir(parents=True)
            shutil.copy(REPO_ROOT / ".agents" / "guardrails.yaml", ws / ".agents" / "guardrails.yaml")
            shutil.copytree(REPO_ROOT / "schemas", ws / "schemas")
            (ws / ".agents" / "brand-truth.md").write_text("---\nstatus: locked\n---\n# Brand Truth\n", encoding="utf-8")

            sync_out = sync_all_platforms(repo_root=ws, demo_fixture=True)
            self.assertIn("google_ads", sync_out["synced_platforms"])
            self.assertIn("meta_ads", sync_out["synced_platforms"])
            self.assertEqual(sync_out["unified_customer_records"], 2)

            brief = generate_next_actions(sync_out["orchestrator_state"], repo_root=ws)
            self.assertEqual(brief["strategy_lock_status"], "locked")
            self.assertGreaterEqual(len(brief["human_readout"]["ranked_decisions"]), 3)
            # Stop-loss on meta-ig-prospecting (spend 510, roas 0.75, 16 days) should trigger circuit breaker
            self.assertTrue(len(brief["circuit_breakers"]) >= 1)

    def test_llm_router_local_openrouter_and_frontier_protocols(self) -> None:
        # Default fallback with empty env -> local ollama (no key required)
        r_local = resolve_llm_route("balanced_worker", env={})
        self.assertEqual(r_local["provider"], "ollama")
        self.assertTrue(r_local["key_configured"])

        # Auto-selects OpenRouter when OPENROUTER_API_KEY is set
        r_or = resolve_llm_route("deep_orchestrator", env={"OPENROUTER_API_KEY": "sk-or-test"})
        self.assertEqual(r_or["provider"], "openrouter")
        self.assertEqual(r_or["model"], "deepseek/deepseek-r1")

        captured_headers: dict[str, str] = {}
        captured_url: list[str] = []

        def mock_gemini_tx(req: urllib.request.Request) -> dict[str, Any]:
            captured_url.append(req.full_url)
            captured_headers.update({k.lower(): v for k, v in req.header_items()})
            return {"candidates": [{"content": {"parts": [{"text": "Gemini verified response"}]}}]}

        gem_out = complete_prompt(
            system_prompt="System rules",
            user_prompt="Hello",
            provider_override="gemini",
            env={"GEMINI_API_KEY": "secret-gem-key"},
            transport=mock_gemini_tx,
        )
        self.assertEqual(gem_out["content"], "Gemini verified response")
        # Security invariant: API key must be in header, never leaked in URL query string
        self.assertNotIn("secret-gem-key", captured_url[0])
        self.assertEqual(captured_headers.get("x-goog-api-key"), "secret-gem-key")

        # SSRF check: non-loopback plain HTTP must raise ValueError
        with self.assertRaises(ValueError):
            resolve_llm_route("fast_decider", provider_override="ollama", env={"OLLAMA_BASE_URL": "http://169.254.169.254/v1"})

    def test_mcp_server_jsonrpc_and_tools(self) -> None:
        init_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        assert init_resp is not None
        self.assertEqual(init_resp["result"]["serverInfo"]["name"], "freecmo-mcp")

        # Notification returns None
        self.assertIsNone(handle_jsonrpc_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))

        tools_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert tools_resp is not None
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("freecmo_promo_breakeven", tool_names)
        self.assertIn("freecmo_sync_platforms", tool_names)

        call_resp = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "freecmo_promo_breakeven",
                    "arguments": {"aov_usd": 120, "gross_margin_pct": 60, "discount_pct": 20},
                },
            }
        )
        assert call_resp is not None
        self.assertFalse(call_resp["result"]["isError"])
        parsed = json.loads(call_resp["result"]["content"][0]["text"])
        self.assertEqual(parsed["required_volume_lift_pct"], 50.0)

        # Path traversal outside workspace must fail closed with isError=True
        bad_path_resp = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "freecmo_weekly_brief", "arguments": {"state_path": "/etc/passwd"}},
            }
        )
        assert bad_path_resp is not None
        self.assertTrue(bad_path_resp["result"]["isError"])

    def test_setup_harness_and_cmo_runner_lock_enforcement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = pathlib.Path(tmp) / "hosts"
            res = generate_host_configs("all", repo_root=REPO_ROOT, output_dir=out_dir)
            self.assertGreaterEqual(len(res["generated_files"]), 7)
            gpt_inst = (out_dir / "chatgpt_custom_gpt_instructions.md").read_text(encoding="utf-8")
            self.assertLessEqual(len(gpt_inst), 8000)

            # Test cmo_runner init + strategy lock enforcement
            ws = pathlib.Path(tmp) / "ws"
            ws.mkdir()
            shutil.copy(REPO_ROOT / "AGENTS.md", ws / "AGENTS.md")
            shutil.copytree(REPO_ROOT / ".agents", ws / ".agents")
            shutil.copytree(REPO_ROOT / "skills", ws / "skills")

            init_out = cmd_init(
                repo_root=ws,
                brand_name="NordicDesk",
                website_url="https://nordicdesk.example",
                aov_usd=140.0,
                gross_margin_pct=70.0,
                monthly_budget_usd=2000.0,
                description="Minimalist standing desks",
            )
            self.assertEqual(init_out["strategy_lock_status"], "draft_pending_review")
            bt_text = (ws / ".agents" / "brand-truth.md").read_text(encoding="utf-8")
            self.assertIn("$98.0", bt_text)

            # Production skill must be blocked while draft_pending_review
            with self.assertRaises(PermissionError):
                cmd_run_skill(
                    repo_root=ws,
                    skill_name="editorial-blog-linkedin-writer",
                    brief_text="Write ergonomic desk blog post",
                    model_tier="balanced_worker",
                    provider="ollama",
                    dry_run=True,
                    env={},
                )

            # Unlock brand-truth.md -> dry-run succeeds with local ollama route
            (ws / ".agents" / "brand-truth.md").write_text(
                bt_text.replace("status: draft_pending_review", "status: locked"),
                encoding="utf-8",
            )
            dry_out = cmd_run_skill(
                repo_root=ws,
                skill_name="editorial-blog-linkedin-writer",
                brief_text="Write ergonomic desk blog post",
                model_tier="balanced_worker",
                provider="ollama",
                dry_run=True,
                env={},
            )
            self.assertTrue(dry_out["dry_run"])
            self.assertEqual(dry_out["route"]["provider"], "ollama")
            status_out = cmd_status(ws, {}, "openrouter")
            self.assertEqual(status_out["strategy_lock_status"], "locked")


if __name__ == "__main__":
    unittest.main()
