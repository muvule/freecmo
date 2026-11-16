"""1,500-token tool output offloading and prefix-cache-stable prompt context ordering."""

from __future__ import annotations

import json
import math
import os
import pathlib
import re
import tempfile
from typing import Any

from calculators import validate_safe_id


DEFAULT_TOKEN_THRESHOLD = 1500
_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_ISO_TS_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def estimate_tokens(payload: Any) -> int:
    """Conservative token estimate (ceil(chars/4)) without external tokenizer dependencies."""
    text = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True)
    return max(1, math.ceil(len(text) / 4))


def _atomic_write_json(target_path: pathlib.Path, data: Any) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target_path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(tmp_name, target_path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    cols = sorted({k for r in rows if isinstance(r, dict) for k in r.keys()})
    numeric_stats: dict[str, dict[str, float]] = {}
    for col in cols:
        vals: list[float] = []
        for r in rows:
            v = r.get(col) if isinstance(r, dict) else None
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals.append(float(v))
        if vals:
            numeric_stats[col] = {
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
                "sum": round(sum(vals), 4),
            }
    return {
        "row_count": len(rows),
        "columns": cols,
        "top_5_rows": rows[:5],
        "numeric_stats": numeric_stats,
    }


def offload_if_oversized(
    subtask_id: str,
    payload: Any,
    offload_dir: pathlib.Path,
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
) -> dict[str, Any]:
    """Offload >1,500-token payloads to data/offload/<subtask_id>.json and return compact summary."""
    safe_id = validate_safe_id(subtask_id, "subtask_id")
    tokens = estimate_tokens(payload)
    if tokens <= token_threshold:
        return {
            "offloaded": False,
            "estimated_tokens": tokens,
            "payload": payload,
        }

    base_resolved = offload_dir.resolve()
    target = (base_resolved / f"{safe_id}.json").resolve()
    if not target.is_relative_to(base_resolved):
        raise ValueError("Offload path escapes offload_dir")

    _atomic_write_json(target, payload)

    if isinstance(payload, list) and all(isinstance(x, dict) for x in payload):
        summary: dict[str, Any] = _summarize_rows(payload)
    elif isinstance(payload, dict):
        if "rows" in payload and isinstance(payload["rows"], list):
            summary = _summarize_rows(payload["rows"])
            summary["top_level_keys"] = sorted(payload.keys())
        else:
            summary = {
                "top_level_keys": sorted(payload.keys()),
                "preview": {k: payload[k] for k in sorted(payload.keys())[:5]},
            }
    else:
        s = str(payload)
        summary = {"char_length": len(s), "head_preview": s[:400]}

    return {
        "offloaded": True,
        "estimated_tokens": tokens,
        "offload_pointer": str(target),
        "summary": summary,
    }


def build_ordered_context(
    static_system_rules: str,
    tool_or_skill_schemas: dict[str, Any],
    brand_truth_md: str,
    visual_dna_json: str,
    instincts_md: str,
    volatile_slice: dict[str, Any],
) -> dict[str, Any]:
    """Assemble context in strict static-to-dynamic KV-prefix-cache-friendly order."""
    sorted_schemas_str = json.dumps(
        {k: tool_or_skill_schemas[k] for k in sorted(tool_or_skill_schemas.keys())},
        indent=2,
        sort_keys=True,
    )
    static_prefix = "\n\n".join(
        [
            "=== 1. STATIC SYSTEM RULES ===\n" + static_system_rules.strip(),
            "=== 2. SORTED TOOL & SKILL SCHEMAS ===\n" + sorted_schemas_str,
            "=== 3. GOVERNANCE MEMORY (BRAND TRUTH / VISUAL DNA / INSTINCTS) ===\n"
            + brand_truth_md.strip()
            + "\n\n"
            + visual_dna_json.strip()
            + "\n\n"
            + instincts_md.strip(),
        ]
    )

    if _UUID_RE.search(static_prefix) or _ISO_TS_RE.search(static_prefix):
        raise ValueError("Volatile UUID or ISO timestamp detected in static prompt prefix")

    tail = "=== 4. VOLATILE SUBTASK SLICE ===\n" + json.dumps(volatile_slice, indent=2, sort_keys=True)
    return {
        "prefix_segments": static_prefix,
        "volatile_tail": tail,
        "full_prompt": static_prefix + "\n\n" + tail,
    }
