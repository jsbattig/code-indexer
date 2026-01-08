"""
TDD Tests for TelemetryConfig dataclass (Story #695).

These tests define the expected behavior for the TelemetryConfig dataclass
and its integration with ServerConfig. Following TDD methodology - tests
written FIRST before implementation.

All tests use real components following MESSI Rule #1: No mocks.
"""

import json
import os
import tempfile

import pytest

from src.code_indexer.server.utils.config_manager import (
    ServerConfig,
    ServerConfigManager,
    TelemetryConfig,
)


# =============================================================================
# AC1: Default telemetry configuration
# =============================================================================


class TestTelemetryConfigDefaults:
    """Tests for TelemetryConfig default values."""

    def test_telemetry_config_disabled_by_default(self):
        """
        AC1: Telemetry disabled by default.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then enabled should be False
        """
        config = TelemetryConfig()
        assert config.enabled is False, "Telemetry should be disabled by default"

    def test_telemetry_config_default_collector_endpoint(self):
        """
        AC1: Default collector endpoint is localhost:4317.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then collector_endpoint should be http://localhost:4317
        """
        config = TelemetryConfig()
        assert (
            config.collector_endpoint == "http://localhost:4317"
        ), "Default endpoint should be http://localhost:4317"

    def test_telemetry_config_default_collector_protocol(self):
        """
        AC1: Default collector protocol is grpc.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then collector_protocol should be grpc
        """
        config = TelemetryConfig()
        assert config.collector_protocol == "grpc", "Default protocol should be grpc"

    def test_telemetry_config_default_service_name(self):
        """
        AC1: Default service name is cidx-server.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then service_name should be cidx-server
        """
        config = TelemetryConfig()
        assert (
            config.service_name == "cidx-server"
        ), "Default service_name should be cidx-server"

    def test_telemetry_config_default_export_flags(self):
        """
        AC1: Default export flags - traces/metrics True, logs False.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then export_traces and export_metrics should be True
        And export_logs should be False
        """
        config = TelemetryConfig()
        assert config.export_traces is True, "export_traces should be True by default"
        assert config.export_metrics is True, "export_metrics should be True by default"
        assert config.export_logs is False, "export_logs should be False by default"

    def test_telemetry_config_default_machine_metrics(self):
        """
        AC1: Default machine metrics settings.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then machine_metrics_enabled should be True
        And machine_metrics_interval_seconds should be 60
        """
        config = TelemetryConfig()
        assert (
            config.machine_metrics_enabled is True
        ), "machine_metrics_enabled should be True by default"
        assert (
            config.machine_metrics_interval_seconds == 60
        ), "machine_metrics_interval_seconds should be 60 by default"

    def test_telemetry_config_default_trace_sample_rate(self):
        """
        AC1: Default trace sample rate is 1.0 (100%).

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then trace_sample_rate should be 1.0
        """
        config = TelemetryConfig()
        assert (
            config.trace_sample_rate == 1.0
        ), "trace_sample_rate should be 1.0 by default"

    def test_telemetry_config_default_deployment_environment(self):
        """
        AC1: Default deployment environment is development.

        Given a fresh TelemetryConfig instance
        When created with no arguments
        Then deployment_environment should be development
        """
        config = TelemetryConfig()
        assert (
            config.deployment_environment == "development"
        ), "deployment_environment should be development by default"


# =============================================================================
# AC1: ServerConfig includes telemetry_config
# =============================================================================


class TestServerConfigTelemetryIntegration:
    """Tests for TelemetryConfig integration with ServerConfig."""

    def test_serverconfig_has_telemetry_config_field(self):
        """
        AC1: ServerConfig includes telemetry_config field.

        Given a new ServerConfig instance
        When created with defaults
        Then it should have a telemetry_config field of type TelemetryConfig
        """
        config = ServerConfig(server_dir="/tmp/test")
        assert hasattr(
            config, "telemetry_config"
        ), "ServerConfig should have telemetry_config field"
        assert isinstance(
            config.telemetry_config, TelemetryConfig
        ), "telemetry_config should be TelemetryConfig instance"

    def test_serverconfig_telemetry_disabled_by_default(self):
        """
        AC1: Fresh ServerConfig has telemetry disabled.

        Given a new ServerConfig instance
        When created with defaults
        Then telemetry_config.enabled should be False
        """
        config = ServerConfig(server_dir="/tmp/test")
        assert (
            config.telemetry_config.enabled is False
        ), "Telemetry should be disabled by default in ServerConfig"


# =============================================================================
# AC2: Enable telemetry via configuration file
# =============================================================================


class TestTelemetryConfigSerialization:
    """Tests for TelemetryConfig JSON serialization/deserialization."""

    def test_telemetry_config_serialization(self):
        """
        AC2: TelemetryConfig serializes to JSON.

        Given a ServerConfig with custom telemetry settings
        When serialized via ServerConfigManager
        Then the JSON includes all telemetry fields
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServerConfigManager(tmpdir)
            config = ServerConfig(server_dir=tmpdir)
            config.telemetry_config = TelemetryConfig(
                enabled=True,
                collector_endpoint="http://collector:4317",
                service_name="test-service",
                trace_sample_rate=0.5,
            )

            manager.save_config(config)

            # Read raw JSON to verify serialization
            with open(manager.config_file_path, "r") as f:
                config_dict = json.load(f)

            assert (
                "telemetry_config" in config_dict
            ), "Serialized config should include telemetry_config"
            telemetry = config_dict["telemetry_config"]
            assert telemetry["enabled"] is True
            assert telemetry["collector_endpoint"] == "http://collector:4317"
            assert telemetry["service_name"] == "test-service"
            assert telemetry["trace_sample_rate"] == 0.5

    def test_telemetry_config_deserialization(self):
        """
        AC2: TelemetryConfig deserializes from JSON.

        Given a config.json with telemetry settings
        When loaded via ServerConfigManager
        Then the TelemetryConfig is properly restored
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServerConfigManager(tmpdir)

            # Create config with telemetry settings
            config_dict = {
                "server_dir": tmpdir,
                "telemetry_config": {
                    "enabled": True,
                    "collector_endpoint": "http://collector:4317",
                    "collector_protocol": "http",
                    "service_name": "test-service",
                    "export_traces": True,
                    "export_metrics": False,
                    "export_logs": True,
                    "machine_metrics_enabled": False,
                    "machine_metrics_interval_seconds": 30,
                    "trace_sample_rate": 0.75,
                    "deployment_environment": "production",
                },
            }

            with open(manager.config_file_path, "w") as f:
                json.dump(config_dict, f)

            config = manager.load_config()

            assert config is not None
            assert config.telemetry_config.enabled is True
            assert config.telemetry_config.collector_endpoint == "http://collector:4317"
            assert config.telemetry_config.collector_protocol == "http"
            assert config.telemetry_config.service_name == "test-service"
            assert config.telemetry_config.export_traces is True
            assert config.telemetry_config.export_metrics is False
            assert config.telemetry_config.export_logs is True
            assert config.telemetry_config.machine_metrics_enabled is False
            assert config.telemetry_config.machine_metrics_interval_seconds == 30
            assert config.telemetry_config.trace_sample_rate == 0.75
            assert config.telemetry_config.deployment_environment == "production"

    def test_telemetry_config_backward_compatibility(self):
        """
        AC2: Old configs without telemetry_config load successfully.

        Given an old config.json without telemetry_config
        When loaded via ServerConfigManager
        Then it loads with default TelemetryConfig (disabled)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServerConfigManager(tmpdir)

            # Create old config WITHOUT telemetry_config
            old_config = {
                "server_dir": tmpdir,
                "host": "127.0.0.1",
                "port": 8000,
            }

            with open(manager.config_file_path, "w") as f:
                json.dump(old_config, f)

            config = manager.load_config()

            assert config is not None, "Old config should load successfully"
            assert hasattr(
                config, "telemetry_config"
            ), "Should have telemetry_config field"
            assert (
                config.telemetry_config.enabled is False
            ), "Telemetry should be disabled for old configs"

    def test_telemetry_config_roundtrip(self):
        """
        AC2: Save + Load roundtrip preserves all telemetry fields.

        Given a ServerConfig with custom telemetry settings
        When saved and reloaded
        Then all telemetry fields are preserved
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = ServerConfigManager(tmpdir)

            original = ServerConfig(server_dir=tmpdir)
            original.telemetry_config = TelemetryConfig(
                enabled=True,
                collector_endpoint="http://custom:4317",
                collector_protocol="http",
                service_name="custom-service",
                export_traces=True,
                export_metrics=True,
                export_logs=True,
                machine_metrics_enabled=True,
                machine_metrics_interval_seconds=120,
                trace_sample_rate=0.25,
                deployment_environment="staging",
            )

            manager.save_config(original)
            loaded = manager.load_config()

            assert loaded is not None
            assert loaded.telemetry_config.enabled == original.telemetry_config.enabled
            assert (
                loaded.telemetry_config.collector_endpoint
                == original.telemetry_config.collector_endpoint
            )
            assert (
                loaded.telemetry_config.collector_protocol
                == original.telemetry_config.collector_protocol
            )
            assert (
                loaded.telemetry_config.service_name
                == original.telemetry_config.service_name
            )
            assert (
                loaded.telemetry_config.export_traces
                == original.telemetry_config.export_traces
            )
            assert (
                loaded.telemetry_config.export_metrics
                == original.telemetry_config.export_metrics
            )
            assert (
                loaded.telemetry_config.export_logs
                == original.telemetry_config.export_logs
            )
            assert (
                loaded.telemetry_config.machine_metrics_enabled
                == original.telemetry_config.machine_metrics_enabled
            )
            assert (
                loaded.telemetry_config.machine_metrics_interval_seconds
                == original.telemetry_config.machine_metrics_interval_seconds
            )
            assert (
                loaded.telemetry_config.trace_sample_rate
                == original.telemetry_config.trace_sample_rate
            )
            assert (
                loaded.telemetry_config.deployment_environment
                == original.telemetry_config.deployment_environment
            )


# =============================================================================
# AC3: Environment variable overrides
# =============================================================================


class TestTelemetryConfigEnvOverrides:
    """Tests for environment variable overrides of telemetry config."""

    def test_env_override_telemetry_enabled(self):
        """
        AC3: CIDX_TELEMETRY_ENABLED overrides config.

        Given a config with telemetry disabled
        When CIDX_TELEMETRY_ENABLED=true is set
        Then apply_env_overrides enables telemetry
        """
        try:
            os.environ["CIDX_TELEMETRY_ENABLED"] = "true"

            config = ServerConfig(server_dir="/tmp/test")
            assert config.telemetry_config.enabled is False

            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.enabled is True
            ), "CIDX_TELEMETRY_ENABLED=true should enable telemetry"
        finally:
            os.environ.pop("CIDX_TELEMETRY_ENABLED", None)

    def test_env_override_telemetry_disabled(self):
        """
        AC3: CIDX_TELEMETRY_ENABLED=false overrides config.

        Given a config with telemetry enabled
        When CIDX_TELEMETRY_ENABLED=false is set
        Then apply_env_overrides disables telemetry
        """
        try:
            os.environ["CIDX_TELEMETRY_ENABLED"] = "false"

            config = ServerConfig(server_dir="/tmp/test")
            config.telemetry_config = TelemetryConfig(enabled=True)

            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.enabled is False
            ), "CIDX_TELEMETRY_ENABLED=false should disable telemetry"
        finally:
            os.environ.pop("CIDX_TELEMETRY_ENABLED", None)

    def test_env_override_collector_endpoint(self):
        """
        AC3: CIDX_OTEL_COLLECTOR_ENDPOINT overrides config.

        Given a config with default collector endpoint
        When CIDX_OTEL_COLLECTOR_ENDPOINT is set
        Then apply_env_overrides uses the env value
        """
        try:
            os.environ["CIDX_OTEL_COLLECTOR_ENDPOINT"] = "http://env-collector:4317"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.collector_endpoint
                == "http://env-collector:4317"
            ), "CIDX_OTEL_COLLECTOR_ENDPOINT should override endpoint"
        finally:
            os.environ.pop("CIDX_OTEL_COLLECTOR_ENDPOINT", None)

    def test_env_override_collector_protocol(self):
        """
        AC3: CIDX_OTEL_COLLECTOR_PROTOCOL overrides config.

        Given a config with default protocol (grpc)
        When CIDX_OTEL_COLLECTOR_PROTOCOL=http is set
        Then apply_env_overrides uses the env value
        """
        try:
            os.environ["CIDX_OTEL_COLLECTOR_PROTOCOL"] = "http"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.collector_protocol == "http"
            ), "CIDX_OTEL_COLLECTOR_PROTOCOL should override protocol"
        finally:
            os.environ.pop("CIDX_OTEL_COLLECTOR_PROTOCOL", None)

    def test_env_override_service_name(self):
        """
        AC3: CIDX_OTEL_SERVICE_NAME overrides config.

        Given a config with default service name
        When CIDX_OTEL_SERVICE_NAME is set
        Then apply_env_overrides uses the env value
        """
        try:
            os.environ["CIDX_OTEL_SERVICE_NAME"] = "env-service-name"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.service_name == "env-service-name"
            ), "CIDX_OTEL_SERVICE_NAME should override service_name"
        finally:
            os.environ.pop("CIDX_OTEL_SERVICE_NAME", None)

    def test_env_override_trace_sample_rate(self):
        """
        AC3: CIDX_OTEL_TRACE_SAMPLE_RATE overrides config.

        Given a config with default trace sample rate
        When CIDX_OTEL_TRACE_SAMPLE_RATE=0.5 is set
        Then apply_env_overrides uses the env value
        """
        try:
            os.environ["CIDX_OTEL_TRACE_SAMPLE_RATE"] = "0.5"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.trace_sample_rate == 0.5
            ), "CIDX_OTEL_TRACE_SAMPLE_RATE should override trace_sample_rate"
        finally:
            os.environ.pop("CIDX_OTEL_TRACE_SAMPLE_RATE", None)

    def test_env_override_deployment_environment(self):
        """
        AC3: CIDX_DEPLOYMENT_ENVIRONMENT overrides config.

        Given a config with default deployment environment
        When CIDX_DEPLOYMENT_ENVIRONMENT=production is set
        Then apply_env_overrides uses the env value
        """
        try:
            os.environ["CIDX_DEPLOYMENT_ENVIRONMENT"] = "production"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.deployment_environment == "production"
            ), "CIDX_DEPLOYMENT_ENVIRONMENT should override deployment_environment"
        finally:
            os.environ.pop("CIDX_DEPLOYMENT_ENVIRONMENT", None)

    def test_env_override_invalid_trace_sample_rate_ignored(self):
        """
        AC3: Invalid CIDX_OTEL_TRACE_SAMPLE_RATE is ignored with warning.

        Given a config with default trace sample rate
        When CIDX_OTEL_TRACE_SAMPLE_RATE=invalid is set
        Then apply_env_overrides keeps default value
        """
        try:
            os.environ["CIDX_OTEL_TRACE_SAMPLE_RATE"] = "invalid"

            config = ServerConfig(server_dir="/tmp/test")
            manager = ServerConfigManager("/tmp/test")
            config = manager.apply_env_overrides(config)

            assert (
                config.telemetry_config.trace_sample_rate == 1.0
            ), "Invalid trace_sample_rate should keep default"
        finally:
            os.environ.pop("CIDX_OTEL_TRACE_SAMPLE_RATE", None)


# =============================================================================
# Validation Tests
# =============================================================================


class TestTelemetryConfigValidation:
    """Tests for TelemetryConfig validation."""

    def test_validation_accepts_valid_config(self):
        """
        Validation accepts valid TelemetryConfig.

        Given a ServerConfig with valid telemetry settings
        When validated
        Then it passes without error
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(
            enabled=True,
            collector_endpoint="http://localhost:4317",
            trace_sample_rate=0.5,
        )

        manager = ServerConfigManager("/tmp/test")
        # Should not raise
        manager.validate_config(config)

    def test_validation_rejects_trace_sample_rate_below_zero(self):
        """
        Validation rejects trace_sample_rate < 0.

        Given a config with trace_sample_rate = -0.1
        When validated
        Then it raises ValueError
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(trace_sample_rate=-0.1)

        manager = ServerConfigManager("/tmp/test")

        with pytest.raises(ValueError) as exc_info:
            manager.validate_config(config)

        assert (
            "trace_sample_rate" in str(exc_info.value).lower()
        ), "Error should mention trace_sample_rate"

    def test_validation_rejects_trace_sample_rate_above_one(self):
        """
        Validation rejects trace_sample_rate > 1.0.

        Given a config with trace_sample_rate = 1.5
        When validated
        Then it raises ValueError
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(trace_sample_rate=1.5)

        manager = ServerConfigManager("/tmp/test")

        with pytest.raises(ValueError) as exc_info:
            manager.validate_config(config)

        assert (
            "trace_sample_rate" in str(exc_info.value).lower()
        ), "Error should mention trace_sample_rate"

    def test_validation_rejects_invalid_collector_protocol(self):
        """
        Validation rejects invalid collector_protocol.

        Given a config with collector_protocol = 'invalid'
        When validated
        Then it raises ValueError
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(collector_protocol="invalid")

        manager = ServerConfigManager("/tmp/test")

        with pytest.raises(ValueError) as exc_info:
            manager.validate_config(config)

        assert (
            "collector_protocol" in str(exc_info.value).lower()
        ), "Error should mention collector_protocol"

    def test_validation_rejects_negative_machine_metrics_interval(self):
        """
        Validation rejects machine_metrics_interval_seconds < 1.

        Given a config with machine_metrics_interval_seconds = 0
        When validated
        Then it raises ValueError
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(machine_metrics_interval_seconds=0)

        manager = ServerConfigManager("/tmp/test")

        with pytest.raises(ValueError) as exc_info:
            manager.validate_config(config)

        assert (
            "machine_metrics_interval" in str(exc_info.value).lower()
        ), "Error should mention machine_metrics_interval"

    def test_validation_accepts_grpc_protocol(self):
        """
        Validation accepts collector_protocol = 'grpc'.

        Given a config with collector_protocol = 'grpc'
        When validated
        Then it passes without error
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(collector_protocol="grpc")

        manager = ServerConfigManager("/tmp/test")
        manager.validate_config(config)

    def test_validation_accepts_http_protocol(self):
        """
        Validation accepts collector_protocol = 'http'.

        Given a config with collector_protocol = 'http'
        When validated
        Then it passes without error
        """
        config = ServerConfig(server_dir="/tmp/test")
        config.telemetry_config = TelemetryConfig(collector_protocol="http")

        manager = ServerConfigManager("/tmp/test")
        manager.validate_config(config)
