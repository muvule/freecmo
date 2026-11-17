import base64
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.request
from typing import Any

from calculators.creative_fatigue import compute_launch_pacing_guard, detect_creative_fatigue
from calculators.fanout_audit import audit_page_fanout_readiness, generate_query_fanout_subquestions
from calculators.runway_churn import (
    compute_churn_and_nrr,
    compute_referral_and_review_economics,
    simulate_cash_flow_runway,
)
from connectors.llm_router import complete_prompt, load_attachment_file, resolve_llm_route
from scripts.build_packages import build_artifacts
from scripts.cmo_runner import cmd_run_skill
from scripts.mcp_server import handle_jsonrpc_message
from scripts.next_action import generate_next_actions
from scripts.setup_harness import generate_host_configs


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestGeminiHydrogenAndSmbCmoFeatures(unittest.TestCase):
    def test_gemini_hydrogen_routing_thinking_level_and_multimodal_attachments(self) -> None:
        r_hyd = resolve_llm_route(
            "balanced_worker",
            provider_override="gemini-hydrogen",
            env={"GEMINI_API_KEY": "AIza-test", "GEMINI_THINKING_LEVEL": "XHIGH"},
        )
        self.assertEqual(r_hyd["provider"], "gemini-hydrogen")
        self.assertEqual(r_hyd["model"], "gemini-4-hydrogen")
        self.assertEqual(r_hyd["thinking_level"], "XHIGH")

        r_fast = resolve_llm_route(
            "fast_decider",
            provider_override="gemini",
            env={"GEMINI_API_KEY": "AIza-test"},
        )
        self.assertEqual(r_fast["model"], "gemini-3.5-flash-lite")

        r_or = resolve_llm_route("multimodal_creative", env={"OPENROUTER_API_KEY": "sk-or-test"})
        self.assertEqual(r_or["model"], "google/gemini-4-hydrogen")

        # Invalid MINIMAL level must raise ValueError before issuing API call
        with self.assertRaises(ValueError):
            resolve_llm_route(
                "balanced_worker",
                provider_override="gemini-hydrogen",
                env={"GEMINI_API_KEY": "AIza-test", "GEMINI_THINKING_LEVEL": "MINIMAL"},
            )

        captured_reqs: list[tuple[str, dict[str, Any], dict[str, str]]] = []

        def mock_hydrogen_tx(req: urllib.request.Request) -> dict[str, Any]:
            body = json.loads(req.data.decode("utf-8")) if req.data else {}
            hdrs = {k.lower(): v for k, v in req.header_items()}
            captured_reqs.append((req.full_url, body, hdrs))
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "Internal reasoning summary...", "thought": True},
                                {"text": "Final Hydrogen critique output"},
                            ]
                        }
                    }
                ]
            }

        with tempfile.TemporaryDirectory() as tmp:
            img = pathlib.Path(tmp) / "hero.png"
            img.write_bytes(b"\x89PNG\r\n\x1a\nfake-png-bytes")
            att = load_attachment_file(img)
            self.assertEqual(att["mime_type"], "image/png")
            self.assertEqual(base64.b64decode(att["data_b64"]), b"\x89PNG\r\n\x1a\nfake-png-bytes")

            res = complete_prompt(
                system_prompt="Rules",
                user_prompt="Critique hero screenshot",
                model_tier="multimodal_creative",
                provider_override="gemini-hydrogen",
                env={"GEMINI_API_KEY": "secret-hyd-key"},
                thinking_level="XHIGH",
                attachments=[att],
                transport=mock_hydrogen_tx,
            )
            self.assertEqual(res["content"], "Final Hydrogen critique output")
            self.assertEqual(res["thinking_level"], "XHIGH")
            url, body, hdrs = captured_reqs[0]
            self.assertIn("/models/gemini-4-hydrogen:generateContent", url)
            self.assertEqual(hdrs.get("x-goog-api-key"), "secret-hyd-key")
            self.assertNotIn("temperature", body["generationConfig"])
            self.assertEqual(body["generationConfig"]["thinkingConfig"], {"thinkingLevel": "XHIGH"})
            parts = body["contents"][0]["parts"]
            self.assertEqual(parts[1]["inlineData"]["mimeType"], "image/png")

            # Test cmo_runner dry-run with --attach + --thinking-level
            ws = pathlib.Path(tmp) / "ws"
            ws.mkdir()
            shutil.copy(REPO_ROOT / "AGENTS.md", ws / "AGENTS.md")
            shutil.copytree(REPO_ROOT / ".agents", ws / ".agents")
            shutil.copytree(REPO_ROOT / "skills", ws / "skills")
            shutil.copytree(REPO_ROOT / "schemas", ws / "schemas")
            bt = (ws / ".agents" / "brand-truth.template.md").read_text(encoding="utf-8")
            (ws / ".agents" / "brand-truth.md").write_text(
                bt.replace("status: draft_pending_review", "status: locked", 1),
                encoding="utf-8",
            )
            dry = cmd_run_skill(
                repo_root=ws,
                skill_name="landing-page-cro-audit",
                brief_text="Critique above-the-fold CTA contrast",
                model_tier="multimodal_creative",
                provider="gemini-hydrogen",
                dry_run=True,
                env={"GEMINI_API_KEY": "secret-hyd-key"},
                thinking_level="HIGH",
                attachment_paths=[str(img)],
            )
            self.assertTrue(dry["dry_run"])
            self.assertEqual(dry["thinking_level"], "HIGH")
            self.assertEqual(dry["attachments"][0]["mime_type"], "image/png")

    def test_runway_churn_and_referral_calculators(self) -> None:
        churn_bad = compute_churn_and_nrr(
            starting_mrr_usd=20000,
            monthly_logo_churn_pct=9.0,
            monthly_revenue_churn_pct=7.0,
            monthly_expansion_pct=2.0,
            new_customers_per_month=18,
        )
        self.assertEqual(churn_bad["status"], "ok")
        self.assertAlmostEqual(churn_bad["monthly_nrr_pct"], 95.0)
        self.assertAlmostEqual(churn_bad["steady_state_customer_ceiling"], 200.0)
        self.assertTrue(churn_bad["leaky_bucket_alert"])

        churn_unk = compute_churn_and_nrr(
            starting_mrr_usd="unknown",
            monthly_logo_churn_pct=4.0,
            monthly_revenue_churn_pct=4.0,
        )
        self.assertEqual(churn_unk["status"], "unknown")

        runway_tight = simulate_cash_flow_runway(
            available_cash_usd=5000,
            monthly_ad_spend_usd=4000,
            allowable_cac_usd=100,
            monthly_gross_profit_per_customer_usd=35,
            monthly_logo_churn_pct=4.0,
            horizon_months=12,
        )
        self.assertEqual(runway_tight["status"], "ok")
        self.assertFalse(runway_tight["runway_safe"])
        self.assertGreater(runway_tight["max_cash_trough_usd"], 3000)

        ref = compute_referral_and_review_economics(
            paid_cac_usd=90,
            allowable_cac_usd=80,
            referral_invite_rate=0.5,
            referral_conversion_rate=0.3,
            referrer_reward_usd=25,
            friend_discount_cost_usd=25,
            current_reviews=40,
            current_rating=4.3,
            target_rating=4.7,
            competitor_reviews=95,
        )
        self.assertEqual(ref["k_factor"], 0.15)
        self.assertAlmostEqual(ref["effective_blended_cac_usd"], 78.26)
        self.assertTrue(ref["reward_within_cac_ceiling"])
        self.assertEqual(ref["five_star_reviews_needed"], 54)
        self.assertEqual(ref["reviews_to_overtake_competitor"], 56)

        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "calculators" / "runway_churn.py"),
                "--mode",
                "churn_nrr",
                "--starting-mrr-usd",
                "10000",
                "--monthly-logo-churn-pct",
                "5",
                "--monthly-revenue-churn-pct",
                "4",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertAlmostEqual(json.loads(proc.stdout)["monthly_grr_pct"], 96.0)

    def test_fanout_audit_and_creative_fatigue(self) -> None:
        subqs = generate_query_fanout_subquestions("Standing Desk")
        self.assertEqual(len(subqs), 6)

        html_doc = """<!doctype html><html><head>
        <script type="application/ld+json">{"@context":"https://schema.org","@type":"FAQPage"}</script>
        </head><body>
        <h2>What is NordicDesk?</h2>
        <p>NordicDesk builds solid European oak sit-stand desks engineered for quiet home studios with dual motors, cable trays, and five year warranties included for every customer.</p>
        <h2>How does NordicDesk compare vs alternatives?</h2>
        <p>Unlike hollow laminate desks, NordicDesk ships pre-drilled solid hardwood desktops rated to 120 kilograms with zero cross-bar wobble at standing height for tall engineers.</p>
        <h3>When does a standing desk pay off?</h3>
        <p>Teams switching from static tables report fewer afternoon posture breaks within fourteen days when pairing memory height presets with anti-fatigue mats during deep work blocks.</p>
        <table><thead><tr><th>Spec</th><th>NordicDesk</th></tr></thead><tbody><tr><td>Desktop</td><td>Solid Oak</td></tr></tbody></table>
        </body></html>"""

        audit_good = audit_page_fanout_readiness(
            html_doc,
            primary_query="solid oak standing desk",
            robots_txt="User-agent: GPTBot\nAllow: /\n",
        )
        self.assertEqual(audit_good["fanout_readiness_score"], 100)
        self.assertEqual(audit_good["grade"], "ready")
        self.assertEqual(audit_good["blocked_ai_crawlers"], [])

        # Respect RFC 9309 group boundaries: GPTBot Allow:/ overrides wildcard; PerplexityBot Disallow:/ only blocks PerplexityBot
        robots_mixed = (
            "User-agent: *\nAllow: /\n\n"
            "User-agent: Google-Extended\nDisallow: /\n\n"
            "User-agent: GPTBot\nAllow: /\n"
        )
        audit_blocked = audit_page_fanout_readiness(
            "## Thin heading\n\nToo short.",
            primary_query="standing desk",
            robots_txt=robots_mixed,
        )
        self.assertEqual(audit_blocked["blocked_ai_crawlers"], ["Google-Extended"])
        self.assertEqual(audit_blocked["grade"], "low_visibility")

        fatigue = detect_creative_fatigue(
            [
                {
                    "ad_id": "ig_reel_hook_a",
                    "frequency": 3.8,
                    "peak_ctr": 0.024,
                    "current_ctr": 0.015,
                    "baseline_cpa_usd": 40,
                    "current_cpa_usd": 58,
                    "impressions": 12000,
                    "spend_usd": 420,
                },
                {
                    "ad_id": "search_rsas",
                    "frequency": 1.4,
                    "peak_ctr": 0.055,
                    "current_ctr": 0.054,
                    "impressions": 5000,
                    "spend_usd": 300,
                },
            ]
        )
        self.assertEqual(fatigue["fatigued_count"], 1)
        self.assertEqual(fatigue["healthy_count"], 1)
        self.assertEqual(fatigue["fatigued_creatives"][0]["ad_id"], "ig_reel_hook_a")

        pacing = compute_launch_pacing_guard(
            launch_budget_usd=5000,
            days_elapsed=4,
            total_launch_days=10,
            spend_to_date_usd=2600,
            revenue_to_date_usd=4680,
            gross_margin_pct=60,
            target_mer=2.5,
        )
        self.assertEqual(pacing["circuit_breaker_action"], "throttle_spend")

        with tempfile.TemporaryDirectory() as tmp:
            html_file = pathlib.Path(tmp) / "desk.html"
            html_file.write_text(html_doc, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "geo_benchmark.py"), "--audit-file", str(html_file)],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(json.loads(proc.stdout)["fanout_readiness_score"], 100)

    def test_orchestrator_mcp_harness_and_retention_profile(self) -> None:
        tools_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
        assert tools_resp is not None
        names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("freecmo_churn_and_runway", names)
        self.assertIn("freecmo_creative_fatigue", names)
        self.assertIn("freecmo_ai_search_fanout_audit", names)

        r1 = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {
                    "name": "freecmo_churn_and_runway",
                    "arguments": {
                        "mode": "referral_loop",
                        "paid_cac_usd": 90,
                        "allowable_cac_usd": 80,
                        "referral_invite_rate": 0.5,
                        "referral_conversion_rate": 0.3,
                        "referrer_reward_usd": 25,
                        "friend_discount_cost_usd": 25,
                    },
                },
            }
        )
        assert r1 is not None
        self.assertFalse(r1["result"]["isError"])
        self.assertAlmostEqual(json.loads(r1["result"]["content"][0]["text"])["effective_blended_cac_usd"], 78.26)

        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp) / "ws"
            ws.mkdir()
            shutil.copy(REPO_ROOT / "AGENTS.md", ws / "AGENTS.md")
            shutil.copytree(REPO_ROOT / ".agents", ws / ".agents")
            shutil.copytree(REPO_ROOT / "skills", ws / "skills")
            shutil.copytree(REPO_ROOT / "schemas", ws / "schemas")
            bt = (ws / ".agents" / "brand-truth.template.md").read_text(encoding="utf-8")
            (ws / ".agents" / "brand-truth.md").write_text(
                bt.replace("status: draft_pending_review", "status: locked", 1),
                encoding="utf-8",
            )

            brief = generate_next_actions(
                {
                    "tracking_verified": True,
                    "churn_metrics": {
                        "starting_mrr_usd": 20000,
                        "monthly_logo_churn_pct": 9.5,
                        "monthly_revenue_churn_pct": 8.0,
                        "monthly_expansion_pct": 1.0,
                    },
                    "cash_runway": {
                        "available_cash_usd": 5000,
                        "monthly_ad_spend_usd": 4500,
                        "allowable_cac_usd": 100,
                        "monthly_gross_profit_per_customer_usd": 30,
                        "monthly_logo_churn_pct": 5.0,
                        "horizon_months": 12,
                    },
                    "ad_creatives": [
                        {
                            "ad_id": "fb_carousel_1",
                            "frequency": 4.0,
                            "peak_ctr": 0.02,
                            "current_ctr": 0.011,
                            "impressions": 9000,
                            "spend_usd": 310,
                        }
                    ],
                },
                repo_root=ws,
            )
            cb_ids = {c["alert_id"] for c in brief["circuit_breakers"]}
            self.assertIn("cb-leaky-bucket-churn", cb_ids)
            self.assertIn("cb-cash-runway-trough", cb_ids)
            titles = " | ".join(d["decision_title"] for d in brief["human_readout"]["ranked_decisions"])
            self.assertIn("churn", titles.lower())
            self.assertIn("rotate 0-3s hooks", titles.lower())

            # Host generation with gemini-hydrogen & retention-launch profile
            hosts = generate_host_configs(
                "all",
                repo_root=ws,
                output_dir=pathlib.Path(tmp) / "hosts",
                profile="retention-launch",
            )
            self.assertTrue(any("env.gemini-hydrogen.example" in f for f in hosts["generated_files"]))
            pkg_res = build_artifacts(repo_root=ws, check_only=False, profile="retention-launch")
            self.assertEqual(pkg_res["active_runtime_skills"], 16)
            self.assertEqual(pkg_res["total_source_skills"], 25)


if __name__ == "__main__":
    unittest.main()
