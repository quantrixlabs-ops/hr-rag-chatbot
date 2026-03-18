"""API rate tiers — different rate limits per plan/role (Phase D9).

Tier definitions:
  - free:       10 queries/min, 2 uploads/min
  - starter:    30 queries/min, 5 uploads/min
  - pro:        100 queries/min, 20 uploads/min
  - enterprise: 500 queries/min, 50 uploads/min
"""

from __future__ import annotations

RATE_TIERS = {
    "free":       {"queries_per_min": 10,  "uploads_per_min": 2,  "api_calls_per_min": 20},
    "trial":      {"queries_per_min": 20,  "uploads_per_min": 5,  "api_calls_per_min": 50},
    "starter":    {"queries_per_min": 30,  "uploads_per_min": 5,  "api_calls_per_min": 100},
    "pro":        {"queries_per_min": 100, "uploads_per_min": 20, "api_calls_per_min": 300},
    "enterprise": {"queries_per_min": 500, "uploads_per_min": 50, "api_calls_per_min": 1000},
}


def get_rate_limit(plan: str, limit_type: str) -> int:
    """Get the rate limit for a plan and limit type.

    Args:
        plan: "free", "trial", "starter", "pro", "enterprise"
        limit_type: "queries_per_min", "uploads_per_min", "api_calls_per_min"

    Returns:
        Rate limit value (requests per minute)
    """
    tier = RATE_TIERS.get(plan, RATE_TIERS["trial"])
    return tier.get(limit_type, 30)
