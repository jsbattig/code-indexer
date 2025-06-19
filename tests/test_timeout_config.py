"""Tests for timeout configuration integration."""

import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from code_indexer.config import ConfigManager, Config, TimeoutsConfig, PollingConfig
from code_indexer.services.health_checker import HealthChecker


class TestTimeoutConfiguration:
    """Test timeout configuration functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config_path = self.temp_dir / "config.json"

    def test_default_timeout_values(self):
        """Test that default timeout values are correct."""
        config = Config()

        assert config.timeouts.service_startup == 180
        assert config.timeouts.service_shutdown == 30
        assert config.timeouts.port_release == 15
        assert config.timeouts.cleanup_validation == 30
        assert config.timeouts.health_check == 60
        assert config.timeouts.data_cleaner_startup == 60

    def test_default_polling_values(self):
        """Test that default polling values are correct."""
        config = Config()

        assert config.polling.initial_interval == 0.5
        assert config.polling.backoff_factor == 1.2
        assert config.polling.max_interval == 2.0

    def test_custom_timeout_configuration(self):
        """Test custom timeout configuration."""
        config_data = {
            "timeouts": {
                "service_startup": 300,
                "service_shutdown": 60,
                "port_release": 30,
                "cleanup_validation": 45,
                "health_check": 120,
                "data_cleaner_startup": 90,
            },
            "polling": {
                "initial_interval": 1.0,
                "backoff_factor": 1.5,
                "max_interval": 5.0,
            },
        }

        with open(self.config_path, "w") as f:
            json.dump(config_data, f)

        config_manager = ConfigManager(self.config_path)
        config = config_manager.get_config()

        assert config.timeouts.service_startup == 300
        assert config.timeouts.service_shutdown == 60
        assert config.timeouts.port_release == 30
        assert config.timeouts.cleanup_validation == 45
        assert config.timeouts.health_check == 120
        assert config.timeouts.data_cleaner_startup == 90

        assert config.polling.initial_interval == 1.0
        assert config.polling.backoff_factor == 1.5
        assert config.polling.max_interval == 5.0

    def test_health_checker_uses_config_manager(self):
        """Test that HealthChecker uses ConfigManager timeouts."""
        config_data = {
            "timeouts": {"service_startup": 240, "health_check": 90},
            "polling": {"initial_interval": 0.2, "backoff_factor": 2.0},
        }

        with open(self.config_path, "w") as f:
            json.dump(config_data, f)

        config_manager = ConfigManager(self.config_path)
        health_checker = HealthChecker(config_manager=config_manager)

        timeouts = health_checker.get_timeouts()
        polling = health_checker.get_polling_config()

        assert timeouts["service_startup"] == 240
        assert timeouts["health_check"] == 90
        assert polling["initial_interval"] == 0.2
        assert polling["backoff_factor"] == 2.0

    def test_health_checker_uses_dict_config(self):
        """Test that HealthChecker uses dictionary config (from main_config)."""
        config_dict = {
            "timeouts": {"service_startup": 360, "port_release": 25},
            "polling": {"max_interval": 3.0, "backoff_factor": 1.8},
        }

        health_checker = HealthChecker(config_manager=config_dict)

        timeouts = health_checker.get_timeouts()
        polling = health_checker.get_polling_config()

        assert timeouts["service_startup"] == 360
        assert timeouts["port_release"] == 25
        assert polling["max_interval"] == 3.0
        assert polling["backoff_factor"] == 1.8

    def test_health_checker_fallback_to_defaults(self):
        """Test that HealthChecker falls back to defaults when config is missing."""
        # Test with no config manager
        health_checker = HealthChecker()

        timeouts = health_checker.get_timeouts()
        polling = health_checker.get_polling_config()

        assert timeouts["service_startup"] == 180  # Default
        assert timeouts["health_check"] == 60  # Default
        assert polling["initial_interval"] == 0.5  # Default
        assert polling["backoff_factor"] == 1.2  # Default

    def test_health_checker_partial_config(self):
        """Test HealthChecker with partial configuration."""
        config_dict = {
            "timeouts": {
                "service_startup": 240,
                # Missing other timeout values
            },
            "polling": {
                "initial_interval": 0.8
                # Missing other polling values
            },
        }

        health_checker = HealthChecker(config_manager=config_dict)

        timeouts = health_checker.get_timeouts()
        polling = health_checker.get_polling_config()

        # Should get custom value where specified
        assert timeouts["service_startup"] == 240
        # And defaults for missing values
        assert timeouts["health_check"] == 60  # Default

        assert polling["initial_interval"] == 0.8
        assert polling["backoff_factor"] == 1.2  # Default

    def test_config_validation(self):
        """Test that config validation works properly."""
        # Test valid config
        config = Config(
            timeouts=TimeoutsConfig(service_startup=300),
            polling=PollingConfig(initial_interval=1.0),
        )

        assert config.timeouts.service_startup == 300
        assert config.polling.initial_interval == 1.0

        # Test that negative values are handled (depends on validation rules)
        # Note: We might want to add validation for positive values

    def test_config_manager_integration(self):
        """Test full integration with ConfigManager."""
        config_data = {
            "codebase_dir": ".",
            "file_extensions": ["py", "js"],
            "timeouts": {"service_startup": 200, "data_cleaner_startup": 75},
            "polling": {"max_interval": 4.0},
            "ollama": {"host": "http://localhost:11434"},
        }

        with open(self.config_path, "w") as f:
            json.dump(config_data, f)

        config_manager = ConfigManager(self.config_path)
        config = config_manager.get_config()

        # Test that all sections work together
        assert config.timeouts.service_startup == 200
        assert config.timeouts.data_cleaner_startup == 75
        assert config.polling.max_interval == 4.0
        assert config.ollama.host == "http://localhost:11434"
        assert config.file_extensions == ["py", "js"]

    def test_save_and_load_config_with_timeouts(self):
        """Test saving and loading config with timeout settings."""
        config = Config()
        config.timeouts.service_startup = 250
        config.timeouts.health_check = 80
        config.polling.initial_interval = 0.3

        config_manager = ConfigManager(self.config_path)
        config_manager.save(config)

        # Load and verify
        loaded_config = config_manager.get_config()
        assert loaded_config.timeouts.service_startup == 250
        assert loaded_config.timeouts.health_check == 80
        assert loaded_config.polling.initial_interval == 0.3


class TestTimeoutConfigurationIntegration:
    """Test timeout configuration integration with other components."""

    def test_health_checker_wait_for_condition_uses_config(self):
        """Test that wait_for_condition uses configured timeouts."""
        config_dict = {
            "timeouts": {"health_check": 5},  # Short timeout for test
            "polling": {
                "initial_interval": 0.1,
                "backoff_factor": 1.1,
                "max_interval": 0.5,
            },
        }

        health_checker = HealthChecker(config_manager=config_dict)

        call_count = 0

        def never_succeeds():
            nonlocal call_count
            call_count += 1
            return False

        import time

        start_time = time.time()
        result = health_checker.wait_for_condition(never_succeeds)
        elapsed = time.time() - start_time

        # Should use configured timeout (5s) not default (60s)
        assert result is False
        assert 4.5 <= elapsed <= 6.0  # Within tolerance of 5s timeout
        assert call_count > 10  # Should have made multiple attempts

    def test_health_checker_service_ready_uses_config(self):
        """Test that wait_for_service_ready uses configured timeout."""
        config_dict = {"timeouts": {"health_check": 2}}  # Short timeout for test

        health_checker = HealthChecker(config_manager=config_dict)

        import time

        start_time = time.time()
        result = health_checker.wait_for_service_ready(
            "http://localhost:65432",  # Unreachable port
            timeout=None,  # Should use config default
        )
        elapsed = time.time() - start_time

        assert result is False
        assert 1.5 <= elapsed <= 3.0  # Should use 2s timeout from config

    def test_docker_manager_with_timeout_config(self):
        """Test DockerManager integration with timeout configuration."""
        from code_indexer.services.docker_manager import DockerManager

        config_dict = {
            "timeouts": {"cleanup_validation": 20, "data_cleaner_startup": 45},
            "polling": {"initial_interval": 0.2},
        }

        mock_console = Mock()
        docker_manager = DockerManager(
            console=mock_console, project_name="test-project", main_config=config_dict
        )

        # Test that health checker gets the config
        timeouts = docker_manager.health_checker.get_timeouts()
        polling = docker_manager.health_checker.get_polling_config()

        assert timeouts["cleanup_validation"] == 20
        assert timeouts["data_cleaner_startup"] == 45
        assert polling["initial_interval"] == 0.2

    def test_engine_optimized_timeouts_with_config(self):
        """Test that engine-optimized timeouts work with configuration."""
        config_dict = {"timeouts": {"port_release": 10, "service_shutdown": 20}}

        health_checker = HealthChecker(config_manager=config_dict)

        # Test Podman optimized timeouts
        podman_timeouts = health_checker.get_container_engine_timeouts("podman")
        assert podman_timeouts["port_release"] == 15  # 10 + 5 for Podman
        assert podman_timeouts["service_shutdown"] == 25  # 20 + 5 for Podman

        # Test Docker timeouts (should use base config)
        docker_timeouts = health_checker.get_container_engine_timeouts("docker")
        assert docker_timeouts["port_release"] == 10  # Base config
        assert docker_timeouts["service_shutdown"] == 20  # Base config
