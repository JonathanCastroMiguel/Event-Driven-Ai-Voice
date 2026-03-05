"""OpenTelemetry SDK setup, Sentry integration, and Prometheus metrics."""

from __future__ import annotations

import structlog
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import Counter, Gauge, Histogram

from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Prometheus metrics (13.3)
# ---------------------------------------------------------------------------

TURN_LATENCY = Histogram(
    "voice_turn_latency_ms",
    "Time from human_turn_finalized to realtime_voice_start (ms)",
    buckets=[50, 100, 200, 350, 500, 750, 1000, 1500, 2000, 5000],
)

ROUTE_A_CONFIDENCE = Histogram(
    "voice_route_a_confidence",
    "Route A classification confidence scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
)

ROUTE_B_CONFIDENCE = Histogram(
    "voice_route_b_confidence",
    "Route B classification confidence scores",
    buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0],
)

TOOL_EXECUTION_MS = Histogram(
    "voice_tool_execution_ms",
    "Tool execution duration in ms",
    buckets=[10, 50, 100, 200, 500, 1000, 2000, 5000, 10000],
)

BARGE_IN_TOTAL = Counter(
    "voice_barge_in_total",
    "Number of barge-in events",
)

FALLBACK_LLM_TOTAL = Counter(
    "voice_fallback_llm_total",
    "Number of 3rd-party LLM fallback invocations",
)

ACTIVE_CALLS = Gauge(
    "voice_active_calls",
    "Number of currently active calls",
)

FILLER_EMITTED_TOTAL = Counter(
    "voice_filler_emitted_total",
    "Number of filler voice starts",
)


# ---------------------------------------------------------------------------
# OpenTelemetry setup (13.1)
# ---------------------------------------------------------------------------


def setup_telemetry(settings: Settings) -> None:
    """Initialize OpenTelemetry tracer provider with OTLP exporter."""
    resource = Resource.create(
        {"service.name": settings.otel_service_name}
    )
    provider = TracerProvider(resource=resource)

    if settings.otel_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("otel_exporter_configured", endpoint=settings.otel_endpoint)
        except Exception:
            logger.warning("otel_exporter_failed", exc_info=True)

    trace.set_tracer_provider(provider)
    logger.info("otel_tracer_initialized", service=settings.otel_service_name)


def get_tracer(name: str = "voice-ai-runtime") -> trace.Tracer:
    """Get a tracer instance."""
    return trace.get_tracer(name)


# ---------------------------------------------------------------------------
# Sentry setup (13.4)
# ---------------------------------------------------------------------------


def setup_sentry(settings: Settings) -> None:
    """Initialize Sentry SDK if DSN is configured."""
    if not settings.sentry_dsn:
        logger.info("sentry_disabled", reason="no_dsn")
        return

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=1.0,
            environment="production",
        )
        logger.info("sentry_initialized")
    except Exception:
        logger.warning("sentry_init_failed", exc_info=True)
