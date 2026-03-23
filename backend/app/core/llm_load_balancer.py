"""LLM Load Balancer — Phase 4 (F-40).

Wraps multiple Ollama nodes behind a single interface.
Eliminates the single-Ollama bottleneck at 5000+ concurrent users.

Strategy: least-busy (fewest in-flight requests).
Fallback: round-robin when load is equal or metrics unavailable.

Configuration:
  OLLAMA_NODES=http://ollama1:11434,http://ollama2:11434,http://ollama3:11434

If OLLAMA_NODES is not set, falls back to OLLAMA_BASE_URL (single node).
This means Phase 1–3 deployments work unchanged — Phase 4 adds nodes without
breaking existing single-node setups.

Node health:
  - Health check: GET /api/tags (returns 200 if Ollama is running)
  - Unhealthy nodes are skipped; re-tried every 30s via background check
  - If all nodes are down, raises LLMLoadBalancerError

Usage:
    balancer = get_load_balancer()
    url = balancer.get_node_url()        # Returns best available node URL
    balancer.record_start(url)           # Call before request
    balancer.record_end(url, success)    # Call after request
"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional

import structlog

logger = structlog.get_logger()

# ── Node state ────────────────────────────────────────────────────────────────

class OllamaNode:
    """Tracks state for a single Ollama node."""

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.in_flight: int = 0        # Active requests
        self.total_requests: int = 0
        self.failures: int = 0
        self.healthy: bool = True
        self.last_health_check: float = 0.0
        self._lock = threading.Lock()

    def record_start(self) -> None:
        with self._lock:
            self.in_flight += 1
            self.total_requests += 1

    def record_end(self, success: bool) -> None:
        with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            if not success:
                self.failures += 1

    def mark_healthy(self, healthy: bool) -> None:
        with self._lock:
            self.healthy = healthy
            self.last_health_check = time.time()

    def stats(self) -> dict:
        return {
            "url": self.url,
            "in_flight": self.in_flight,
            "total_requests": self.total_requests,
            "failures": self.failures,
            "healthy": self.healthy,
        }


class LLMLoadBalancerError(Exception):
    """Raised when no healthy Ollama nodes are available."""


# ── Load balancer ─────────────────────────────────────────────────────────────

class LLMLoadBalancer:
    """Least-busy load balancer across multiple Ollama nodes."""

    HEALTH_CHECK_INTERVAL = 30  # seconds between health checks per node

    def __init__(self, node_urls: list[str]):
        if not node_urls:
            raise ValueError("LLMLoadBalancer requires at least one node URL")
        self.nodes = [OllamaNode(url) for url in node_urls]
        self._round_robin_idx = 0
        self._lock = threading.Lock()
        logger.info("llm_balancer_initialized", nodes=len(self.nodes), urls=node_urls)

    def get_node(self) -> OllamaNode:
        """Return the least-busy healthy node.

        Selection:
        1. Filter to healthy nodes only
        2. Among healthy nodes, pick the one with fewest in-flight requests
        3. On tie: round-robin

        Refreshes health checks for nodes that haven't been checked recently.
        """
        self._maybe_refresh_health()

        healthy = [n for n in self.nodes if n.healthy]
        if not healthy:
            raise LLMLoadBalancerError(
                f"All {len(self.nodes)} Ollama node(s) are unhealthy. "
                "Check OLLAMA_NODES configuration and node availability."
            )

        # Least-busy selection
        chosen = min(healthy, key=lambda n: n.in_flight)
        return chosen

    def get_node_url(self) -> str:
        """Return URL of the best available node."""
        return self.get_node().url

    def record_start(self, node_url: str) -> None:
        """Call before sending a request to a node."""
        node = self._find_node(node_url)
        if node:
            node.record_start()

    def record_end(self, node_url: str, success: bool = True) -> None:
        """Call after a request to a node completes."""
        node = self._find_node(node_url)
        if node:
            node.record_end(success)
            if not success:
                # Mark for health re-check after failure
                node.last_health_check = 0.0

    def stats(self) -> dict:
        """Return load balancer stats for monitoring."""
        return {
            "total_nodes": len(self.nodes),
            "healthy_nodes": sum(1 for n in self.nodes if n.healthy),
            "nodes": [n.stats() for n in self.nodes],
        }

    def _find_node(self, url: str) -> Optional[OllamaNode]:
        for node in self.nodes:
            if node.url == url.rstrip("/"):
                return node
        return None

    def _maybe_refresh_health(self) -> None:
        """Background health check for stale nodes (non-blocking)."""
        now = time.time()
        for node in self.nodes:
            if now - node.last_health_check > self.HEALTH_CHECK_INTERVAL:
                # Run in thread to avoid blocking the request
                t = threading.Thread(target=self._check_node_health, args=(node,), daemon=True)
                t.start()

    def _check_node_health(self, node: OllamaNode) -> None:
        """Health check: GET /api/tags. Marks node healthy/unhealthy."""
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{node.url}/api/tags")
                healthy = resp.status_code == 200
        except Exception:
            healthy = False

        was_healthy = node.healthy
        node.mark_healthy(healthy)

        if was_healthy != healthy:
            logger.warning(
                "ollama_node_health_changed",
                url=node.url,
                healthy=healthy,
            )


# ── Singleton ─────────────────────────────────────────────────────────────────

_balancer: Optional[LLMLoadBalancer] = None
_balancer_lock = threading.Lock()


def get_load_balancer() -> LLMLoadBalancer:
    """Return the global load balancer instance (lazy init, thread-safe)."""
    global _balancer
    if _balancer is not None:
        return _balancer

    with _balancer_lock:
        if _balancer is not None:
            return _balancer

        nodes_env = os.getenv("OLLAMA_NODES", "").strip()
        if nodes_env:
            node_urls = [url.strip() for url in nodes_env.split(",") if url.strip()]
        else:
            # Single-node fallback — Phase 1-3 compatible
            default_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            node_urls = [default_url]

        _balancer = LLMLoadBalancer(node_urls)
        return _balancer


def reset_load_balancer() -> None:
    """Force re-init on next use — for testing or config reload."""
    global _balancer
    with _balancer_lock:
        _balancer = None
