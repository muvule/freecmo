<div align="center">

<img src="./assets/freecmo-logo.svg" alt="FreeCMO Logo" width="520" />

<br />
<br />

**An attention-budgeted, deterministic AI Marketing & Comms Department for solo founders and lean SMBs.**

Works in **Antigravity** · **Claude Code & Desktop** · **ChatGPT** · **Codex** · **Cursor** · **Gemini CLI** · **Local Ollama / LM Studio** · **OpenRouter**  
Zero external Python dependencies (`Python 3.11+` stdlib) · Built-in Stdio MCP Server · MIT Licensed

[Quick Start](#quick-start) &nbsp;·&nbsp; [User Journeys](#user-journeys) &nbsp;·&nbsp; [Harness & Local LLM Setup](./docs/HARNESS_SETUP.md) &nbsp;·&nbsp; [Safeguards](#built-in-safeguards) &nbsp;·&nbsp; [22-Skill Library](#22-skill-library)

</div>

---

Most AI marketing tools are noisy prompt dumps that invent metrics and bury you in 50-page docs. **FreeCMO** takes the opposite approach: calm, verifiable execution across ads, search, social, editorial, and comms.

- **Automated telemetry, zero guesswork** — Pulls read-only performance directly from **Google Ads, Meta (Instagram & Facebook), LinkedIn, TikTok, GA4, Search Console, Stripe, and Shopify** (or offline CSVs) and computes CAC payback, blended MER, promo break-even, and creator caps in pure Python. Missing numbers stay `unknown`.
- **Strategy before production** — Ads, blog posts, press releases, and code PRs stay hard-blocked until you review and lock `.agents/brand-truth.md`.
- **10 minutes a week** — Synthesizes cross-channel outcomes into **one batched Weekly Composer's Brief (max 5 ranked decisions)**, surfacing Circuit Breaker alerts only when tracking breaks or spend spikes.

<br />

<div align="center">
<img src="./assets/channels-and-hosts.svg" alt="FreeCMO Platform Sync, Editorial & Ad Studio, and Multi-Host Ecosystem" width="900" />
</div>

---

## User Journeys

<div align="center">
<img src="./assets/weekly-loop.svg" alt="FreeCMO 5-Stage Weekly Operating Loop" width="900" />
</div>

<br />

<table>
<tr>
<td width="50%" valign="top">

### 01 · Day-1 Setup & Strategy Lock
`/cmo init` · `cmo_runner.py init`

Point FreeCMO at your site URL or repo with your budget and margins. It stages `.agents/brand-truth.md` and `.agents/visual-dna.json`, calculates your **break-even ROAS** and **allowable CAC**, and locks out campaign production until you approve `status: locked`.

</td>
<td width="50%" valign="top">

### 02 · Automated Weekly Monday Brief
`sync_platforms.py --emit-brief`

Automatically pulls Google Ads, Meta/IG/FB Ads & organic insights, LinkedIn, TikTok, GA4, GSC, Stripe, and Shopify (SHA-256 hashing customer emails locally), reconciles **blended MER**, shifts budget toward higher-ROI retention cohorts, and emits **≤5 P0/P1/P2 decisions** with receipts.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 03 · Social, Display & Native Creative Studio
`display-native-ad-studio` · `/cmo run-with-this`

Guides **AI image generation prompts**, **real photo/UI shot lists**, safe zones, and character-bounded copy across **Instagram** (`9:16` Reels/Stories, `4:5` Carousels), **Facebook** (Feed/Reels/Groups), **LinkedIn**, **X**, **Google Display IAB banners** (`300x250`, `728x90`, `300x600`, `320x50`, `160x600`), and **Native discovery ads**.

</td>
<td width="50%" valign="top">

### 04 · Editorial Blog, Forum & Comms PR Desk
`editorial-blog-linkedin-writer` · `comms-press-release-writer`

Writes answer-first **SEO/GEO web blog posts** (with `Article` & `FAQPage` JSON-LD), zero-fluff **Reddit/HN/forum posts** (with automatic affiliation disclosure), **LinkedIn articles**, and **AP-style press releases** + journalist pitches strictly separating `[STONE]` facts from `[OPINION]` quotes.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 05 · Waste Mining, GEO & Code PRs
`seo-geo-code-pr` · `geo_benchmark.py`

Clusters wasted search terms into negative keywords (`ngram_waste.py`), suppresses cannibalizing paid terms where organic ranks #1–2, benchmarks AI citations across **10 buyer prompts**, and opens isolated git branches adding structured data and comparison tables.

</td>
<td width="50%" valign="top">

### 06 · Battlecards, Promo Math & Creator Caps
`competitor-battlecard-pricing` · `creator-affiliate-partnerships`

Builds dated competitor battlecards, calculates exact **promo volume-lift break-even** before you run margin-eroding discounts, caps **creator flat fees + affiliate commissions** within allowable CAC, and enforces governed UTMs + FTC `#ad` disclosures.

</td>
</tr>
</table>

---

## Architecture

<div align="center">
<img src="./assets/architecture-flow.svg" alt="FreeCMO Composer to Orchestrator to Ephemeral Subtask Architecture" width="900" />
</div>

<br />

Only the **Orchestrator** (`AGENTS.md` + `scripts/next_action.py`) reasons across channels. Specialist skills are stateless and blind to other channels, keeping active context lean (`<=16` active runtime skills per profile, payloads `>1,500` tokens offloaded to `data/offload/`, static-to-dynamic KV-cache ordering, permanent taste memory in `.agents/instincts.md`, and 1-click rollbacks in `data/rollbacks/`).

---

## Run Anywhere: IDE, Desktop, Web, Local Machine (`$0`), or OpenRouter

Generate ready-to-use configs for any host in one command (full step-by-step instructions in **[`docs/HARNESS_SETUP.md`](./docs/HARNESS_SETUP.md)**):

```bash
python3 scripts/setup_harness.py --host all
```

| Environment | How FreeCMO Connects |
|---|---|
| **Antigravity & Gemini CLI** | Native `GEMINI.md`, `AGENTS.md`, `gemini-extension.json`, and `scripts/mcp_server.py`. |
| **Claude Code & Claude Desktop** | Native `CLAUDE.md`, `.claude-plugin/plugin.json`, and zero-dependency stdio MCP (`freecmo-core`). |
| **ChatGPT & Claude Web Projects** | `setup_harness.py` exports `<8,000`-char Custom GPT / Project Instructions + a single Knowledge bundle. |
| **OpenAI Codex & Cursor** | Native `AGENTS.md`, `.codex-plugin/plugin.json`, `.cursor/rules/freecmo.mdc`, and MCP tools. |
| **Local LLMs (`$0` API Cost)** | `cmo_runner.py` routes directly to **Ollama** (`127.0.0.1:11434`), **LM Studio** (`127.0.0.1:1234`), or **vLLM**. |
| **OpenRouter / DeepSeek / Groq** | Tiered routing sends worker tasks to low-cost models (`deepseek-chat`, `llama-3.3-70b`) and orchestration to reasoning models. |

---

## Built-In Safeguards

| SMB Failure Mode | Deterministic Code Defense |
|---|---|
| **Invented benchmarks & hallucinated ROI** | Calculators propagate `"unknown"` on missing inputs; Validator blocks unreceipted numbers. |
| **Margin-destroying discounts & creator deals** | `cac_ltv.py` blocks negative-margin promos (`impossible_negative_margin`) and caps creator fees + commissions within allowable CAC. |
| **Burning cash on broken tracking or slow pages** | `budget_gate.py` locks paid scaling when `tracking_verified != true`, `site_load_sec >= 4.0`, or payback exceeds target. |
| **Silent ad-spend blowups** | Google Ads defaults to `validate_only=True`; Meta/IG/FB defaults to `PAUSED`; conditional stop-losses fire Circuit Breakers. |
| **Raw PII leaks or VIP outreach** | `ad_platform_sync.py` & `identity_resolver.py` SHA-256 hash customer emails locally; `guardrails.yaml` blocks VIP domains/contacts. |
| **Prompt injection, SSRF & formula exploits** | `sanitizer.py` neutralizes `</untrusted_data>`; `validate_endpoint_url` blocks private/metadata SSRF; `csv_normalizer.py` neutralizes formulas. |

---

## Quick Start

```bash
git clone https://github.com/muvule/freecmo.git
cd freecmo

# 1. Run automated platform sync + Weekly Composer's Brief (try offline with --demo-fixture)
python3 scripts/sync_platforms.py --demo-fixture --emit-brief

# 2. Configure your preferred AI host (Claude, ChatGPT, Antigravity, Cursor, Codex, Ollama, OpenRouter)
python3 scripts/setup_harness.py --host all

# 3. Verify all 22 skills, 44 live-recomputed worked examples, and unit tests
python3 scripts/validate_skills.py
python3 -m unittest discover -s tests -v
```

---

## 22-Skill Library

All 22 canonical skills in `skills/` compile into channel packages (`packages/{core,search,social,content,lifecycle}`) and selectable **16-skill runtime profiles** (`default`, `content-comms`, `paid-media`) so active context stays tiny.

| Domain | Skills |
|---|---|
| **Core, Strategy & Pricing** | `cmo-init` · `unit-economics-floors` · `weekly-cmo-brief` · `competitor-battlecard-pricing` |
| **Analytics & Attribution** | `blended-mer-reconciler` · `tracking-health-audit` |
| **Editorial & Comms PR** | `editorial-blog-linkedin-writer` · `comms-press-release-writer` |
| **Social, Display & Native Ads** | `meta-ads-smb-audit` · `ad-creative-angle-matrix` · `display-native-ad-studio` · `social-seo-repurposer` · `community-pain-radar` |
| **Paid Search** | `google-ads-smb-audit` · `search-term-negative-miner` |
| **Organic Search & GEO** | `gsc-query-drift-triage` · `local-seo-gbp-optimizer` · `aeo-entity-readiness` · `seo-geo-code-pr` |
| **Lifecycle, Creators & CRO** | `landing-page-cro-audit` · `email-deliverability-flows` · `creator-affiliate-partnerships` |

<details>
<summary><strong>Repository Structure</strong></summary>

```text
freecmo/
├── AGENTS.md / CLAUDE.md / GEMINI.md   # Cross-host orchestrator & governance contract
├── docs/HARNESS_SETUP.md               # Step-by-step setup for IDEs, Desktop, Web, Local LLMs & OpenRouter
├── .agents/                            # Brand truth template, Visual DNA v1.1, instincts.md, guardrails.yaml, active skills (<=16)
├── assets/                             # Minimalist Scandinavian SVG logo & system diagrams
├── calculators/                        # Pure Python 3.11+ math (cac_ltv + promo + creator caps, mer, experiment_math, ngram_waste, budget_gate)
├── connectors/                         # ad_platform_sync, llm_router, utm_governance, csv_normalizer, identity_resolver, radar_store, approval_gate
├── schemas/                            # Draft 2020-12 JSON Schemas (subtask_spec, worker_output, storyboard, creative_asset_spec, experiment, composers_brief)
├── skills/ & packages/                 # 22 source SKILL.md files and compiled channel packages
├── scripts/                            # sync_platforms.py, mcp_server.py, setup_harness.py, cmo_runner.py, next_action.py, geo_benchmark.py, validate_skills.py
└── tests/                              # Stdlib unittest suite covering math, platform sync, LLM routing, MCP, schemas, and security invariants
```

</details>

---

<div align="center">

MIT License · [LICENSE](./LICENSE)

</div>
