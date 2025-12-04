"""
Tests for ConfigService Claude CLI settings exposure (Story #546 - AC3).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import tempfile

import pytest

from src.code_indexer.server.services.config_service import ConfigService


# =============================================================================
# AC3: ConfigService exposes new fields
# =============================================================================


class TestConfigServiceNewFields:
    """Tests for ConfigService exposure of new Claude CLI fields."""

    def test_config_service_get_all_settings_includes_claude_cli_section(self):
        """
        AC3: ConfigService.get_all_settings() includes claude_cli section.

        Given I create a ConfigService
        When I call get_all_settings()
        Then it includes a claude_cli section with new fields
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            settings = service.get_all_settings()

            assert "claude_cli" in settings, (
                "get_all_settings should include claude_cli section"
            )

    def test_config_service_exposes_max_concurrent_claude_cli(self):
        """
        AC3: ConfigService exposes max_concurrent_claude_cli in claude_cli section.

        Given I create a ConfigService
        When I call get_all_settings()
        Then claude_cli section includes max_concurrent_claude_cli
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            settings = service.get_all_settings()

            assert "max_concurrent_claude_cli" in settings["claude_cli"], (
                "claude_cli section should include max_concurrent_claude_cli"
            )
            assert settings["claude_cli"]["max_concurrent_claude_cli"] == 4, (
                "max_concurrent_claude_cli should default to 4"
            )

    def test_config_service_exposes_description_refresh_interval_hours(self):
        """
        AC3: ConfigService exposes description_refresh_interval_hours in claude_cli section.

        Given I create a ConfigService
        When I call get_all_settings()
        Then claude_cli section includes description_refresh_interval_hours
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            settings = service.get_all_settings()

            assert "description_refresh_interval_hours" in settings["claude_cli"], (
                "claude_cli section should include description_refresh_interval_hours"
            )
            assert settings["claude_cli"]["description_refresh_interval_hours"] == 24, (
                "description_refresh_interval_hours should default to 24"
            )

    def test_config_service_masks_anthropic_api_key_when_set(self):
        """
        AC3: ConfigService masks anthropic_api_key showing only prefix.

        Given I have a config with anthropic_api_key set
        When I call get_all_settings()
        Then anthropic_api_key shows as "sk-ant-***"
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            # Set API key
            config = service.get_config()
            config.anthropic_api_key = "sk-ant-api03-test-key-123456789"
            service.config_manager.save_config(config)

            # Reload to get fresh settings
            service._config = None
            settings = service.get_all_settings()

            assert "anthropic_api_key" in settings["claude_cli"], (
                "claude_cli section should include anthropic_api_key"
            )
            assert settings["claude_cli"]["anthropic_api_key"] == "sk-ant-***", (
                "anthropic_api_key should be masked"
            )

    def test_config_service_shows_none_when_anthropic_api_key_not_set(self):
        """
        AC3: ConfigService shows None when anthropic_api_key is not set.

        Given I have a config without anthropic_api_key
        When I call get_all_settings()
        Then anthropic_api_key shows as None
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            settings = service.get_all_settings()

            assert settings["claude_cli"]["anthropic_api_key"] is None, (
                "anthropic_api_key should be None when not set"
            )

    def test_config_service_update_setting_accepts_claude_cli_category(self):
        """
        AC3: ConfigService.update_setting() accepts claude_cli category.

        Given I create a ConfigService
        When I call update_setting("claude_cli", "max_concurrent_claude_cli", 8)
        Then the setting is updated and persisted
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            service.update_setting("claude_cli", "max_concurrent_claude_cli", 8)

            # Verify it's updated
            settings = service.get_all_settings()
            assert settings["claude_cli"]["max_concurrent_claude_cli"] == 8, (
                "max_concurrent_claude_cli should be updated to 8"
            )

            # Verify it's persisted
            service2 = ConfigService(tmpdir)
            settings2 = service2.get_all_settings()
            assert settings2["claude_cli"]["max_concurrent_claude_cli"] == 8, (
                "max_concurrent_claude_cli should persist after reload"
            )

    def test_config_service_update_setting_accepts_anthropic_api_key(self):
        """
        AC3: ConfigService.update_setting() accepts anthropic_api_key updates.

        Given I create a ConfigService
        When I call update_setting("claude_cli", "anthropic_api_key", "sk-ant-...")
        Then the API key is updated and persisted (unmasked in storage)
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            service.update_setting("claude_cli", "anthropic_api_key", "sk-ant-api03-test-key-123")

            # Verify it's stored unmasked
            config = service.get_config()
            assert config.anthropic_api_key == "sk-ant-api03-test-key-123", (
                "anthropic_api_key should be stored unmasked"
            )

            # Verify get_all_settings masks it
            settings = service.get_all_settings()
            assert settings["claude_cli"]["anthropic_api_key"] == "sk-ant-***", (
                "anthropic_api_key should be masked in get_all_settings"
            )

    def test_config_service_update_setting_validates_max_concurrent_claude_cli(self):
        """
        AC3: ConfigService.update_setting() validates max_concurrent_claude_cli.

        Given I create a ConfigService
        When I call update_setting with invalid max_concurrent_claude_cli (0)
        Then it raises ValueError
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            with pytest.raises(ValueError) as exc_info:
                service.update_setting("claude_cli", "max_concurrent_claude_cli", 0)

            assert "max_concurrent_claude_cli" in str(exc_info.value).lower(), (
                "Error should mention max_concurrent_claude_cli"
            )

    def test_config_service_update_setting_validates_description_refresh_interval_hours(self):
        """
        AC3: ConfigService.update_setting() validates description_refresh_interval_hours.

        Given I create a ConfigService
        When I call update_setting with invalid description_refresh_interval_hours (0)
        Then it raises ValueError
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            service = ConfigService(tmpdir)

            with pytest.raises(ValueError) as exc_info:
                service.update_setting("claude_cli", "description_refresh_interval_hours", 0)

            assert "description_refresh_interval_hours" in str(exc_info.value).lower(), (
                "Error should mention description_refresh_interval_hours"
            )
