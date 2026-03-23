"""OpenTelemetry distributed tracing — Phase 5 (F-57).

Instruments every chat query with child spans for each pipeline stage:
  query [root]
    ├── auth.validate_token
    ├── cache.lookup
    ├── embed.query
    ├── rag.retrieve
    │     ├── qdrant.search
    │     └── bm25.search
    ├── rag.rerank
    ├── llm.generate
    └── response.serialize

Configuration:
  OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317   (Jaeger OTLP gRPC)
  OTEL_SERVICE_NAME=hr-chatbot-api                 (default)
  OTEL_TRACES_ENABLED=true                         (set false to disable)

If OpenTelemetry packages are not installed or OTLP endpoint is not set,
tracing is a no-op — all span() calls become pass-through context managers.

Installation:
  pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-grpc \
              opentelemetry-instrumentation-fastapi
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Generator, Optional

import structlog

logger = structlog.get_logger()

_tracer = None
_initialized = False


def init_tracing() -> None:
    """Initialize OpenTelemetry. Call once at app startup."""
    global _tracer, _initialized
    if _initialized:
        return
    _initialized = True

    if os.getenv("OTEL_TRACES_ENABLED", "true").lower() != "true":
        logger.info("tracing_disabled", reason="OTEL_TRACES_ENABLED=false")
        return

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    service_name = os.getenv("OTEL_SERVICE_NAME", "hr-chatbot-api")

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("tracing_otlp_configured", endpoint=otlp_endpoint, service=service_name)
        else:
            # No exporter configured — traces produced but not exported
            logger.info("tracing_no_exporter", note="Set OTEL_EXPORTER_OTLP_ENDPOINT to export traces")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        logger.info("tracing_initialized", service=service_name)

    except ImportError:
        logger.info("tracing_disabled", reason="opentelemetry-sdk not installed")
    except Exception as e:
        logger.warning("tracing_init_failed", error=str(e))


def instrument_fastapi(app: Any) -> None:
    """Auto-instrument FastAPI app with OpenTelemetry spans for all requests."""
    if _tracer is None:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("tracing_fastapi_instrumented")
    except ImportError:
        pass
    except Exception as e:
        logger.warning("tracing_fastapi_instrument_failed", error=str(e))


@contextmanager
def span(
    name: str,
    attributes: Optional[dict] = None,
) -> Generator:
    """Create a trace span as a context manager.

    No-op if tracing is disabled or OTEL packages not installed.

    Usage:
        with span("qdrant.search", {"tenant_id": tid, "top_k": 20}):
            results = qdrant.search(...)
    """
    if _tracer is None:
        yield
        return

    try:
        from opentelemetry import trace
        with _tracer.start_as_current_span(name) as s:
            if attributes:
                for k, v in attributes.items():
                    s.set_attribute(k, str(v))
            try:
                yield s
            except Exception as exc:
                s.record_exception(exc)
                s.set_status(
                    trace.Status(trace.StatusCode.ERROR, str(exc))
                )
                raise
    except ImportError:
        yield


def set_span_attribute(key: str, value: Any) -> None:
    """Set an attribute on the current active span (if any)."""
    if _tracer is None:
        return
    try:
        from opentelemetry import trace
        current = trace.get_current_span()
        if current:
            current.set_attribute(key, str(value))
    except Exception:
        pass


def get_trace_id() -> str:
    """Return the current trace ID as a hex string (for logging correlation)."""
    if _tracer is None:
        return ""
    try:
        from opentelemetry import trace
        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.is_valid:
            return format(ctx.trace_id, "032x")
    except Exception:
        pass
    return ""
