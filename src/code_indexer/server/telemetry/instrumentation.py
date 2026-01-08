"""
FastAPI Auto-Instrumentation for OTEL Tracing (Story #697).

This module provides functions to instrument FastAPI applications with
OpenTelemetry tracing. It uses the official FastAPIInstrumentor for
automatic span creation on HTTP requests.

Usage:
    from src.code_indexer.server.telemetry.instrumentation import instrument_fastapi

    # Instrument the app (typically in lifespan)
    instrument_fastapi(app, telemetry_manager)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from fastapi import FastAPI
    from src.code_indexer.server.telemetry.manager import TelemetryManager

logger = logging.getLogger(__name__)

# Default endpoints to exclude from tracing (health checks, metrics)
DEFAULT_EXCLUDED_URLS: List[str] = [
    "health",
    "healthz",
    "ready",
    "readiness",
    "live",
    "liveness",
    "metrics",
    "favicon.ico",
]

# Track instrumentation state
_is_instrumented: bool = False


def instrument_fastapi(
    app: "FastAPI",
    telemetry_manager: "TelemetryManager",
    excluded_urls: List[str] | None = None,
) -> bool:
    """
    Instrument a FastAPI application with OTEL tracing.

    Args:
        app: FastAPI application instance
        telemetry_manager: TelemetryManager instance
        excluded_urls: Optional list of URL patterns to exclude from tracing

    Returns:
        True if instrumentation was applied, False if skipped
    """
    global _is_instrumented

    # Skip if telemetry is not initialized or traces disabled
    if not telemetry_manager.is_initialized:
        logger.debug("Skipping FastAPI instrumentation: telemetry not initialized")
        return False

    if not telemetry_manager._config.export_traces:
        logger.debug("Skipping FastAPI instrumentation: export_traces is False")
        return False

    # Skip if already instrumented
    if _is_instrumented:
        logger.debug("FastAPI already instrumented, skipping")
        return True

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        # Build exclusion pattern
        urls_to_exclude = excluded_urls or DEFAULT_EXCLUDED_URLS
        exclude_pattern = "|".join(urls_to_exclude)

        # Instrument the app
        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls=exclude_pattern,
            tracer_provider=telemetry_manager._tracer_provider,
        )

        _is_instrumented = True
        logger.info(
            f"FastAPI instrumented with OTEL tracing "
            f"(excluded: {len(urls_to_exclude)} URL patterns)"
        )
        return True

    except ImportError as e:
        logger.warning(
            f"FastAPI instrumentation unavailable: {e}. "
            "Install opentelemetry-instrumentation-fastapi for auto-tracing."
        )
        return False
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")
        return False


def uninstrument_fastapi() -> bool:
    """
    Remove OTEL instrumentation from FastAPI.

    Returns:
        True if uninstrumentation was performed, False if not instrumented
    """
    global _is_instrumented

    if not _is_instrumented:
        return False

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.uninstrument()
        _is_instrumented = False
        logger.info("FastAPI OTEL instrumentation removed")
        return True

    except Exception as e:
        logger.error(f"Failed to uninstrument FastAPI: {e}")
        return False


def reset_instrumentation_state() -> None:
    """Reset the instrumentation state (for testing)."""
    global _is_instrumented
    _is_instrumented = False
