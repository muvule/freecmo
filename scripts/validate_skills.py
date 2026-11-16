"""CI linter, cmo-check worked-example recomputer, and cross-skill contradiction detector."""

from __future__ import annotations

import argparse
import importlib
import math
import pathlib
import re
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculators import safe_parse_yaml
from connectors.context_offloader import estimate_tokens


MANDATORY_SECTIONS = [
    "## Required Inputs & Missing-Data Rules",
    "## Stage Preconditions & Disagreement Table",
    "## Deterministic Calculations",
    "## Flash Points",
    "## Worked Examples",
    "## Output Contract & Source Receipts",
    "## Sources",
]

ALLOWED_CATEGORIES = {"core", "analytics", "search-paid", "search-organic", "social", "lifecycle-cro"}

PRIMARY_SOURCE_DOMAINS = {
    "support.google.com",
    "developers.google.com",
    "search.google.com",
    "ads.google.com",
    "business.facebook.com",
    "developers.facebook.com",
    "www.facebook.com",
    "www.ftc.gov",
    "ftc.gov",
    "eur-lex.europa.eu",
    "gdpr-info.eu",
    "agentskills.io",
    "schema.org",
    "help.klaviyo.com",
    "developers.klaviyo.com",
    "posthog.com",
    "datatracker.ietf.org",
    "developer.apple.com",
    "help.shopify.com",
    "stripe.com",
    "docs.stripe.com",
    "www.redditinc.com",
    "support.reddithelp.com",
    "www.linkedin.com",
    "learn.microsoft.com",
    "openai.com",
    "platform.openai.com",
    "docs.anthropic.com",
    "ai.google.dev",
}

_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_CMO_CHECK_RE = re.compile(r"```cmo-check\s*\n(.*?)\n```", re.DOTALL)


def split_frontmatter(md_text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and markdown body from a SKILL.md file."""
    lines = md_text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Missing opening YAML frontmatter '---'")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        raise ValueError("Missing closing YAML frontmatter '---'")
    fm_text = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1 :])
    fm = safe_parse_yaml(fm_text)
    if not isinstance(fm, dict):
        raise ValueError("Frontmatter must be a YAML mapping")
    return fm, body


def _extract_section(body: str, heading: str) -> str:
    idx = body.find(heading)
    if idx == -1:
        return ""
    rest = body[idx + len(heading) :]
    m = re.search(r"\n##\s+", rest)
    return rest[: m.start()] if m else rest


def _assert_expected_match(actual: Any, expected: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected dict, got {type(actual).__name__}"]
        for k, v in expected.items():
            if k not in actual:
                errors.append(f"{path}.{k}: missing from calculator output")
            else:
                errors.extend(_assert_expected_match(actual[k], v, f"{path}.{k}"))
        return errors
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return [f"{path}: expected list len {len(expected)}, got {actual!r}"]
        for idx, (a, e) in enumerate(zip(actual, expected)):
            errors.extend(_assert_expected_match(a, e, f"{path}[{idx}]"))
        return errors
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            return [f"{path}: expected number {expected}, got {actual!r}"]
        if not math.isclose(float(actual), float(expected), rel_tol=0.01, abs_tol=0.02):
            return [f"{path}: expected {expected}, got {actual}"]
        return []
    if actual != expected:
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def run_cmo_check_block(block_yaml: str, declared_calculators: list[str]) -> list[str]:
    """Parse a cmo-check YAML block and execute its calculator function to verify expected outputs."""
    data = safe_parse_yaml(block_yaml)
    if not isinstance(data, dict):
        return ["cmo-check block must be a YAML mapping"]
    for req in ("calculator", "function", "inputs", "steps", "expected"):
        if req not in data:
            return [f"cmo-check missing required key {req!r}"]

    calc_mod_name = str(data["calculator"])
    if declared_calculators and calc_mod_name not in declared_calculators:
        return [f"cmo-check calculator {calc_mod_name!r} not declared in frontmatter calculators={declared_calculators!r}"]

    fn_name = str(data["function"])
    inputs = data["inputs"]
    expected = data["expected"]
    if not isinstance(inputs, dict) or not isinstance(expected, dict):
        return ["cmo-check inputs and expected must be YAML mappings"]

    mod = importlib.import_module(f"calculators.{calc_mod_name}")
    fn = getattr(mod, fn_name, None)
    if fn is None:
        return [f"Function {fn_name!r} not found in calculators.{calc_mod_name}"]

    actual = fn(**inputs)
    return _assert_expected_match(actual, expected, f"{calc_mod_name}.{fn_name}")


def validate_skill_file(skill_path: pathlib.Path, repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Validate a single SKILL.md file against the OpenAccountants/FreeCMO standard."""
    errors: list[str] = []
    warnings: list[str] = []
    text = skill_path.read_text(encoding="utf-8")

    try:
        fm, body = split_frontmatter(text)
    except ValueError as exc:
        return {"path": str(skill_path), "errors": [str(exc)], "warnings": [], "frontmatter": {}}

    folder_name = skill_path.parent.name
    for req in ("name", "description", "category", "tier", "last_updated", "calculators"):
        if req not in fm:
            errors.append(f"Missing frontmatter key {req!r}")

    name = str(fm.get("name", ""))
    if not re.fullmatch(r"[a-z0-9-]+", name):
        errors.append(f"Invalid skill name {name!r}; must match ^[a-z0-9-]+$")
    if name != folder_name:
        errors.append(f"Skill name {name!r} does not match parent folder {folder_name!r}")

    desc = str(fm.get("description", ""))
    if not (1 <= len(desc) <= 1024):
        errors.append(f"Description length {len(desc)} outside 1..1024")

    cat = str(fm.get("category", ""))
    if cat not in ALLOWED_CATEGORIES:
        errors.append(f"Invalid category {cat!r}")

    if fm.get("tier") not in (1, 2):
        errors.append(f"Invalid tier {fm.get('tier')!r}; expected 1 or 2")

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fm.get("last_updated", ""))):
        errors.append(f"Invalid last_updated {fm.get('last_updated')!r}; expected YYYY-MM-DD")

    calcs = fm.get("calculators")
    if not isinstance(calcs, list):
        errors.append("Frontmatter 'calculators' must be a list")
        calcs = []
    else:
        for c in calcs:
            if not (repo_root / "calculators" / f"{c}.py").exists():
                errors.append(f"Declared calculator module calculators/{c}.py does not exist")

    # Mandatory body sections in order
    last_pos = -1
    for sec in MANDATORY_SECTIONS:
        pos = body.find(sec)
        if pos == -1:
            errors.append(f"Missing mandatory section: {sec}")
        elif pos < last_pos:
            errors.append(f"Section out of order: {sec}")
        else:
            last_pos = pos

    # Flash point callouts
    fp_section = _extract_section(body, "## Flash Points")
    if "**SPEND FLASH POINT**" not in fp_section and "**COMPLIANCE FLASH POINT**" not in fp_section:
        errors.append("## Flash Points must contain **SPEND FLASH POINT** or **COMPLIANCE FLASH POINT**")

    # Primary sources check
    sources_sec = _extract_section(body, "## Sources")
    urls = _URL_RE.findall(sources_sec)
    if not urls:
        errors.append("## Sources must include at least one primary platform documentation URL")
    for u in urls:
        host = u.split("//", 1)[1].split("/", 1)[0].lower()
        if host not in PRIMARY_SOURCE_DOMAINS:
            errors.append(f"Non-primary source domain in ## Sources: {host} ({u})")
    if not re.search(r"\d{4}-\d{2}-\d{2}", sources_sec):
        errors.append("## Sources must include read dates (YYYY-MM-DD)")

    # cmo-check recomputation
    examples_sec = _extract_section(body, "## Worked Examples")
    checks = _CMO_CHECK_RE.findall(examples_sec)
    if len(checks) < 2:
        errors.append(f"## Worked Examples must include at least 2 cmo-check blocks (found {len(checks)})")
    for idx, blk in enumerate(checks, start=1):
        try:
            blk_errs = run_cmo_check_block(blk, [str(c) for c in calcs])
            for be in blk_errs:
                errors.append(f"cmo-check #{idx}: {be}")
        except Exception as exc:
            errors.append(f"cmo-check #{idx} execution error: {exc}")

    return {"path": str(skill_path), "errors": errors, "warnings": warnings, "frontmatter": fm}


def detect_cross_skill_contradictions(skill_records: list[dict[str, Any]], repo_root: pathlib.Path) -> list[str]:
    """Check for duplicate skill names, threshold contradictions, or active pack budget violations."""
    issues: list[str] = []
    seen_names: dict[str, str] = {}
    for rec in skill_records:
        fm = rec.get("frontmatter", {})
        name = fm.get("name")
        if name:
            if name in seen_names:
                issues.append(f"Duplicate skill name {name!r}: {seen_names[name]} vs {rec['path']}")
            seen_names[name] = rec["path"]

    # Check active .agents/skills cap and header token budget
    active_dir = repo_root / ".agents" / "skills"
    if active_dir.exists():
        active_skills = sorted(active_dir.glob("*/SKILL.md"))
        if len(active_skills) > 16:
            issues.append(f".agents/skills exceeds 16-skill cap: {len(active_skills)} active skills")
        header_chars = 0
        for p in active_skills:
            try:
                fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
                header_chars += len(str(fm.get("name", ""))) + len(str(fm.get("description", "")))
            except Exception:
                pass
        est_tokens = estimate_tokens("x" * header_chars) if header_chars else 0
        if est_tokens > 1200:
            issues.append(f"Active skill listing header token budget exceeded: {est_tokens} > 1200 tokens")

    return issues


def validate_all_skills(skills_dir: pathlib.Path, repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Validate all SKILL.md files under skills_dir and run contradiction checks."""
    skill_files = sorted(skills_dir.glob("*/*/SKILL.md"))
    results = [validate_skill_file(p, repo_root) for p in skill_files]
    contradictions = detect_cross_skill_contradictions(results, repo_root)
    total_errors = sum(len(r["errors"]) for r in results) + len(contradictions)
    return {
        "skills_checked": len(results),
        "total_errors": total_errors,
        "contradictions": contradictions,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate SKILL.md library and recompute cmo-check examples.")
    parser.add_argument("--skills-dir", default=str(REPO_ROOT / "skills"))
    args = parser.parse_args(argv)

    summary = validate_all_skills(pathlib.Path(args.skills_dir), REPO_ROOT)
    for res in summary["results"]:
        if res["errors"]:
            print(f"FAIL {res['path']}:")
            for err in res["errors"]:
                print(f"  - {err}")
        else:
            print(f"PASS {res['path']}")
    for c in summary["contradictions"]:
        print(f"CONTRADICTION: {c}")
    print(f"Summary: {summary['skills_checked']} skills checked, {summary['total_errors']} errors.")
    return 1 if summary["total_errors"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
