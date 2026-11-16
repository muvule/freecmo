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


if __name__ == "__main__":
    unittest.main()
