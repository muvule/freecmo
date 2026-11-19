import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from calculators import format_money, normalize_currency, round_money, usd_equivalent_floor
from calculators.budget_gate import evaluate_budget_gate
from calculators.cac_ltv import (
    compute_cac_ltv,
    compute_creator_commission_cap,
    compute_promo_breakeven,
)
from calculators.creative_fatigue import compute_launch_pacing_guard, detect_creative_fatigue
from calculators.local_channels import (
    analyze_sms_segments,
    compute_offline_channel_economics,
    evaluate_low_bandwidth_readiness,
)
from calculators.mer import allocate_acquisition_vs_retention, compute_blended_mer
from calculators.ngram_waste import mine_ngram_waste
from calculators.runway_churn import (
    compute_churn_and_nrr,
    compute_referral_and_review_economics,
    simulate_cash_flow_runway,
)
from connectors.llm_router import resolve_llm_route
from scripts.build_packages import build_artifacts
from scripts.cmo_runner import cmd_init
from scripts.mcp_server import handle_jsonrpc_message
from scripts.next_action import generate_next_actions
from scripts.setup_harness import generate_host_configs
from scripts.validate_skills import validate_all_skills


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestLocalEntrepreneurFeatures(unittest.TestCase):
    def test_currency_primitives_and_multi_currency_calculators(self) -> None:
        self.assertEqual(normalize_currency(" kes "), "KES")
        self.assertEqual(format_money(1800, "KES"), "KSh 1,800.00")
        self.assertEqual(format_money(150000, "IDR"), "Rp 150,000")
        self.assertEqual(format_money(450, "MXN"), "MX$ 450.00")
        self.assertEqual(round_money(15700.75, "IDR"), 15701.0)
        with self.assertRaises(ValueError):
            normalize_currency("US$")

        # CAC/LTV, promo, creator cap in KES
        econ = compute_cac_ltv(
            aov=1800,
            gross_margin_pct=55,
            repeat_orders=2.0,
            target_payback_months=3,
            monthly_orders_per_customer=1,
            actual_spend=14000,
            new_customers=20,
            currency="KES",
        )
        self.assertEqual(econ["currency"], "KES")
        self.assertEqual(econ["gross_profit_per_order"], 990.0)
        self.assertEqual(econ["gross_profit_per_order_formatted"], "KSh 990.00")
        self.assertEqual(econ["allowable_cac"], 1980.0)
        self.assertEqual(econ["actual_cac"], 700.0)
        self.assertTrue(econ["payback_gate_pass"])

        promo = compute_promo_breakeven(aov=150000, gross_margin_pct=60, discount_pct=15, currency="IDR")
        self.assertEqual(promo["currency"], "IDR")
        self.assertEqual(promo["baseline_gp"], 90000.0)
        self.assertEqual(promo["baseline_gp_formatted"], "Rp 90,000")

        cap = compute_creator_commission_cap(
            allowable_cac=450,
            paid_whitelisting_cpa=50,
            creator_flat_fee=500,
            expected_conversions=10,
            currency="MXN",
        )
        self.assertEqual(cap["max_affiliate_payout"], 350.0)
        self.assertEqual(cap["max_affiliate_payout_formatted"], "MX$ 350.00")

        # MER & allocator in IDR
        mer = compute_blended_mer(total_revenue=75000000, total_ad_spend=15000000, currency="IDR")
        self.assertEqual(mer["currency"], "IDR")
        self.assertEqual(mer["blended_mer"], 5.0)

        alloc = allocate_acquisition_vs_retention(
            segments=[
                {"segment_name": "WhatsApp VIPs", "motion": "retention", "cost": 500000, "incremental_gross_profit": 2000000},
                {"segment_name": "Cold Feed", "motion": "cold_acquisition", "cost": 1000000, "incremental_gross_profit": 2500000},
            ],
            reallocation_pool=400000,
            currency="IDR",
        )
        self.assertEqual(alloc["recommendation"]["currency"], "IDR")
        self.assertIn("Rp 400,000", alloc["recommendation"]["summary"])

        # Budget gate uses local-currency floor (~$300 USD -> ~38,700 KES) unless min_paid_budget provided
        kes_floor = usd_equivalent_floor(300.0, "KES")
        self.assertIsNotNone(kes_floor)
        gate_blocked = evaluate_budget_gate(
            channel="paid_social",
            tracking_verified=True,
            site_load_sec=2.1,
            payback_months=1.5,
            monthly_budget=5000,
            currency="KES",
        )
        self.assertFalse(gate_blocked["unlocked"])
        self.assertTrue(any("KSh" in b for b in gate_blocked["blockers"]))

        # Runway, churn, referral in NGN
        churn = compute_churn_and_nrr(
            starting_mrr=2500000,
            monthly_logo_churn_pct=4.0,
            monthly_revenue_churn_pct=4.0,
            monthly_expansion_pct=6.0,
            currency="NGN",
        )
        self.assertEqual(churn["currency"], "NGN")
        self.assertIn("₦", churn["net_mrr_after_1m_formatted"])

        runway = simulate_cash_flow_runway(
            available_cash=500000,
            monthly_ad_spend=300000,
            allowable_cac=15000,
            monthly_gross_profit_per_customer=6000,
            horizon_months=6,
            currency="KES",
        )
        self.assertEqual(runway["currency"], "KES")
        self.assertIn("KSh", runway["min_cash_balance_formatted"])

        ref = compute_referral_and_review_economics(
            paid_cac=800,
            allowable_cac=900,
            referral_invite_rate=0.5,
            referral_conversion_rate=0.4,
            referrer_reward=250,
            friend_discount_cost=250,
            currency="MXN",
        )
        self.assertTrue(ref["reward_within_cac_ceiling"])
        self.assertEqual(ref["total_referral_reward_formatted"], "MX$ 500.00")

        # Creative fatigue & launch pacing in IDR + ngram waste in MXN
        fatigue = detect_creative_fatigue(
            [
                {
                    "ad_id": "wa_click_id",
                    "frequency": 3.5,
                    "peak_ctr": 0.03,
                    "current_ctr": 0.018,
                    "impressions": 500,
                    "spend": 1500000,  # >= ~$75 USD equivalent (~1,177,500 IDR)
                }
            ],
            currency="IDR",
        )
        self.assertEqual(fatigue["fatigued_count"], 1)
        self.assertEqual(fatigue["fatigued_creatives"][0]["spend_formatted"], "Rp 1,500,000")

        pacing = compute_launch_pacing_guard(
            launch_budget=20000,
            days_elapsed=4,
            total_launch_days=10,
            spend_to_date=11000,
            revenue_to_date=18000,
            gross_margin_pct=55,
            target_mer=2.5,
            currency="MXN",
        )
        self.assertEqual(pacing["circuit_breaker_action"], "throttle_spend")
        self.assertEqual(pacing["expected_spend_to_date_formatted"], "MX$ 8,000.00")

        waste = mine_ngram_waste(
            [
                {"search_term": "gratis muebles oficina", "spend": 600, "clicks": 30, "conversions": 0},
                {"search_term": "gratis sillas df", "spend": 500, "clicks": 25, "conversions": 0},
            ],
            allowable_cac=800,
            currency="MXN",
        )
        self.assertEqual(waste["currency"], "MXN")
        self.assertEqual(waste["flagged_ngrams"][0]["ngram"], "gratis")

    def test_offline_local_channels_economics_and_low_bandwidth_readiness(self) -> None:
        wa_econ = compute_offline_channel_economics(
            channel="whatsapp_broadcast",
            recipients_or_reach=800,
            total_campaign_cost=4000,
            response_or_redemption_rate_pct=3.5,
            aov=1800,
            gross_margin_pct=55,
            allowable_cac=990,
            currency="KES",
        )
        self.assertEqual(wa_econ["status"], "ok")
        self.assertEqual(wa_econ["expected_orders"], 28.0)
        self.assertEqual(wa_econ["net_contribution"], 23720.0)
        self.assertEqual(wa_econ["net_contribution_formatted"], "KSh 23,720.00")
        self.assertTrue(wa_econ["within_allowable_cac"])

        missing = compute_offline_channel_economics(
            channel="sms_blast",
            recipients_or_reach=500,
            currency="IDR",
        )
        self.assertEqual(missing["status"], "unknown")
        self.assertIn("total_campaign_cost", missing["missing_inputs"])

        # GSM-7 clean SMS vs UCS-2 smart-quote/emoji trap
        gsm7 = analyze_sms_segments(
            "Panaderia Sol: 2x1 en pan dulce hoy hasta 7pm. Paga en efectivo o WhatsApp 5512345678. Envia STOP para cancelar."
        )
        self.assertEqual(gsm7["sms_encoding"], "GSM-7")
        self.assertEqual(gsm7["sms_segments"], 1)
        self.assertEqual(gsm7["cost_multiplier_vs_gsm7"], 1.0)

        ucs2 = evaluate_low_bandwidth_readiness(
            message_text="🔥 Panadería Sol’s fresh 2x1 pan dulce deal today until 7pm! Reply ORDER or visit Main St. Reply STOP.",
            channel="sms",
            currency="MXN",
        )
        self.assertEqual(ucs2["sms_encoding"], "UCS-2")
        self.assertEqual(ucs2["sms_segments"], 2)
        self.assertEqual(ucs2["cost_multiplier_vs_gsm7"], 2.0)
        self.assertIn("🔥", ucs2["non_gsm7_chars"])
        self.assertIn("’", ucs2["non_gsm7_chars"])

        # Community radio 15s spot too long & single phone mention
        radio_bad = evaluate_low_bandwidth_readiness(
            message_text=(
                "Visit Mama Mboga Fresh Market near Kangemi stage every morning for fresh sukuma wiki, "
                "tomatoes, onions, bananas, avocados, potatoes, and maize flour at fair neighborhood prices "
                "delivered fast straight to your kitchen door. Call 0712345678 now for fresh baskets."
            ),
            channel="radio_15s",
            currency="KES",
        )
        self.assertFalse(radio_bad["ready"])
        self.assertTrue(any("radio_script_too_long" in b for b in radio_bad["blockers"]))

        # Low-data 2G HTML check (>150 KB warning)
        flyer_heavy = evaluate_low_bandwidth_readiness(
            message_text="FRESH COFFEE BEANS 1kg Rp 120,000. Next to Pasar Baru gate. WhatsApp 08123456789.",
            channel="bulletin_board",
            html_payload_kb=240.0,
            currency="IDR",
        )
        self.assertFalse(flyer_heavy["low_data_web_pass"])
        self.assertTrue(any("150 KB" in w for w in flyer_heavy["warnings"]))

        # CLI check
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "calculators" / "local_channels.py"),
                "--mode",
                "economics",
                "--currency",
                "KES",
                "--channel",
                "print_flyer",
                "--recipients-or-reach",
                "1000",
                "--total-campaign-cost",
                "5000",
                "--response-or-redemption-rate-pct",
                "2.0",
                "--aov",
                "1500",
                "--gross-margin-pct",
                "50",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        cli_out = json.loads(proc.stdout)
        self.assertEqual(cli_out["currency"], "KES")
        self.assertEqual(cli_out["expected_orders"], 20.0)

    def test_ollama_7b_routing_profile_harness_runner_and_mcp(self) -> None:
        r_7b = resolve_llm_route("deep_orchestrator", provider_override="ollama-7b", env={})
        self.assertEqual(r_7b["provider"], "ollama-7b")
        self.assertEqual(r_7b["model"], "qwen2.5:7b")
        self.assertFalse(r_7b["requires_key"])
        self.assertTrue(r_7b["key_configured"])

        r_7b_mm = resolve_llm_route(
            "multimodal_creative",
            provider_override="ollama-7b",
            env={"OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1"},
        )
        self.assertEqual(r_7b_mm["model"], "llava:7b")

        with tempfile.TemporaryDirectory() as tmp:
            ws = pathlib.Path(tmp) / "ws"
            ws.mkdir()
            shutil.copy(REPO_ROOT / "AGENTS.md", ws / "AGENTS.md")
            shutil.copytree(REPO_ROOT / ".agents", ws / ".agents")
            shutil.copytree(REPO_ROOT / "calculators", ws / "calculators")
            shutil.copytree(REPO_ROOT / "skills", ws / "skills")
            shutil.copytree(REPO_ROOT / "schemas", ws / "schemas")

            # Test local-entrepreneur profile build + skill validation token budget
            pkg = build_artifacts(repo_root=ws, check_only=False, profile="local-entrepreneur")
            self.assertEqual(pkg["active_runtime_skills"], 16)
            self.assertEqual(pkg["total_source_skills"], 26)
            self.assertTrue((ws / ".agents" / "skills" / "offline-local-channels" / "SKILL.md").exists())
            val = validate_all_skills(ws / "skills", repo_root=ws)
            self.assertEqual(val["total_errors"], 0, msg=f"Validation errors: {val}")

            # Test local-llm harness generates env.local-7b-offline.example + ChatGPT <8k chars
            hosts = generate_host_configs(
                "all",
                repo_root=ws,
                output_dir=pathlib.Path(tmp) / "hosts",
                profile="local-entrepreneur",
            )
            self.assertTrue(any("env.local-7b-offline.example" in f for f in hosts["generated_files"]))

            # Test currency-aware cmo_runner.init + next_action currency propagation
            init_res = cmd_init(
                repo_root=ws,
                brand_name="JuaKazi Solar",
                website_url="https://example.com",
                aov=1800.0,
                gross_margin_pct=55.0,
                monthly_budget=15000.0,
                description="Solar dairy cooling kits in Nakuru",
                currency="KES",
            )
            self.assertEqual(init_res["currency"], "KES")
            bt_text = (ws / ".agents" / "brand-truth.md").read_text(encoding="utf-8")
            self.assertIn('currency: "KES"', bt_text)
            self.assertIn("KSh 990.00", bt_text)
            (ws / ".agents" / "brand-truth.md").write_text(
                bt_text.replace("status: draft_pending_review", "status: locked", 1),
                encoding="utf-8",
            )

            brief = generate_next_actions(
                {
                    "tracking_verified": True,
                    "cohort_segments": [
                        {"segment_name": "WhatsApp Repeat", "motion": "retention", "cost": 2000, "incremental_gross_profit": 8000},
                        {"segment_name": "Cold Flyers", "motion": "cold_acquisition", "cost": 4000, "incremental_gross_profit": 8000},
                    ],
                    "reallocation_pool": 1500,
                },
                repo_root=ws,
            )
            self.assertIn("KSh 1,500.00", brief["human_readout"]["ranked_decisions"][0]["decision_title"])

        # MCP JSON-RPC tool tests
        tools_resp = handle_jsonrpc_message({"jsonrpc": "2.0", "id": 21, "method": "tools/list"})
        assert tools_resp is not None
        tool_names = {t["name"] for t in tools_resp["result"]["tools"]}
        self.assertIn("freecmo_offline_local_channel", tool_names)

        mcp_econ = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "tools/call",
                "params": {
                    "name": "freecmo_offline_local_channel",
                    "arguments": {
                        "mode": "economics",
                        "channel": "whatsapp_broadcast",
                        "recipients_or_reach": 500,
                        "total_campaign_cost": 150000,
                        "response_or_redemption_rate_pct": 4.0,
                        "aov": 100000,
                        "gross_margin_pct": 50,
                        "currency": "IDR",
                    },
                },
            }
        )
        assert mcp_econ is not None
        self.assertFalse(mcp_econ["result"]["isError"])
        parsed = json.loads(mcp_econ["result"]["content"][0]["text"])
        self.assertEqual(parsed["currency"], "IDR")
        self.assertEqual(parsed["gross_revenue_formatted"], "Rp 2,000,000")

        mcp_unit = handle_jsonrpc_message(
            {
                "jsonrpc": "2.0",
                "id": 23,
                "method": "tools/call",
                "params": {
                    "name": "freecmo_unit_economics",
                    "arguments": {"aov": 1800, "gross_margin_pct": 55, "currency": "KES"},
                },
            }
        )
        assert mcp_unit is not None
        self.assertFalse(mcp_unit["result"]["isError"])
        self.assertEqual(json.loads(mcp_unit["result"]["content"][0]["text"])["allowable_cac_formatted"], "KSh 990.00")


if __name__ == "__main__":
    unittest.main()
