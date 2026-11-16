import json
import pathlib
import unittest

from calculators import safe_parse_yaml, validate_json_schema


REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCHEMAS_DIR = REPO_ROOT / "schemas"


class TestSchemasAndYaml(unittest.TestCase):
    def test_guardrails_yaml_parses_safely(self) -> None:
        data = safe_parse_yaml((REPO_ROOT / ".agents/guardrails.yaml").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 1)
        self.assertTrue(data["autonomy_envelope"]["strategy_lock_required"])
        self.assertIn("example-investor.com", data["protected_relationships"]["vip_domains"])
        self.assertEqual(len(data["stop_loss_rules"]), 2)

    def test_unsafe_yaml_tags_rejected(self) -> None:
        with self.assertRaises(ValueError):
            safe_parse_yaml("bad: !!python/object/apply:os.system ['echo hi']")

    def test_valid_and_invalid_subtask_spec(self) -> None:
        schema = json.loads((SCHEMAS_DIR / "subtask_spec.schema.json").read_text(encoding="utf-8"))
        valid = {
            "subtask_id": "sub-001",
            "skill_names": ["google-ads-smb-audit"],
            "model_tier": "balanced_worker",
            "max_tool_calls": 6,
            "max_tokens_budget": 16000,
            "requires_reviewer": True,
            "data_slice_pointers": ["data/exports/gads.csv"],
            "file_touch_boundaries": {"allowed_paths": ["data/offload/*"], "forbidden_paths": [".env*"]},
            "goal": "Audit Google Ads search campaigns for wasted spend.",
        }
        self.assertEqual(validate_json_schema(valid, schema, SCHEMAS_DIR), [])

        invalid = dict(valid)
        invalid["subtask_id"] = "../escape"
        errs = validate_json_schema(invalid, schema, SCHEMAS_DIR)
        self.assertTrue(any("pattern" in e for e in errs))

    def test_storyboard_schema_enforces_visual_dna(self) -> None:
        schema = json.loads((SCHEMAS_DIR / "storyboard.schema.json").read_text(encoding="utf-8"))
        sb = {
            "storyboard_id": "sb-01",
            "aspect_ratio": "9:16",
            "visual_dna_ref": ".agents/visual-dna.json",
            "palette_hex": ["#111827", "#2563EB"],
            "hook_angle": "Cut manual reporting hours by 75%",
            "timed_beats": [
                {"beat_role": "hook", "start_sec": 0, "end_sec": 4, "visual_frame": "Dashboard close-up", "spoken_or_overlay_copy": "Still pulling Monday CSVs?"},
                {"beat_role": "proof", "start_sec": 4, "end_sec": 10, "visual_frame": "Cohort MER chart", "spoken_or_overlay_copy": "See blended MER in 30s."},
                {"beat_role": "cta", "start_sec": 10, "end_sec": 15, "visual_frame": "Repo URL card", "spoken_or_overlay_copy": "Try FreeCMO free."},
            ],
            "cta_text": "Clone FreeCMO",
            "source_receipt": "data/exports/meta_winners.csv#row2",
        }
        self.assertEqual(validate_json_schema(sb, schema, SCHEMAS_DIR), [])


if __name__ == "__main__":
    unittest.main()
