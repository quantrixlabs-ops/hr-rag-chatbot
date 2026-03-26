"""AI Router — multi-provider routing with fallback chain.

Routes LLM requests through: Internal (default) → External providers (by priority).
The internal Ollama/vLLM system is ALWAYS the primary. External providers are
optional fallbacks configured by Admin.

Architecture:
  Request → Internal AI (Ollama/vLLM)
              ↓ (if fails or external enabled as primary)
            External Provider 1 (highest priority)
              ↓ (if fails)
            External Provider 2
              ↓ ...
            Final fallback error

CRITICAL: This module NEVER modifies the internal ModelGateway.
It wraps it with an additional routing layer.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass

import httpx
import structlog

from backend.app.core.config import get_settings
from backend.app.core.encryption import encrypt_field, decrypt_field
from backend.app.models.document_models import LLMResponse

logger = structlog.get_logger()

# Supported external providers and their API patterns
SUPPORTED_PROVIDERS = {
    "openai": {
        "display_name": "OpenAI (GPT)",
        "default_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
    },
    "claude": {
        "display_name": "Anthropic (Claude)",
        "default_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-20250514",
    },
    "gemini": {
        "display_name": "Google (Gemini)",
        "default_url": "https://generativelanguage.googleapis.com/v1beta",
        "default_model": "gemini-2.0-flash",
    },
    "groq": {
        "display_name": "Groq",
        "default_url": "https://api.groq.com/openai/v1",
        "default_model": "llama-3.1-8b-instant",
    },
    "perplexity": {
        "display_name": "Perplexity",
        "default_url": "https://api.perplexity.ai",
        "default_model": "llama-3.1-sonar-small-128k-online",
    },
    "grok": {
        "display_name": "xAI (Grok)",
        "default_url": "https://api.x.ai/v1",
        "default_model": "grok-3-mini",
    },
}


@dataclass
class ProviderConfig:
    """Configuration for an external AI provider."""
    id: int
    provider_name: str
    api_key: str  # Decrypted
    model_name: str
    base_url: str
    priority: int
    max_tokens: int
    temperature: float


def _log_usage(
    db_path: str, provider: str, model: str, query_hash: str,
    response_time_ms: float, prompt_tokens: int, completion_tokens: int,
    success: bool, error_msg: str = "", fallback_from: str = "",
):
    """Log AI provider usage for audit and cost tracking."""
    try:
        with sqlite3.connect(db_path) as con:
            con.execute(
                "INSERT INTO ai_usage_logs "
                "(provider_name, model_name, query_hash, response_time_ms, "
                "prompt_tokens, completion_tokens, success, error_message, "
                "fallback_from, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (provider, model, query_hash, response_time_ms,
                 prompt_tokens, completion_tokens, 1 if success else 0,
                 error_msg, fallback_from, time.time()),
            )
            # Increment usage counter
            if success:
                con.execute(
                    "UPDATE ai_providers SET usage_count = usage_count + 1 "
                    "WHERE provider_name = ? AND status = 'active'",
                    (provider,),
                )
    except Exception as e:
        logger.warning("ai_usage_log_failed", error=str(e))


def get_ai_mode(db_path: str = "") -> dict:
    """Get the current AI mode setting (internal vs external)."""
    path = db_path or get_settings().db_path
    try:
        with sqlite3.connect(path) as con:
            row = con.execute(
                "SELECT ai_mode, active_provider FROM ai_settings WHERE id = 1"
            ).fetchone()
            if row:
                return {"ai_mode": row[0], "active_provider": row[1]}
    except Exception:
        pass
    return {"ai_mode": "internal", "active_provider": ""}


def get_active_providers(db_path: str = "") -> list[ProviderConfig]:
    """Get all active external providers sorted by priority."""
    path = db_path or get_settings().db_path
    try:
        with sqlite3.connect(path) as con:
            rows = con.execute(
                "SELECT id, provider_name, api_key_encrypted, model_name, "
                "base_url, priority, max_tokens, temperature, usage_count, usage_limit "
                "FROM ai_providers WHERE status = 'active' "
                "ORDER BY priority ASC"
            ).fetchall()
    except Exception:
        return []

    providers = []
    for r in rows:
        # Check usage limit (0 = unlimited)
        if r[9] > 0 and r[8] >= r[9]:
            logger.info("ai_provider_limit_reached", provider=r[1], usage=r[8], limit=r[9])
            continue
        providers.append(ProviderConfig(
            id=r[0], provider_name=r[1],
            api_key=decrypt_field(r[2]),
            model_name=r[3], base_url=r[4],
            priority=r[5], max_tokens=r[6] or 1024,
            temperature=r[7] if r[7] is not None else 0.0,
        ))
    return providers


# ── Provider adapter implementations ──────────────────────────────────────────

def _call_openai_compatible(
    base_url: str, api_key: str, model: str, prompt: str,
    temperature: float, max_tokens: int, extra_headers: dict | None = None,
) -> LLMResponse:
    """Call any OpenAI-compatible API (OpenAI, Groq, Perplexity, Grok, vLLM)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)

    resp = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        headers=headers,
        timeout=60.0,
    )
    resp.raise_for_status()
    d = resp.json()
    choice = d["choices"][0]
    usage = d.get("usage", {})
    return LLMResponse(
        text=choice["message"]["content"],
        model=model,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
    )


def _call_claude(
    base_url: str, api_key: str, model: str, prompt: str,
    temperature: float, max_tokens: int,
) -> LLMResponse:
    """Call Anthropic Claude API (Messages API)."""
    resp = httpx.post(
        f"{base_url.rstrip('/')}/v1/messages",
        json={
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        },
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    d = resp.json()
    text = ""
    for block in d.get("content", []):
        if block.get("type") == "text":
            text += block["text"]
    usage = d.get("usage", {})
    return LLMResponse(
        text=text,
        model=model,
        prompt_tokens=usage.get("input_tokens", 0),
        completion_tokens=usage.get("output_tokens", 0),
    )


def _call_gemini(
    base_url: str, api_key: str, model: str, prompt: str,
    temperature: float, max_tokens: int,
) -> LLMResponse:
    """Call Google Gemini API."""
    resp = httpx.post(
        f"{base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}",
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        },
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    )
    resp.raise_for_status()
    d = resp.json()
    text = ""
    for candidate in d.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")
    usage = d.get("usageMetadata", {})
    return LLMResponse(
        text=text,
        model=model,
        prompt_tokens=usage.get("promptTokenCount", 0),
        completion_tokens=usage.get("candidatesTokenCount", 0),
    )


def call_external_provider(provider: ProviderConfig, prompt: str) -> LLMResponse:
    """Route a request to the correct external provider adapter."""
    name = provider.provider_name.lower()

    if name == "claude":
        return _call_claude(
            provider.base_url, provider.api_key, provider.model_name,
            prompt, provider.temperature, provider.max_tokens,
        )
    elif name == "gemini":
        return _call_gemini(
            provider.base_url, provider.api_key, provider.model_name,
            prompt, provider.temperature, provider.max_tokens,
        )
    else:
        # OpenAI, Groq, Perplexity, Grok all use OpenAI-compatible API
        return _call_openai_compatible(
            provider.base_url, provider.api_key, provider.model_name,
            prompt, provider.temperature, provider.max_tokens,
        )


# ── AI Router: main entry point ──────────────────────────────────────────────

class AIRouter:
    """Routes LLM requests through internal → external provider fallback chain.

    The internal ModelGateway is ALWAYS tried first. External providers are
    only used as fallbacks (or as primary if admin has configured them that way).
    """

    def __init__(self, internal_gateway, settings=None):
        """
        Args:
            internal_gateway: The existing ModelGateway (Ollama/vLLM)
            settings: App settings (for db_path, model config)
        """
        self.internal = internal_gateway
        self.s = settings or get_settings()

    def generate(
        self,
        prompt: str,
        model: str = "",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        """Generate a response based on admin's AI mode setting.

        Mode 'internal': Use Ollama/vLLM (default) → external fallback if fails
        Mode 'external': Use the admin-selected API provider → internal fallback if fails
        """
        model = model or self.s.llm_model
        query_hash = hashlib.sha256(prompt[:200].encode()).hexdigest()[:16]

        # Check admin's AI mode setting
        mode_config = get_ai_mode(self.s.db_path)
        ai_mode = mode_config["ai_mode"]
        active_provider_name = mode_config["active_provider"]

        if ai_mode == "external" and active_provider_name:
            return self._generate_external_primary(
                prompt, model, temperature, max_tokens, query_hash, active_provider_name
            )
        else:
            return self._generate_internal_primary(
                prompt, model, temperature, max_tokens, query_hash
            )

    def _generate_internal_primary(
        self, prompt: str, model: str, temperature: float,
        max_tokens: int, query_hash: str,
    ) -> LLMResponse:
        """Internal AI (Ollama) as primary → external providers as fallback."""
        # Step 1: Try internal
        t0 = time.time()
        try:
            result = self.internal.generate(prompt, model, temperature, max_tokens)
            ms = (time.time() - t0) * 1000
            _log_usage(self.s.db_path, f"internal/{self.internal.provider}",
                       model, query_hash, ms,
                       result.prompt_tokens, result.completion_tokens, True)
            return result
        except Exception as internal_err:
            ms = (time.time() - t0) * 1000
            _log_usage(self.s.db_path, f"internal/{self.internal.provider}",
                       model, query_hash, ms, 0, 0, False,
                       str(internal_err)[:200])
            logger.warning("internal_ai_failed", error=str(internal_err)[:100])

        # Step 2: Fallback to external providers
        providers = get_active_providers(self.s.db_path)
        if not providers:
            raise RuntimeError(f"Internal AI failed and no external providers configured: {internal_err}")

        return self._try_external_providers(providers, prompt, query_hash,
                                            fallback_from=f"internal/{self.internal.provider}")

    def _generate_external_primary(
        self, prompt: str, model: str, temperature: float,
        max_tokens: int, query_hash: str, provider_name: str,
    ) -> LLMResponse:
        """External API as primary → internal Ollama as fallback."""
        # Find the admin-selected provider
        providers = get_active_providers(self.s.db_path)
        primary = next((p for p in providers if p.provider_name == provider_name), None)

        if primary:
            t0 = time.time()
            try:
                result = call_external_provider(primary, prompt)
                ms = (time.time() - t0) * 1000
                _log_usage(self.s.db_path, primary.provider_name,
                           primary.model_name, query_hash, ms,
                           result.prompt_tokens, result.completion_tokens, True)
                logger.info("external_primary_success",
                            provider=primary.provider_name,
                            model=primary.model_name,
                            latency_ms=round(ms))
                return result
            except Exception as ext_err:
                ms = (time.time() - t0) * 1000
                _log_usage(self.s.db_path, primary.provider_name,
                           primary.model_name, query_hash, ms, 0, 0, False,
                           str(ext_err)[:200])
                logger.warning("external_primary_failed",
                               provider=primary.provider_name,
                               error=str(ext_err)[:100])
        else:
            logger.warning("external_primary_not_found", provider=provider_name)

        # Fallback to internal AI
        t1 = time.time()
        try:
            result = self.internal.generate(prompt, model, temperature, max_tokens)
            ms = (time.time() - t1) * 1000
            _log_usage(self.s.db_path, f"internal/{self.internal.provider}",
                       model, query_hash, ms,
                       result.prompt_tokens, result.completion_tokens, True,
                       fallback_from=provider_name)
            logger.info("internal_fallback_success", latency_ms=round(ms))
            return result
        except Exception as internal_err:
            ms = (time.time() - t1) * 1000
            _log_usage(self.s.db_path, f"internal/{self.internal.provider}",
                       model, query_hash, ms, 0, 0, False,
                       str(internal_err)[:200], fallback_from=provider_name)

        raise RuntimeError(f"Both external ({provider_name}) and internal AI failed")

    def _try_external_providers(
        self, providers: list[ProviderConfig], prompt: str,
        query_hash: str, fallback_from: str = "",
    ) -> LLMResponse:
        """Try external providers in priority order."""
        last_error: Exception = RuntimeError("No providers available")
        for provider in providers:
            t1 = time.time()
            try:
                result = call_external_provider(provider, prompt)
                ms = (time.time() - t1) * 1000
                _log_usage(
                    self.s.db_path, provider.provider_name,
                    provider.model_name, query_hash, ms,
                    result.prompt_tokens, result.completion_tokens, True,
                    fallback_from=fallback_from,
                )
                logger.info("external_ai_success",
                            provider=provider.provider_name,
                            model=provider.model_name,
                            latency_ms=round(ms))
                return result
            except Exception as ext_err:
                ms = (time.time() - t1) * 1000
                _log_usage(
                    self.s.db_path, provider.provider_name,
                    provider.model_name, query_hash, ms, 0, 0, False,
                    str(ext_err)[:200], fallback_from=fallback_from,
                )
                logger.warning("external_ai_failed",
                               provider=provider.provider_name,
                               error=str(ext_err)[:100])
                last_error = ext_err

        # All providers failed
        raise RuntimeError(f"All AI providers failed. Last error: {last_error}")

    def generate_stream(self, prompt: str, model: str = "", temperature: float = 0.0, max_tokens: int = 1024):
        """Stream from internal AI only — external providers don't support streaming in this implementation."""
        return self.internal.generate_stream(
            prompt, model or self.s.llm_model, temperature, max_tokens
        )
