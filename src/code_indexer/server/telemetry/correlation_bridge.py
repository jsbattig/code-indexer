"""
Correlation ID Bridge for OTEL Tracing (Story #697).

This module provides middleware to bridge X-Correlation-ID headers from
incoming requests into OTEL span attributes, enabling correlation between
existing request tracking and OTEL traces.

Usage:
    from src.code_indexer.server.telemetry.correlation_bridge import (
        CorrelationBridgeMiddleware,
        get_current_correlation_id,
    )

    # Add middleware to FastAPI app
    app.add_middleware(CorrelationBridgeMiddleware)

    # Get correlation ID in request handlers
    correlation_id = get_current_correlation_id()
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Context variable to store correlation ID for current request
_correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Header name for correlation ID
CORRELATION_ID_HEADER = "X-Correlation-ID"

# OTEL attribute name for correlation ID
CORRELATION_ID_ATTRIBUTE = "correlation.id"


def get_current_correlation_id() -> str | None:
    """
    Get the correlation ID for the current request context.

    Returns:
        Correlation ID string or None if not in a request context
    """
    return _correlation_id_var.get()


def set_current_correlation_id(correlation_id: str) -> None:
    """
    Set the correlation ID for the current request context.

    Args:
        correlation_id: Correlation ID to set
    """
    _correlation_id_var.set(correlation_id)


def generate_correlation_id() -> str:
    """
    Generate a new correlation ID.

    Returns:
        New UUID-based correlation ID
    """
    return str(uuid.uuid4())


class CorrelationBridgeMiddleware(BaseHTTPMiddleware):
    """
    Middleware to bridge X-Correlation-ID headers into OTEL spans.

    This middleware:
    1. Extracts X-Correlation-ID from incoming request headers
    2. Generates a new ID if header is missing
    3. Sets the ID in context for access by handlers
    4. Adds correlation.id attribute to current OTEL span
    5. Includes X-Correlation-ID in response headers
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and bridge correlation ID to OTEL."""
        # Extract or generate correlation ID
        correlation_id = request.headers.get(CORRELATION_ID_HEADER)
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Set in context variable for access by handlers
        token = _correlation_id_var.set(correlation_id)

        try:
            # Add correlation ID to current OTEL span if tracing is active
            self._set_span_attribute(correlation_id)

            # Process the request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[CORRELATION_ID_HEADER] = correlation_id

            return response

        finally:
            # Reset context variable
            _correlation_id_var.reset(token)

    def _set_span_attribute(self, correlation_id: str) -> None:
        """
        Set correlation ID attribute on current OTEL span.

        Args:
            correlation_id: Correlation ID to set
        """
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_attribute(CORRELATION_ID_ATTRIBUTE, correlation_id)

        except ImportError:
            # OTEL not available, skip span attribute
            pass
        except Exception as e:
            # Log but don't fail request if span attribute fails
            logger.debug(f"Failed to set correlation ID on span: {e}")
