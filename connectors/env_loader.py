"""Shared zero-dependency .env file loader supporting export prefixes, quotes, and inline comments."""

from __future__ import annotations

import os
import pathlib
import re

_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_dotenv_value(raw_val: str) -> str:
    val = raw_val.strip()
    if not val:
        return ""
    if val[0] in ('"', "'"):
        quote = val[0]
        chars: list[str] = []
        i = 1
        while i < len(val):
            ch = val[i]
            if ch == "\\" and quote == '"' and i + 1 < len(val):
                nxt = val[i + 1]
                if nxt == "n":
                    chars.append("\n")
                elif nxt in ('"', "\\"):
                    chars.append(nxt)
                else:
                    chars.append(ch + nxt)
                i += 2
                continue
            if ch == quote:
                return "".join(chars)
            chars.append(ch)
            i += 1
        return "".join(chars)
    # Unquoted value: strip whitespace + inline comment (`VALUE # comment`)
    val = _INLINE_COMMENT_RE.sub("", val).strip()
    return val


def load_dotenv_file(
    dotenv_path: pathlib.Path,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Load KEY=VALUE (and `export KEY=VALUE`) lines from .env without overriding existing env vars."""
    merged = dict(base_env) if base_env is not None else dict(os.environ)
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return merged

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[6:].strip()
        if "=" not in line:
            continue
        raw_key, raw_val = line.split("=", 1)
        key = raw_key.strip()
        if not _ENV_KEY_RE.match(key):
            continue
        if key not in merged:
            merged[key] = _parse_dotenv_value(raw_val)
    return merged
