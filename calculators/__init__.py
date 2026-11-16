"""Shared deterministic primitives for FreeCMO calculators, schemas, and YAML."""

from __future__ import annotations

import json
import math
import pathlib
import re
from typing import Any


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_safe_id(value: str, label: str = "id") -> str:
    """Ensure identifier is safe against path traversal and injection."""
    if not isinstance(value, str) or not SAFE_ID_RE.match(value):
        raise ValueError(f"Unsafe or invalid {label}: {value!r}")
    return value


def is_missing(val: Any) -> bool:
    """Return True if a value is None, empty string, 'unknown', or non-finite."""
    if val is None:
        return True
    if isinstance(val, str) and val.strip().lower() in ("", "unknown", "none", "null", "na", "n/a"):
        return True
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return True
    return False


def to_float(val: Any) -> float | None:
    """Convert to finite float or return None if missing/invalid."""
    if is_missing(val) or isinstance(val, bool):
        return None
    try:
        num = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num


def unknown_result(
    missing_inputs: list[str],
    formula_trace: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standard deterministic envelope when required inputs are absent or division by zero occurs."""
    out: dict[str, Any] = {
        "status": "unknown",
        "value": "unknown",
        "missing_inputs": sorted(set(missing_inputs)),
        "formula_trace": formula_trace,
    }
    if extra:
        out.update(extra)
    return out


def ok_result(
    metrics: dict[str, Any],
    formula_trace: str,
    status: str = "ok",
) -> dict[str, Any]:
    """Standard deterministic envelope for computed metrics."""
    out = {"status": status, "formula_trace": formula_trace}
    out.update(metrics)
    return out


# ---------------------------------------------------------------------------
# Restricted Safe YAML Parser (pure stdlib, rejects tags/anchors/aliases)
# ---------------------------------------------------------------------------

def _strip_yaml_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\" and in_double:
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if idx == 0 or line[idx - 1].isspace():
                return line[:idx].rstrip()
    return line.rstrip()


def _parse_yaml_scalar(token: str) -> Any:
    s = token.strip()
    if s == "" or s in ("null", "Null", "NULL", "~"):
        return None
    if s.startswith("!!") or (s.startswith("!") and not s.startswith("!=")):
        raise ValueError(f"Unsafe YAML tag disallowed: {s!r}")
    if (s.startswith("&") or s.startswith("*")) and len(s) > 1:
        raise ValueError(f"YAML anchors/aliases disallowed: {s!r}")
    if (s.startswith('"') and s.endswith('"') and len(s) >= 2) or (
        s.startswith("'") and s.endswith("'") and len(s) >= 2
    ):
        if s.startswith('"'):
            return bytes(s[1:-1], "utf-8").decode("unicode_escape")
        return s[1:-1].replace("''", "'")
    if s == "[]":
        return []
    if s == "{}":
        return {}
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [_parse_yaml_scalar(part) for part in _split_inline_csv(inner)]
    if s in ("true", "True", "TRUE", "yes", "Yes", "YES"):
        return True
    if s in ("false", "False", "FALSE", "no", "No", "NO"):
        return False
    if re.fullmatch(r"-?[0-9]+", s):
        return int(s)
    if re.fullmatch(r"-?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", s):
        return float(s)
    return s


def _split_inline_csv(text: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    in_s = False
    in_d = False
    for ch in text:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "," and not in_s and not in_d:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur or text.endswith(","):
        parts.append("".join(cur).strip())
    return parts


def _split_key_val(text: str) -> tuple[str, str] | None:
    in_s = False
    in_d = False
    for i, ch in enumerate(text):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == ":" and not in_s and not in_d:
            if i + 1 == len(text) or text[i + 1].isspace():
                key = text[:i].strip().strip('"').strip("'")
                val = text[i + 1 :].strip()
                return key, val
    return None


def safe_parse_yaml(text: str) -> Any:
    """Parse a safe subset of YAML (mappings, lists, scalars) with pure stdlib."""
    raw_lines = text.splitlines()
    tokens: list[tuple[int, str]] = []
    for raw in raw_lines:
        cleaned = _strip_yaml_comment(raw)
        if not cleaned.strip():
            continue
        if cleaned.strip() in ("---", "..."):
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        if "\t" in cleaned[:indent]:
            raise ValueError("Tabs are not allowed in YAML indentation")
        tokens.append((indent, cleaned.strip()))

    if not tokens:
        return {}

    def parse_block(idx: int, min_indent: int) -> tuple[Any, int]:
        indent, content = tokens[idx]
        if content.startswith("- ") or content == "-":
            return parse_list(idx, indent)
        kv = _split_key_val(content)
        if kv is not None:
            return parse_map(idx, indent)
        return _parse_yaml_scalar(content), idx + 1

    def parse_list(idx: int, list_indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while idx < len(tokens):
            indent, content = tokens[idx]
            if indent < list_indent:
                break
            if indent > list_indent:
                raise ValueError(f"Unexpected indentation in YAML list near {content!r}")
            if not (content.startswith("- ") or content == "-"):
                break
            rest = content[1:].strip() if content == "-" else content[2:].strip()
            if not rest:
                idx += 1
                if idx < len(tokens) and tokens[idx][0] > list_indent:
                    val, idx = parse_block(idx, tokens[idx][0])
                    items.append(val)
                else:
                    items.append(None)
                continue
            kv = _split_key_val(rest)
            if kv is not None:
                key, val_str = kv
                item_map: dict[str, Any] = {}
                if val_str == "":
                    idx += 1
                    if idx < len(tokens) and tokens[idx][0] > list_indent + 1:
                        item_map[key], idx = parse_block(idx, tokens[idx][0])
                    else:
                        item_map[key] = None
                else:
                    item_map[key] = _parse_yaml_scalar(val_str)
                    idx += 1
                if idx < len(tokens) and tokens[idx][0] > list_indent:
                    child_indent = tokens[idx][0]
                    if _split_key_val(tokens[idx][1]) is not None:
                        extra_map, idx = parse_map(idx, child_indent)
                        item_map.update(extra_map)
                items.append(item_map)
            else:
                items.append(_parse_yaml_scalar(rest))
                idx += 1
        return items, idx

    def parse_map(idx: int, map_indent: int) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {}
        while idx < len(tokens):
            indent, content = tokens[idx]
            if indent < map_indent:
                break
            if indent > map_indent:
                raise ValueError(f"Unexpected indentation in YAML map near {content!r}")
            if content.startswith("- ") or content == "-":
                break
            kv = _split_key_val(content)
            if kv is None:
                raise ValueError(f"Expected key: value in YAML map near {content!r}")
            key, val_str = kv
            if val_str == "":
                idx += 1
                if idx < len(tokens) and tokens[idx][0] > map_indent:
                    mapping[key], idx = parse_block(idx, tokens[idx][0])
                else:
                    mapping[key] = None
            elif val_str in ("|", ">"):
                block_lines: list[str] = []
                idx += 1
                if idx < len(tokens) and tokens[idx][0] > map_indent:
                    block_indent = tokens[idx][0]
                    while idx < len(tokens) and tokens[idx][0] >= block_indent:
                        block_lines.append(tokens[idx][1])
                        idx += 1
                joiner = "\n" if val_str == "|" else " "
                mapping[key] = joiner.join(block_lines)
            else:
                mapping[key] = _parse_yaml_scalar(val_str)
                idx += 1
        return mapping, idx

    parsed, next_idx = parse_block(0, tokens[0][0])
    if next_idx != len(tokens):
        raise ValueError(f"Trailing unparsed YAML near token {next_idx}")
    return parsed


# ---------------------------------------------------------------------------
# Pure-Stdlib Draft 2020-12 JSON Schema Validator
# ---------------------------------------------------------------------------

def _matches_json_type(val: Any, expected_type: str) -> bool:
    if expected_type == "null":
        return val is None
    if expected_type == "boolean":
        return isinstance(val, bool)
    if expected_type == "integer":
        return isinstance(val, int) and not isinstance(val, bool)
    if expected_type == "number":
        return isinstance(val, (int, float)) and not isinstance(val, bool)
    if expected_type == "string":
        return isinstance(val, str)
    if expected_type == "array":
        return isinstance(val, list)
    if expected_type == "object":
        return isinstance(val, dict)
    return True


def _resolve_ref(ref: str, root_schema: dict[str, Any], schema_dir: pathlib.Path | None) -> tuple[dict[str, Any], dict[str, Any], pathlib.Path | None]:
    if ref.startswith("#/"):
        cur: Any = root_schema
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            cur = cur[part]
        return cur, root_schema, schema_dir
    if schema_dir is not None and not ref.startswith("http"):
        file_part, _, frag = ref.partition("#")
        target_path = (schema_dir / file_part).resolve()
        if not target_path.is_relative_to(schema_dir.resolve()):
            raise ValueError(f"Schema $ref escapes schema directory: {ref}")
        with open(target_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if frag:
            sub, _, _ = _resolve_ref("#" + frag, loaded, target_path.parent)
            return sub, loaded, target_path.parent
        return loaded, loaded, target_path.parent
    raise ValueError(f"Unsupported $ref: {ref}")


def validate_json_schema(
    instance: Any,
    schema: dict[str, Any],
    schema_dir: pathlib.Path | None = None,
    _root: dict[str, Any] | None = None,
    _path: str = "$",
) -> list[str]:
    """Validate instance against a Draft 2020-12 JSON schema subset. Returns list of errors."""
    root = _root if _root is not None else schema
    errors: list[str] = []

    if "$ref" in schema:
        sub_schema, sub_root, sub_dir = _resolve_ref(schema["$ref"], root, schema_dir)
        return validate_json_schema(instance, sub_schema, sub_dir, sub_root, _path)

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{_path}: expected const {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{_path}: value {instance!r} not in enum {schema['enum']!r}")

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_matches_json_type(instance, t) for t in types):
            errors.append(f"{_path}: expected type {types}, got {type(instance).__name__}")
            return errors

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{_path}: length {len(instance)} < minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{_path}: length {len(instance)} > maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{_path}: string {instance!r} does not match pattern {schema['pattern']!r}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{_path}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{_path}: {instance} > maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{_path}: array len {len(instance)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{_path}: array len {len(instance)} > maxItems {schema['maxItems']}")
        if "items" in schema and isinstance(schema["items"], dict):
            for idx, item in enumerate(instance):
                errors.extend(
                    validate_json_schema(item, schema["items"], schema_dir, root, f"{_path}[{idx}]")
                )

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{_path}: missing required field {req!r}")
        props = schema.get("properties", {})
        add_props = schema.get("additionalProperties", True)
        for key, val in instance.items():
            if key in props:
                errors.extend(
                    validate_json_schema(val, props[key], schema_dir, root, f"{_path}.{key}")
                )
            elif add_props is False:
                errors.append(f"{_path}: additional property {key!r} is not allowed")
            elif isinstance(add_props, dict):
                errors.extend(
                    validate_json_schema(val, add_props, schema_dir, root, f"{_path}.{key}")
                )

    for sub in schema.get("allOf", []):
        errors.extend(validate_json_schema(instance, sub, schema_dir, root, _path))

    if "anyOf" in schema:
        if not any(not validate_json_schema(instance, sub, schema_dir, root, _path) for sub in schema["anyOf"]):
            errors.append(f"{_path}: failed anyOf constraint")

    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not validate_json_schema(instance, sub, schema_dir, root, _path))
        if matches != 1:
            errors.append(f"{_path}: expected exactly 1 oneOf match, got {matches}")

    return errors


# ---------------------------------------------------------------------------
# AST / Token-Whitelisted Condition Evaluator (Zero eval())
# ---------------------------------------------------------------------------

_CMP_OPS = {
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _resolve_operand(token: str, metrics: dict[str, Any]) -> float | None:
    t = token.strip()
    if re.fullmatch(r"-?(?:[0-9]+(?:\.[0-9]+)?)", t):
        return float(t)
    m_mult = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)x\s+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+spend)?", t)
    if m_mult:
        factor = float(m_mult.group(1))
        var_name = m_mult.group(2)
        base = to_float(metrics.get(var_name))
        if base is None:
            return None
        return factor * base
    if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", t):
        return to_float(metrics.get(t))
    raise ValueError(f"Disallowed token in condition expression: {token!r}")


def _eval_atomic_clause(clause: str, metrics: dict[str, Any]) -> tuple[bool | str, list[str]]:
    c = clause.strip()
    if not c:
        raise ValueError("Empty condition clause")
    # Reject dangerous syntax immediately
    if any(bad in c for bad in ("(", ")", "[", "]", ";", "__", "import", "lambda", "eval", "exec")):
        raise ValueError(f"Disallowed syntax in condition clause: {c!r}")

    # Pattern: "after_days >= 14" or "after_impressions >= 2500"
    m_after_var = re.fullmatch(r"after_(days|impressions)\s*(>=|>|==)\s*([0-9]+(?:\.[0-9]+)?)", c)
    if m_after_var:
        metric_key = m_after_var.group(1)
        op = m_after_var.group(2)
        threshold = float(m_after_var.group(3))
        observed = to_float(metrics.get(metric_key))
        if observed is None:
            return "unknown", [metric_key]
        return _CMP_OPS[op](observed, threshold), []

    # Pattern: "after 2500 impressions" or "after 14 days"
    m_after = re.fullmatch(r"after\s+([0-9]+(?:\.[0-9]+)?)\s+(days|impressions)", c, flags=re.IGNORECASE)
    if m_after:
        threshold = float(m_after.group(1))
        metric_key = m_after.group(2).lower()
        observed = to_float(metrics.get(metric_key))
        if observed is None:
            return "unknown", [metric_key]
        return observed >= threshold, []

    # Pattern: "after 2.0x allowable_cac_usd spend"
    m_after_mult = re.fullmatch(
        r"after\s+([0-9]+(?:\.[0-9]+)?)x\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+spend",
        c,
        flags=re.IGNORECASE,
    )
    if m_after_mult:
        factor = float(m_after_mult.group(1))
        var_name = m_after_mult.group(2)
        base = to_float(metrics.get(var_name))
        spend = to_float(metrics.get("spend"))
        missing: list[str] = []
        if base is None:
            missing.append(var_name)
        if spend is None:
            missing.append("spend")
        if missing:
            return "unknown", missing
        assert base is not None and spend is not None
        return spend >= (factor * base), []

    # General comparison: "<lhs> <op> <rhs>"
    m_cmp = re.fullmatch(r"(.+?)\s*(<=|>=|==|!=|<|>)\s*(.+)", c)
    if not m_cmp:
        raise ValueError(f"Unrecognized condition clause: {c!r}")
    lhs_tok, op, rhs_tok = m_cmp.group(1).strip(), m_cmp.group(2), m_cmp.group(3).strip()
    lhs_val = _resolve_operand(lhs_tok, metrics)
    rhs_val = _resolve_operand(rhs_tok, metrics)
    missing = []
    if lhs_val is None:
        missing.append(lhs_tok)
    if rhs_val is None:
        missing.append(rhs_tok)
    if missing:
        return "unknown", missing
    assert lhs_val is not None and rhs_val is not None
    return _CMP_OPS[op](lhs_val, rhs_val), []


def safe_eval_condition(condition: str, metrics: dict[str, Any]) -> dict[str, Any]:
    """Safely evaluate compound AND/OR disproof or stop-loss conditions without eval().

    Supports patterns such as:
    - "ctr < 0.005 after 2500 impressions OR conversions == 0 after 2.0x allowable_cac_usd spend"
    - "roas < 1.0 after_days >= 14 and spend >= 150"
    """
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("Condition must be a non-empty string")

    or_branches = re.split(r"\s+\bOR\b\s+", condition.strip(), flags=re.IGNORECASE)
    branch_results: list[bool | str] = []
    all_missing: list[str] = []

    for branch in or_branches:
        explicit_parts = re.split(r"\s+\bAND\b\s+", branch.strip(), flags=re.IGNORECASE)
        and_clauses: list[str] = []
        for part in explicit_parts:
            sub_clauses = re.split(
                r"\s+(?=after(?:_days|_impressions)?\b)",
                part.strip(),
                flags=re.IGNORECASE,
            )
            and_clauses.extend(sc.strip() for sc in sub_clauses if sc.strip())
        clause_vals: list[bool | str] = []
        for cl in and_clauses:
            res, missing = _eval_atomic_clause(cl, metrics)
            clause_vals.append(res)
            all_missing.extend(missing)
        if False in clause_vals:
            branch_results.append(False)
        elif "unknown" in clause_vals:
            branch_results.append("unknown")
        else:
            branch_results.append(True)

    if True in branch_results:
        triggered: bool | str = True
    elif "unknown" in branch_results:
        triggered = "unknown"
    else:
        triggered = False

    return {
        "triggered": triggered,
        "missing_inputs": sorted(set(all_missing)),
        "condition": condition,
    }
