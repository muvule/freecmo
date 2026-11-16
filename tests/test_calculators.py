import unittest

from calculators import safe_eval_condition
from calculators.budget_gate import evaluate_budget_gate
from calculators.cac_ltv import compute_cac_ltv
from calculators.experiment_math import (
    evaluate_disproof_condition,
    mann_whitney_u,
    required_sample_size_per_arm,
    two_proportion_z_test,
)
from calculators.mer import allocate_acquisition_vs_retention, compute_blended_mer, evaluate_stop_losses
from calculators.ngram_waste import mine_ngram_waste


class TestCalculators(unittest.TestCase):
    def test_cac_ltv_and_unknown_propagation(self) -> None:
        res = compute_cac_ltv(
            aov_usd=100,
            gross_margin_pct=70,
            repeat_orders=2.5,
            target_payback_months=3,
            monthly_orders_per_customer=1,
            actual_spend_usd=1500,
            new_customers=10,
        )
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["gross_profit_per_order_usd"], 70.0)
        self.assertEqual(res["ltv_gross_profit_usd"], 175.0)
        self.assertEqual(res["allowable_cac_usd"], 175.0)
        self.assertEqual(res["actual_cac_usd"], 150.0)
        self.assertTrue(res["payback_gate_pass"])

        miss = compute_cac_ltv(aov_usd=None, gross_margin_pct=70)
        self.assertEqual(miss["status"], "unknown")
        self.assertIn("aov_usd", miss["missing_inputs"])

    def test_mer_and_acquisition_vs_retention(self) -> None:
        mer = compute_blended_mer(
            total_revenue_usd=50000,
            total_ad_spend_usd=10000,
            branded_paid_revenue_usd=15000,
            branded_paid_spend_usd=2000,
            non_branded_paid_revenue_usd=20000,
            non_branded_paid_spend_usd=8000,
            organic_revenue_usd=15000,
        )
        self.assertEqual(mer["blended_mer"], 5.0)
        self.assertEqual(mer["branded_roas"], 7.5)
        self.assertEqual(mer["non_branded_roas"], 2.5)
        self.assertEqual(mer["organic_revenue_share_pct"], 30.0)

        alloc = allocate_acquisition_vs_retention(
            segments=[
                {"segment_name": "Segment A", "motion": "retention", "cost_usd": 500, "incremental_gross_profit_usd": 1720},
                {"segment_name": "Segment C", "motion": "cold_acquisition", "cost_usd": 1000, "incremental_gross_profit_usd": 3220},
            ],
            reallocation_pool_usd=400,
        )
        self.assertIsNotNone(alloc["recommendation"])
        self.assertEqual(alloc["recommendation"]["shift_usd"], 400.0)
        self.assertAlmostEqual(alloc["recommendation"]["marginal_roi_delta_pct"], 22.0, places=1)

    def test_ast_safe_condition_rejects_injection(self) -> None:
        with self.assertRaises(ValueError):
            safe_eval_condition("__import__('os').system('ls') == 0", {"spend": 100})

        ev = evaluate_disproof_condition(
            "ctr < 0.005 after 2500 impressions OR conversions == 0 after 2.0x allowable_cac_usd spend",
            {"ctr": 0.01, "impressions": 1000, "conversions": 0, "spend": 250, "allowable_cac_usd": 100},
        )
        self.assertTrue(ev["killed"])

        sl = evaluate_stop_losses(
            [{"id": "sl1", "channel": "paid_social", "condition": "roas < 1.0 after_days >= 14 and spend >= 150", "action": "stage_pause"}],
            [{"campaign_id": "camp-1", "channel": "paid_social", "roas": 0.75, "days": 15, "spend": 200}],
        )
        self.assertEqual(sl["alert_count"], 1)

        explicit_and = safe_eval_condition("roas < 1.0 and after_days >= 14", {"roas": 0.8, "days": 15})
        self.assertTrue(explicit_and["triggered"])

    def test_experiment_math_functions(self) -> None:
        pwr = required_sample_size_per_arm(baseline_rate=0.04, relative_mde=0.25)
        self.assertGreater(pwr["n_per_arm"], 2000)
        z = two_proportion_z_test(40, 1000, 75, 1000)
        self.assertTrue(z["statistically_significant"])
        mwu = mann_whitney_u([1.0, 2.0, 3.0, 4.0], [10.0, 11.0, 12.0, 13.0])
        self.assertTrue(mwu["statistically_significant"])

    def test_ngram_waste_and_budget_gate(self) -> None:
        nw = mine_ngram_waste(
            [
                {"search_term": "free crm template", "spend_usd": 80, "clicks": 25, "conversions": 0},
                {"search_term": "free crm download", "spend_usd": 60, "clicks": 20, "conversions": 0},
                {"search_term": "smb crm pricing", "spend_usd": 90, "clicks": 15, "conversions": 3},
            ],
            allowable_cac_usd=100,
        )
        self.assertEqual(nw["flagged_ngrams"][0]["ngram"], "free crm")

        gate = evaluate_budget_gate(
            channel="paid_search",
            tracking_verified=True,
            site_load_sec=2.1,
            payback_months=4.5,
            max_payback_months=3.0,
            monthly_conversions=12,
            monthly_budget_usd=600,
        )
        self.assertFalse(gate["unlocked"])
        self.assertTrue(any("payback_too_long" in b for b in gate["blockers"]))


if __name__ == "__main__":
    unittest.main()
