"""
Tests for global refresh interval configuration.

Tests AC5: Configurable Global Refresh Interval
- Configuration via config file
- Default: 600 seconds (10 minutes)
- Minimum: 60 seconds (1 minute)
- Persistence across restarts
"""

import pytest
from code_indexer.config import ConfigManager


class TestRefreshIntervalConfiguration:
    """Test suite for refresh interval configuration."""

    def test_default_refresh_interval_is_600_seconds(self, tmp_path):
        """
        Test that default global refresh interval is 600 seconds (10 minutes).

        AC5 Technical Requirement: Default 600 seconds (10 minutes)
        """
        # Create config manager with temp config dir
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_manager = ConfigManager(config_dir / "config.json")

        # Get global refresh interval (should return default)
        interval = config_manager.get_global_refresh_interval()

        assert interval == 600, "Default refresh interval should be 600 seconds"

    def test_set_refresh_interval_via_config(self, tmp_path):
        """
        Test setting refresh interval via configuration.

        AC5 Technical Requirement: Configuration via config file
        """
        # Create config manager
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_manager = ConfigManager(config_dir / "config.json")

        # Set refresh interval to 5 minutes (300 seconds)
        config_manager.set_global_refresh_interval(300)

        # Verify it was saved
        interval = config_manager.get_global_refresh_interval()
        assert interval == 300

    def test_refresh_interval_persists_across_restarts(self, tmp_path):
        """
        Test that refresh interval persists across ConfigManager restarts.

        AC5 Technical Requirement: Setting persists across restarts
        """
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()
        config_path = config_dir / "config.json"

        # First instance: set interval
        config1 = ConfigManager(config_path)
        config1.set_global_refresh_interval(180)

        # Second instance: verify persisted
        config2 = ConfigManager(config_path)
        interval = config2.get_global_refresh_interval()

        assert interval == 180, "Refresh interval should persist across restarts"

    def test_minimum_refresh_interval_is_60_seconds(self, tmp_path):
        """
        Test that minimum refresh interval is enforced at 60 seconds.

        AC5 Technical Requirement: Minimum 60 seconds (1 minute)
        """
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_manager = ConfigManager(config_dir / "config.json")

        # Try to set interval below minimum
        with pytest.raises(ValueError, match="60.*minimum"):
            config_manager.set_global_refresh_interval(30)

    def test_refresh_interval_rejects_negative_values(self, tmp_path):
        """
        Test that negative refresh intervals are rejected.
        """
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_manager = ConfigManager(config_dir / "config.json")

        # Try to set negative interval
        with pytest.raises(ValueError):
            config_manager.set_global_refresh_interval(-100)

    def test_refresh_interval_rejects_zero(self, tmp_path):
        """
        Test that zero refresh interval is rejected.
        """
        config_dir = tmp_path / ".code-indexer"
        config_dir.mkdir()

        config_manager = ConfigManager(config_dir / "config.json")

        # Try to set zero interval
        with pytest.raises(ValueError):
            config_manager.set_global_refresh_interval(0)
