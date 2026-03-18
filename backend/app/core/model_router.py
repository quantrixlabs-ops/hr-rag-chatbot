"""Multi-model routing — routes queries to appropriate LLM based on complexity (Phase C4).

Simple queries → smaller/faster model
Complex queries → larger/more capable model
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()

# Model tiers — configurable per deployment
MODEL_TIERS = {
    "fast": "llama3:8b",       # Simple factual queries
    "standard": "llama3:8b",   # Default — moderate complexity
    "advanced": "llama3:8b",   # Complex comparative/multi-doc queries
}


def select_model(query_type: str, complexity: str, default_model: str) -> str:
    """Select the best model based on query characteristics.

    In production, different tiers can point to different models:
      fast → llama3:8b (or phi-3)
      standard → llama3:8b
      advanced → llama3:70b (or mixtral)
    """
    if complexity == "simple" and query_type in ("factual", "greeting", "redirect"):
        tier = "fast"
    elif complexity == "complex" or query_type == "comparative":
        tier = "advanced"
    else:
        tier = "standard"

    model = MODEL_TIERS.get(tier, default_model)

    # If all tiers point to the same model, just use default
    if model == default_model:
        return default_model

    logger.info("model_routed", tier=tier, model=model, query_type=query_type, complexity=complexity)
    return model
