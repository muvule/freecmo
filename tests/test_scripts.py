import json
import pathlib
import tempfile
import unittest

from scripts.geo_benchmark import build_10_buyer_prompts, score_benchmark_responses, validate_endpoint_url
from scripts.instinct_extractor import append_instinct
from scripts.next_action import generate_next_actions


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


class TestScripts(unittest.TestCase):
    def test_next_action_strategy_lock_and_disproof_migration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            bt = root / "brand-truth.md"
            bt.write_text((REPO_ROOT / ".agents/brand-truth.template.md").read_text(encoding="utf-8"), encoding="utf-8")
            ledger = root / "ledger.jsonl"
            ledger.write_text("", encoding="utf-8")

            # Draft lock blocks production
            brief = generate_next_actions(
                {"brand_truth_path": str(bt), "experiment_ledger_path": str(ledger)},
                repo_root=REPO_ROOT,
            )
            self.assertEqual(brief["strategy_lock_status"], "draft_pending_review")
            self.assertEqual(brief["human_readout"]["ranked_decisions"][0]["priority"], "P0")

            # Unlock strategy + add running experiment that breached disproof condition
            bt.write_text(bt.read_text(encoding="utf-8").replace("status: draft_pending_review", "status: locked"), encoding="utf-8")
            exp = {
                "experiment_id": "exp-bad-angle",
                "channel": "paid_social",
                "hypothesis": "Generic discount hook",
                "primary_metric": "ctr",
                "min_runtime_days": 14,
                "target_sample_size": 2500,
                "disproof_condition": "ctr < 0.005 after 2500 impressions",
                "status": "running",
                "platform_execution_mode": "meta_paused_study",
                "observed_metrics": {"ctr": 0.002, "impressions": 3000},
            }
            ledger.write_text(json.dumps(exp) + "\n", encoding="utf-8")

            unlocked_brief = generate_next_actions(
                {
                    "brand_truth_path": str(bt),
                    "experiment_ledger_path": str(ledger),
                    "tracking_verified": True,
                    "site_load_sec": 1.8,
                    "payback_months": 2.0,
                    "monthly_budget_usd": 1200,
                    "reallocation_pool_usd": 300,
                    "cohort_segments": [
                        {"segment_name": "Seg A", "motion": "retention", "cost_usd": 300, "incremental_gross_profit_usd": 1000},
                        {"segment_name": "Seg C", "motion": "cold_acquisition", "cost_usd": 300, "incremental_gross_profit_usd": 600},
                    ],
                },
                repo_root=REPO_ROOT,
            )
            self.assertEqual(unlocked_brief["strategy_lock_status"], "locked")
            self.assertLessEqual(len(unlocked_brief["human_readout"]["ranked_decisions"]), 5)
            self.assertIn("exp-bad-angle", bt.read_text(encoding="utf-8"))

    def test_geo_benchmark_and_ssrf_guard(self) -> None:
        with self.assertRaises(ValueError):
            validate_endpoint_url("http://169.254.169.254/latest/meta-data")
        with self.assertRaises(ValueError):
            validate_endpoint_url("http://0.0.0.0:8000/v1")
        with self.assertRaises(ValueError):
            validate_endpoint_url("http://metadata.google.internal/computeMetadata/v1/")
        with self.assertRaises(ValueError):
            validate_endpoint_url("http://api.external.com/v1")
        self.assertTrue(validate_endpoint_url("http://127.0.0.1:11434/v1").startswith("http://127.0.0.1"))

        prompts = build_10_buyer_prompts("AI accounting", "freelancers", ["CompA", "CompB"])
        self.assertEqual(len(prompts), 10)
        responses = [
            {"prompt": prompts[0], "response": "Try MyBrand at https://mybrand.io or CompA at https://compa.com/pricing"},
            {"prompt": prompts[1], "response": "CompA leads https://compa.com/compare"},
        ]
        scored = score_benchmark_responses(
            "MyBrand",
            "mybrand.io",
            [{"name": "CompA", "domain": "compa.com"}],
            responses,
        )
        self.assertEqual(scored["citation_share"], "1/2")
        self.assertEqual(len(scored["entity_gap_roadmap"]), 1)

    def test_instinct_extractor_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "instincts.md"
            r1 = append_instinct(p, "Reject #2: we never use discount codes", "copy", "2026-11-16")
            r2 = append_instinct(p, "Reject #2: we never use discount codes", "copy", "2026-11-16")
            self.assertTrue(r1["added"])
            self.assertFalse(r2["added"])
            self.assertIn("we never use discount codes", p.read_text(encoding="utf-8"))

    def test_end_to_end_pipeline_integration(self) -> None:
        from calculators.cac_ltv import compute_cac_ltv
        from calculators.mer import compute_blended_mer
        from connectors.approval_gate import ApprovalGate
        from connectors.context_offloader import build_ordered_context, offload_if_oversized
        from connectors.csv_normalizer import normalize_csv_export
        from connectors.identity_resolver import IdentityResolver
        from connectors.platform_adapters import build_platform_experiment_payload
        from connectors.radar_store import RadarStore, draft_community_reply

        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            # 1. Tier 0 CSV dropzone -> IdentityResolver
            csv_path = root / "orders.csv"
            csv_path.write_text(
                "Email,First_Touch_UTM,Segment,Orders,LTV,Cost\n"
                "u1@test.io,google_cpc,Ret_Seg,3,$600,$50\n"
                "u2@test.io,meta_cpc,Cold_Seg,1,$120,$100\n",
                encoding="utf-8",
            )
            norm = normalize_csv_export(csv_path, "shopify")
            db_path = root / "radar.db"
            resolver = IdentityResolver(db_path)
            self.assertEqual(resolver.unify_csv_records(norm["rows"], "shopify"), 2)

            # 2. Radar store + FTC reply
            radar = RadarStore(db_path)
            radar.upsert_competitor("LegacyApp", "legacyapp.io")
            radar.add_community_thread("reddit", "https://reddit.com/r/smb/1", "Slow billing sync", "LegacyApp sync breaks.", "billing-sync", "LegacyApp")
            self.assertEqual(len(radar.search_threads("billing sync")), 1)
            self.assertIn("(Disclosure: I built/work on FreeCMO)", draft_community_reply("Check out our sync.", "FreeCMO"))

            # 3. Calculators + Context Offloading
            cac = compute_cac_ltv(aov_usd=200, gross_margin_pct=65, repeat_orders=2, target_payback_months=3)
            self.assertEqual(cac["status"], "ok")
            mer = compute_blended_mer(total_revenue_usd=30000, total_ad_spend_usd=6000)
            self.assertEqual(mer["blended_mer"], 5.0)
            offloaded = offload_if_oversized("sub-e2e", [{"k": i} for i in range(400)], root / "offload", token_threshold=500)
            self.assertTrue(offloaded["offloaded"])
            ctx = build_ordered_context("System", {"z": 1, "a": 2}, "# Brand", "{}", "# Instincts", {"slice": offloaded["offload_pointer"]})
            self.assertIn("=== 4. VOLATILE SUBTASK SLICE ===", ctx["full_prompt"])

            # 4. Locked brand-truth -> Orchestrator Dual Readout
            bt = root / "brand-truth.md"
            bt.write_text((REPO_ROOT / ".agents/brand-truth.template.md").read_text(encoding="utf-8").replace("status: draft_pending_review", "status: locked"), encoding="utf-8")
            ledger = root / "ledger.jsonl"
            ledger.write_text("", encoding="utf-8")
            brief = generate_next_actions(
                {
                    "brand_truth_path": str(bt),
                    "experiment_ledger_path": str(ledger),
                    "tracking_verified": True,
                    "site_load_sec": 1.6,
                    "payback_months": 1.8,
                    "monthly_budget_usd": 1500,
                    "monthly_conversions": 35,
                    "allowable_cac_usd": cac["allowable_cac_usd"],
                    "reallocation_pool_usd": 300,
                    "cohort_segments": [
                        {"segment_name": "Ret_Seg", "motion": "retention", "cost_usd": 200, "incremental_gross_profit_usd": 900},
                        {"segment_name": "Cold_Seg", "motion": "cold_acquisition", "cost_usd": 400, "incremental_gross_profit_usd": 600},
                    ],
                    "paid_seo_overlaps": [{"query": "freecmo", "organic_position": 1, "competitor_impression_share_pct": 1.5, "monthly_paid_spend_usd": 180}],
                    "seo_geo_opportunities": [{"topic": "billing sync comparison", "paid_conversions": 5, "paid_cpa_usd": 80, "geo_citation_score": 1}],
                    "organic_social_posts": [{"post_id": "post-99", "save_or_watch_multiplier": 2.8, "test_budget_usd": 120}],
                },
                repo_root=REPO_ROOT,
            )
            self.assertEqual(brief["strategy_lock_status"], "locked")
            self.assertGreaterEqual(len(brief["human_readout"]["ranked_decisions"]), 4)
            self.assertLessEqual(len(brief["human_readout"]["ranked_decisions"]), 5)

            # 5. Platform adapter + ApprovalGate -> Execute -> Rollback
            exp_payload = build_platform_experiment_payload(
                {
                    "experiment_id": "exp-e2e-1",
                    "channel": "paid_search",
                    "hypothesis": "Billing sync landing page lifts demo CVR",
                    "primary_metric": "demo_cvr",
                    "min_runtime_days": 7,
                    "target_sample_size": 500,
                    "disproof_condition": "ctr < 0.01 after 2500 impressions",
                    "status": "proposed",
                    "platform_execution_mode": "google_ads_validate_only",
                },
                schema_path=REPO_ROOT / "schemas/experiment.schema.json",
            )
            self.assertTrue(exp_payload["validate_only"])

            gate = ApprovalGate(root / "shift.jsonl", root / "rollbacks", bt)
            gate.record_validator_pass("sub-e2e", exp_payload)
            gate.record_reviewer_approval("sub-e2e", exp_payload, True)
            gate.record_composer_signoff("app-e2e", "sub-e2e", exp_payload)
            target = root / "staged_exp.json"
            target.write_text('{"validate_only": false}', encoding="utf-8")
            gate.execute_write("act-e2e", "sub-e2e", "app-e2e", exp_payload, {"validate_only": False}, target_file=target)
            self.assertTrue(json.loads(target.read_text(encoding="utf-8"))["validate_only"])
            gate.rollback("act-e2e")
            self.assertFalse(json.loads(target.read_text(encoding="utf-8"))["validate_only"])


if __name__ == "__main__":
    unittest.main()
