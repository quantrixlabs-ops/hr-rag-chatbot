"""LLM gateway — Section 10. Unified Ollama / vLLM interface.

Hardened with:
- Connection error retries
- Timeout handling
- Meaningful error messages for common failures
"""

from __future__ import annotations

import time

import httpx
import structlog

from backend.app.models.document_models import LLMResponse

logger = structlog.get_logger()

_MAX_RETRIES = 2
_RETRY_DELAY = 1.0


class ModelGateway:
    def __init__(self, provider: str = "ollama"):
        self.provider = provider
        self.cfg = {
            "ollama": {"base_url": "http://localhost:11434"},
            "vllm": {"base_url": "http://localhost:8001/v1"},
        }

    def configure(self, provider: str, base_url: str) -> None:
        self.provider = provider
        self.cfg.setdefault(provider, {})["base_url"] = base_url

    def generate(
        self,
        prompt: str,
        model: str = "llama3:8b",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        if self.provider == "ollama":
            return self._ollama(prompt, model, temperature, max_tokens)
        return self._vllm(prompt, model, temperature, max_tokens)

    def _ollama(self, prompt: str, model: str, temp: float, mt: int) -> LLMResponse:
        url = f"{self.cfg['ollama']['base_url']}/api/generate"
        last_err: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                r = httpx.post(
                    url,
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": temp, "num_predict": mt},
                    },
                    timeout=120.0,
                )
                r.raise_for_status()
                d = r.json()
                return LLMResponse(
                    d["response"], model,
                    d.get("prompt_eval_count", 0),
                    d.get("eval_count", 0),
                )
            except httpx.ConnectError as e:
                last_err = e
                logger.warning(
                    "ollama_llm_connect_failed",
                    attempt=attempt,
                    url=url,
                    hint="Is Ollama running? → ollama serve",
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
            except httpx.ReadTimeout as e:
                last_err = e
                logger.warning("ollama_llm_timeout", attempt=attempt, model=model)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
            except httpx.HTTPStatusError as e:
                last_err = e
                if e.response.status_code == 404:
                    raise RuntimeError(
                        f"Ollama model '{model}' not found. Pull it: ollama pull {model}"
                    ) from e
                logger.error("ollama_llm_http_error", status=e.response.status_code)
                raise

        raise RuntimeError(
            f"Ollama LLM request failed after {_MAX_RETRIES} attempts: {last_err}"
        ) from last_err

    def generate_stream(
        self,
        prompt: str,
        model: str = "llama3:8b",
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ):
        """Yield token chunks from Ollama streaming API."""
        import json as _json
        url = f"{self.cfg['ollama']['base_url']}/api/generate"
        with httpx.stream(
            "POST", url,
            json={"model": model, "prompt": prompt, "stream": True,
                  "options": {"temperature": temperature, "num_predict": max_tokens}},
            timeout=120.0,
        ) as response:
            for line in response.iter_lines():
                if line:
                    chunk = _json.loads(line)
                    if "response" in chunk:
                        yield chunk["response"]
                    if chunk.get("done"):
                        break

    def _vllm(self, prompt: str, model: str, temp: float, mt: int) -> LLMResponse:
        url = f"{self.cfg['vllm']['base_url']}/chat/completions"
        try:
            r = httpx.post(
                url,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temp,
                    "max_tokens": mt,
                },
                timeout=120.0,
            )
            r.raise_for_status()
            d = r.json()
            c = d["choices"][0]
            return LLMResponse(
                c["message"]["content"], model,
                d["usage"]["prompt_tokens"],
                d["usage"]["completion_tokens"],
            )
        except httpx.ConnectError as e:
            raise RuntimeError(f"vLLM unreachable at {url}") from e
