"""
Unit tests for PayloadCacheConfig.from_server_config method.

Story #679: Add Payload Cache Settings to Web UI Config Screen

Tests that PayloadCacheConfig can read from server config with env var overrides.
"""

import os
import pytest
from unittest.mock import patch

from code_indexer.server.cache.payload_cache import PayloadCacheConfig
from code_indexer.server.utils.config_manager import CacheConfig


class TestPayloadCacheFromServerConfig:
    """Tests for PayloadCacheConfig.from_server_config class method."""

    def test_from_server_config_uses_cache_config_values(self):
        """Test that from_server_config uses values from CacheConfig."""
        cache_config = CacheConfig(
            payload_preview_size_chars=3000,
            payload_max_fetch_size_chars=8000,
            payload_cache_ttl_seconds=1200,
            payload_cleanup_interval_seconds=90,
        )

        config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.preview_size_chars == 3000
        assert config.max_fetch_size_chars == 8000
        assert config.cache_ttl_seconds == 1200
        assert config.cleanup_interval_seconds == 90

    def test_from_server_config_with_default_cache_config(self):
        """Test that from_server_config works with default CacheConfig values."""
        cache_config = CacheConfig()  # All defaults

        config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.preview_size_chars == 2000
        assert config.max_fetch_size_chars == 5000
        assert config.cache_ttl_seconds == 900
        assert config.cleanup_interval_seconds == 60

    def test_from_server_config_env_override_preview_size(self):
        """Test that env var overrides preview_size_chars from server config."""
        cache_config = CacheConfig(payload_preview_size_chars=3000)

        with patch.dict(os.environ, {"CIDX_PREVIEW_SIZE_CHARS": "5000"}):
            config = PayloadCacheConfig.from_server_config(cache_config)

        # Env var should override server config
        assert config.preview_size_chars == 5000
        # Other values should come from server config (or defaults)
        assert config.max_fetch_size_chars == 5000
        assert config.cache_ttl_seconds == 900
        assert config.cleanup_interval_seconds == 60

    def test_from_server_config_env_override_max_fetch_size(self):
        """Test that env var overrides max_fetch_size_chars from server config."""
        cache_config = CacheConfig(payload_max_fetch_size_chars=8000)

        with patch.dict(os.environ, {"CIDX_MAX_FETCH_SIZE_CHARS": "10000"}):
            config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.max_fetch_size_chars == 10000

    def test_from_server_config_env_override_cache_ttl(self):
        """Test that env var overrides cache_ttl_seconds from server config."""
        cache_config = CacheConfig(payload_cache_ttl_seconds=1200)

        with patch.dict(os.environ, {"CIDX_CACHE_TTL_SECONDS": "1800"}):
            config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.cache_ttl_seconds == 1800

    def test_from_server_config_env_override_cleanup_interval(self):
        """Test that env var overrides cleanup_interval_seconds from server config."""
        cache_config = CacheConfig(payload_cleanup_interval_seconds=90)

        with patch.dict(os.environ, {"CIDX_CLEANUP_INTERVAL_SECONDS": "120"}):
            config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.cleanup_interval_seconds == 120

    def test_from_server_config_invalid_env_var_uses_server_config(self):
        """Test that invalid env var falls back to server config value."""
        cache_config = CacheConfig(payload_preview_size_chars=4000)

        with patch.dict(os.environ, {"CIDX_PREVIEW_SIZE_CHARS": "invalid"}):
            config = PayloadCacheConfig.from_server_config(cache_config)

        # Invalid env var should fall back to server config value
        assert config.preview_size_chars == 4000

    def test_from_server_config_with_none_uses_defaults(self):
        """Test that from_server_config with None cache_config uses defaults."""
        config = PayloadCacheConfig.from_server_config(None)

        assert config.preview_size_chars == 2000
        assert config.max_fetch_size_chars == 5000
        assert config.cache_ttl_seconds == 900
        assert config.cleanup_interval_seconds == 60

    def test_from_server_config_all_env_overrides(self):
        """Test that all env vars override server config values."""
        cache_config = CacheConfig(
            payload_preview_size_chars=1000,
            payload_max_fetch_size_chars=2000,
            payload_cache_ttl_seconds=300,
            payload_cleanup_interval_seconds=30,
        )

        with patch.dict(
            os.environ,
            {
                "CIDX_PREVIEW_SIZE_CHARS": "5000",
                "CIDX_MAX_FETCH_SIZE_CHARS": "10000",
                "CIDX_CACHE_TTL_SECONDS": "1800",
                "CIDX_CLEANUP_INTERVAL_SECONDS": "120",
            },
        ):
            config = PayloadCacheConfig.from_server_config(cache_config)

        assert config.preview_size_chars == 5000
        assert config.max_fetch_size_chars == 10000
        assert config.cache_ttl_seconds == 1800
        assert config.cleanup_interval_seconds == 120
