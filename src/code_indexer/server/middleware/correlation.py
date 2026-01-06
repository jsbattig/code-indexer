"""
Correlation ID context management and middleware for CIDX Server.

Implements correlation ID generation, storage in contextvars (async-safe),
and FastAPI middleware for automatic request/response correlation tracking.

Following Story #666 AC2: CorrelationContextMiddleware Implementation
"""

import contextvars
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .error_formatters import generate_correlation_id


# ContextVar for storing correlation ID (async-safe, request-scoped)
_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def get_correlation_id() -> Optional[str]:
    """
    Get current correlation ID from context.

    Returns:
        Optional[str]: Current correlation ID or None if not set

    Example:
        >>> correlation_id = get_correlation_id()
        >>> if correlation_id:
        ...     logger.error("Error occurred", extra={"correlation_id": correlation_id})
    """
    return _correlation_id.get()


def set_correlation_id(correlation_id: str) -> None:
    """
    Set correlation ID in context.

    Args:
        correlation_id: Correlation ID to store in context

    Example:
        >>> set_correlation_id("abc-123-def")
        >>> assert get_correlation_id() == "abc-123-def"
    """
    _correlation_id.set(correlation_id)


def clear_correlation_id() -> None:
    """
    Clear correlation ID from context.

    Useful for test cleanup and explicit context clearing.

    Example:
        >>> set_correlation_id("test-id")
        >>> clear_correlation_id()
        >>> assert get_correlation_id() is None
    """
    _correlation_id.set(None)


class CorrelationContextMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for automatic correlation ID management.

    Features:
    - Extracts correlation ID from X-Correlation-ID request header
    - Generates UUID v4 if header not present
    - Stores correlation ID in contextvars (async-safe)
    - Adds X-Correlation-ID to response headers
    - Ensures correlation ID persists throughout request lifecycle

    Usage:
        >>> from fastapi import FastAPI
        >>> from code_indexer.server.middleware.correlation import CorrelationContextMiddleware
        >>>
        >>> app = FastAPI()
        >>> app.add_middleware(CorrelationContextMiddleware)

    Following Story #666 AC2 requirements:
    - Generate UUID v4 if X-Correlation-ID header not present ✓
    - Store correlation ID in contextvars (async-safe) ✓
    - Create get_correlation_id() helper function ✓
    - Add X-Correlation-ID to response headers ✓
    - Ensure middleware runs before all other processing ✓
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request and inject correlation ID.

        Args:
            request: FastAPI request object
            call_next: Next middleware/route handler

        Returns:
            Response with X-Correlation-ID header
        """
        # Extract or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = generate_correlation_id()

        # Store in context for request lifecycle
        set_correlation_id(correlation_id)

        # Process request
        response = await call_next(request)

        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response
