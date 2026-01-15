"""
Unit tests for Claude Delegation config skip_ssl_verify persistence (Story #721).

Tests verify that the ClaudeDelegationManager correctly persists
the skip_ssl_verify setting, which the update_claude_delegation_config
route handler relies on.
"""

from code_indexer.server.config.delegation_config import (
    ClaudeDelegationConfig,
    ClaudeDelegationManager,
    DEFAULT_FUNCTION_REPO_ALIAS,
)


class TestClaudeDelegationSkipSSLVerifyPersistence:
    """Test skip_ssl_verify persistence in ClaudeDelegationManager."""

    def test_skip_ssl_verify_true_saved_and_loaded(self, tmp_path):
        """Test that skip_ssl_verify=True is properly saved and loaded."""
        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        config = ClaudeDelegationConfig(
            function_repo_alias=DEFAULT_FUNCTION_REPO_ALIAS,
            claude_server_url="https://test.example.com",
            claude_server_username="user",
            claude_server_credential_type="password",
            claude_server_credential="pass",
            cidx_callback_url="http://localhost:8000",
            skip_ssl_verify=True,
        )
        manager.save_config(config)

        loaded_config = manager.load_config()
        assert loaded_config is not None
        assert loaded_config.skip_ssl_verify is True

    def test_skip_ssl_verify_false_saved_and_loaded(self, tmp_path):
        """Test that skip_ssl_verify=False is properly saved and loaded."""
        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        config = ClaudeDelegationConfig(
            function_repo_alias=DEFAULT_FUNCTION_REPO_ALIAS,
            claude_server_url="https://test.example.com",
            claude_server_username="user",
            claude_server_credential_type="password",
            claude_server_credential="pass",
            cidx_callback_url="http://localhost:8000",
            skip_ssl_verify=False,
        )
        manager.save_config(config)

        loaded_config = manager.load_config()
        assert loaded_config is not None
        assert loaded_config.skip_ssl_verify is False

    def test_skip_ssl_verify_defaults_to_false(self, tmp_path):
        """Test that skip_ssl_verify defaults to False when not specified."""
        config = ClaudeDelegationConfig(
            claude_server_url="https://test.example.com",
            claude_server_username="user",
            claude_server_credential="pass",
        )
        assert config.skip_ssl_verify is False

    def test_skip_ssl_verify_can_be_toggled(self, tmp_path):
        """Test that skip_ssl_verify can be toggled from True to False."""
        manager = ClaudeDelegationManager(server_dir_path=str(tmp_path))

        # Save with True
        config_true = ClaudeDelegationConfig(
            function_repo_alias=DEFAULT_FUNCTION_REPO_ALIAS,
            claude_server_url="https://test.example.com",
            claude_server_username="user",
            claude_server_credential_type="password",
            claude_server_credential="pass",
            cidx_callback_url="http://localhost:8000",
            skip_ssl_verify=True,
        )
        manager.save_config(config_true)

        loaded = manager.load_config()
        assert loaded.skip_ssl_verify is True

        # Save with False (toggle)
        config_false = ClaudeDelegationConfig(
            function_repo_alias=DEFAULT_FUNCTION_REPO_ALIAS,
            claude_server_url="https://test.example.com",
            claude_server_username="user",
            claude_server_credential_type="password",
            claude_server_credential="pass",
            cidx_callback_url="http://localhost:8000",
            skip_ssl_verify=False,
        )
        manager.save_config(config_false)

        loaded = manager.load_config()
        assert loaded.skip_ssl_verify is False
