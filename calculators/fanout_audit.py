"""Deterministic Google AI Mode Query Fan-Out auditor and readiness scorer."""

from __future__ import annotations

import argparse
import html.parser
import json
import pathlib
import re
import sys
from typing import Any

_REPO_ROOT = str(pathlib.Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from calculators import to_float, unknown_result


def generate_query_fanout_subquestions(
    primary_query: str,
    brand_category: str = "solution",
    target_icp: str = "buyers",
) -> list[dict[str, str]]:
    """Deterministically build 6 Google AI Mode (Gemini 4 Hydrogen) sub-question intents."""
    query = primary_query.strip()
    return [
        {
            "intent": "direct_definition",
            "subquestion": f"What is {query} and who is it best for?",
            "recommended_html_pattern": "definition_answer_first_block",
        },
        {
            "intent": "comparison_tradeoffs",
            "subquestion": f"How does {query} compare to top alternatives in terms of trade-offs?",
            "recommended_html_pattern": "comparison_table_and_verdict",
        },
        {
            "intent": "pricing_tco",
            "subquestion": f"What is the total cost of ownership, pricing tiers, and hidden fees for {query}?",
            "recommended_html_pattern": "pricing_breakdown_table",
        },
        {
            "intent": "implementation_effort",
            "subquestion": f"How long does it take to implement and onboard {query} for {target_icp}?",
            "recommended_html_pattern": "step_by_step_timeline_list",
        },
        {
            "intent": "edge_cases_limitations",
            "subquestion": f"What are the limitations, missing features, and deal-breakers of {query}?",
            "recommended_html_pattern": "pros_cons_limitations_callout",
        },
        {
            "intent": "proof_verification",
            "subquestion": f"What verified ROI data, customer benchmarks, and third-party reviews exist for {query}?",
            "recommended_html_pattern": "metric_cards_and_faq_schema",
        },
    ]


class _HeadingAndParagraphHTMLParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sections: list[tuple[str, str]] = []  # (heading_text, next_p_text)
        self.in_heading = False
        self.heading_tag = ""
        self.current_heading_parts: list[str] = []
        self.in_p = False
        self.current_p_parts: list[str] = []
        self.awaiting_p = False
        self.last_heading = ""
        self.has_table = False
        self.has_th = False
        self.in_script = False
        self.script_type = ""
        self.script_content: list[str] = []
        self.ld_json_blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        if tag_lower in ("h2", "h3"):
            if self.awaiting_p and self.last_heading:
                self.sections.append((self.last_heading, ""))
                self.awaiting_p = False
            self.in_heading = True
            self.heading_tag = tag_lower
            self.current_heading_parts = []
        elif tag_lower == "p" and self.awaiting_p:
            self.in_p = True
            self.current_p_parts = []
        elif tag_lower == "table":
            self.has_table = True
        elif tag_lower == "th":
            self.has_th = True
        elif tag_lower == "script":
            if attr_dict.get("type", "").lower() == "application/ld+json":
                self.in_script = True
                self.script_content = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in ("h2", "h3") and self.in_heading:
            self.in_heading = False
            self.last_heading = " ".join("".join(self.current_heading_parts).split())
            self.awaiting_p = True
        elif tag_lower == "p" and self.in_p:
            self.in_p = False
            p_text = " ".join("".join(self.current_p_parts).split())
            if self.awaiting_p and self.last_heading:
                self.sections.append((self.last_heading, p_text))
                self.awaiting_p = False
                self.last_heading = ""
        elif tag_lower == "script" and self.in_script:
            self.in_script = False
            self.ld_json_blocks.append("".join(self.script_content))

    def handle_data(self, data: str) -> None:
        if self.in_heading:
            self.current_heading_parts.append(data)
        elif self.in_p:
            self.current_p_parts.append(data)
        elif self.in_script:
            self.script_content.append(data)

    def close(self) -> None:
        super().close()
        if self.awaiting_p and self.last_heading:
            self.sections.append((self.last_heading, ""))
            self.awaiting_p = False


_QUESTION_PREFIXES = (
    "what ",
    "how ",
    "why ",
    "when ",
    "which ",
    "who ",
    "can ",
    "should ",
    "is ",
    "are ",
    "compare ",
)


def _is_question_heading(text: str) -> bool:
    s = text.strip().lower()
    if not s:
        return False
    if s.endswith("?"):
        return True
    if any(s.startswith(p) for p in _QUESTION_PREFIXES):
        return True
    if " vs " in s or s.startswith("vs ") or s.endswith(" vs"):
        return True
    return False


def _parse_robots_txt_disallow_all(robots_txt: str) -> list[str]:
    """Parse robots.txt per RFC 9309 group rules to detect if AI crawlers have root Disallow: /."""
    ai_crawlers = {"google-extended", "gptbot", "claudebot", "perplexitybot"}
    lines = robots_txt.splitlines()
    current_agents: list[str] = []
    saw_rule_in_group = False
    disallowed_agents: set[str] = set()
    allowed_agents: set[str] = set()

    for line in lines:
        cleaned = line.split("#")[0].strip()
        if not cleaned:
            if saw_rule_in_group:
                current_agents = []
                saw_rule_in_group = False
            continue
        if ":" not in cleaned:
            continue
        directive, val = cleaned.split(":", 1)
        directive = directive.strip().lower()
        val = val.strip()

        if directive == "user-agent":
            if saw_rule_in_group:
                current_agents = []
                saw_rule_in_group = False
            current_agents.append(val.lower())
        elif directive == "disallow":
            saw_rule_in_group = True
            if val == "/":
                for ag in current_agents:
                    if ag in ai_crawlers or ag == "*":
                        disallowed_agents.add(ag)
            elif val == "":
                for ag in current_agents:
                    if ag in ai_crawlers or ag == "*":
                        allowed_agents.add(ag)
        elif directive == "allow":
            saw_rule_in_group = True
            if val == "/":
                for ag in current_agents:
                    if ag in ai_crawlers or ag == "*":
                        allowed_agents.add(ag)
        elif directive in ("sitemap", "crawl-delay"):
            pass

    blocked: list[str] = []
    has_star_root_disallow = ("*" in disallowed_agents) and ("*" not in allowed_agents)

    for bot in ("Google-Extended", "GPTBot", "ClaudeBot", "PerplexityBot"):
        bot_lower = bot.lower()
        if bot_lower in allowed_agents:
            continue
        if bot_lower in disallowed_agents or has_star_root_disallow:
            blocked.append(bot)

    return blocked


def audit_page_fanout_readiness(
    content: Any,
    primary_query: str = "",
    content_format: str = "auto",
    robots_txt: str | None = None,
) -> dict[str, Any]:
    """Score page readiness for Google AI Search / Query Fan-Out indexing."""
    trace = (
        "question_pts = 25 if question_headings_count >= 3 else (12 if question_headings_count >= 1 else 0); "
        "answer_pts = 25 if answer_first_sections_count >= 2 else (12 if answer_first_sections_count == 1 else 0); "
        "table_pts = 25 if has_comparison_table else 0; "
        "schema_pts = 25 if has_structured_jsonld else 0; "
        "penalty = 30 if blocked_ai_crawlers else 0; "
        "score = max(0, min(100, question_pts + answer_pts + table_pts + schema_pts - penalty))"
    )

    if content is None or content == "" or (isinstance(content, str) and content.strip().lower() in ("", "unknown")):
        return unknown_result(["content"], trace)

    text = str(content)

    is_html = False
    if content_format == "html":
        is_html = True
    elif content_format == "markdown" or content_format == "md":
        is_html = False
    else:  # auto
        if "<html" in text.lower() or "<h2" in text.lower() or "<p>" in text.lower() or "<div" in text.lower():
            is_html = True
        else:
            is_html = False

    question_headings_count = 0
    answer_first_sections_count = 0
    has_comparison_table = False
    has_structured_jsonld = False

    schema_types = ("FAQPage", "Product", "SoftwareApplication", "Article", "LocalBusiness", "HowTo")

    if is_html:
        parser = _HeadingAndParagraphHTMLParser()
        parser.feed(text)
        parser.close()

        has_comparison_table = parser.has_table and parser.has_th
        for h, p in parser.sections:
            if _is_question_heading(h):
                question_headings_count += 1
            words = [w for w in p.split() if w]
            if 20 <= len(words) <= 80:
                answer_first_sections_count += 1

        for block in parser.ld_json_blocks:
            for st in schema_types:
                if f'"{st}"' in block or f"'{st}'" in block:
                    has_structured_jsonld = True
                    break
            if has_structured_jsonld:
                break

        # Also regex check fallback in case raw script tag wasn't caught by parser
        if not has_structured_jsonld:
            for st in schema_types:
                if re.search(rf'application/ld\+json[^>]*>.*?{st}', text, re.DOTALL | re.IGNORECASE):
                    has_structured_jsonld = True
                    break

        if not has_comparison_table and "<table" in text.lower() and "<th" in text.lower():
            has_comparison_table = True

    else:
        # Markdown parsing
        lines = text.splitlines()
        headings_with_para: list[tuple[str, str]] = []
        i = 0
        n = len(lines)
        while i < n:
            line = lines[i].strip()
            if line.startswith("## ") or line.startswith("### "):
                h_text = line.lstrip("#").strip()
                # Find subsequent paragraph
                j = i + 1
                para_lines: list[str] = []
                while j < n and not lines[j].strip():
                    j += 1
                while j < n and lines[j].strip() and not lines[j].strip().startswith("#"):
                    para_lines.append(lines[j].strip())
                    j += 1
                p_text = " ".join(para_lines)
                headings_with_para.append((h_text, p_text))
                i = j
            else:
                i += 1

        for h, p in headings_with_para:
            if _is_question_heading(h):
                question_headings_count += 1
            words = [w for w in p.split() if w]
            if 20 <= len(words) <= 80:
                answer_first_sections_count += 1

        # Check for comparison table
        if ("|---" in text or "| ---" in text or "|:---" in text or "| :---" in text) or ("<table" in text.lower() and "<th" in text.lower()):
            has_comparison_table = True

        # Check for JSON-LD in markdown
        for st in schema_types:
            if st in text and ("application/ld+json" in text or "@context" in text):
                has_structured_jsonld = True
                break

    blocked_ai_crawlers: list[str] = []
    if robots_txt:
        blocked_ai_crawlers = _parse_robots_txt_disallow_all(robots_txt)

    question_pts = 25 if question_headings_count >= 3 else (12 if question_headings_count >= 1 else 0)
    answer_pts = 25 if answer_first_sections_count >= 2 else (12 if answer_first_sections_count == 1 else 0)
    table_pts = 25 if has_comparison_table else 0
    schema_pts = 25 if has_structured_jsonld else 0
    penalty = 30 if blocked_ai_crawlers else 0

    score = max(0, min(100, question_pts + answer_pts + table_pts + schema_pts - penalty))
    grade = "ready" if score >= 75 else ("needs_enrichment" if score >= 45 else "low_visibility")

    missing_elements: list[str] = []
    if question_headings_count < 3:
        missing_elements.append("add_question_headings_h2_h3")
    if answer_first_sections_count < 2:
        missing_elements.append("add_direct_20_to_80_word_answer_blocks")
    if not has_comparison_table:
        missing_elements.append("add_comparison_table")
    if not has_structured_jsonld:
        missing_elements.append("add_structured_jsonld_schema")
    if blocked_ai_crawlers:
        missing_elements.append("unblock_ai_crawlers_in_robots_txt")

    fanout_subquestions = (
        generate_query_fanout_subquestions(primary_query) if primary_query.strip() else []
    )

    return {
        "status": "ok",
        "fanout_readiness_score": score,
        "grade": grade,
        "question_headings_count": question_headings_count,
        "answer_first_sections_count": answer_first_sections_count,
        "has_comparison_table": has_comparison_table,
        "has_structured_jsonld": has_structured_jsonld,
        "blocked_ai_crawlers": blocked_ai_crawlers,
        "missing_elements": missing_elements,
        "fanout_subquestions": fanout_subquestions,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit webpage/markdown readiness for Google AI Mode Query Fan-Out."
    )
    parser.add_argument("--input", help="JSON input file path with content and optional primary_query, robots_txt")
    parser.add_argument("--file", help="HTML or Markdown file path to audit")
    parser.add_argument("--primary-query", default="", help="Primary search query to generate fan-out subquestions for")
    parser.add_argument("--format", default="auto", choices=["auto", "html", "markdown", "md"], help="Content format")
    parser.add_argument("--robots-file", help="Optional robots.txt file path to check crawler blocking")
    args = parser.parse_args(argv)

    content = ""
    query = args.primary_query
    fmt = args.format
    robots_txt = None

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            payload = json.load(f)
        out = audit_page_fanout_readiness(**payload)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.robots_file:
        robots_txt = pathlib.Path(args.robots_file).read_text(encoding="utf-8")

    if args.file:
        content = pathlib.Path(args.file).read_text(encoding="utf-8")
        out = audit_page_fanout_readiness(
            content=content,
            primary_query=query,
            content_format=fmt,
            robots_txt=robots_txt,
        )
    else:
        out = audit_page_fanout_readiness(
            content="",
            primary_query=query,
            content_format=fmt,
            robots_txt=robots_txt,
        )

    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
