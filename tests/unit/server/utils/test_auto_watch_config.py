"""
Unit tests for AutoWatchConfig - Story #640.

Tests configuration for auto-watch functionality.
"""

from code_indexer.server.utils.config_manager import AutoWatchConfig, ServerConfig


class TestAutoWatchConfig:
    """Test AutoWatchConfig dataclass."""

    def test_auto_watch_config_defaults(self):
        """Test that AutoWatchConfig has correct default values."""
        config = AutoWatchConfig()

        assert config.auto_watch_enabled is True
        assert config.auto_watch_timeout == 300

    def test_auto_watch_config_custom_values(self):
        """Test that AutoWatchConfig accepts custom values."""
        config = AutoWatchConfig(
            auto_watch_enabled=False,
            auto_watch_timeout=600,
        )

        assert config.auto_watch_enabled is False
        assert config.auto_watch_timeout == 600


class TestServerConfigAutoWatchIntegration:
    """Test AutoWatchConfig integration with ServerConfig."""

    def test_server_config_includes_auto_watch_config(self):
        """Test that ServerConfig includes AutoWatchConfig."""
        server_config = ServerConfig(server_dir="/tmp/test")

        assert hasattr(server_config, "auto_watch_config")
        assert server_config.auto_watch_config is not None
        assert isinstance(server_config.auto_watch_config, AutoWatchConfig)

    def test_server_config_auto_watch_defaults(self):
        """Test that ServerConfig initializes AutoWatchConfig with defaults."""
        server_config = ServerConfig(server_dir="/tmp/test")

        assert server_config.auto_watch_config.auto_watch_enabled is True
        assert server_config.auto_watch_config.auto_watch_timeout == 300
