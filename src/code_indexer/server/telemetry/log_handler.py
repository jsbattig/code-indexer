"""
Log Correlation with Trace Context (Story #701).

This module provides log handlers and formatters that inject OTEL trace
context (trace_id, span_id) into Python logging records, enabling
correlation between logs and traces in observability platforms.

Fields added to log records:
- trace_id (32-char hex) - OTEL trace ID
- span_id (16-char hex) - OTEL span ID
- dd.trace_id - Datadog-compatible trace ID (decimal)
- dd.span_id - Datadog-compatible span ID (decimal)

Usage:
    from src.code_indexer.server.telemetry.log_handler import (
        OTELLogFormatter,
        OTELLogHandler,
    )

    # Add formatter to existing handler
    handler = logging.StreamHandler()
    handler.setFormatter(OTELLogFormatter(
        fmt="%(levelname)s - %(message)s - trace_id=%(trace_id)s"
    ))

    # Or use the handler directly
    handler = OTELLogHandler()
    logger.addHandler(handler)
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Zero values for when no trace context is available
ZERO_TRACE_ID = "0" * 32
ZERO_SPAN_ID = "0" * 16

# Mask for extracting lower 64 bits for Datadog compatibility
# Datadog uses 64-bit trace IDs while OTEL uses 128-bit
DATADOG_64BIT_MASK = 0xFFFFFFFFFFFFFFFF


def get_trace_context() -> Dict[str, str]:
    """
    Get current trace context from active OTEL span.

    Returns:
        Dictionary with trace_id (32-char hex), span_id (16-char hex),
        and Datadog-compatible fields (dd.trace_id, dd.span_id).
    """
    trace_id = ZERO_TRACE_ID
    span_id = ZERO_SPAN_ID
    dd_trace_id = "0"
    dd_span_id = "0"

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        if span and span.is_recording():
            span_context = span.get_span_context()
            if span_context and span_context.is_valid:
                # Format as 32-char hex for trace_id, 16-char hex for span_id
                trace_id = format(span_context.trace_id, "032x")
                span_id = format(span_context.span_id, "016x")

                # Datadog expects decimal representation with lower 64 bits
                dd_trace_id = str(span_context.trace_id & DATADOG_64BIT_MASK)
                dd_span_id = str(span_context.span_id)

    except ImportError:
        # OpenTelemetry not available
        pass
    except Exception as e:
        # Log at debug level to avoid noise
        logger.debug(f"Failed to get trace context: {e}")

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "dd.trace_id": dd_trace_id,
        "dd.span_id": dd_span_id,
    }


class OTELLogFormatter(logging.Formatter):
    """
    Log formatter that injects OTEL trace context into log records.

    Adds trace_id, span_id, and Datadog-compatible fields to log records
    before formatting, allowing them to be included in log output format.

    Example format strings:
        "%(levelname)s - %(message)s - trace_id=%(trace_id)s span_id=%(span_id)s"
        "%(message)s [dd.trace_id=%(dd.trace_id)s dd.span_id=%(dd.span_id)s]"
    """

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with trace context injected.

        Args:
            record: Log record to format

        Returns:
            Formatted log string with trace context
        """
        # Get current trace context
        trace_context = get_trace_context()

        # Inject trace context into record
        record.trace_id = trace_context["trace_id"]
        record.span_id = trace_context["span_id"]

        # Use setattr for dotted attribute names (Datadog fields)
        setattr(record, "dd.trace_id", trace_context["dd.trace_id"])
        setattr(record, "dd.span_id", trace_context["dd.span_id"])

        # Call parent formatter
        return super().format(record)


class OTELLogHandler(logging.Handler):
    """
    Log handler that ensures trace context is available in log records.

    This handler can be used alongside other handlers to ensure trace
    context is injected into all log records processed by it.

    The handler uses OTELLogFormatter by default if no formatter is set.
    """

    def __init__(
        self,
        level: int = logging.NOTSET,
        formatter: Optional[logging.Formatter] = None,
    ) -> None:
        """
        Initialize OTELLogHandler.

        Args:
            level: Logging level for the handler
            formatter: Optional formatter (defaults to OTELLogFormatter)
        """
        super().__init__(level)

        if formatter is None:
            # Default format includes trace context
            self.setFormatter(
                OTELLogFormatter(
                    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s "
                    "[trace_id=%(trace_id)s span_id=%(span_id)s]"
                )
            )
        else:
            self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record with trace context.

        This handler injects trace context but doesn't output directly.
        It's designed to be used with a formatter that includes trace fields.

        Args:
            record: Log record to emit
        """
        try:
            # Ensure trace context is in record
            if not hasattr(record, "trace_id"):
                trace_context = get_trace_context()
                record.trace_id = trace_context["trace_id"]
                record.span_id = trace_context["span_id"]
                setattr(record, "dd.trace_id", trace_context["dd.trace_id"])
                setattr(record, "dd.span_id", trace_context["dd.span_id"])

            # Format the record (trace context injection happens in formatter)
            self.format(record)

        except Exception:
            self.handleError(record)
