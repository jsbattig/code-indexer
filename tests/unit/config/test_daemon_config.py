"""Unit tests for daemon configuration in ConfigManager.

This module tests the daemon configuration functionality added in Story 2.2.
Tests follow TDD methodology - written before implementation.
"""

import json
import pytest
from pathlib import Path
from code_indexer.config import ConfigManager, Config


class TestDaemonDefaults:
    """Test DAEMON_DEFAULTS constant exists and has correct structure."""

    def test_daemon_defaults_exist(self):
        """DAEMON_DEFAULTS should be defined on ConfigManager."""
        assert hasattr(ConfigManager, "DAEMON_DEFAULTS")
        defaults = ConfigManager.DAEMON_DEFAULTS
        assert isinstance(defaults, dict)

    def test_daemon_defaults_structure(self):
        """DAEMON_DEFAULTS should contain all required fields."""
        defaults = ConfigManager.DAEMON_DEFAULTS
        assert defaults["enabled"] is False
        assert defaults["ttl_minutes"] == 10
        assert defaults["auto_shutdown_on_idle"] is True
        assert defaults["max_retries"] == 4
        assert defaults["retry_delays_ms"] == [100, 500, 1000, 2000]
        assert defaults["eviction_check_interval_seconds"] == 60


class TestEnableDaemon:
    """Test enable_daemon method."""

    def test_enable_daemon_default_ttl(self, tmp_path):
        """Enable daemon with default TTL (10 minutes)."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon()
        config = config_manager.get_config()

        # Check daemon section exists and is correct
        assert hasattr(config, "daemon")
        daemon_config = config.daemon
        assert daemon_config.enabled is True
        assert daemon_config.ttl_minutes == 10
        assert daemon_config.auto_shutdown_on_idle is True
        assert daemon_config.max_retries == 4
        assert daemon_config.retry_delays_ms == [100, 500, 1000, 2000]
        assert daemon_config.eviction_check_interval_seconds == 60

    def test_enable_daemon_custom_ttl(self, tmp_path):
        """Enable daemon with custom TTL."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon(ttl_minutes=20)
        config = config_manager.get_config()

        daemon_config = config.daemon
        assert daemon_config.enabled is True
        assert daemon_config.ttl_minutes == 20

    def test_enable_daemon_persists_to_file(self, tmp_path):
        """Enable daemon should persist configuration to file."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon(ttl_minutes=15)

        # Reload from disk
        new_manager = ConfigManager(config_path)
        config = new_manager.load()

        # Verify persisted correctly
        assert config.daemon is not None
        assert config.daemon.enabled is True
        assert config.daemon.ttl_minutes == 15

    def test_enable_daemon_idempotent(self, tmp_path):
        """Calling enable_daemon multiple times should work."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Enable twice with different TTLs
        config_manager.enable_daemon(ttl_minutes=10)
        config_manager.enable_daemon(ttl_minutes=20)

        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.enabled is True
        assert daemon_config.ttl_minutes == 20


class TestDisableDaemon:
    """Test disable_daemon method."""

    def test_disable_daemon(self, tmp_path):
        """Disable daemon should set enabled to False."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Enable then disable
        config_manager.enable_daemon()
        config_manager.disable_daemon()

        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.enabled is False

    def test_disable_daemon_preserves_settings(self, tmp_path):
        """Disable daemon should preserve other settings like TTL."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Enable with custom TTL
        config_manager.enable_daemon(ttl_minutes=30)
        config_manager.disable_daemon()

        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.enabled is False
        assert daemon_config.ttl_minutes == 30

    def test_disable_daemon_persists_to_file(self, tmp_path):
        """Disable daemon should persist to file."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon()
        config_manager.disable_daemon()

        # Reload from disk
        new_manager = ConfigManager(config_path)
        config = new_manager.load()
        assert config.daemon.enabled is False

    def test_disable_daemon_without_enable(self, tmp_path):
        """Disabling daemon when not enabled should handle gracefully."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Should not raise, should create daemon section with enabled=False
        config_manager.disable_daemon()
        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.enabled is False


class TestUpdateDaemonTTL:
    """Test update_daemon_ttl method."""

    def test_update_daemon_ttl(self, tmp_path):
        """Update daemon TTL should change ttl_minutes."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon(ttl_minutes=10)
        config_manager.update_daemon_ttl(ttl_minutes=25)

        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.ttl_minutes == 25

    def test_update_daemon_ttl_persists(self, tmp_path):
        """Update daemon TTL should persist to file."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon(ttl_minutes=10)
        config_manager.update_daemon_ttl(ttl_minutes=35)

        # Reload from disk
        new_manager = ConfigManager(config_path)
        config = new_manager.load()
        assert config.daemon.ttl_minutes == 35

    def test_update_daemon_ttl_without_daemon_creates_it(self, tmp_path):
        """Updating TTL when daemon not configured should create daemon config."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Update TTL without enabling daemon first
        config_manager.update_daemon_ttl(ttl_minutes=15)

        config = config_manager.get_config()
        daemon_config = config.daemon
        assert daemon_config.ttl_minutes == 15
        # Should default to disabled
        assert daemon_config.enabled is False


class TestGetDaemonConfig:
    """Test get_daemon_config method."""

    def test_get_daemon_config_with_enabled_daemon(self, tmp_path):
        """Get daemon config when daemon is enabled."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        config_manager.enable_daemon(ttl_minutes=20)
        daemon_config = config_manager.get_daemon_config()

        assert daemon_config["enabled"] is True
        assert daemon_config["ttl_minutes"] == 20
        assert daemon_config["auto_shutdown_on_idle"] is True
        assert daemon_config["max_retries"] == 4
        assert daemon_config["retry_delays_ms"] == [100, 500, 1000, 2000]
        assert daemon_config["eviction_check_interval_seconds"] == 60

    def test_get_daemon_config_without_daemon_section(self, tmp_path):
        """Get daemon config when no daemon section exists returns defaults."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        daemon_config = config_manager.get_daemon_config()

        # Should return defaults with enabled=False
        assert daemon_config["enabled"] is False
        assert daemon_config["ttl_minutes"] == 10
        assert daemon_config["auto_shutdown_on_idle"] is True
        assert daemon_config["max_retries"] == 4
        assert daemon_config["retry_delays_ms"] == [100, 500, 1000, 2000]
        assert daemon_config["eviction_check_interval_seconds"] == 60

    def test_get_daemon_config_merges_with_defaults(self, tmp_path):
        """Get daemon config merges partial config with defaults."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Manually create config with partial daemon section (using dict, not model_dump)
        old_config = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "daemon": {
                "enabled": True,
                "ttl_minutes": 15
                # Missing other fields
            }
        }

        config_path.write_text(json.dumps(old_config, indent=2))

        # Reload and check defaults are merged
        new_manager = ConfigManager(config_path)
        daemon_config = new_manager.get_daemon_config()

        assert daemon_config["enabled"] is True
        assert daemon_config["ttl_minutes"] == 15
        # Should have defaults for missing fields
        assert daemon_config["auto_shutdown_on_idle"] is True
        assert daemon_config["max_retries"] == 4


class TestGetSocketPath:
    """Test get_socket_path method."""

    def test_get_socket_path(self, tmp_path):
        """Socket path should be in /tmp/cidx/ with hash-based naming."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)

        socket_path = config_manager.get_socket_path()

        # Should be in /tmp/cidx/ directory
        assert socket_path.parent == Path("/tmp/cidx")
        # Should end with .sock
        assert socket_path.suffix == ".sock"
        # Socket path should be short (under 108 chars)
        assert len(str(socket_path)) < 108
        # Should be exactly /tmp/cidx/{16-char-hash}.sock
        assert len(socket_path.stem) == 16
        # Hash should be hexadecimal
        assert all(c in '0123456789abcdef' for c in socket_path.stem)

    def test_get_socket_path_with_nested_project(self, tmp_path):
        """Socket path calculation for nested projects."""
        project_dir = tmp_path / "workspace" / "project"
        project_dir.mkdir(parents=True)
        config_path = project_dir / ".code-indexer" / "config.json"

        config_manager = ConfigManager(config_path)
        socket_path = config_manager.get_socket_path()

        # Should still be in /tmp/cidx/ regardless of project depth
        assert socket_path.parent == Path("/tmp/cidx")
        # Should end with .sock
        assert socket_path.suffix == ".sock"
        # Socket path should be short even for deep directories
        assert len(str(socket_path)) < 108
        # Should be exactly /tmp/cidx/{16-char-hash}.sock
        assert len(socket_path.stem) == 16


class TestConfigurationValidation:
    """Test validation of daemon configuration values."""

    def test_ttl_validation_positive(self, tmp_path):
        """TTL must be positive."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Should raise for non-positive TTL
        with pytest.raises(ValueError, match="TTL must be positive"):
            config_manager.enable_daemon(ttl_minutes=0)

        with pytest.raises(ValueError, match="TTL must be positive"):
            config_manager.enable_daemon(ttl_minutes=-1)

    def test_ttl_validation_max_value(self, tmp_path):
        """TTL must be <= 10080 minutes (1 week)."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Should raise for TTL > 1 week
        with pytest.raises(ValueError, match="TTL must be between 1 and 10080 minutes"):
            config_manager.enable_daemon(ttl_minutes=10081)

    def test_ttl_validation_boundary_values(self, tmp_path):
        """Test boundary values for TTL validation."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_manager = ConfigManager(config_path)
        config_manager.create_default_config(tmp_path)

        # Should accept 1 minute
        config_manager.enable_daemon(ttl_minutes=1)
        config = config_manager.get_config()
        assert config.daemon.ttl_minutes == 1

        # Should accept 10080 minutes (1 week)
        config_manager.enable_daemon(ttl_minutes=10080)
        config = config_manager.get_config()
        assert config.daemon.ttl_minutes == 10080


class TestBackwardCompatibility:
    """Test backward compatibility with existing configs."""

    def test_existing_config_without_daemon_section(self, tmp_path):
        """Existing configs without daemon section should work."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create old-style config without daemon section
        old_config = {
            "codebase_dir": str(tmp_path),
            "file_extensions": ["py", "js"],
            "exclude_dirs": ["node_modules"],
            "embedding_provider": "voyage-ai"
        }
        config_path.write_text(json.dumps(old_config, indent=2))

        # Should load without errors
        config_manager = ConfigManager(config_path)
        config = config_manager.load()

        # Should return defaults when querying daemon config
        daemon_config = config_manager.get_daemon_config()
        assert daemon_config["enabled"] is False
        assert daemon_config["ttl_minutes"] == 10

    def test_partial_daemon_config(self, tmp_path):
        """Configs with partial daemon section should merge with defaults."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create config with partial daemon section
        partial_config = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "daemon": {
                "enabled": True
                # Missing ttl_minutes and other fields
            }
        }
        config_path.write_text(json.dumps(partial_config, indent=2))

        config_manager = ConfigManager(config_path)
        daemon_config = config_manager.get_daemon_config()

        # Should have enabled from config
        assert daemon_config["enabled"] is True
        # Should have defaults for missing fields
        assert daemon_config["ttl_minutes"] == 10
        assert daemon_config["auto_shutdown_on_idle"] is True

    def test_deprecated_fields_ignored(self, tmp_path):
        """Old deprecated fields should be ignored."""
        config_path = tmp_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # Create config with deprecated fields
        old_config = {
            "codebase_dir": str(tmp_path),
            "embedding_provider": "voyage-ai",
            "daemon": {
                "enabled": True,
                "ttl_minutes": 10,
                "socket_type": "unix",  # Deprecated
                "socket_path": "/old/path.sock",  # Deprecated
                "tcp_port": 50051  # Deprecated
            }
        }
        config_path.write_text(json.dumps(old_config, indent=2))

        # Should load without errors
        config_manager = ConfigManager(config_path)
        config_manager.load()

        # Socket path should be calculated using new hash-based system
        socket_path = config_manager.get_socket_path()
        # Should be in /tmp/cidx/ with hash-based naming
        assert socket_path.parent == Path("/tmp/cidx")
        assert socket_path.suffix == ".sock"
        assert len(socket_path.stem) == 16
        # Should not use deprecated field
        assert socket_path != Path("/old/path.sock")
