# Harness Setup & Platform Sync Guide

**FreeCMO** follows the open `AGENTS.md` + Agent Skills (`agentskills.io`) + Model Context Protocol (`MCP`) standards. Run it inside your preferred AI coding IDE, desktop/web chat app, or directly on your own machine with local or low-cost LLMs.

---

## 1. Quick Generator Command

Generate host-specific rule files, MCP configs, and single-file Knowledge bundles for ChatGPT or Claude Web in one command:

```bash
python3 scripts/setup_harness.py --host all
```

Or target a single host (`antigravity`, `gemini-cli`, `gemini-hydrogen`, `claude-code`, `claude-desktop`, `claude-web`, `chatgpt`, `codex`, `cursor`, `local-llm`, `openrouter`):

```bash
python3 scripts/setup_harness.py --host gemini-hydrogen
python3 scripts/setup_harness.py --host claude-desktop
python3 scripts/setup_harness.py --host chatgpt
python3 scripts/setup_harness.py --host cursor --write-workspace-cursor
```

---

## 2. Host-by-Host Setup

### Google Antigravity & Gemini CLI
1. Open the cloned `FreeCMO` folder in **Antigravity** (or run `gemini` inside the repo directory).
2. `GEMINI.md`, `AGENTS.md`, `gemini-extension.json`, and `.agents/skills/` (`<= 16` active skills) load automatically.
3. Optional MCP tools: merge `mcp_config.json.example` into your MCP settings so `freecmo-core` (`python3 scripts/mcp_server.py`) exposes deterministic calculators and platform sync as native tools.

### Claude Code (CLI)
1. Run `claude` inside the `FreeCMO` directory.
2. `CLAUDE.md`, `.claude-plugin/plugin.json`, and `.agents/skills/` load automatically under Claude Code's 1% context budget.
3. Add the built-in zero-dependency MCP server:
   ```bash
   claude mcp add freecmo-core -- python3 "$(pwd)/scripts/mcp_server.py"
   ```

### Claude Desktop (macOS / Windows)
1. Run `python3 scripts/setup_harness.py --host claude-desktop`.
2. Copy the `freecmo-core` block from `dist/hosts/claude_desktop_and_mcp_config.json` into your `claude_desktop_config.json`:
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
3. Restart Claude Desktop. Claude now has live access to `freecmo_unit_economics`, `freecmo_promo_breakeven`, `freecmo_creator_commission_cap`, `freecmo_blended_mer`, `freecmo_churn_and_runway`, `freecmo_creative_fatigue`, `freecmo_ai_search_fanout_audit`, `freecmo_offline_local_channel`, `freecmo_utm_builder`, `freecmo_sync_platforms`, and `freecmo_weekly_brief`.

### Claude Web (`claude.ai` Projects)
1. Run `python3 scripts/setup_harness.py --host claude-web`.
2. Create a new **Claude Project**.
3. Paste `dist/hosts/claude_project_instructions.md` into **Project Instructions**.
4. Upload `dist/hosts/claude_project_knowledge_bundle.md` (plus any CSV exports) to **Project Knowledge**.

### ChatGPT (Custom GPTs & ChatGPT Projects)
1. Run `python3 scripts/setup_harness.py --host chatgpt`.
2. Open **ChatGPT -> Explore GPTs -> Create** (or create a **ChatGPT Project**):
   - Paste `dist/hosts/chatgpt_custom_gpt_instructions.md` (`< 8,000` characters) into **Instructions**.
   - Upload `dist/hosts/chatgpt_knowledge_bundle.md` into **Knowledge** (and enable **Code Interpreter & Data Analysis** so ChatGPT executes the deterministic Python math formulas).

### OpenAI Codex (CLI & Cloud)
1. Open the repository in **Codex**; `AGENTS.md` and `.codex-plugin/plugin.json` load automatically within Codex's 2% skill-listing cap.
2. Register `python3 scripts/mcp_server.py` in `~/.codex/config.toml` if you want native MCP tool calls alongside shell execution.

### Cursor IDE
1. Run:
   ```bash
   python3 scripts/setup_harness.py --host cursor --write-workspace-cursor
   ```
2. This writes `.cursor/rules/freecmo.mdc` and `dist/hosts/cursor_mcp.json` (copy to `.cursor/mcp.json` to enable the local `freecmo-core` MCP server).

---

## 3. Gemini 4 Hydrogen (`$0` AI Studio Free Tier), Local BYO-Machine LLMs & OpenRouter

You do **not** need an expensive IDE subscription to run FreeCMO. `scripts/cmo_runner.py` and `connectors/llm_router.py` execute the full harness from any terminal.

### Option A — Google Gemini 4 Hydrogen (`gemini-4-hydrogen` — `$0` Google AI Studio Free Tier + Multimodal Critique)
`gemini-4-hydrogen` supports 1M context, tunable `LOW | MEDIUM | HIGH | XHIGH` agentic thinking levels, and native multimodal inspection of ad mockups, landing-page screenshots, and PDF decks:

```bash
python3 scripts/setup_harness.py --host gemini-hydrogen
cp dist/hosts/env.gemini-hydrogen.example .env
# Paste your free Google AI Studio GEMINI_API_KEY into .env
python3 scripts/cmo_runner.py status --provider gemini-hydrogen
python3 scripts/cmo_runner.py run-skill \
  --provider gemini-hydrogen \
  --thinking-level HIGH \
  --skill landing-page-cro-audit \
  --attach path/to/landing-page-screenshot.png \
  --brief "Audit hero message match, CTA clarity, and trust signals"
```

### Option B — 100% Local Machine (`Ollama`, `LM Studio`, `vLLM`, `llama.cpp`) & Low-RAM 7B Offline Pack
1. Install [Ollama](https://ollama.com) and pull a capable local model (`qwen2.5:7b` runs cleanly on 8 GB laptops with `$0` cloud fees):
   ```bash
   ollama pull qwen2.5:7b
   # Optional on 16 GB+ machines:
   ollama pull qwen2.5:14b
   ```
2. Copy either the standard preset or the **7B offline preset** (optionally activating the `local-entrepreneur` 16-skill profile):
   ```bash
   python3 scripts/setup_harness.py --host local-llm --profile local-entrepreneur
   cp dist/hosts/env.local-7b-offline.example .env   # or env.local-llm.example for 14b
   ```
   *(Using **LM Studio** instead? Set `CMO_LLM_PROVIDER=lmstudio` and `LMSTUDIO_BASE_URL=http://127.0.0.1:1234/v1` in `.env`.)*
3. Run FreeCMO in any local currency (`KES`, `IDR`, `MXN`, `NGN`, `INR`, `USD`, etc.) without converting to USD:
   ```bash
   python3 scripts/cmo_runner.py status --provider ollama-7b
   python3 scripts/cmo_runner.py init --brand-name "JuaKazi Solar" --website-url "https://example.com" --currency KES --aov 1800 --gross-margin-pct 55 --monthly-budget 15000
   # After reviewing .agents/brand-truth.md and setting status: locked:
   python3 scripts/cmo_runner.py run-skill --provider ollama-7b --skill offline-local-channels --brief "Draft a WhatsApp broadcast, GSM-7 SMS alert, and 30s community radio spot for our Nakuru market promo"
   ```

### Option C — OpenRouter, DeepSeek, Groq, or Together AI (~85–95% Lower Cost)
Route fast worker subtasks to ultra-low-cost models (`deepseek/deepseek-chat`, `llama-3.3-70b-versatile`), multimodal creative audits to `google/gemini-4-hydrogen`, and orchestration to reasoning models (`deepseek/deepseek-r1`):

```bash
python3 scripts/setup_harness.py --host openrouter
cp dist/hosts/env.openrouter.example .env
# Add your OPENROUTER_API_KEY (or DEEPSEEK_API_KEY / GROQ_API_KEY / TOGETHER_API_KEY) in .env
python3 scripts/cmo_runner.py status --provider openrouter
python3 scripts/cmo_runner.py run-skill --provider openrouter --skill comms-press-release-writer --brief "Announcing our SOC 2 Type II compliance certification"
```

---

## 4. Automated Ad, Social (IG/FB), Analytics & Revenue Sync

No manual CSV exporting required. Configure read-only tokens in `.env` (see `.env.example`) for any combination of:
- **Google Ads** (`GOOGLE_ADS_CUSTOMER_ID`, Google OAuth2 refresh token — `v26`, developer token optional)
- **Meta Ads + Instagram Business + Facebook Page** (`META_ACCESS_TOKEN`, `META_AD_ACCOUNT_ID`, `IG_BUSINESS_ACCOUNT_ID`, `FB_PAGE_ID` — Graph API `v27.0` with `views,reach,saved` insights)
- **LinkedIn Ads & TikTok Ads** (`LINKEDIN_ACCESS_TOKEN` / `202610`, `TIKTOK_ACCESS_TOKEN` / `v1.3`)
- **GA4 & Google Search Console** (`GA4_PROPERTY_ID` using `keyEvents`, `GSC_SITE_URL`)
- **Stripe & Shopify** (`STRIPE_RESTRICTED_KEY` via `/v1/payment_intents`, `SHOPIFY_STORE_DOMAIN` + `SHOPIFY_ADMIN_TOKEN` via GraphQL Admin `2026-10` — customer emails are SHA-256 hashed locally before touching disk or SQLite)

Run a live sync + Weekly Composer's Brief:
```bash
python3 scripts/sync_platforms.py --emit-brief --output-brief data/weekly_brief.json
```

Test offline anytime with deterministic multi-platform telemetry:
```bash
python3 scripts/sync_platforms.py --demo-fixture --emit-brief
```

To run hands-free every Monday in GitHub Actions, add your read-only keys to **Repository Settings -> Secrets and variables -> Actions** and trigger or uncomment the cron schedule in `.github/workflows/weekly_shift.yml`.
