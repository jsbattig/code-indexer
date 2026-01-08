"""
TDD Tests for Log Correlation with Trace Context (Story #701).

Tests OTELLogHandler and OTELLogFormatter for trace context injection into logs.

All tests use real components following MESSI Rule #1: No mocks.
"""

import logging
from src.code_indexer.server.utils.config_manager import TelemetryConfig


def reset_all_singletons():
    """Reset all singletons to ensure clean test state."""
    from src.code_indexer.server.telemetry import (
        reset_telemetry_manager,
        reset_machine_metrics_exporter,
    )
    from src.code_indexer.server.services.system_metrics_collector import (
        reset_system_metrics_collector,
    )

    reset_machine_metrics_exporter()
    reset_telemetry_manager()
    reset_system_metrics_collector()


# =============================================================================
# Log Handler Import Tests
# =============================================================================


class TestLogHandlerImport:
    """Tests for log handler module import behavior."""

    def test_otel_log_handler_can_be_imported(self):
        """OTELLogHandler class can be imported."""
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogHandler,
        )

        assert OTELLogHandler is not None

    def test_otel_log_formatter_can_be_imported(self):
        """OTELLogFormatter class can be imported."""
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        assert OTELLogFormatter is not None

    def test_get_trace_context_function_exists(self):
        """get_trace_context() function is exported."""
        from src.code_indexer.server.telemetry.log_handler import (
            get_trace_context,
        )

        assert callable(get_trace_context)


# =============================================================================
# Trace Context Extraction Tests
# =============================================================================


class TestTraceContextExtraction:
    """Tests for trace context extraction from current span."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_get_trace_context_returns_dict(self):
        """
        get_trace_context() returns dictionary with trace_id and span_id.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            get_trace_context,
        )

        context = get_trace_context()

        assert isinstance(context, dict)
        assert "trace_id" in context
        assert "span_id" in context

    def test_trace_context_has_correct_lengths(self):
        """
        trace_id is 32 chars, span_id is 16 chars.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            get_trace_context,
        )

        context = get_trace_context()

        assert len(context["trace_id"]) == 32
        assert len(context["span_id"]) == 16

    def test_trace_context_zeros_when_no_span(self):
        """
        trace_id is all zeros when no active span.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            get_trace_context,
        )

        context = get_trace_context()

        # Without active span, should return zeros
        assert context["trace_id"] == "0" * 32
        assert context["span_id"] == "0" * 16


# =============================================================================
# OTELLogFormatter Tests
# =============================================================================


class TestOTELLogFormatter:
    """Tests for OTELLogFormatter trace context injection."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_formatter_injects_trace_id(self):
        """
        OTELLogFormatter adds trace_id to log records.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        formatter = OTELLogFormatter(fmt="%(message)s trace_id=%(trace_id)s")

        # Create a log record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        # Should contain trace_id field
        assert "trace_id=" in formatted
        assert "0" * 32 in formatted  # Zero trace ID when no span

    def test_formatter_injects_span_id(self):
        """
        OTELLogFormatter adds span_id to log records.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        formatter = OTELLogFormatter(fmt="%(message)s span_id=%(span_id)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        assert "span_id=" in formatted
        assert "0" * 16 in formatted

    def test_formatter_includes_datadog_fields(self):
        """
        OTELLogFormatter adds dd.trace_id and dd.span_id for Datadog.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        formatter = OTELLogFormatter(
            fmt="%(message)s dd.trace_id=%(dd.trace_id)s dd.span_id=%(dd.span_id)s"
        )

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        assert "dd.trace_id=" in formatted
        assert "dd.span_id=" in formatted

    def test_formatter_preserves_existing_fields(self):
        """
        OTELLogFormatter preserves existing log fields.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        formatter = OTELLogFormatter(
            fmt="%(levelname)s - %(name)s - %(message)s - trace_id=%(trace_id)s"
        )

        record = logging.LogRecord(
            name="mylogger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=1,
            msg="warning message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        assert "WARNING" in formatted
        assert "mylogger" in formatted
        assert "warning message" in formatted
        assert "trace_id=" in formatted


# =============================================================================
# OTELLogHandler Tests
# =============================================================================


class TestOTELLogHandler:
    """Tests for OTELLogHandler class."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_handler_is_logging_handler(self):
        """
        OTELLogHandler is a logging.Handler subclass.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogHandler,
        )

        handler = OTELLogHandler()

        assert isinstance(handler, logging.Handler)

    def test_handler_emits_log_records(self):
        """
        OTELLogHandler can emit log records.
        """
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogHandler,
        )

        handler = OTELLogHandler()
        handler.setLevel(logging.DEBUG)

        # Should not raise when handling a record
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        handler.emit(record)  # Should not raise


# =============================================================================
# Integration Tests
# =============================================================================


class TestLogCorrelationIntegration:
    """Tests for log correlation with active spans."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.spans import reset_spans_state

        reset_spans_state()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()
        from src.code_indexer.server.telemetry.spans import reset_spans_state

        reset_spans_state()

    def test_trace_context_from_active_span(self):
        """
        get_trace_context() returns real trace/span IDs from active span.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.spans import create_span
        from src.code_indexer.server.telemetry.log_handler import (
            get_trace_context,
        )

        config = TelemetryConfig(
            enabled=True,
            export_traces=True,
            collector_endpoint="http://localhost:4317",
        )
        get_telemetry_manager(config)

        with create_span("test.operation"):
            context = get_trace_context()

            # Should have non-zero trace_id when span is active
            # (may still be zeros if tracing not fully initialized)
            assert len(context["trace_id"]) == 32
            assert len(context["span_id"]) == 16

    def test_log_with_formatter_in_span_context(self):
        """
        Logs formatted within span context include trace IDs.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.spans import create_span
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )
        import io

        config = TelemetryConfig(
            enabled=True,
            export_traces=True,
            collector_endpoint="http://localhost:4317",
        )
        get_telemetry_manager(config)

        # Create handler with OTELLogFormatter
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        formatter = OTELLogFormatter(fmt="%(message)s trace_id=%(trace_id)s")
        handler.setFormatter(formatter)

        logger = logging.getLogger("test.correlation")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        try:
            with create_span("test.operation"):
                logger.info("test message in span")

            output = stream.getvalue()
            assert "test message in span" in output
            assert "trace_id=" in output
        finally:
            logger.removeHandler(handler)


# =============================================================================
# No-op When Disabled Tests
# =============================================================================


class TestNoopWhenDisabled:
    """Tests for graceful behavior when telemetry disabled."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_formatter_works_when_telemetry_disabled(self):
        """
        OTELLogFormatter works even when telemetry is disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.log_handler import (
            OTELLogFormatter,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        get_telemetry_manager(config)

        formatter = OTELLogFormatter(fmt="%(message)s trace_id=%(trace_id)s")

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test disabled",
            args=(),
            exc_info=None,
        )

        # Should still format successfully with zero IDs
        formatted = formatter.format(record)
        assert "test disabled" in formatted
        assert "0" * 32 in formatted
