"""Multi-model routing — Phase 4 (F-41).

Routes queries to the correct model based on query type and complexity:
  greeting / simple factual  → llama3.2:3b   (fast, low compute)
  policy / standard          → llama3.1:8b   (balanced)
  multi-step / comparative   → llama3.1:70b  (accurate, slow)

Model tiers are configured via env vars so operators can swap models
without code changes:
  MODEL_FAST=llama3.2:3b
  MODEL_STANDARD=llama3.1:8b
  MODEL_ADVANCED=llama3.1:70b

If only one Ollama model is pulled (common in dev), all tiers fall back
to LLM_MODEL (the default configured model).
"""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger()

# ── Model tier configuration (env-overridable) ────────────────────────────────

def _model_tiers() -> dict[str, str]:
    """Build tier→model mapping from env vars.

    Falls back to LLM_MODEL for any tier not explicitly set,
    so single-model deployments work without configuration.
    """
    default = os.getenv("LLM_MODEL", "llama3:8b")
    return {
        "fast":     os.getenv("MODEL_FAST", default),
        "standard": os.getenv("MODEL_STANDARD", default),
        "advanced": os.getenv("MODEL_ADVANCED", default),
    }


# ── Query classification ──────────────────────────────────────────────────────

# Keywords that indicate simple queries (→ fast tier)
_SIMPLE_PATTERNS = frozenset([
    "hello", "hi", "hey", "thanks", "thank you", "bye", "goodbye",
    "what is", "who is", "when is", "where is", "how many",
])

# Keywords that indicate complex reasoning (→ advanced tier)
_COMPLEX_PATTERNS = frozenset([
    "compare", "difference between", "pros and cons", "explain why",
    "analyze", "what would happen if", "step by step", "calculate",
    "multi-step", "summarize all", "across departments", "versus",
    "trade-off", "evaluate", "recommend", "best option",
])


def _classify_complexity(query: str) -> tuple[str, str]:
    """Classify query into (query_type, complexity).

    Returns:
        query_type: "greeting" | "factual" | "policy" | "comparative" | "analytical"
        complexity: "simple" | "standard" | "complex"
    """
    q = query.lower().strip()

    # Greetings
    if any(q.startswith(p) for p in ("hello", "hi ", "hey", "thanks", "thank", "bye")):
        return "greeting", "simple"

    # Complex patterns
    for pattern in _COMPLEX_PATTERNS:
        if pattern in q:
            return "comparative" if "compare" in pattern or "versus" in pattern else "analytical", "complex"

    # Simple factual
    if any(q.startswith(p) for p in ("what is", "who is", "when is", "where is", "how many")):
        # Short queries with simple structure
        if len(q.split()) <= 10:
            return "factual", "simple"

    # Default: policy question of standard complexity
    return "policy", "standard"


# ── Main routing function ─────────────────────────────────────────────────────

def select_model(
    query_type: str,
    complexity: str,
    default_model: str,
    override_tier: Optional[str] = None,
) -> str:
    """Select the best model based on query characteristics.

    Args:
        query_type:    Classification from _classify_complexity or caller
        complexity:    "simple" | "standard" | "complex"
        default_model: Fallback model from settings (LLM_MODEL)
        override_tier: Force a specific tier ("fast"|"standard"|"advanced")

    Returns the model name string to use for this query.
    """
    tiers = _model_tiers()

    if override_tier and override_tier in tiers:
        tier = override_tier
    elif complexity == "simple" and query_type in ("greeting", "factual", "redirect"):
        tier = "fast"
    elif complexity == "complex" or query_type in ("comparative", "analytical"):
        tier = "advanced"
    else:
        tier = "standard"

    model = tiers.get(tier, default_model)

    logger.info(
        "model_routed",
        tier=tier,
        model=model,
        query_type=query_type,
        complexity=complexity,
    )
    return model


def select_model_for_query(query: str, default_model: str) -> str:
    """Convenience wrapper: classify query and select model in one call.

    Used by the orchestrator when multi-model routing is enabled.
    """
    query_type, complexity = _classify_complexity(query)
    return select_model(query_type, complexity, default_model)


def get_routing_info(query: str, default_model: str) -> dict:
    """Return full routing decision for observability/logging."""
    query_type, complexity = _classify_complexity(query)
    tiers = _model_tiers()

    if complexity == "simple" and query_type in ("greeting", "factual"):
        tier = "fast"
    elif complexity == "complex" or query_type in ("comparative", "analytical"):
        tier = "advanced"
    else:
        tier = "standard"

    return {
        "query_type": query_type,
        "complexity": complexity,
        "tier": tier,
        "model": tiers.get(tier, default_model),
        "tiers_config": tiers,
    }
