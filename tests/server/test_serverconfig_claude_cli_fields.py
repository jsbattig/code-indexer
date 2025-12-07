"""
Tests for ServerConfig Claude CLI fields (Story #546 - AC1).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

from src.code_indexer.server.utils.config_manager import ServerConfig


# =============================================================================
# AC1: ServerConfig has new fields with correct defaults
# =============================================================================


class TestServerConfigNewFields:
    """Tests for new Claude CLI fields in ServerConfig."""

    def test_serverconfig_has_anthropic_api_key_field(self):
        """
        AC1: ServerConfig has anthropic_api_key field with None default.

        Given I create a new ServerConfig
        When I inspect the anthropic_api_key field
        Then it exists and defaults to None
        """
        config = ServerConfig(server_dir="/tmp/test")

        assert hasattr(
            config, "anthropic_api_key"
        ), "ServerConfig should have anthropic_api_key field"
        assert (
            config.anthropic_api_key is None
        ), "anthropic_api_key should default to None"

    def test_serverconfig_has_max_concurrent_claude_cli_field(self):
        """
        AC1: ServerConfig has max_concurrent_claude_cli field with default 4.

        Given I create a new ServerConfig
        When I inspect the max_concurrent_claude_cli field
        Then it exists and defaults to 4
        """
        config = ServerConfig(server_dir="/tmp/test")

        assert hasattr(
            config, "max_concurrent_claude_cli"
        ), "ServerConfig should have max_concurrent_claude_cli field"
        assert (
            config.max_concurrent_claude_cli == 4
        ), "max_concurrent_claude_cli should default to 4"

    def test_serverconfig_has_description_refresh_interval_hours_field(self):
        """
        AC1: ServerConfig has description_refresh_interval_hours field with default 24.

        Given I create a new ServerConfig
        When I inspect the description_refresh_interval_hours field
        Then it exists and defaults to 24
        """
        config = ServerConfig(server_dir="/tmp/test")

        assert hasattr(
            config, "description_refresh_interval_hours"
        ), "ServerConfig should have description_refresh_interval_hours field"
        assert (
            config.description_refresh_interval_hours == 24
        ), "description_refresh_interval_hours should default to 24"

    def test_serverconfig_accepts_custom_anthropic_api_key(self):
        """
        AC1: ServerConfig accepts custom anthropic_api_key value.

        Given I create a ServerConfig with custom anthropic_api_key
        When I inspect the field
        Then it has the custom value
        """
        config = ServerConfig(
            server_dir="/tmp/test", anthropic_api_key="sk-ant-test-key-123"
        )

        assert (
            config.anthropic_api_key == "sk-ant-test-key-123"
        ), "anthropic_api_key should accept custom value"

    def test_serverconfig_accepts_custom_max_concurrent_claude_cli(self):
        """
        AC1: ServerConfig accepts custom max_concurrent_claude_cli value.

        Given I create a ServerConfig with custom max_concurrent_claude_cli
        When I inspect the field
        Then it has the custom value
        """
        config = ServerConfig(server_dir="/tmp/test", max_concurrent_claude_cli=8)

        assert (
            config.max_concurrent_claude_cli == 8
        ), "max_concurrent_claude_cli should accept custom value"

    def test_serverconfig_accepts_custom_description_refresh_interval_hours(self):
        """
        AC1: ServerConfig accepts custom description_refresh_interval_hours value.

        Given I create a ServerConfig with custom description_refresh_interval_hours
        When I inspect the field
        Then it has the custom value
        """
        config = ServerConfig(
            server_dir="/tmp/test", description_refresh_interval_hours=48
        )

        assert (
            config.description_refresh_interval_hours == 48
        ), "description_refresh_interval_hours should accept custom value"
