"""Unified zero-dependency LLM router for Frontier, OpenRouter/Budget APIs, and Local LLMs.

Supports:
- Local BYO-Machine: Ollama (127.0.0.1:11434), LM Studio (127.0.0.1:1234), vLLM / llama.cpp
- Cheaper / Multi-Model Aggregators: OpenRouter, DeepSeek, Groq, Together AI
- Frontier Native APIs: OpenAI, Anthropic Messages API, Google Gemini generateContent API
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from scripts.geo_benchmark import validate_endpoint_url


MODEL_TIERS = ("fast_decider", "balanced_worker", "deep_orchestrator", "multimodal_creative")

PROVIDER_DEFAULTS: dict[str, dict[str, Any]] = {
    "openai": {
        "protocol": "openai_chat",
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "gpt-4o-mini",
            "balanced_worker": "gpt-4o-mini",
            "deep_orchestrator": "gpt-4o",
            "multimodal_creative": "gpt-4o",
        },
    },
    "anthropic": {
        "protocol": "anthropic_messages",
        "base_url": "https://api.anthropic.com/v1",
        "key_env": "ANTHROPIC_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "claude-3-5-haiku-latest",
            "balanced_worker": "claude-3-5-sonnet-latest",
            "deep_orchestrator": "claude-3-5-sonnet-latest",
            "multimodal_creative": "claude-3-5-sonnet-latest",
        },
    },
    "gemini": {
        "protocol": "gemini_generate",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_env": "GEMINI_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "gemini-2.5-flash",
            "balanced_worker": "gemini-2.5-flash",
            "deep_orchestrator": "gemini-2.5-pro",
            "multimodal_creative": "gemini-2.5-flash",
        },
    },
    "openrouter": {
        "protocol": "openai_chat",
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "deepseek/deepseek-chat",
            "balanced_worker": "deepseek/deepseek-chat",
            "deep_orchestrator": "deepseek/deepseek-r1",
            "multimodal_creative": "google/gemini-2.5-flash",
        },
    },
    "deepseek": {
        "protocol": "openai_chat",
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "deepseek-chat",
            "balanced_worker": "deepseek-chat",
            "deep_orchestrator": "deepseek-reasoner",
            "multimodal_creative": "deepseek-chat",
        },
    },
    "groq": {
        "protocol": "openai_chat",
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "llama-3.1-8b-instant",
            "balanced_worker": "llama-3.3-70b-versatile",
            "deep_orchestrator": "llama-3.3-70b-versatile",
            "multimodal_creative": "llama-3.3-70b-versatile",
        },
    },
    "together": {
        "protocol": "openai_chat",
        "base_url": "https://api.together.xyz/v1",
        "key_env": "TOGETHER_API_KEY",
        "requires_key": True,
        "models": {
            "fast_decider": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "balanced_worker": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
            "deep_orchestrator": "deepseek-ai/DeepSeek-R1",
            "multimodal_creative": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        },
    },
    "ollama": {
        "protocol": "openai_chat",
        "base_url": "http://127.0.0.1:11434/v1",
        "key_env": "OLLAMA_API_KEY",
        "requires_key": False,
        "models": {
            "fast_decider": "qwen2.5:7b",
            "balanced_worker": "qwen2.5:14b",
            "deep_orchestrator": "qwen2.5:14b",
            "multimodal_creative": "llava:13b",
        },
    },
    "lmstudio": {
        "protocol": "openai_chat",
        "base_url": "http://127.0.0.1:1234/v1",
        "key_env": "LMSTUDIO_API_KEY",
        "requires_key": False,
        "models": {
            "fast_decider": "local-model",
            "balanced_worker": "local-model",
            "deep_orchestrator": "local-model",
            "multimodal_creative": "local-model",
        },
    },
}

TIER_ENV_OVERRIDES = {
    "fast_decider": "CMO_FAST_MODEL",
    "balanced_worker": "CMO_WORKER_MODEL",
    "deep_orchestrator": "CMO_ORCHESTRATOR_MODEL",
    "multimodal_creative": "CMO_MULTIMODAL_MODEL",
}

LLMTransportFn = Callable[[urllib.request.Request], dict[str, Any]]


def _default_llm_transport(req: urllib.request.Request) -> dict[str, Any]:
    validate_endpoint_url(req.full_url)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw.strip():
                raise RuntimeError("LLM API returned empty response body")
            return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM API returned invalid JSON: {exc.msg}") from None
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"LLM API HTTP {exc.code} from {urllib.parse.urlparse(req.full_url).hostname}") from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM API connection failed: {exc.reason}") from None


def resolve_llm_route(
    model_tier: str = "balanced_worker",
    provider_override: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Resolve provider, base_url, protocol, and model name for the requested tier."""
    if model_tier not in MODEL_TIERS:
        raise ValueError(f"Unknown model_tier {model_tier!r}; expected one of {MODEL_TIERS}")
    e = env if env is not None else dict(os.environ)

    requested = (provider_override or e.get("CMO_LLM_PROVIDER") or "auto").strip().lower()
    if requested == "auto":
        for candidate in ("openrouter", "anthropic", "openai", "gemini", "deepseek", "groq", "together"):
            key_name = PROVIDER_DEFAULTS[candidate]["key_env"]
            if (e.get(key_name) or "").strip():
                requested = candidate
                break
        else:
            has_lmstudio = bool((e.get("LMSTUDIO_BASE_URL") or "").strip() or (e.get("LMSTUDIO_MODEL") or "").strip())
            has_ollama = bool((e.get("OLLAMA_BASE_URL") or "").strip() or (e.get("OLLAMA_MODEL") or "").strip())
            requested = "lmstudio" if (has_lmstudio and not has_ollama) else "ollama"

    if requested not in PROVIDER_DEFAULTS:
        raise ValueError(f"Unsupported LLM provider {requested!r}; supported={sorted(PROVIDER_DEFAULTS)}")

    spec = PROVIDER_DEFAULTS[requested]
    base_url_env = f"{requested.upper()}_BASE_URL"
    base_url = (e.get(base_url_env) or spec["base_url"]).rstrip("/")
    validate_endpoint_url(base_url)

    model_env = f"{requested.upper()}_MODEL"
    tier_override = (e.get(TIER_ENV_OVERRIDES[model_tier]) or "").strip()
    provider_model_override = (e.get(model_env) or "").strip()
    model = tier_override or provider_model_override or spec["models"][model_tier]

    api_key = (e.get(spec["key_env"]) or "").strip()
    return {
        "provider": requested,
        "protocol": spec["protocol"],
        "base_url": base_url,
        "model": model,
        "model_tier": model_tier,
        "requires_key": spec["requires_key"],
        "key_configured": bool(api_key) or not spec["requires_key"],
    }


def complete_prompt(
    system_prompt: str,
    user_prompt: str,
    model_tier: str = "balanced_worker",
    provider_override: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    env: dict[str, str] | None = None,
    transport: LLMTransportFn | None = None,
) -> dict[str, Any]:
    """Execute a completion call across OpenAI-compatible, Anthropic, Gemini, or local Ollama/LM Studio."""
    e = env if env is not None else dict(os.environ)
    tx = transport or _default_llm_transport
    route = resolve_llm_route(model_tier=model_tier, provider_override=provider_override, env=e)
    provider = route["provider"]
    spec = PROVIDER_DEFAULTS[provider]
    api_key = (e.get(spec["key_env"]) or "").strip()

    if route["requires_key"] and not api_key:
        raise ValueError(
            f"Missing API key {spec['key_env']} for provider {provider!r}. "
            "Set it in .env or use CMO_LLM_PROVIDER=ollama for local zero-cost execution."
        )

    protocol = route["protocol"]
    base_url = route["base_url"]
    model = route["model"]

    if protocol == "openai_chat":
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        elif not route["requires_key"]:
            headers["Authorization"] = "Bearer local-no-key"
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/muvule/freecmo"
            headers["X-Title"] = "FreeCMO"
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        resp = tx(req)
        choices = resp.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            raise RuntimeError(f"{provider} returned empty completion choices")
        first = choices[0]
        text = str(((first.get("message") or {}).get("content")) or "")
        return {"provider": provider, "model": model, "model_tier": model_tier, "content": text}

    if protocol == "anthropic_messages":
        url = f"{base_url}/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        resp = tx(req)
        blocks = resp.get("content") or []
        text = "\n".join(str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text")
        if not blocks or not text:
            raise RuntimeError(f"{provider} returned empty message content")
        return {"provider": provider, "model": model, "model_tier": model_tier, "content": text}

    if protocol == "gemini_generate":
        safe_model = urllib.parse.quote(model, safe="-_.")
        url = f"{base_url}/models/{safe_model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        }
        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        resp = tx(req)
        cands = resp.get("candidates") or []
        if not cands or not isinstance(cands[0], dict):
            raise RuntimeError(f"{provider} returned empty candidates")
        first_cand = cands[0]
        parts = ((first_cand.get("content") or {}).get("parts")) or []
        text = "\n".join(str(p.get("text", "")) for p in parts if isinstance(p, dict) and "text" in p)
        return {"provider": provider, "model": model, "model_tier": model_tier, "content": text}

    raise ValueError(f"Unhandled protocol {protocol!r}")
