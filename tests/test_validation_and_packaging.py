import json
import pathlib
import tempfile
import unittest

from scripts.build_packages import build_artifacts
from scripts.nightly_exam import run_exam
from scripts.validate_skills import validate_skill_file


VALID_SKILL_FIXTURE = """---
name: sample-skill
description: Deterministic sample skill for unit testing validator and packager.
category: core
tier: 1
last_updated: 2026-11-16
calculators:
  - cac_ltv
---

# Sample Skill

## Required Inputs & Missing-Data Rules
If `aov_usd` or `gross_margin_pct` is missing, output `unknown`.

## Stage Preconditions & Disagreement Table
Run before paid acquisition; if LTV conflicts with cash payback, 3-month payback governs.

## Deterministic Calculations
Run `python3 -m calculators.cac_ltv --aov-usd 100 --gross-margin-pct 70`.

## Flash Points
- **SPEND FLASH POINT**: Never scale paid ads above allowable CAC.

## Worked Examples

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 100
  gross_margin_pct: 70
  repeat_orders: 2
  target_payback_months: 3
  monthly_orders_per_customer: 1
steps:
  - gp_per_order = 100 * 0.70 = 70
  - ltv_gp = 70 * 2 = 140
expected:
  status: ok
  allowable_cac_usd: 140.0
  break_even_roas: 1.4286
```

```cmo-check
calculator: cac_ltv
function: compute_cac_ltv
inputs:
  aov_usd: 100
  gross_margin_pct: 50
steps:
  - missing_aov_handled: false
expected:
  status: ok
  allowable_cac_usd: 50.0
```

## Output Contract & Source Receipts
Conforms to `schemas/worker_output.schema.json` with source receipts and `disproof_condition`.

## Sources
- Google Ads Help (read 2026-11-16): https://support.google.com/google-ads/answer/6325025
"""


class TestValidationAndPackaging(unittest.TestCase):
    def test_valid_skill_passes_and_bad_cmo_check_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            skill_dir = root / "skills" / "core" / "sample-skill"
            skill_dir.mkdir(parents=True)
            (root / "calculators").mkdir()
            (root / "calculators" / "cac_ltv.py").write_text("# stub", encoding="utf-8")

            p = skill_dir / "SKILL.md"
            p.write_text(VALID_SKILL_FIXTURE, encoding="utf-8")
            res = validate_skill_file(p, repo_root=root)
            self.assertEqual(res["errors"], [])

            # Tamper with expected math
            p.write_text(VALID_SKILL_FIXTURE.replace("allowable_cac_usd: 140.0", "allowable_cac_usd: 999.0"), encoding="utf-8")
            bad_math = validate_skill_file(p, repo_root=root)
            self.assertTrue(any("expected 999.0, got 140.0" in e for e in bad_math["errors"]))

            # Tamper with non-primary source domain
            p.write_text(VALID_SKILL_FIXTURE.replace("https://support.google.com/google-ads/answer/6325025", "https://randommarketingblog.io/seo"), encoding="utf-8")
            bad_src = validate_skill_file(p, repo_root=root)
            self.assertTrue(any("Non-primary source domain" in e for e in bad_src["errors"]))

    def test_packager_respects_needs_sources_hold_and_16_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            for i in range(18):
                name = f"skill-{i:02d}"
                sdir = root / "skills" / "core" / name
                sdir.mkdir(parents=True)
                status_line = "status: needs_sources\n" if i == 0 else ""
                (sdir / "SKILL.md").write_text(
                    f"---\nname: {name}\ndescription: Desc {i}\ncategory: core\ntier: 1\nlast_updated: 2026-11-16\ncalculators: []\n{status_line}---\n# {name}\n",
                    encoding="utf-8",
                )
            res = build_artifacts(root, check_only=False)
            self.assertEqual(res["total_source_skills"], 18)
            self.assertEqual(res["publication_holds"], 1)
            self.assertEqual(res["active_runtime_skills"], 16)
            idx = json.loads((root / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(len(idx["publication_holds"]), 1)
            self.assertFalse((root / "packages" / "core" / "skill-00" / "SKILL.md").exists())

    def test_nightly_exam_passes(self) -> None:
        report = run_exam()
        self.assertEqual(report["failed"], 0)


if __name__ == "__main__":
    unittest.main()
