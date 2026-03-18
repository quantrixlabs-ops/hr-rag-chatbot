"""A/B testing framework for RAG parameters (Phase C2).

Allows running experiments to compare different RAG configurations
(chunk sizes, retrieval top-k, reranking models, etc.) and measuring
their impact on quality metrics.

Usage:
    from backend.app.core.ab_testing import get_experiment_variant

    variant = get_experiment_variant("rerank_top_n", user_id)
    # variant = {"name": "control", "value": 8} or {"name": "variant_a", "value": 12}
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

# Active experiments — modify to add/change experiments
EXPERIMENTS = {
    "rerank_top_n": {
        "control": {"value": 8, "weight": 50},
        "more_chunks": {"value": 12, "weight": 50},
    },
    "dense_weight": {
        "control": {"value": 0.6, "weight": 50},
        "bm25_heavy": {"value": 0.4, "weight": 50},
    },
    "min_relevance_score": {
        "control": {"value": 0.20, "weight": 50},
        "strict": {"value": 0.30, "weight": 50},
    },
}


@dataclass
class ExperimentVariant:
    experiment: str
    variant_name: str
    value: Any


def get_experiment_variant(experiment_name: str, user_id: str) -> ExperimentVariant:
    """Get the A/B test variant for a user.

    Uses deterministic hashing so the same user always gets the same variant.
    """
    experiment = EXPERIMENTS.get(experiment_name)
    if not experiment:
        return ExperimentVariant(experiment_name, "default", None)

    # Deterministic assignment: hash(experiment + user_id) → bucket
    hash_input = f"{experiment_name}:{user_id}"
    bucket = int(hashlib.md5(hash_input.encode()).hexdigest()[:8], 16) % 100

    cumulative = 0
    for variant_name, config in experiment.items():
        cumulative += config["weight"]
        if bucket < cumulative:
            return ExperimentVariant(experiment_name, variant_name, config["value"])

    # Fallback to first variant
    first = next(iter(experiment))
    return ExperimentVariant(experiment_name, first, experiment[first]["value"])


def list_experiments() -> dict:
    """Return all active experiments and their variants."""
    return {
        name: {
            "variants": {vn: vc["value"] for vn, vc in exp.items()},
            "weights": {vn: vc["weight"] for vn, vc in exp.items()},
        }
        for name, exp in EXPERIMENTS.items()
    }
