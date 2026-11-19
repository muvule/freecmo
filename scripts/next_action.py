"""Stage-precondition, disproof-condition, stop-loss, and cross-channel Orchestrator queue engine."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timezone
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from calculators import format_money, normalize_currency, resolve_amount, safe_parse_yaml, validate_json_schema
from calculators.budget_gate import evaluate_budget_gate
from calculators.creative_fatigue import detect_creative_fatigue
from calculators.experiment_math import evaluate_disproof_condition
from calculators.mer import allocate_acquisition_vs_retention, evaluate_stop_losses
from calculators.runway_churn import compute_churn_and_nrr, simulate_cash_flow_runway
from connectors.approval_gate import check_strategy_lock
from scripts.validate_skills import split_frontmatter


PRODUCTION_SKILLS = {
    "google-ads-smb-audit",
    "search-term-negative-miner",
    "meta-ads-smb-audit",
    "ad-creative-angle-matrix",
    "display-native-ad-studio",
    "social-seo-repurposer",
    "offline-local-channels",
    "editorial-blog-linkedin-writer",
    "comms-press-release-writer",
    "competitor-battlecard-pricing",
    "creator-affiliate-partnerships",
    "churn-winback-engine",
    "launch-campaign-playbook",
    "review-referral-flywheel",
    "seo-geo-code-pr",
    "aeo-entity-readiness",
    "landing-page-cro-audit",
    "email-deliverability-flows",
    "community-pain-radar",
}


def _resolve_brand_currency(state: dict[str, Any], brand_truth_path: pathlib.Path) -> str:
    raw = state.get("currency")
    if not raw and brand_truth_path.exists():
        try:
            fm, _ = split_frontmatter(brand_truth_path.read_text(encoding="utf-8"))
            raw = fm.get("currency")
        except Exception:
            raw = None
    return normalize_currency(str(raw) if raw else "USD")


def load_killed_assumptions(brand_truth_path: pathlib.Path) -> list[str]:
    """Extract disproven angle keywords/bet IDs from brand-truth.md Killed Assumptions table."""
    if not brand_truth_path.exists():
        return []
    text = brand_truth_path.read_text(encoding="utf-8")
    killed: list[str] = []
    in_section = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## 4. Killed Assumptions"):
            in_section = True
            continue
        if in_section and s.startswith("## "):
            break
        if in_section and s.startswith("|") and not s.startswith("| Bet ID") and not s.startswith("|---"):
            cols = [c.strip().strip("`") for c in s.strip("|").split("|")]
            if len(cols) >= 2 and cols[0] and cols[0] != "—":
                killed.append(cols[0].lower())
                if cols[1] and cols[1] != "None recorded yet":
                    killed.append(cols[1].lower())
    return killed


def append_killed_assumption(
    brand_truth_path: pathlib.Path,
    bet_id: str,
    angle: str,
    evidence: str,
    killed_date: str,
) -> None:
    """Record a failed disproof condition in brand-truth.md Killed Assumptions table."""
    if not brand_truth_path.exists():
        return
    text = brand_truth_path.read_text(encoding="utf-8")
    if f"| `{bet_id}` |" in text:
        return
    new_row = f"| `{bet_id}` | {angle} | {evidence} | `{killed_date}` | Explicit market or product change approved by Composer |"
    placeholder = "| — | None recorded yet | — | — | Requires explicit market/product shift approved by Composer |"
    if placeholder in text:
        text = text.replace(placeholder, new_row)
    else:
        marker = "## 5. Validated Learnings"
        if marker in text:
            text = text.replace(marker, new_row + "\n\n" + marker)
        else:
            text += "\n" + new_row + "\n"
    brand_truth_path.write_text(text, encoding="utf-8")


def process_experiment_ledger(
    ledger_path: pathlib.Path,
    brand_truth_path: pathlib.Path,
    today: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate running experiments for disproof conditions; migrate failed bets to Killed Assumptions."""
    if not ledger_path.exists():
        return []
    date_str = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [ln.strip() for ln in ledger_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    updated_records: list[dict[str, Any]] = []
    newly_killed: list[dict[str, Any]] = []

    for ln in lines:
        rec = json.loads(ln)
        if rec.get("status") == "running" and rec.get("observed_metrics") and rec.get("disproof_condition"):
            ev = evaluate_disproof_condition(rec["disproof_condition"], rec["observed_metrics"])
            if ev.get("killed") is True:
                rec["status"] = "killed"
                rec["concluded_at"] = date_str
                newly_killed.append(rec)
                append_killed_assumption(
                    brand_truth_path=brand_truth_path,
                    bet_id=rec["experiment_id"],
                    angle=rec["hypothesis"],
                    evidence=f"Disproof triggered: {rec['disproof_condition']}",
                    killed_date=date_str,
                )
        updated_records.append(rec)

    if newly_killed:
        ledger_path.write_text(
            "\n".join(json.dumps(r, sort_keys=True) for r in updated_records) + "\n",
            encoding="utf-8",
        )
    return newly_killed


def generate_next_actions(state: dict[str, Any], repo_root: pathlib.Path = REPO_ROOT) -> dict[str, Any]:
    """Evaluate preconditions, stop-losses, cross-channel rules, and emit Dual Readout Brief."""
    brand_truth_path = pathlib.Path(state.get("brand_truth_path") or (repo_root / ".agents/brand-truth.md"))
    guardrails_path = pathlib.Path(state.get("guardrails_path") or (repo_root / ".agents/guardrails.yaml"))
    ledger_path = pathlib.Path(state.get("experiment_ledger_path") or (repo_root / "experiments/ledger.jsonl"))

    lock_status = check_strategy_lock(brand_truth_path)
    normalized_lock = "locked" if lock_status == "locked" else "draft_pending_review"
    cur = _resolve_brand_currency(state, brand_truth_path)
    newly_killed = process_experiment_ledger(ledger_path, brand_truth_path)
    killed_markers = load_killed_assumptions(brand_truth_path)

    guardrails = {}
    if guardrails_path.exists():
        guardrails = safe_parse_yaml(guardrails_path.read_text(encoding="utf-8")) or {}
    org_paid = guardrails.get("organic_paid_rules", {}) or {}
    stop_rules = guardrails.get("stop_loss_rules", []) or []

    decisions: list[dict[str, Any]] = []
    subtasks: list[dict[str, Any]] = []
    circuit_breakers: list[dict[str, Any]] = []
    segment_shifts: list[dict[str, Any]] = []

    # 1. Hard Strategy-Before-Production Lock check
    if normalized_lock != "locked":
        decisions.append(
            {
                "rank": 1,
                "priority": "P0",
                "decision_title": "Lock brand-truth.md strategy before production",
                "rationale": (
                    "brand-truth.md is currently missing or draft_pending_review. "
                    "All production creative, paid-ad, and code-PR subtasks are hard-blocked until Composer locks strategy."
                ),
                "dollar_impact_usd": 0.0,
                "disproof_condition": "strategy_lock_status != locked after Composer review",
                "source_receipts": [str(brand_truth_path)],
            }
        )
        subtasks.append(
            {
                "subtask_id": "subtask-cmo-init-lock",
                "skill_names": ["cmo-init", "unit-economics-floors"],
                "model_tier": "deep_orchestrator",
                "max_tool_calls": 6,
                "max_tokens_budget": 16000,
                "requires_reviewer": True,
                "is_production_mutation": False,
                "data_slice_pointers": [str(brand_truth_path)],
                "file_touch_boundaries": {
                    "allowed_paths": [".agents/brand-truth.md", ".agents/visual-dna.json"],
                    "forbidden_paths": [".agents/guardrails.yaml", "calculators/*", "connectors/*"],
                },
                "goal": "Complete unit economics and strategy draft for Composer lock approval.",
                "disproof_condition": "unit_economics == unknown after founder interview",
            }
        )
        return _build_dual_readout(normalized_lock, circuit_breakers, decisions, segment_shifts, subtasks, repo_root)

    # 2. Tracking & Stop-Loss Circuit Breakers
    if state.get("tracking_verified") is False:
        circuit_breakers.append(
            {
                "alert_id": "cb-tracking-broken",
                "severity": "critical",
                "message": "Conversion tracking verification failed; pause paid scaling immediately.",
                "recommended_pause": True,
            }
        )
        budget_impact = resolve_amount(state.get("monthly_budget"), state.get("monthly_budget_usd")) or 0.0
        decisions.append(
            {
                "rank": len(decisions) + 1,
                "priority": "P0",
                "decision_title": "Repair conversion tracking before any paid spend",
                "rationale": "Tracking health check failed. Scaling paid channels with broken attribution burns budget blindly.",
                "dollar_impact_usd": float(budget_impact),
                "disproof_condition": "conversion_events == 0 after 24h post-fix QA check",
                "source_receipts": [state.get("tracking_receipt", "analytics/tracking_health")],
            }
        )
        subtasks.append(
            {
                "subtask_id": "subtask-tracking-repair",
                "skill_names": ["tracking-health-audit"],
                "model_tier": "balanced_worker",
                "max_tool_calls": 6,
                "max_tokens_budget": 16000,
                "requires_reviewer": False,
                "is_production_mutation": False,
                "data_slice_pointers": ["data/exports/ga4_events.csv"],
                "file_touch_boundaries": {
                    "allowed_paths": ["data/offload/*"],
                    "forbidden_paths": [".agents/guardrails.yaml"],
                },
                "goal": "Diagnose missing conversion tags, server-side events, and UTM drop-offs.",
                "disproof_condition": "purchase_event_match_rate < 0.95 after tag fix",
            }
        )

    # Stop-losses
    sl_res = evaluate_stop_losses(stop_rules, state.get("active_campaigns", []))
    for alert in sl_res.get("triggered_alerts", []):
        circuit_breakers.append(
            {
                "alert_id": f"cb-{alert['rule_id']}-{alert['campaign_id']}",
                "severity": "critical",
                "message": f"Stop-loss {alert['rule_id']} triggered on {alert['campaign_id']}: {alert['condition']}",
                "recommended_pause": True,
            }
        )

    # 2b. Leaky-Bucket Churn & J-Curve Working-Capital Runway Circuit Breakers
    if isinstance(state.get("churn_metrics"), dict):
        churn_kwargs = dict(state["churn_metrics"])
        churn_kwargs.setdefault("currency", cur)
        churn_res = compute_churn_and_nrr(**churn_kwargs)
        if churn_res.get("status") == "ok" and churn_res.get("leaky_bucket_alert") is True:
            circuit_breakers.append(
                {
                    "alert_id": "cb-leaky-bucket-churn",
                    "severity": "critical",
                    "message": (
                        f"Leaky-bucket retention alert (monthly NRR={churn_res['monthly_nrr_pct']}%, "
                        f"implied lifetime={churn_res['implied_lifetime_months']}m); freeze cold paid scaling."
                    ),
                    "recommended_pause": True,
                }
            )
            if len(decisions) < 5:
                mrr_base = resolve_amount(
                    churn_kwargs.get("starting_mrr"),
                    churn_kwargs.get("starting_mrr_usd"),
                ) or 0.0
                mrr_at_risk = round(
                    mrr_base * (float(churn_kwargs.get("monthly_revenue_churn_pct", 0.0)) / 100.0),
                    2,
                )
                decisions.append(
                    {
                        "rank": len(decisions) + 1,
                        "priority": "P0",
                        "decision_title": "Freeze cold paid scaling and deploy churn win-back engine",
                        "rationale": (
                            f"Monthly NRR is {churn_res['monthly_nrr_pct']}% with "
                            f"{churn_res['implied_lifetime_months']}m implied lifetime; plug churn before buying new CAC."
                        ),
                        "dollar_impact_usd": mrr_at_risk,
                        "disproof_condition": "monthly_logo_churn_pct >= baseline after 30-day cancel-deflection & dunning rollout",
                        "source_receipts": ["calculators/runway_churn.py#compute_churn_and_nrr"],
                    }
                )
                subtasks.append(
                    {
                        "subtask_id": "subtask-churn-winback",
                        "skill_names": ["churn-winback-engine", "email-deliverability-flows"],
                        "model_tier": "balanced_worker",
                        "max_tool_calls": 6,
                        "max_tokens_budget": 16000,
                        "requires_reviewer": True,
                        "is_production_mutation": False,
                        "data_slice_pointers": ["data/radar.db"],
                        "file_touch_boundaries": {
                            "allowed_paths": ["data/offload/*"],
                            "forbidden_paths": [".agents/guardrails.yaml"],
                        },
                        "goal": "Design pre-dunning recovery, cancel-flow pause/downgrade deflection, and 30/60/90d win-back sequence.",
                        "disproof_condition": "save_rate_on_cancel_flow < 0.10 after 100 cancel intents",
                    }
                )

    if isinstance(state.get("cash_runway"), dict):
        runway_kwargs = dict(state["cash_runway"])
        runway_kwargs.setdefault("currency", cur)
        runway_res = simulate_cash_flow_runway(**runway_kwargs)
        if runway_res.get("status") == "ok" and runway_res.get("runway_safe") is False:
            trough_fmt = runway_res.get("max_cash_trough_formatted") or f"${runway_res['max_cash_trough_usd']:.0f}"
            min_bal_fmt = runway_res.get("min_cash_balance_formatted") or f"${runway_res['min_cash_balance_usd']:.0f}"
            circuit_breakers.append(
                {
                    "alert_id": "cb-cash-runway-trough",
                    "severity": "critical",
                    "message": (
                        f"J-curve cash trough ({trough_fmt}) leaves minimum cash "
                        f"{min_bal_fmt} below 1-month operating buffer."
                    ),
                    "recommended_pause": True,
                }
            )
            if len(decisions) < 5:
                decisions.append(
                    {
                        "rank": len(decisions) + 1,
                        "priority": "P0",
                        "decision_title": "Throttle paid ad spend to protect working-capital cash runway",
                        "rationale": (
                            f"Upfront CAC creates a {trough_fmt} cash trough before payback "
                            f"(min balance {min_bal_fmt}). Cap spend or shift to annual prepay."
                        ),
                        "dollar_impact_usd": float(runway_res["max_cash_trough_usd"]),
                        "disproof_condition": "min_cash_balance_usd < monthly_outflow_usd under revised spend cap",
                        "source_receipts": ["calculators/runway_churn.py#simulate_cash_flow_runway"],
                    }
                )

    # 3. Acquisition vs. Retention Reallocation
    if state.get("cohort_segments"):
        pool_amt = resolve_amount(state.get("reallocation_pool"), state.get("reallocation_pool_usd")) or 0.0
        alloc = allocate_acquisition_vs_retention(
            state["cohort_segments"],
            reallocation_pool=pool_amt,
            currency=cur,
        )
        rec = alloc.get("recommendation")
        if rec and len(decisions) < 5:
            shift_fmt = rec.get("shift_formatted") or format_money(rec["shift_usd"], cur)
            segment_shifts.append(
                {
                    "from_segment": rec["from_segment"],
                    "to_segment": rec["to_segment"],
                    "amount_usd": rec["shift_usd"],
                    "marginal_roi_delta_pct": rec["marginal_roi_delta_pct"],
                }
            )
            decisions.append(
                {
                    "rank": len(decisions) + 1,
                    "priority": "P0",
                    "decision_title": f"Shift {shift_fmt} from {rec['from_segment']} to {rec['to_segment']}",
                    "rationale": rec["summary"],
                    "dollar_impact_usd": rec["shift_usd"],
                    "disproof_condition": "retention_segment_incremental_roas < 2.0 after 14 days",
                    "source_receipts": ["data/radar.db#cohort_profiles"],
                }
            )
            subtasks.append(
                {
                    "subtask_id": "subtask-retention-shift",
                    "skill_names": ["email-deliverability-flows"],
                    "model_tier": "balanced_worker",
                    "max_tool_calls": 6,
                    "max_tokens_budget": 16000,
                    "requires_reviewer": True,
                    "is_production_mutation": False,
                    "data_slice_pointers": ["data/radar.db"],
                    "file_touch_boundaries": {
                        "allowed_paths": ["data/offload/*"],
                        "forbidden_paths": [".agents/guardrails.yaml"],
                    },
                    "goal": f"Stage win-back/retention flow for {rec['to_segment']} with VIP exclusion check.",
                    "disproof_condition": "flow_revenue_per_recipient < 0.50 after 14 days",
                }
            )

    # 4. Paid Search <-> SEO Cannibalization
    max_pos = float(org_paid.get("seo_cannibalization_max_organic_pos", 2))
    max_comp_is = float(org_paid.get("seo_cannibalization_max_competitor_is_pct", 5.0))
    for overlap in state.get("paid_seo_overlaps", []):
        if (
            overlap.get("organic_position", 99) <= max_pos
            and overlap.get("competitor_impression_share_pct", 100) < max_comp_is
            and len(decisions) < 5
        ):
            saved = resolve_amount(overlap.get("monthly_paid_spend"), overlap.get("monthly_paid_spend_usd")) or 0.0
            decisions.append(
                {
                    "rank": len(decisions) + 1,
                    "priority": "P1",
                    "decision_title": f"Suppress cannibalizing paid term '{overlap['query']}'",
                    "rationale": (
                        f"Organic ranks #{overlap['organic_position']} with only "
                        f"{overlap['competitor_impression_share_pct']}% competitor impression share; save {format_money(saved, cur)}/mo."
                    ),
                    "dollar_impact_usd": saved,
                    "disproof_condition": "total_blended_conversions_on_term drops > 15% after 14 days",
                    "source_receipts": [overlap.get("receipt", "gsc_google_ads_join")],
                }
            )

    # 5. Paid Winners / GEO Entity Gaps / Pain Clusters -> SEO/GEO Code PR
    min_paid_conv = float(org_paid.get("paid_to_seo_min_conversions", 3))
    allowable_cac = resolve_amount(state.get("allowable_cac"), state.get("allowable_cac_usd")) or 100.0
    seo_candidates = [
        c
        for c in state.get("seo_geo_opportunities", [])
        if (
            (c.get("paid_conversions", 0) >= min_paid_conv and (resolve_amount(c.get("paid_cpa"), c.get("paid_cpa_usd")) or 9999) <= allowable_cac)
            or c.get("geo_citation_score", 10) < 3
            or c.get("pain_mentions", 0) >= 3
        )
        and not any(k in str(c.get("topic", "")).lower() for k in killed_markers)
    ]
    if seo_candidates and len(decisions) < 5:
        top = seo_candidates[0]
        est_val = resolve_amount(top.get("estimated_monthly_value"), top.get("estimated_monthly_value_usd")) or 250.0
        decisions.append(
            {
                "rank": len(decisions) + 1,
                "priority": "P1",
                "decision_title": f"Stage SEO/GEO Code PR for '{top['topic']}'",
                "rationale": "High-intent paid/pain/entity gap qualifies for answer-first FAQPage & comparison schema PR.",
                "dollar_impact_usd": float(est_val),
                "disproof_condition": "organic_impressions_increase < 10% and geo_citations == 0 after 28 days",
                "source_receipts": [top.get("receipt", "data/radar.db")],
            }
        )
        subtasks.append(
            {
                "subtask_id": "subtask-seo-geo-pr",
                "skill_names": ["aeo-entity-readiness", "seo-geo-code-pr"],
                "model_tier": "balanced_worker",
                "max_tool_calls": 6,
                "max_tokens_budget": 16000,
                "requires_reviewer": True,
                "is_production_mutation": True,
                "data_slice_pointers": ["data/radar.db"],
                "file_touch_boundaries": {
                    "allowed_paths": ["src/pages/*", "app/*", "public/robots.txt"],
                    "forbidden_paths": [".env*", "auth/*", "billing/*"],
                },
                "goal": f"Create isolated branch PR adding FAQPage JSON-LD and comparison block for {top['topic']}.",
                "disproof_condition": "geo_citation_share < 3 after 28 days",
            }
        )

    # 5b. Ad Creative Fatigue Detection -> 0-3s Hook Rotation
    if isinstance(state.get("ad_creatives"), list) and state.get("ad_creatives") and len(decisions) < 5:
        fatigue_res = detect_creative_fatigue(state["ad_creatives"], currency=cur)
        if fatigue_res.get("status") == "ok" and fatigue_res.get("fatigued_count", 0) > 0:
            fatigued_list = fatigue_res["fatigued_creatives"]
            fatigued_spend = round(sum(float(x.get("spend_usd", 0.0)) for x in fatigued_list), 2)
            lead_ad = fatigued_list[0]
            decisions.append(
                {
                    "rank": len(decisions) + 1,
                    "priority": "P1",
                    "decision_title": f"Rotate 0-3s hooks on {len(fatigued_list)} fatigued ad creative(s)",
                    "rationale": (
                        f"Lead ad '{lead_ad['ad_id']}' hit frequency {lead_ad['frequency']} with "
                        f"{lead_ad['ctr_drop_pct']}% CTR decay from peak; keep targeting intact and swap opening hooks."
                    ),
                    "dollar_impact_usd": fatigued_spend,
                    "disproof_condition": "replacement_hook_ctr <= fatigued_ad_current_ctr after 2500 impressions",
                    "source_receipts": ["calculators/creative_fatigue.py#detect_creative_fatigue"],
                }
            )
            subtasks.append(
                {
                    "subtask_id": "subtask-creative-fatigue-refresh",
                    "skill_names": ["ad-creative-angle-matrix", "display-native-ad-studio"],
                    "model_tier": "multimodal_creative",
                    "max_tool_calls": 6,
                    "max_tokens_budget": 16000,
                    "requires_reviewer": True,
                    "is_production_mutation": False,
                    "data_slice_pointers": ["data/exports/meta_ads.csv"],
                    "file_touch_boundaries": {
                        "allowed_paths": ["data/offload/*"],
                        "forbidden_paths": [".agents/guardrails.yaml"],
                    },
                    "goal": f"Stage 3 fresh 0-3s visual/copy hooks for fatigued ad {lead_ad['ad_id']} in PAUSED state.",
                    "disproof_condition": "ctr < 0.010 after 2500 impressions",
                }
            )

    # 6. Organic Social SEO / Run-With-This -> Paid Creative Seeding
    min_mult = float(org_paid.get("social_to_paid_min_median_multiplier", 2.0))
    for idx, post in enumerate(state.get("organic_social_posts", []), start=1):
        if post.get("save_or_watch_multiplier", 0.0) >= min_mult and len(decisions) < 5:
            budget_amt = resolve_amount(state.get("monthly_budget"), state.get("monthly_budget_usd")) or 0.0
            gate = evaluate_budget_gate(
                channel="paid_social",
                tracking_verified=state.get("tracking_verified", False),
                site_load_sec=state.get("site_load_sec", 2.5),
                payback_months=state.get("payback_months"),
                max_payback_months=state.get("max_payback_months", 3.0),
                monthly_conversions=state.get("monthly_conversions", 0),
                monthly_budget=budget_amt,
                currency=cur,
                min_paid_budget=state.get("min_paid_budget"),
            )
            if gate.get("unlocked"):
                test_amt = resolve_amount(post.get("test_budget"), post.get("test_budget_usd")) or 100.0
                decisions.append(
                    {
                        "rank": len(decisions) + 1,
                        "priority": "P2",
                        "decision_title": f"Seed PAUSED Spark Ad from top organic post {post['post_id']}",
                        "rationale": f"Organic winner beat 30d median by {post['save_or_watch_multiplier']}x; stage PAUSED Meta test.",
                        "dollar_impact_usd": float(test_amt),
                        "disproof_condition": "ctr < 0.008 after 2500 impressions OR conversions == 0 after 2.0x allowable_cac_usd spend",
                        "source_receipts": [post.get("receipt", "social_analytics_export")],
                    }
                )
                subtasks.append(
                    {
                        "subtask_id": f"subtask-social-to-paid-{idx}",
                        "skill_names": ["ad-creative-angle-matrix", "meta-ads-smb-audit"],
                        "model_tier": "multimodal_creative",
                        "max_tool_calls": 6,
                        "max_tokens_budget": 16000,
                        "requires_reviewer": True,
                        "is_production_mutation": False,
                        "data_slice_pointers": ["data/exports/meta_ads.csv"],
                        "file_touch_boundaries": {
                            "allowed_paths": ["data/offload/*"],
                            "forbidden_paths": [".agents/guardrails.yaml"],
                        },
                        "goal": f"Build timed storyboard & PAUSED Meta Spark Ad spec from post {post['post_id']}.",
                        "disproof_condition": "ctr < 0.008 after 2500 impressions",
                    }
                )

    if newly_killed and len(decisions) < 5:
        decisions.append(
            {
                "rank": len(decisions) + 1,
                "priority": "P1",
                "decision_title": f"Retired {len(newly_killed)} disproven experiment(s) to Killed Assumptions",
                "rationale": "Experiments breached quantitative disproof conditions and are now blocked from re-pitching.",
                "dollar_impact_usd": 0.0,
                "disproof_condition": "Explicit market shift approved by Composer",
                "source_receipts": [str(ledger_path)],
            }
        )

    for idx, d in enumerate(decisions[:5], start=1):
        d["rank"] = idx

    return _build_dual_readout(normalized_lock, circuit_breakers, decisions[:5], segment_shifts, subtasks, repo_root)


def _build_dual_readout(
    lock_status: str,
    circuit_breakers: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    segment_shifts: list[dict[str, Any]],
    subtasks: list[dict[str, Any]],
    repo_root: pathlib.Path,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    brief = {
        "brief_id": f"brief-{now.strftime('%Y%m%d-%H%M%S')}",
        "generated_at": now.isoformat(),
        "strategy_lock_status": lock_status,
        "circuit_breakers": circuit_breakers,
        "human_readout": {
            "executive_summary": (
                f"Generated {len(decisions)} prioritized Composer decision(s) with "
                f"{len(circuit_breakers)} circuit breaker alert(s); lock={lock_status}."
            ),
            "ranked_decisions": decisions[:5],
            "segment_budget_shifts": segment_shifts,
        },
        "agent_brief": {"subtasks": subtasks},
    }
    schema_path = repo_root / "schemas" / "composers_brief.schema.json"
    if schema_path.exists():
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errs = validate_json_schema(brief, schema, schema_path.parent)
        if errs:
            raise ValueError("Generated brief failed schema validation: " + "; ".join(errs))
    return brief


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate preconditions & generate Dual Readout Brief.")
    parser.add_argument("--input", required=True, help="JSON state snapshot path")
    args = parser.parse_args(argv)
    state = json.loads(pathlib.Path(args.input).read_text(encoding="utf-8"))
    out = generate_next_actions(state)
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
