"""
TDD Tests for MachineMetricsExporter (Story #696).

Tests the OTEL observable gauges that export machine metrics from
SystemMetricsCollector to the OTEL collector.

All tests use real components following MESSI Rule #1: No mocks.
"""

import socket

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
# MachineMetricsExporter Import Tests
# =============================================================================


class TestMachineMetricsExporterImport:
    """Tests for MachineMetricsExporter import behavior."""

    def test_machine_metrics_exporter_can_be_imported(self):
        """MachineMetricsExporter can be imported."""
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        assert MachineMetricsExporter is not None

    def test_get_machine_metrics_exporter_function_exists(self):
        """get_machine_metrics_exporter() function is exported."""
        from src.code_indexer.server.telemetry.machine_metrics import (
            get_machine_metrics_exporter,
        )

        assert callable(get_machine_metrics_exporter)


# =============================================================================
# MachineMetricsExporter Creation Tests
# =============================================================================


class TestMachineMetricsExporterCreation:
    """Tests for MachineMetricsExporter instantiation."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_exporter_created_when_telemetry_and_machine_metrics_enabled(self):
        """
        MachineMetricsExporter is created when both telemetry and machine_metrics are enabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        exporter = MachineMetricsExporter(telemetry_manager)

        assert exporter is not None
        assert exporter.is_active

    def test_exporter_not_active_when_machine_metrics_disabled(self):
        """
        MachineMetricsExporter is not active when machine_metrics is disabled.
        """
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=False,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)

        exporter = MachineMetricsExporter(
            telemetry_manager, machine_metrics_enabled=False
        )

        assert exporter is not None
        assert not exporter.is_active


# =============================================================================
# Observable Gauge Registration Tests
# =============================================================================


class TestMachineMetricsGaugeRegistration:
    """Tests for observable gauge registration."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_cpu_usage_gauge_registered(self):
        """system.cpu.usage gauge is registered."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        # The gauge should be registered
        assert "system.cpu.usage" in exporter.registered_gauges

    def test_memory_usage_gauge_registered(self):
        """system.memory.usage gauge is registered."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        assert "system.memory.usage" in exporter.registered_gauges

    def test_disk_free_gauge_registered(self):
        """system.disk.free gauge is registered."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        assert "system.disk.free" in exporter.registered_gauges

    def test_network_io_gauges_registered(self):
        """Network I/O gauges are registered."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        assert "system.network.io.receive" in exporter.registered_gauges
        assert "system.network.io.transmit" in exporter.registered_gauges


# =============================================================================
# Host Identification Tests
# =============================================================================


class TestMachineMetricsHostIdentification:
    """Tests for host identification attributes."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_host_name_attribute_set(self):
        """Metrics include host.name attribute."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
            service_name="test-service",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        # Host name should be set
        assert exporter.host_name is not None
        assert len(exporter.host_name) > 0
        # Should match actual hostname
        assert exporter.host_name == socket.gethostname()

    def test_service_name_attribute_set(self):
        """Metrics include service.name attribute."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
            service_name="test-cidx-server",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        assert exporter.service_name == "test-cidx-server"


# =============================================================================
# Metric Collection Callback Tests
# =============================================================================


class TestMachineMetricsCallbacks:
    """Tests for metric collection callbacks."""

    def setup_method(self):
        """Reset singletons before each test."""
        reset_all_singletons()

    def teardown_method(self):
        """Reset singletons after each test."""
        reset_all_singletons()

    def test_cpu_callback_returns_valid_value(self):
        """CPU callback returns value between 0 and 100."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        # Call the CPU callback directly
        observations = list(exporter._cpu_callback(None))
        assert len(observations) == 1
        value, attributes = observations[0]
        assert 0.0 <= value <= 100.0

    def test_memory_callback_returns_valid_value(self):
        """Memory callback returns value between 0 and 100."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        observations = list(exporter._memory_callback(None))
        assert len(observations) == 1
        value, attributes = observations[0]
        assert 0.0 <= value <= 100.0

    def test_callbacks_include_attributes(self):
        """Callbacks include host.name and service.name attributes."""
        from src.code_indexer.server.telemetry import get_telemetry_manager
        from src.code_indexer.server.telemetry.machine_metrics import (
            MachineMetricsExporter,
        )

        config = TelemetryConfig(
            enabled=True,
            machine_metrics_enabled=True,
            collector_endpoint="http://localhost:4317",
            service_name="test-service",
        )
        telemetry_manager = get_telemetry_manager(config)
        exporter = MachineMetricsExporter(telemetry_manager)

        observations = list(exporter._cpu_callback(None))
        _, attributes = observations[0]

        assert "host.name" in attributes
        assert "service.name" in attributes
        assert attributes["service.name"] == "test-service"
