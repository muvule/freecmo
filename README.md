# FreeCMO

**Your AI Marketing Department in a Box — built for solo founders and lean SMBs.**

Most AI marketing tools are either bloated prompt dumps that invent fake benchmarks or chatty bots that require constant babysitting. **FreeCMO** is an open-source, MIT-licensed **CMO Agent Harness** that runs directly inside your coding agent (**Antigravity**, **Gemini CLI**, **Claude Code / Cowork**, **OpenAI Codex**, **Cursor**) or with local **Ollama** models—using **pure Python 3.11+ stdlib** with zero third-party dependencies.

Instead of drowning you in 50-page strategy docs or burning ad budget on unverified guesses, FreeCMO acts like a disciplined Chief Marketing Officer:
- **It does the math first** (allowable CAC, 3-month cash payback, blended MER, statistical sample size) and marks missing numbers as `unknown`—never guessed.
- **It locks strategy before creating assets** so zero copy, ads, or PRs ship until you approve your positioning and unit economics.
- **It respects your attention**—bundling cross-channel telemetry into **one Weekly Brief with at most 5 ranked decisions**, plus urgent Circuit Breaker alerts only when tracking breaks or spend spikes.

---

## Supported User Journeys

### Journey 1: Day-1 Onboarding & Strategy Lock (`/cmo init`)
> *"I have a product and a website/repo—tell me what channels actually make sense for my margins."*

1. Point FreeCMO at your website URL or local repository, add your product description, monthly budget, AOV, and gross margin.
2. FreeCMO extracts your brand facts, tone, and visual identity into `.agents/brand-truth.md` (`status: draft_pending_review`) and `.agents/visual-dna.json` (palette, typography, `9:16` / `1:1` / `16:9` safe zones, forbidden tropes).
3. `unit-economics-floors` computes your exact **break-even ROAS**, **gross-margin LTV**, and **allowable CAC** (`calculators/cac_ltv.py`), while `budget_gate.py` checks hard prerequisites (tracking health, `<4s` site load, `<3` month payback, `$300/mo` minimum paid budget).
4. **Hard Safety Lock:** All production ad, creative, email, and code-PR skills stay **hard-blocked** until you review and flip `status: locked`.

---

### Journey 2: The 10-Minute Weekly Monday Brief (`weekly-cmo-brief`)
> *"Tell me where every marketing dollar should go this week without checking 6 dashboards."*

1. Drop your CSV exports (Google Ads, Meta Ads, GA4, Google Search Console, Shopify/Stripe) into `data/exports/`—or enable read-only MCPs in `mcp_config.json`.
2. FreeCMO normalizes exports (`csv_normalizer.py`), unifies anonymized customer cohorts (`identity_resolver.py`), and reconciles **storewide blended MER** against **platform-reported ROAS** (`mer.py`).
3. The Orchestrator runs cross-channel trade-off rules in `scripts/next_action.py`:
   - **Retention vs. Cold Acquisition:** Compares marginal ROI of win-back/retention flows vs. cold paid segments and recommends exact dollar shifts (e.g., *"Segment A retention outperforms Segment C cold acquisition by 22pp—shift $300"*).
   - **Auto-Kill Losing Experiments:** Checks every running test in `experiments/ledger.jsonl` against its quantitative `disproof_condition` and retires losers to `Killed Assumptions` so no agent re-pitches them.
4. You review **one batched Weekly Composer's Brief** (capped at **5 P0/P1/P2 decisions**), each backed by verbatim CSV/URL source receipts, dollar impact, and a falsifiable disproof condition.

---

### Journey 3: Instant Content & Creative Amplification (`/cmo run-with-this`)
> *"I just shipped a feature / got a great customer quote / took an event photo—turn this into a full campaign."*

1. Drop a raw note, screenshot, or milestone into `/cmo run-with-this <file_or_note>`.
2. `social-seo-repurposer` and `ad-creative-angle-matrix` generate coordinated drafts across LinkedIn, X, Reddit (with automatic `(Disclosure: I built/work on <Brand>)` FTC compliance), email, and **second-by-second timed video storyboards** (`0–4s` hook → `4–10s` proof → `10–15s` CTA) locked to `.agents/visual-dna.json`.
3. **Zero-Context 4-Lens Review:** Before reaching you, an isolated Reviewer audits **Brand QA** (blocks AI-slop clichés), **Claims & Disclosure QA**, **CRO QA**, and **Falsifiability QA**.
4. Only organic posts that beat your 30-day median save/watch-time by `>= 2x` graduate to `PAUSED` Meta Spark/Boosted ad tests.

---

### Journey 4: Stop Ad Waste, Win AI Search (GEO), & Ship SEO Code PRs
> *"Find what's wasting my Google/Meta budget and fix my site so Google and AI assistants actually cite us."*

- **Mine Wasted Search Spend (`search-term-negative-miner`):** Clusters zero-conversion search terms by 1-gram and 2-gram tokens (`ngram_waste.py`) to surface exact negative keywords.
- **Stop Paying for Your Own Organic #1 Ranks (`gsc-query-drift-triage`):** Cross-joins GSC and Google Ads; if you already rank #1–2 organically with `<5%` competitor impression share, proposes suppressing paid spend on that query.
- **Track & Close AI Citation Gaps (`geo_benchmark.py` + `aeo-entity-readiness`):** Runs 10 buyer-intent prompts against your configured LLM/Ollama endpoint, calculates your citation share (`X/10`), logs which competitor pages got cited, and prioritizes entity gaps.
- **Mine Community Pain (`community-pain-radar`):** Indexes sanitized Reddit/HN/forum discussions in a local SQLite FTS5 graph (`data/radar.db`) to uncover high-converting messaging hooks.
- **Stage Real Website PRs (`seo-geo-code-pr`):** Inspects your Next.js, Astro, WordPress, or HTML repo and opens an isolated branch (`cmo/seo-geo-fixes-<date>`) adding canonical tags, meta descriptions, `FAQPage` JSON-LD, comparison tables, and AI-crawler `robots.txt` rules—never touching `.env`, auth, or billing files.

---

### Journey 5: Teach It Your Taste Once & Roll Back Safely
> *"Stop making me repeat the same feedback—and never let an agent push risky changes silently."*

- **Permanent Voice Memory (`scripts/instinct_extractor.py`):** Whenever you reject or edit a Weekly Brief item (e.g., *"Reject #2: never use discount codes, always write in first-person plural"*), FreeCMO distills it into `.agents/instincts.md` so every channel obeys it forever.
- **VIP & Relationship Protection (`.agents/guardrails.yaml`):** Define `vip_domains`, `vip_contacts_csv`, and `never_cold_pitch_segments` (investors, active customers, advisors, speakers) so outbound pitches to protected contacts are deterministically blocked.
- **Time-Windowed Stop-Losses & `PAUSED` Defaults:** Google Ads payloads default to `validate_only=True`; Meta Ads default to `PAUSED`; conditional stop-losses (`roas < 1.0 after_days >= 14 and spend >= 150`) fire Circuit Breakers automatically.
- **Cryptographic Approval Chain & 1-Click Rollback (`connectors/approval_gate.py`):** Production writes require a fresh (`<=60m`) Validator pass, latest Reviewer approval, and a **single-use** `approval_id` nonce matching the exact payload SHA-256 hash—and automatically save a pre-mutation snapshot to `data/rollbacks/<action_id>.json` for `/cmo rollback <action_id>`.

---

## How FreeCMO Benefits Lean Teams

| Common SMB Marketing Pain | How FreeCMO Solves It in Code |
|---|---|
| **AI hallucinates metrics & benchmarks** | Calculators return `"unknown"` on missing inputs; Validator blocks invented figures without CSV/URL receipts. |
| **Wasted ad spend on broken tracking or slow pages** | `budget_gate.py` blocks paid scaling when `tracking_verified != true`, `site_load_sec >= 4.0`, or payback exceeds target. |
| **Platform ROAS looks great while bank balance drops** | `mer.py` reconciles storewide gross revenue ÷ total ad spend and separates Branded vs. Non-Branded Paid vs. Organic. |
| **Agents keep re-suggesting failed ideas** | Breached `disproof_condition` tests move automatically to `Killed Assumptions` and are blocked by Validator & Reviewer. |
| **Context bloat & runaway tool loops** | Payloads `>1,500` tokens offload to `data/offload/`; workers cap at `6` tool calls / `16k` tokens and `<=16` active skills. |
| **Prompt injection from scraped web/Reddit data** | `sanitizer.py` strips injection patterns, escapes `</untrusted_data>` breakouts, neutralizes CSV formulas, and enforces file-path I/O. |

---

## Quick Start

### 1. Clone & Verify (Zero Dependencies — Python 3.11+ Only)
```bash
git clone https://github.com/muvule/freecmo.git
cd freecmo

# Verify schemas, deterministic calculators, 34 skill worked examples, and safety gates
python3 scripts/build_packages.py --check
python3 scripts/validate_skills.py
python3 scripts/nightly_exam.py
python3 -m unittest discover -s tests -v
```

### 2. Choose Your Data & Model Tier
- **Tier 0 (Zero API Keys / Offline):** Drop CSV exports into `data/exports/` and run deterministic calculators & orchestrator evaluations directly:
  ```bash
  python3 -m calculators.cac_ltv --aov-usd 120 --gross-margin-pct 70 --repeat-orders 2
  python3 scripts/next_action.py --input path/to/state.json
  ```
- **Tier 1 (BYOK LLM or Local Ollama):** Copy `.env.example` to `.env` and set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, or local `OLLAMA_BASE_URL=http://127.0.0.1:11434/v1`:
  ```bash
  cp .env.example .env
  python3 scripts/geo_benchmark.py --brand-name "Your Brand" --brand-domain "yourdomain.com"
  ```
- **Tier 2 (Optional Read-Only MCPs):** Copy `mcp_config.json.example` to `mcp_config.json` to lazy-load read-only GA4, Google Search Console, Meta Ads, PostHog, or Klaviyo servers.

### 3. Use in Your Favorite Coding Harness
- **Antigravity / Gemini CLI:** Reads `GEMINI.md` & `gemini-extension.json` → loads `.agents/skills/`
- **Claude Code / Cowork:** Reads `CLAUDE.md` & `.claude-plugin/plugin.json`
- **OpenAI Codex / Cursor:** Reads `AGENTS.md` & `.codex-plugin/plugin.json`

---

## Included 17-Skill Library

FreeCMO compiles 17 verified source skills in `skills/` into channel packages (`packages/`) and a lean **16-skill active runtime pack** in `.agents/skills/` (`cmo-init` runs as the one-time bootstrap skill). Every skill enforces missing-data rules, stage preconditions, spend/compliance flash points, primary-platform documentation citations, and recomputable `cmo-check` math tests.

| Domain | Skills |
|---|---|
| **Core & Strategy** | `cmo-init`, `unit-economics-floors`, `weekly-cmo-brief` |
| **Analytics & Tracking** | `blended-mer-reconciler`, `tracking-health-audit` |
| **Paid Search** | `google-ads-smb-audit`, `search-term-negative-miner` |
| **Organic Search & GEO/AEO** | `gsc-query-drift-triage`, `local-seo-gbp-optimizer`, `aeo-entity-readiness`, `seo-geo-code-pr` |
| **Paid & Organic Social** | `meta-ads-smb-audit`, `ad-creative-angle-matrix`, `social-seo-repurposer`, `community-pain-radar` |
| **Lifecycle & CRO** | `landing-page-cro-audit`, `email-deliverability-flows` |

---

## Repository Structure

- `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` — Cross-host Orchestrator rules, 4-Lens Reviewer, and prefix-cache prompt contract
- `.agents/` — Brand truth template, Visual DNA, learned Composer `instincts.md`, `guardrails.yaml`, and active skills (`<=16`)
- `calculators/` — Pure stdlib math engines (`cac_ltv`, `mer`, `experiment_math`, `ngram_waste`, `budget_gate`)
- `connectors/` — CSV normalizer, SQLite CDP identity resolver, FTS5 market radar, 1,500-token offloader, injection/VIP sanitizer, safe platform adapters, and temporal approval/rollback gate
- `schemas/` — Draft 2020-12 JSON Schemas for subtask dispatch, evidence bundles, timed storyboards, experiments, and Dual Readout briefs
- `skills/` & `packages/` — Verified `SKILL.md` library and compiled channel bundles
- `scripts/` — Orchestrator (`next_action.py`), 10-prompt GEO benchmark (`geo_benchmark.py`), instinct distiller (`instinct_extractor.py`), CI validator (`validate_skills.py`), packager (`build_packages.py`), doc watcher (`source_watch.py`), and behavioral eval (`nightly_exam.py`)
- `tests/` — Stdlib `unittest` suite including end-to-end pipeline and adversarial security tests

## License

MIT License — see [LICENSE](./LICENSE).
