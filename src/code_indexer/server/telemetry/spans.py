"""
Custom Spans for Key Operations (Story #700).

This module provides utilities for creating custom OTEL spans for key
operations beyond HTTP request boundaries. Includes a @traced decorator
and create_span() context manager.

Usage:
    from src.code_indexer.server.telemetry.spans import traced, create_span

    # Using decorator
    @traced(name="cidx.search.semantic")
    def semantic_search(query: str):
        ...

    # Using context manager
    with create_span("cidx.git.clone", attributes={"repo": url}) as span:
        ...
"""

from __future__ import annotations

import asyncio
import functools
import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Optional, TypeVar

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

logger = logging.getLogger(__name__)

# Type variables for decorator
F = TypeVar("F", bound=Callable[..., Any])

# Module-level tracer cache
_tracer: Optional["Tracer"] = None
_tracing_enabled: bool = False


def get_tracer(name: str = "cidx.spans") -> Optional["Tracer"]:
    """
    Get or create a tracer for creating spans.

    Args:
        name: Tracer name (instrument name)

    Returns:
        Tracer instance or None if tracing unavailable
    """
    global _tracer, _tracing_enabled

    if _tracer is not None:
        return _tracer

    try:
        from opentelemetry import trace

        # Check if we have a real tracer provider (not NoOpTracerProvider)
        tracer = trace.get_tracer(name)
        _tracer = tracer
        _tracing_enabled = True
        return tracer
    except ImportError:
        logger.debug("OpenTelemetry not available")
        return None
    except Exception as e:
        logger.debug(f"Failed to get tracer: {e}")
        return None


def _get_correlation_id() -> Optional[str]:
    """Get current correlation ID from context."""
    try:
        from src.code_indexer.server.telemetry.correlation_bridge import (
            get_current_correlation_id,
        )

        return get_current_correlation_id()
    except ImportError:
        return None
    except Exception:
        return None


@contextmanager
def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
    record_exception: bool = True,
) -> Generator[Any, None, None]:
    """
    Context manager for creating a custom span.

    Args:
        name: Span name (e.g., "cidx.search.semantic")
        attributes: Optional attributes to set on span
        record_exception: Whether to record exceptions on span

    Yields:
        Span object (or NoOp span if tracing disabled)

    Example:
        with create_span("cidx.git.clone", attributes={"repo": url}) as span:
            # Do work
            span.set_attribute("files_count", 100)
    """
    tracer = get_tracer()

    if tracer is None:
        yield _NoOpSpan()
        return

    try:
        from opentelemetry import context
        from opentelemetry.trace import Status, StatusCode, set_span_in_context
    except ImportError:
        yield _NoOpSpan()
        return

    # Start span and manage context manually
    span = tracer.start_span(name)
    ctx = set_span_in_context(span)
    token = context.attach(ctx)

    try:
        # Add correlation ID if available
        correlation_id = _get_correlation_id()
        if correlation_id:
            span.set_attribute("correlation.id", correlation_id)

        # Add custom attributes
        if attributes:
            for key, value in attributes.items():
                if value is not None:
                    span.set_attribute(key, value)

        yield span

    except Exception as e:
        if record_exception:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
        raise

    finally:
        span.end()
        context.detach(token)


class _NoOpSpan:
    """No-op span for when tracing is disabled."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op set attribute."""
        pass

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """No-op add event."""
        pass

    def record_exception(self, exception: Exception) -> None:
        """No-op record exception."""
        pass

    def set_status(self, status: Any) -> None:
        """No-op set status."""
        pass

    def is_recording(self) -> bool:
        """Return False for no-op span."""
        return False


def traced(
    name: Optional[str] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> Callable[[F], F]:
    """
    Decorator for automatic span creation around functions.

    Args:
        name: Custom span name (defaults to function name)
        attributes: Static attributes to add to span

    Returns:
        Decorated function

    Example:
        @traced(name="cidx.search.semantic", attributes={"type": "semantic"})
        def semantic_search(query: str):
            ...

        @traced()  # Uses function name as span name
        async def process_request():
            ...
    """

    def decorator(func: F) -> F:
        # Determine span name
        span_name = name or f"cidx.{func.__module__}.{func.__name__}"

        if asyncio.iscoroutinefunction(func):
            # Async function wrapper
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with create_span(span_name, attributes=attributes):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore
        else:
            # Sync function wrapper
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                with create_span(span_name, attributes=attributes):
                    return func(*args, **kwargs)

            return sync_wrapper  # type: ignore

    return decorator


def add_span_attribute(key: str, value: Any) -> None:
    """
    Add an attribute to the current span.

    Args:
        key: Attribute key
        value: Attribute value
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.set_attribute(key, value)
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Failed to add span attribute: {e}")


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """
    Add an event to the current span.

    Args:
        name: Event name
        attributes: Optional event attributes
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span.add_event(name, attributes=attributes)
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"Failed to add span event: {e}")


def reset_spans_state() -> None:
    """Reset module state (for testing)."""
    global _tracer, _tracing_enabled
    _tracer = None
    _tracing_enabled = False
