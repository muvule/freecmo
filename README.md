# FreeCMO

An open-source, MIT-licensed **SMB CMO Agent Harness** implementing a deterministic, attention-budgeted **Composer → Orchestrator → Ephemeral Subtask Micro-Pipeline** compliant with the [Agent Skills open standard](https://agentskills.io/specification).

Designed for solo marketers and SMB founders across **Antigravity**, **Gemini CLI**, **Claude Code / Cowork**, **OpenAI Codex**, **Cursor**, and local **OpenAI-compatible / Ollama** endpoints — with zero third-party Python dependencies (`Python 3.11+` stdlib only).

## Core Architecture

1. **Human as Composer (Attention-Budgeted Control):**
   - `/cmo init` crawls your site/repo and stages `.agents/brand-truth.md` (`status: draft_pending_review`) and `.agents/visual-dna.json`.
   - **Hard Strategy-Before-Production Lock:** Production subtasks are hard-blocked until the Composer reviews and sets `status: locked`.
   - **Discrete Shift Execution:** Auditable shifts (`data/shift_ledger.jsonl`) roll up into a single batched **Weekly Composer's Brief** (max 5 ranked decisions) plus Circuit Breaker alerts only on tracking failures or spend spikes.
   - `/cmo run-with-this <file_or_note>` amplifies a single photo, customer win, or milestone into coordinated multi-channel drafts.
2. **CMO Orchestrator (`AGENTS.md` + `scripts/next_action.py`):**
   - Exclusively reasons across channels: Acquisition vs. Retention reallocation, Paid Search ↔ SEO cannibalization, Paid/Entity/Community → SEO/GEO Code PRs, Organic Social SEO → Paid Creative seeding, Blended MER vs. Platform ROAS, and Closed-Loop Experimentation.
   - Evaluates hard stage preconditions before unlocking any channel.
3. **Blind Ephemeral Subtask Pipeline (`Worker → Validator → 4-Lens Reviewer`):**
   - **Shadow Judge** checks `brand-truth.md`, `instincts.md`, and `experiments/ledger.jsonl` before escalating to the human.
   - **Worker** executes 1–2 stateless `SKILL.md` files on its scoped data slice with verbatim **Source Receipts**.
   - **Validator** deterministically verifies JSON schemas, calculator traceability (`unknown` on missing data), `disproof_condition` presence, `**SPEND FLASH POINT**`, VIP exclusions, and `guardrails.yaml`.
   - **4-Lens Reviewer** (zero-context critic) audits Brand QA, Claims & Disclosure QA (`[OPINION]` vs `[STONE]`, FTC), CRO QA, and Falsifiability QA (`Killed Assumptions` non-resurrection).

## Quick Start

```bash
# 1. Configure BYOK models / optional MCPs (no secrets committed)
cp .env.example .env

# 2. Verify deterministic core, schemas, and skill pack
python3 scripts/build_packages.py --check
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v

# 3. Evaluate next actions & generate dual readout
python3 scripts/next_action.py --help
```

## Directory Layout

- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` — Cross-host orchestrator & governance contract
- `.agents/` — Brand truth template, Visual DNA, learned Composer `instincts.md`, `guardrails.yaml`, and active runtime skill pack (`<=16`)
- `calculators/` — Pure Python 3.11+ stdlib math engines (`cac_ltv`, `mer`, `experiment_math`, `ngram_waste`, `budget_gate`)
- `connectors/` — CSV normalizer, SQLite CDP identity resolver, FTS5 market radar, 1,500-token context offloader, injection/VIP sanitizer, platform adapters, and temporal approval/rollback gate
- `schemas/` — Draft 2020-12 JSON Schemas for subtask dispatch, worker evidence bundles, timed storyboards, experiments, and dual-readout Composer briefs
- `skills/` — Source-of-truth `SKILL.md` library with primary-source citations, flash points, and `cmo-check` worked examples
- `scripts/` — Orchestrator queue (`next_action.py`), 10-prompt GEO benchmark (`geo_benchmark.py`), instinct distiller (`instinct_extractor.py`), CI skill validator (`validate_skills.py`), packager (`build_packages.py`), doc watcher (`source_watch.py`), and eval harness (`nightly_exam.py`)
- `tests/` — Stdlib `unittest` suite
