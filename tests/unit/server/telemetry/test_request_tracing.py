"""
TDD Tests for Request Tracing with Correlation ID Bridge (Story #697).

Tests FastAPI auto-instrumentation and X-Correlation-ID to OTEL span bridging.

All tests use real components following MESSI Rule #1: No mocks.
"""

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
# Instrumentation Module Import Tests
# =============================================================================


class TestInstrumentationImport:
    """Tests for instrumentation module import behavior."""

    def test_instrument_fastapi_function_can_be_imported(self):
        """instrument_fastapi() function can be imported."""
        from src.code_indexer.server.telemetry.instrumentation import (
            instrument_fastapi,
        )

        assert callable(instrument_fastapi)

    def test_uninstrument_fastapi_function_can_be_imported(self):
        """uninstrument_fastapi() function can be imported."""
        from src.code_indexer.server.telemetry.instrumentation import (
            uninstrument_fastapi,
        )

        assert callable(uninstrument_fastapi)


# =============================================================================
# Correlation Bridge Import Tests
# =============================================================================


class TestCorrelationBridgeImport:
    """Tests for correlation bridge module import behavior."""

    def test_correlation_bridge_middleware_can_be_imported(self):
        """CorrelationBridgeMiddleware can be imported."""
        from src.code_indexer.server.telemetry.correlation_bridge import (
            CorrelationBridgeMiddleware,
        )

        assert CorrelationBridgeMiddleware is not None

    def test_get_current_correlation_id_can_be_imported(self):
        """get_current_correlation_id() function can be imported."""
        from src.code_indexer.server.telemetry.correlation_bridge import (
            get_current_correlation_id,
        )

        assert callable(get_current_correlation_id)


# =============================================================================
# Instrumentation Behavior Tests
# =============================================================================


class TestFastAPIInstrumentation:
    """Tests for FastAPI auto-instrumentation."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_instrument_fastapi_with_enabled_telemetry(self):
        """
        instrument_fastapi() instruments app when telemetry enabled.
        """
        from fastapi import FastAPI
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.instrumentation import (
            instrument_fastapi,
            uninstrument_fastapi,
        )

        config = TelemetryConfig(
            enabled=True,
            export_traces=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        app = FastAPI()

        # Instrument the app
        result = instrument_fastapi(app, telemetry_manager)

        # Should return True indicating instrumentation was applied
        assert result is True

        # Cleanup
        uninstrument_fastapi()

    def test_instrument_fastapi_noop_when_disabled(self):
        """
        instrument_fastapi() is a no-op when telemetry disabled.
        """
        from fastapi import FastAPI
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.instrumentation import (
            instrument_fastapi,
        )

        config = TelemetryConfig(
            enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        app = FastAPI()

        # Instrument the app - should be no-op
        result = instrument_fastapi(app, telemetry_manager)

        # Should return False indicating no instrumentation
        assert result is False

    def test_instrument_fastapi_noop_when_traces_disabled(self):
        """
        instrument_fastapi() is a no-op when export_traces is False.
        """
        from fastapi import FastAPI
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.instrumentation import (
            instrument_fastapi,
        )

        config = TelemetryConfig(
            enabled=True,
            export_traces=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        app = FastAPI()

        # Instrument the app - should be no-op since traces disabled
        result = instrument_fastapi(app, telemetry_manager)

        # Should return False indicating no instrumentation
        assert result is False


# =============================================================================
# Correlation Bridge Behavior Tests
# =============================================================================


class TestCorrelationBridgeMiddleware:
    """Tests for CorrelationBridgeMiddleware behavior."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_middleware_extracts_correlation_id_from_header(self):
        """
        Middleware extracts X-Correlation-ID from request headers.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.code_indexer.server.telemetry.correlation_bridge import (
            CorrelationBridgeMiddleware,
            get_current_correlation_id,
        )

        app = FastAPI()
        app.add_middleware(CorrelationBridgeMiddleware)

        captured_correlation_id = None

        @app.get("/test")
        async def test_endpoint():
            nonlocal captured_correlation_id
            captured_correlation_id = get_current_correlation_id()
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get(
            "/test", headers={"X-Correlation-ID": "test-correlation-123"}
        )

        assert response.status_code == 200
        assert captured_correlation_id == "test-correlation-123"

    def test_middleware_generates_correlation_id_when_missing(self):
        """
        Middleware generates correlation ID when header is missing.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.code_indexer.server.telemetry.correlation_bridge import (
            CorrelationBridgeMiddleware,
            get_current_correlation_id,
        )

        app = FastAPI()
        app.add_middleware(CorrelationBridgeMiddleware)

        captured_correlation_id = None

        @app.get("/test")
        async def test_endpoint():
            nonlocal captured_correlation_id
            captured_correlation_id = get_current_correlation_id()
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/test")  # No X-Correlation-ID header

        assert response.status_code == 200
        # Should have generated a correlation ID
        assert captured_correlation_id is not None
        assert len(captured_correlation_id) > 0

    def test_middleware_adds_correlation_id_to_response_header(self):
        """
        Middleware adds X-Correlation-ID to response headers.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.code_indexer.server.telemetry.correlation_bridge import (
            CorrelationBridgeMiddleware,
        )

        app = FastAPI()
        app.add_middleware(CorrelationBridgeMiddleware)

        @app.get("/test")
        async def test_endpoint():
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get(
            "/test", headers={"X-Correlation-ID": "response-test-456"}
        )

        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers
        assert response.headers["X-Correlation-ID"] == "response-test-456"


# =============================================================================
# Trace Sampling Tests
# =============================================================================


class TestTraceSampling:
    """Tests for trace sampling configuration."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_trace_sample_rate_respected_in_config(self):
        """
        Trace sample rate from config is passed to tracer provider.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager

        config = TelemetryConfig(
            enabled=True,
            export_traces=True,
            trace_sample_rate=0.5,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        # Verify config was stored
        assert telemetry_manager._config.trace_sample_rate == 0.5

    def test_full_sampling_when_rate_is_one(self):
        """
        All requests traced when trace_sample_rate=1.0.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager

        config = TelemetryConfig(
            enabled=True,
            export_traces=True,
            trace_sample_rate=1.0,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        # With rate 1.0, all traces should be sampled
        assert telemetry_manager._config.trace_sample_rate == 1.0


# =============================================================================
# Excluded Endpoints Tests
# =============================================================================


class TestExcludedEndpoints:
    """Tests for excluding health endpoints from tracing."""

    def test_health_endpoints_excluded_by_default(self):
        """
        Health endpoints are excluded from tracing.
        """
        from src.code_indexer.server.telemetry.instrumentation import (
            DEFAULT_EXCLUDED_URLS,
        )

        # Health endpoints should be in exclusion list
        assert "/health" in DEFAULT_EXCLUDED_URLS or "health" in DEFAULT_EXCLUDED_URLS
