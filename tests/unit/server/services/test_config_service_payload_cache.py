"""
Unit tests for ConfigService payload cache field handling.

Story #679: Add Payload Cache Settings to Web UI Config Screen

Tests that ConfigService properly exposes and updates payload cache settings.
"""

import pytest

from code_indexer.server.services.config_service import ConfigService


class TestConfigServicePayloadCacheFields:
    """Tests for payload cache fields in ConfigService."""

    def test_get_all_settings_includes_payload_cache_fields(self, tmp_path):
        """Test that get_all_settings() includes payload cache fields."""
        service = ConfigService(str(tmp_path))

        settings = service.get_all_settings()

        assert "cache" in settings
        cache_settings = settings["cache"]

        # Check all payload cache fields are present
        assert "payload_preview_size_chars" in cache_settings
        assert "payload_max_fetch_size_chars" in cache_settings
        assert "payload_cache_ttl_seconds" in cache_settings
        assert "payload_cleanup_interval_seconds" in cache_settings

        # Check default values
        assert cache_settings["payload_preview_size_chars"] == 2000
        assert cache_settings["payload_max_fetch_size_chars"] == 5000
        assert cache_settings["payload_cache_ttl_seconds"] == 900
        assert cache_settings["payload_cleanup_interval_seconds"] == 60

    def test_update_payload_preview_size_chars(self, tmp_path):
        """Test updating payload_preview_size_chars setting."""
        service = ConfigService(str(tmp_path))

        service.update_setting("cache", "payload_preview_size_chars", 3000)

        settings = service.get_all_settings()
        assert settings["cache"]["payload_preview_size_chars"] == 3000

    def test_update_payload_max_fetch_size_chars(self, tmp_path):
        """Test updating payload_max_fetch_size_chars setting."""
        service = ConfigService(str(tmp_path))

        service.update_setting("cache", "payload_max_fetch_size_chars", 8000)

        settings = service.get_all_settings()
        assert settings["cache"]["payload_max_fetch_size_chars"] == 8000

    def test_update_payload_cache_ttl_seconds(self, tmp_path):
        """Test updating payload_cache_ttl_seconds setting."""
        service = ConfigService(str(tmp_path))

        service.update_setting("cache", "payload_cache_ttl_seconds", 1800)

        settings = service.get_all_settings()
        assert settings["cache"]["payload_cache_ttl_seconds"] == 1800

    def test_update_payload_cleanup_interval_seconds(self, tmp_path):
        """Test updating payload_cleanup_interval_seconds setting."""
        service = ConfigService(str(tmp_path))

        service.update_setting("cache", "payload_cleanup_interval_seconds", 120)

        settings = service.get_all_settings()
        assert settings["cache"]["payload_cleanup_interval_seconds"] == 120

    def test_update_all_payload_cache_fields_at_once(self, tmp_path):
        """Test updating all payload cache fields in batch."""
        service = ConfigService(str(tmp_path))

        # Update all settings without saving (batch mode)
        service.update_setting(
            "cache", "payload_preview_size_chars", 4000, skip_validation=True
        )
        service.update_setting(
            "cache", "payload_max_fetch_size_chars", 10000, skip_validation=True
        )
        service.update_setting(
            "cache", "payload_cache_ttl_seconds", 600, skip_validation=True
        )
        service.update_setting(
            "cache", "payload_cleanup_interval_seconds", 30, skip_validation=True
        )

        # Verify all were updated in memory
        settings = service.get_all_settings()
        assert settings["cache"]["payload_preview_size_chars"] == 4000
        assert settings["cache"]["payload_max_fetch_size_chars"] == 10000
        assert settings["cache"]["payload_cache_ttl_seconds"] == 600
        assert settings["cache"]["payload_cleanup_interval_seconds"] == 30

    def test_payload_cache_settings_persist_to_disk(self, tmp_path):
        """Test that payload cache settings persist after save and reload."""
        service = ConfigService(str(tmp_path))

        # Update settings
        service.update_setting("cache", "payload_preview_size_chars", 5000)
        service.update_setting("cache", "payload_max_fetch_size_chars", 12000)
        service.update_setting("cache", "payload_cache_ttl_seconds", 1200)
        service.update_setting("cache", "payload_cleanup_interval_seconds", 45)

        # Create new service instance (simulating server restart)
        service2 = ConfigService(str(tmp_path))
        settings = service2.get_all_settings()

        # Verify settings persisted
        assert settings["cache"]["payload_preview_size_chars"] == 5000
        assert settings["cache"]["payload_max_fetch_size_chars"] == 12000
        assert settings["cache"]["payload_cache_ttl_seconds"] == 1200
        assert settings["cache"]["payload_cleanup_interval_seconds"] == 45
