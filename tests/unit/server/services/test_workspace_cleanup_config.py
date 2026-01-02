"""
Unit tests for Workspace Cleanup Configuration (Story #647 - AC1).

Tests configurable retention period for SCIP self-healing workspace cleanup:
- Default retention period (7 days)
- Environment variable override (CIDX_SCIP_WORKSPACE_RETENTION_DAYS)
- Config file setting (scip_workspace_retention_days)
- Range validation (minimum 1 day, maximum 365 days)
- Integration with ServerConfig
"""

import os
import pytest
from pathlib import Path

from code_indexer.server.utils.config_manager import (
    ServerConfig,
    ServerConfigManager,
)


class TestWorkspaceCleanupConfigAC1:
    """AC1: Configurable Retention Period tests."""

    def test_default_retention_period_is_7_days(self, tmp_path):
        """
        Given the CIDX server configuration system
        When a new ServerConfig is created with defaults
        Then scip_workspace_retention_days should default to 7
        """
        server_dir = str(tmp_path / "server")
        os.makedirs(server_dir, exist_ok=True)

        config = ServerConfig(server_dir=server_dir)

        # AC1 requirement: default retention period is 7 days
        assert hasattr(config, 'scip_workspace_retention_days')
        assert config.scip_workspace_retention_days == 7

    def test_retention_period_via_config_file(self, tmp_path):
        """
        Given the CIDX server configuration system
        When scip_workspace_retention_days is set in config file
        Then the value should be loaded from config file
        """
        server_dir = tmp_path / "server"
        server_dir.mkdir(parents=True)
        config_file = server_dir / "config.json"

        # Write config with retention period
        config_file.write_text('{"scip_workspace_retention_days": 14}')

        manager = ServerConfigManager(str(server_dir))
        config = manager.load_config()

        # AC1 requirement: config file setting
        assert config is not None
        assert config.scip_workspace_retention_days == 14

    def test_retention_period_via_environment_variable(self, tmp_path, monkeypatch):
        """
        Given the CIDX server configuration system
        When CIDX_SCIP_WORKSPACE_RETENTION_DAYS environment variable is set
        Then the environment variable value should override config file
        """
        server_dir = tmp_path / "server"
        server_dir.mkdir(parents=True)
        config_file = server_dir / "config.json"

        # Write config with retention period 14 days
        config_file.write_text('{"scip_workspace_retention_days": 14}')

        # Set environment variable to override (21 days)
        monkeypatch.setenv("CIDX_SCIP_WORKSPACE_RETENTION_DAYS", "21")

        manager = ServerConfigManager(str(server_dir))
        config = manager.load_config()

        # Apply environment overrides
        config = manager.apply_env_overrides(config)

        # AC1 requirement: environment variable override
        assert config is not None
        assert config.scip_workspace_retention_days == 21

    def test_retention_period_minimum_validation(self, tmp_path):
        """
        Given the CIDX server configuration system
        When retention period is set to less than 1 day
        Then validation should raise ValueError
        """
        server_dir = str(tmp_path / "server")
        os.makedirs(server_dir, exist_ok=True)

        config = ServerConfig(server_dir=server_dir)
        config.scip_workspace_retention_days = 0

        manager = ServerConfigManager(server_dir)

        # AC1 requirement: minimum retention period is 1 day
        with pytest.raises(ValueError, match="scip_workspace_retention_days must be between 1 and 365"):
            manager.validate_config(config)

    def test_retention_period_maximum_validation(self, tmp_path):
        """
        Given the CIDX server configuration system
        When retention period is set to more than 365 days
        Then validation should raise ValueError
        """
        server_dir = str(tmp_path / "server")
        os.makedirs(server_dir, exist_ok=True)

        config = ServerConfig(server_dir=server_dir)
        config.scip_workspace_retention_days = 366

        manager = ServerConfigManager(server_dir)

        # AC1 requirement: maximum retention period is 365 days
        with pytest.raises(ValueError, match="scip_workspace_retention_days must be between 1 and 365"):
            manager.validate_config(config)

    def test_retention_period_valid_range(self, tmp_path):
        """
        Given the CIDX server configuration system
        When retention period is set to valid values (1-365)
        Then validation should succeed
        """
        server_dir = str(tmp_path / "server")
        os.makedirs(server_dir, exist_ok=True)

        manager = ServerConfigManager(server_dir)

        # Test minimum boundary
        config_min = ServerConfig(server_dir=server_dir)
        config_min.scip_workspace_retention_days = 1
        manager.validate_config(config_min)  # Should not raise

        # Test maximum boundary
        config_max = ServerConfig(server_dir=server_dir)
        config_max.scip_workspace_retention_days = 365
        manager.validate_config(config_max)  # Should not raise

        # Test mid-range value
        config_mid = ServerConfig(server_dir=server_dir)
        config_mid.scip_workspace_retention_days = 30
        manager.validate_config(config_mid)  # Should not raise

    def test_retention_period_persists_to_config_file(self, tmp_path):
        """
        Given the CIDX server configuration system
        When retention period is updated via API
        Then the new value should persist to config.json
        """
        server_dir = tmp_path / "server"
        server_dir.mkdir(parents=True)

        manager = ServerConfigManager(str(server_dir))
        config = ServerConfig(server_dir=str(server_dir))
        config.scip_workspace_retention_days = 14

        manager.save_config(config)

        # Reload and verify persistence
        loaded_config = manager.load_config()
        assert loaded_config is not None
        assert loaded_config.scip_workspace_retention_days == 14

    def test_retention_period_type_validation(self, tmp_path):
        """
        Given the CIDX server configuration system
        When retention period is set to non-integer value
        Then validation should raise TypeError or convert to int
        """
        server_dir = str(tmp_path / "server")
        os.makedirs(server_dir, exist_ok=True)

        config = ServerConfig(server_dir=server_dir)

        # Should accept integer
        config.scip_workspace_retention_days = 7
        manager = ServerConfigManager(server_dir)
        manager.validate_config(config)  # Should not raise

        # Should reject string (or convert if that's the behavior)
        with pytest.raises((TypeError, ValueError)):
            config.scip_workspace_retention_days = "not an integer"
            manager.validate_config(config)
