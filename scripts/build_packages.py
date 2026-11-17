"""Compile skills/ -> packages/, .agents/skills/ (<=16), index.json, llms.txt, llms-full.txt."""

from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import sys
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validate_skills import split_frontmatter


CATEGORY_TO_PACKAGE = {
    "core": "core",
    "analytics": "core",
    "search-paid": "search",
    "search-organic": "search",
    "social": "social",
    "content-comms": "content",
    "lifecycle-cro": "lifecycle",
}

BOOTSTRAP_ONLY_SKILLS = {"cmo-init"}

RUNTIME_PROFILES: dict[str, list[str]] = {
    "default": [
        "weekly-cmo-brief",
        "unit-economics-floors",
        "blended-mer-reconciler",
        "tracking-health-audit",
        "google-ads-smb-audit",
        "search-term-negative-miner",
        "meta-ads-smb-audit",
        "ad-creative-angle-matrix",
        "display-native-ad-studio",
        "social-seo-repurposer",
        "editorial-blog-linkedin-writer",
        "comms-press-release-writer",
        "seo-geo-code-pr",
        "landing-page-cro-audit",
        "email-deliverability-flows",
        "creator-affiliate-partnerships",
    ],
    "content-comms": [
        "weekly-cmo-brief",
        "editorial-blog-linkedin-writer",
        "comms-press-release-writer",
        "social-seo-repurposer",
        "display-native-ad-studio",
        "community-pain-radar",
        "aeo-entity-readiness",
        "seo-geo-code-pr",
        "gsc-query-drift-triage",
        "local-seo-gbp-optimizer",
        "competitor-battlecard-pricing",
        "creator-affiliate-partnerships",
        "email-deliverability-flows",
        "landing-page-cro-audit",
        "unit-economics-floors",
        "blended-mer-reconciler",
    ],
    "paid-media": [
        "weekly-cmo-brief",
        "unit-economics-floors",
        "blended-mer-reconciler",
        "tracking-health-audit",
        "google-ads-smb-audit",
        "search-term-negative-miner",
        "meta-ads-smb-audit",
        "ad-creative-angle-matrix",
        "display-native-ad-studio",
        "social-seo-repurposer",
        "competitor-battlecard-pricing",
        "creator-affiliate-partnerships",
        "landing-page-cro-audit",
        "gsc-query-drift-triage",
        "seo-geo-code-pr",
        "email-deliverability-flows",
    ],
}


def build_artifacts(
    repo_root: pathlib.Path = REPO_ROOT,
    check_only: bool = False,
    profile: str = "default",
) -> dict[str, Any]:
    """Build channel packages, active runtime pack (<=16), index.json, llms.txt, and llms-full.txt."""
    if profile not in RUNTIME_PROFILES:
        raise ValueError(f"Unknown profile {profile!r}; choose from {sorted(RUNTIME_PROFILES)}")

    skills_dir = repo_root / "skills"
    packages_dir = repo_root / "packages"
    active_dir = repo_root / ".agents" / "skills"

    skill_files = sorted(skills_dir.glob("*/*/SKILL.md"))
    index_entries: list[dict[str, Any]] = []
    publication_holds: list[dict[str, str]] = []
    active_candidates: dict[str, tuple[str, pathlib.Path, dict[str, Any], str]] = {}

    if not check_only:
        for pkg_name in ("core", "search", "social", "content", "lifecycle"):
            pkg_path = packages_dir / pkg_name
            if pkg_path.exists():
                shutil.rmtree(pkg_path)
            pkg_path.mkdir(parents=True, exist_ok=True)
        if active_dir.exists():
            shutil.rmtree(active_dir)
        active_dir.mkdir(parents=True, exist_ok=True)

    for skill_path in skill_files:
        raw_text = skill_path.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(raw_text)
        name = str(fm["name"])
        cat = str(fm["category"])
        status = str(fm.get("status", "active"))
        pkg = CATEGORY_TO_PACKAGE[cat]

        entry = {
            "name": name,
            "category": cat,
            "package": pkg,
            "tier": fm.get("tier"),
            "status": status,
            "last_updated": fm.get("last_updated"),
            "calculators": fm.get("calculators", []),
            "description": fm.get("description", ""),
            "source_path": str(skill_path.relative_to(repo_root)),
        }
        index_entries.append(entry)

        if status == "needs_sources":
            publication_holds.append({"name": name, "reason": "status: needs_sources"})
            continue

        if not check_only:
            pkg_target = packages_dir / pkg / name / "SKILL.md"
            pkg_target.parent.mkdir(parents=True, exist_ok=True)
            pkg_target.write_text(raw_text, encoding="utf-8")

        if name not in BOOTSTRAP_ONLY_SKILLS:
            active_candidates[name] = (name, skill_path, fm, raw_text)

    # Select curated <=16 active skills for .agents/skills/ (preserving context budget caps)
    preferred_names = RUNTIME_PROFILES[profile]
    active_pack: list[tuple[str, pathlib.Path, dict[str, Any], str]] = []
    for pname in preferred_names:
        if pname in active_candidates and len(active_pack) < 16:
            active_pack.append(active_candidates[pname])
    for name in sorted(active_candidates.keys()):
        if len(active_pack) >= 16:
            break
        if all(item[0] != name for item in active_pack):
            active_pack.append(active_candidates[name])

    if not check_only:
        for name, _, _, raw_text in active_pack:
            act_target = active_dir / name / "SKILL.md"
            act_target.parent.mkdir(parents=True, exist_ok=True)
            act_target.write_text(raw_text, encoding="utf-8")

    index_payload = {
        "schema_version": "1.1.0",
        "total_source_skills": len(index_entries),
        "active_runtime_skills": len(active_pack),
        "active_profile": profile,
        "publication_holds": publication_holds,
        "skills": sorted(index_entries, key=lambda x: x["name"]),
    }
    index_str = json.dumps(index_payload, indent=2, sort_keys=True) + "\n"

    llms_lines = [
        "# FreeCMO",
        "",
        "> Open-source SMB CMO Agent Harness: Composer -> Orchestrator -> Ephemeral Subtask Micro-Pipeline.",
        "",
        "## Canonical Rules & Guides",
        "- [AGENTS.md](./AGENTS.md): Orchestrator cross-channel rules, strategy lock, and 4-lens reviewer",
        "- [guardrails.yaml](./.agents/guardrails.yaml): Autonomy envelope, stop-losses, VIP exclusions",
        "- [HARNESS_SETUP.md](./docs/HARNESS_SETUP.md): Setup for Claude, ChatGPT, Antigravity, Cursor, Codex, Local LLMs & OpenRouter",
        "",
        "## Canonical Skills",
    ]
    for e in sorted(index_entries, key=lambda x: x["name"]):
        if e["status"] != "needs_sources":
            llms_lines.append(f"- [{e['name']}](./{e['source_path']}): {e['description']}")
    llms_str = "\n".join(llms_lines) + "\n"

    full_lines = [llms_str, "## Full Skill Catalog Metadata", ""]
    for e in sorted(index_entries, key=lambda x: x["name"]):
        full_lines.append(f"### {e['name']} ({e['category']} / tier {e['tier']})")
        full_lines.append(f"- Status: {e['status']}")
        full_lines.append(f"- Calculators: {', '.join(e['calculators']) or 'none'}")
        full_lines.append(f"- Description: {e['description']}")
        full_lines.append("")
    llms_full_str = "\n".join(full_lines)

    drift: list[str] = []
    targets = {
        repo_root / "index.json": index_str,
        repo_root / "llms.txt": llms_str,
        repo_root / "llms-full.txt": llms_full_str,
    }
    for path, content in targets.items():
        if check_only:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                drift.append(str(path.relative_to(repo_root)))
        else:
            path.write_text(content, encoding="utf-8")

    return {
        "total_source_skills": len(index_entries),
        "active_runtime_skills": len(active_pack),
        "publication_holds": len(publication_holds),
        "drift": drift,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile skills/ into packages/, .agents/skills/, and catalogs.")
    parser.add_argument("--check", action="store_true", help="Verify generated files match source skills without writing.")
    parser.add_argument("--profile", choices=sorted(RUNTIME_PROFILES.keys()), default="default")
    args = parser.parse_args(argv)

    res = build_artifacts(REPO_ROOT, check_only=args.check, profile=args.profile)
    if args.check and res["drift"]:
        print("FAIL: Packaging drift detected in:", ", ".join(res["drift"]))
        return 1
    print(
        f"OK: {res['total_source_skills']} source skills, "
        f"{res['active_runtime_skills']} active runtime skills ({args.profile}), "
        f"{res['publication_holds']} holds."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
