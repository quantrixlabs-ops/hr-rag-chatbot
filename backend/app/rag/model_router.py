"""Multi-LLM Routing Engine — selects the optimal Ollama model per query.

Routes queries to different local models based on complexity and risk:
- Simple/factual queries → fast lightweight model (e.g., gemma3:4b)
- Complex/multi-step queries → standard model (e.g., llama3:8b)
- Critical/sensitive queries → advanced model + reasoning enforcement

This module does NOT modify any existing logic. It provides a single function
`select_model()` that returns the appropriate model name. The pipeline
calls it instead of using a hardcoded model name.

Admin configures available models via the `model_routing_config` table.
If no routing config exists, the system falls back to the default model.
"""

from __future__ import annotations

import sqlite3
import time

import structlog

from backend.app.core.config import get_settings

logger = structlog.get_logger()


# ── Routing tiers ─────────────────────────────────────────────────────────────

TIER_FAST = "fast"          # Simple lookups, FAQ, greetings
TIER_STANDARD = "standard"  # Moderate queries, most HR questions
TIER_ADVANCED = "advanced"  # Complex reasoning, sensitive, calculations


def select_model(
    complexity: str = "simple",
    intent: str = "policy_lookup",
    is_sensitive: bool = False,
    is_calculation: bool = False,
    requires_multi_retrieval: bool = False,
    query_type: str = "factual",
) -> tuple[str, str]:
    """Select the optimal model based on query analysis.

    Args:
        complexity: "simple" | "moderate" | "complex" (from QueryAnalyzer)
        intent: "policy_lookup" | "factual" | "procedural" | "sensitive" | "calculation" | "comparative"
        is_sensitive: True if query involves termination, harassment, etc.
        is_calculation: True if query requires numerical reasoning
        requires_multi_retrieval: True if compound query
        query_type: The query type classification

    Returns:
        Tuple of (model_name, tier) — e.g., ("gemma3:4b", "fast")
    """
    s = get_settings()

    # Determine tier based on query characteristics
    tier = _classify_tier(complexity, intent, is_sensitive, is_calculation,
                          requires_multi_retrieval, query_type)

    # Get the model for this tier from config/database
    model = _get_model_for_tier(tier, s)

    logger.info("model_routed",
                tier=tier, model=model,
                complexity=complexity, intent=intent,
                is_sensitive=is_sensitive)

    return model, tier


def _classify_tier(
    complexity: str, intent: str, is_sensitive: bool,
    is_calculation: bool, requires_multi: bool, query_type: str,
) -> str:
    """Map query characteristics to a routing tier."""

    # ADVANCED tier: critical queries that need the strongest model
    if is_sensitive:
        return TIER_ADVANCED
    if is_calculation:
        return TIER_ADVANCED
    if intent == "comparative":
        return TIER_ADVANCED
    if requires_multi:
        return TIER_ADVANCED
    if complexity == "complex":
        return TIER_ADVANCED

    # FAST tier: simple queries that a lightweight model handles well
    if complexity == "simple" and intent in ("policy_lookup", "factual"):
        return TIER_FAST
    if query_type in ("greeting", "redirect", "clarification"):
        return TIER_FAST

    # STANDARD tier: everything else
    return TIER_STANDARD


def _get_model_for_tier(tier: str, settings=None) -> str:
    """Resolve tier to actual model name.

    Priority:
    1. Database config (admin-set via model_routing_config table)
    2. Settings config (model_fast/model_standard/model_advanced from .env)
    3. Default model (llm_model from .env — typically llama3:8b)
    """
    s = settings or get_settings()

    # Try database config first (admin can change without restart)
    db_model = _get_db_model(tier, s.db_path)
    if db_model:
        return db_model

    # Fall back to .env config
    if tier == TIER_FAST and s.model_fast:
        return s.model_fast
    if tier == TIER_STANDARD and s.model_standard:
        return s.model_standard
    if tier == TIER_ADVANCED and s.model_advanced:
        return s.model_advanced

    # Ultimate fallback: default model for all tiers
    return s.llm_model


def _get_db_model(tier: str, db_path: str) -> str:
    """Check if admin has configured a model for this tier in the database."""
    try:
        with sqlite3.connect(db_path) as con:
            # Check if table exists (may not on first run)
            tables = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='model_routing_config'"
            ).fetchone()
            if not tables:
                return ""

            row = con.execute(
                "SELECT model_name FROM model_routing_config "
                "WHERE tier = ? AND is_enabled = 1",
                (tier,),
            ).fetchone()
            return row[0] if row else ""
    except Exception:
        return ""


# ── Admin configuration ───────────────────────────────────────────────────────

def get_routing_config(db_path: str = "") -> list[dict]:
    """Get the current model routing configuration."""
    path = db_path or get_settings().db_path
    try:
        with sqlite3.connect(path) as con:
            tables = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='model_routing_config'"
            ).fetchone()
            if not tables:
                return []
            rows = con.execute(
                "SELECT tier, model_name, is_enabled, description, updated_at "
                "FROM model_routing_config ORDER BY tier"
            ).fetchall()
            return [
                {"tier": r[0], "model_name": r[1], "is_enabled": bool(r[2]),
                 "description": r[3], "updated_at": r[4]}
                for r in rows
            ]
    except Exception:
        return []


def set_routing_model(db_path: str, tier: str, model_name: str, enabled: bool = True) -> None:
    """Set the model for a routing tier."""
    if tier not in (TIER_FAST, TIER_STANDARD, TIER_ADVANCED):
        raise ValueError(f"Invalid tier: {tier}")

    descriptions = {
        TIER_FAST: "Simple queries — FAQ, basic lookups, greetings",
        TIER_STANDARD: "Moderate queries — most HR policy questions",
        TIER_ADVANCED: "Complex queries — calculations, sensitive topics, multi-step",
    }

    now = time.time()
    with sqlite3.connect(db_path) as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS model_routing_config ("
            "  tier TEXT PRIMARY KEY,"
            "  model_name TEXT NOT NULL,"
            "  is_enabled INTEGER DEFAULT 1,"
            "  description TEXT DEFAULT '',"
            "  updated_at REAL"
            ")"
        )
        con.execute(
            "INSERT OR REPLACE INTO model_routing_config (tier, model_name, is_enabled, description, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (tier, model_name.strip(), 1 if enabled else 0, descriptions.get(tier, ""), now),
        )

    logger.info("model_routing_updated", tier=tier, model=model_name, enabled=enabled)
