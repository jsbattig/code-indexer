"""
Unit tests for resource configuration externalization.

Tests verify that:
1. ServerResourceConfig is properly instantiated with default values
2. Timeout values are configurable
3. Configuration integrates with ServerConfig properly

NOTE: Artificial resource limits (max_golden_repos, max_repo_size_bytes, max_jobs_per_user)
have been REMOVED from the codebase. They were nonsensical limitations that served no purpose.
"""

from code_indexer.server.utils.config_manager import (
    ServerConfig,
    ServerResourceConfig,
    ServerConfigManager,
)


class TestServerResourceConfig:
    """Test ServerResourceConfig class."""

    def test_default_timeout_values_are_lenient(self):
        """Test that default timeout values are set to lenient values."""
        config = ServerResourceConfig()

        # Git operation timeouts should be lenient (in seconds)
        assert config.git_clone_timeout == 3600  # 1 hour
        assert config.git_pull_timeout == 3600  # 1 hour
        assert config.git_refresh_timeout == 3600  # 1 hour
        assert config.git_init_conflict_timeout == 1800  # 30 minutes
        assert config.git_service_conflict_timeout == 1800  # 30 minutes
        assert config.git_service_cleanup_timeout == 300  # 5 minutes
        assert config.git_service_wait_timeout == 180  # 3 minutes
        assert config.git_process_check_timeout == 30  # 30 seconds
        assert config.git_untracked_file_timeout == 60  # 1 minute

    def test_custom_timeout_values_can_be_set(self):
        """Test that custom timeout values can be configured."""
        config = ServerResourceConfig(
            git_clone_timeout=7200,  # 2 hours
            git_pull_timeout=1800,  # 30 minutes
        )

        assert config.git_clone_timeout == 7200
        assert config.git_pull_timeout == 1800

    def test_refresh_scheduler_timeout_values(self):
        """Test that refresh scheduler timeout values are set correctly."""
        config = ServerResourceConfig()

        # Refresh scheduler timeouts
        assert config.cow_clone_timeout == 600  # 10 minutes
        assert config.git_update_index_timeout == 300  # 5 minutes
        assert config.git_restore_timeout == 300  # 5 minutes
        assert config.cidx_fix_config_timeout == 60  # 1 minute
        assert config.cidx_index_timeout == 3600  # 1 hour


class TestServerConfigIntegration:
    """Test ServerResourceConfig integration with ServerConfig."""

    def test_server_config_includes_resource_config(self):
        """Test that ServerConfig includes resource configuration."""
        config = ServerConfig(server_dir="/tmp/test")

        assert config.resource_config is not None
        assert isinstance(config.resource_config, ServerResourceConfig)

    def test_server_config_auto_initializes_resource_config(self):
        """Test that ServerConfig auto-initializes resource config if not provided."""
        config = ServerConfig(server_dir="/tmp/test")

        # Resource config should be auto-initialized with defaults
        assert config.resource_config is not None
        assert config.resource_config.git_clone_timeout == 3600

    def test_server_config_accepts_custom_resource_config(self):
        """Test that ServerConfig accepts custom resource configuration."""
        custom_resource_config = ServerResourceConfig(
            git_clone_timeout=7200,
        )

        config = ServerConfig(
            server_dir="/tmp/test", resource_config=custom_resource_config
        )

        assert config.resource_config.git_clone_timeout == 7200

    def test_config_manager_creates_config_with_resource_config(self):
        """Test that ServerConfigManager creates config with resource config."""
        config_manager = ServerConfigManager(server_dir_path="/tmp/test-server")
        config = config_manager.create_default_config()

        assert config.resource_config is not None
        assert isinstance(config.resource_config, ServerResourceConfig)


class TestResourceConfigPersistence:
    """Test that resource configuration can be persisted and loaded."""

    def test_resource_config_persists_to_file(self, tmp_path):
        """Test that resource configuration persists to file correctly."""
        config_manager = ServerConfigManager(server_dir_path=str(tmp_path))

        custom_resource_config = ServerResourceConfig(
            git_clone_timeout=7200,
        )

        config = ServerConfig(
            server_dir=str(tmp_path), resource_config=custom_resource_config
        )

        # Save config
        config_manager.save_config(config)

        # Load config back
        loaded_config = config_manager.load_config()

        assert loaded_config is not None
        assert loaded_config.resource_config is not None
        assert loaded_config.resource_config.git_clone_timeout == 7200

    def test_resource_config_default_values_persist_correctly(self, tmp_path):
        """Test that default values persist correctly."""
        config_manager = ServerConfigManager(server_dir_path=str(tmp_path))

        config = ServerConfig(server_dir=str(tmp_path))

        # Save config with default values
        config_manager.save_config(config)

        # Load config back
        loaded_config = config_manager.load_config()

        assert loaded_config is not None
        assert loaded_config.resource_config is not None
        # Verify timeout defaults are preserved
        assert loaded_config.resource_config.git_clone_timeout == 3600
        assert loaded_config.resource_config.git_pull_timeout == 3600
