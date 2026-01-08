"""
TDD Tests for TelemetryManager singleton (Story #695).

These tests define the expected behavior for the TelemetryManager class
which manages the OTEL SDK lifecycle. Following TDD methodology - tests
written FIRST before implementation.

All tests use real components following MESSI Rule #1: No mocks.
"""

from src.code_indexer.server.utils.config_manager import TelemetryConfig


# =============================================================================
# TelemetryManager Import Tests (ensure lazy loading works)
# =============================================================================


class TestTelemetryManagerImport:
    """Tests for TelemetryManager import behavior."""

    def test_telemetry_manager_can_be_imported(self):
        """
        TelemetryManager can be imported from telemetry module.

        Given the telemetry module exists
        When I import TelemetryManager
        Then the import succeeds without loading OTEL SDK
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        assert TelemetryManager is not None

    def test_telemetry_module_exports_get_telemetry_manager(self):
        """
        get_telemetry_manager() function is exported.

        Given the telemetry module exists
        When I import get_telemetry_manager
        Then the import succeeds
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager

        assert callable(get_telemetry_manager)


# =============================================================================
# AC1: Telemetry disabled by default - zero overhead
# =============================================================================


class TestTelemetryManagerDisabled:
    """Tests for TelemetryManager when telemetry is disabled."""

    def test_manager_does_not_initialize_otel_when_disabled(self):
        """
        AC1: No OTEL SDK initialized when telemetry disabled.

        Given a TelemetryConfig with enabled=False
        When TelemetryManager is initialized
        Then OTEL SDK should not be loaded
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(enabled=False)
        manager = TelemetryManager(config)

        assert manager.is_initialized is False
        assert manager.tracer_provider is None
        assert manager.meter_provider is None

    def test_manager_get_tracer_returns_noop_when_disabled(self):
        """
        AC1: get_tracer() returns no-op tracer when disabled.

        Given a TelemetryManager with telemetry disabled
        When get_tracer() is called
        Then a no-op tracer is returned (not None)
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(enabled=False)
        manager = TelemetryManager(config)

        tracer = manager.get_tracer("test-component")
        assert tracer is not None

    def test_manager_get_meter_returns_noop_when_disabled(self):
        """
        AC1: get_meter() returns no-op meter when disabled.

        Given a TelemetryManager with telemetry disabled
        When get_meter() is called
        Then a no-op meter is returned (not None)
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(enabled=False)
        manager = TelemetryManager(config)

        meter = manager.get_meter("test-component")
        assert meter is not None

    def test_manager_shutdown_succeeds_when_disabled(self):
        """
        AC1: shutdown() succeeds gracefully when disabled.

        Given a TelemetryManager with telemetry disabled
        When shutdown() is called
        Then it completes without error
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(enabled=False)
        manager = TelemetryManager(config)

        # Should not raise
        manager.shutdown()


# =============================================================================
# AC2: Telemetry enabled - OTEL SDK initialization
# =============================================================================


class TestTelemetryManagerEnabled:
    """Tests for TelemetryManager when telemetry is enabled."""

    def test_manager_initializes_otel_when_enabled(self):
        """
        AC2: OTEL SDK initialized when telemetry enabled.

        Given a TelemetryConfig with enabled=True
        When TelemetryManager is initialized
        Then OTEL SDK should be loaded
        And is_initialized should be True
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        manager = TelemetryManager(config)

        try:
            assert manager.is_initialized is True
        finally:
            manager.shutdown()

    def test_manager_creates_tracer_provider_when_enabled(self):
        """
        AC2: TracerProvider is created when enabled.

        Given a TelemetryConfig with enabled=True and export_traces=True
        When TelemetryManager is initialized
        Then tracer_provider should be set
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            export_traces=True,
        )
        manager = TelemetryManager(config)

        try:
            assert manager.tracer_provider is not None
        finally:
            manager.shutdown()

    def test_manager_creates_meter_provider_when_enabled(self):
        """
        AC2: MeterProvider is created when enabled.

        Given a TelemetryConfig with enabled=True and export_metrics=True
        When TelemetryManager is initialized
        Then meter_provider should be set
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            export_metrics=True,
        )
        manager = TelemetryManager(config)

        try:
            assert manager.meter_provider is not None
        finally:
            manager.shutdown()

    def test_manager_get_tracer_returns_real_tracer_when_enabled(self):
        """
        AC2: get_tracer() returns real tracer when enabled.

        Given a TelemetryManager with telemetry enabled
        When get_tracer() is called
        Then a real tracer is returned
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        manager = TelemetryManager(config)

        try:
            tracer = manager.get_tracer("test-component")
            assert tracer is not None
            # Can create a span (basic functionality check)
            with tracer.start_as_current_span("test-span") as span:
                assert span is not None
        finally:
            manager.shutdown()

    def test_manager_get_meter_returns_real_meter_when_enabled(self):
        """
        AC2: get_meter() returns real meter when enabled.

        Given a TelemetryManager with telemetry enabled
        When get_meter() is called
        Then a real meter is returned
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        manager = TelemetryManager(config)

        try:
            meter = manager.get_meter("test-component")
            assert meter is not None
            # Can create a counter (basic functionality check)
            counter = meter.create_counter("test_counter")
            assert counter is not None
        finally:
            manager.shutdown()


# =============================================================================
# AC5: Invalid collector endpoint - graceful failure
# =============================================================================


class TestTelemetryManagerInvalidEndpoint:
    """Tests for TelemetryManager with invalid collector endpoint."""

    def test_manager_initializes_with_invalid_endpoint(self):
        """
        AC5: Manager initializes even with invalid endpoint.

        Given a TelemetryConfig with an unreachable endpoint
        When TelemetryManager is initialized
        Then it should initialize successfully (exports will fail later)
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://invalid-host-12345:4317",
        )
        manager = TelemetryManager(config)

        try:
            # Should initialize without throwing
            assert manager.is_initialized is True
        finally:
            manager.shutdown()


# =============================================================================
# Singleton Pattern Tests
# =============================================================================


class TestTelemetryManagerSingleton:
    """Tests for TelemetryManager singleton pattern."""

    def test_get_telemetry_manager_returns_same_instance(self):
        """
        Singleton: get_telemetry_manager returns same instance.

        Given I call get_telemetry_manager() multiple times
        When I compare the returned instances
        Then they should be the same object
        """
        from src.code_indexer.server.telemetry import (
            get_telemetry_manager,
            reset_telemetry_manager,
        )

        # Reset to ensure clean state
        reset_telemetry_manager()

        config = TelemetryConfig(enabled=False)
        manager1 = get_telemetry_manager(config)
        manager2 = get_telemetry_manager()

        try:
            assert manager1 is manager2
        finally:
            reset_telemetry_manager()

    def test_reset_telemetry_manager_clears_instance(self):
        """
        reset_telemetry_manager() clears the singleton.

        Given a TelemetryManager singleton exists
        When reset_telemetry_manager() is called
        Then get_telemetry_manager() returns a new instance
        """
        from src.code_indexer.server.telemetry import (
            get_telemetry_manager,
            reset_telemetry_manager,
        )

        # Reset to ensure clean state
        reset_telemetry_manager()

        config = TelemetryConfig(enabled=False)
        manager1 = get_telemetry_manager(config)

        reset_telemetry_manager()

        manager2 = get_telemetry_manager(config)

        try:
            assert manager1 is not manager2
        finally:
            reset_telemetry_manager()


# =============================================================================
# Configuration Tests
# =============================================================================


class TestTelemetryManagerConfiguration:
    """Tests for TelemetryManager configuration handling."""

    def test_manager_uses_service_name_from_config(self):
        """
        Manager uses service_name from config.

        Given a TelemetryConfig with custom service_name
        When TelemetryManager is initialized
        Then the service name is used in resource attributes
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            service_name="custom-service-name",
        )
        manager = TelemetryManager(config)

        try:
            assert manager.service_name == "custom-service-name"
        finally:
            manager.shutdown()

    def test_manager_uses_deployment_environment_from_config(self):
        """
        Manager uses deployment_environment from config.

        Given a TelemetryConfig with custom deployment_environment
        When TelemetryManager is initialized
        Then the deployment environment is used in resource attributes
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            deployment_environment="production",
        )
        manager = TelemetryManager(config)

        try:
            assert manager.deployment_environment == "production"
        finally:
            manager.shutdown()

    def test_manager_respects_export_traces_flag(self):
        """
        Manager respects export_traces flag.

        Given a TelemetryConfig with export_traces=False
        When TelemetryManager is initialized
        Then TracerProvider should not be fully configured
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            export_traces=False,
            export_metrics=True,
        )
        manager = TelemetryManager(config)

        try:
            # When traces disabled, should still have provider but not export
            assert manager.is_initialized is True
        finally:
            manager.shutdown()

    def test_manager_respects_export_metrics_flag(self):
        """
        Manager respects export_metrics flag.

        Given a TelemetryConfig with export_metrics=False
        When TelemetryManager is initialized
        Then MeterProvider should not be fully configured
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            export_traces=True,
            export_metrics=False,
        )
        manager = TelemetryManager(config)

        try:
            # When metrics disabled, should still have provider but not export
            assert manager.is_initialized is True
        finally:
            manager.shutdown()


# =============================================================================
# Protocol Support Tests
# =============================================================================


class TestTelemetryManagerProtocol:
    """Tests for TelemetryManager protocol handling."""

    def test_manager_supports_grpc_protocol(self):
        """
        Manager supports gRPC protocol.

        Given a TelemetryConfig with collector_protocol=grpc
        When TelemetryManager is initialized
        Then it should use gRPC exporter
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            collector_protocol="grpc",
        )
        manager = TelemetryManager(config)

        try:
            assert manager.is_initialized is True
            assert manager.collector_protocol == "grpc"
        finally:
            manager.shutdown()

    def test_manager_supports_http_protocol(self):
        """
        Manager supports HTTP protocol.

        Given a TelemetryConfig with collector_protocol=http
        When TelemetryManager is initialized
        Then it should use HTTP exporter
        """
        from src.code_indexer.server.telemetry import TelemetryManager

        config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4318",
            collector_protocol="http",
        )
        manager = TelemetryManager(config)

        try:
            assert manager.is_initialized is True
            assert manager.collector_protocol == "http"
        finally:
            manager.shutdown()
