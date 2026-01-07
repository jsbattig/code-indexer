"""Unit tests for PayloadCacheConfig.

Story #679: S1 - Semantic Search with Payload Control (Foundation)
AC1: Configuration Parameters

These tests follow TDD methodology - written BEFORE implementation.
"""

import os
import pytest
from unittest.mock import patch


class TestPayloadCacheConfig:
    """Tests for PayloadCacheConfig dataclass (AC1)."""

    def test_default_values(self):
        """Test that PayloadCacheConfig has correct default values."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        config = PayloadCacheConfig()

        assert config.preview_size_chars == 2000
        assert config.max_fetch_size_chars == 5000
        assert config.cache_ttl_seconds == 900
        assert config.cleanup_interval_seconds == 60

    def test_custom_values(self):
        """Test that PayloadCacheConfig accepts custom values."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        config = PayloadCacheConfig(
            preview_size_chars=1000,
            max_fetch_size_chars=3000,
            cache_ttl_seconds=300,
            cleanup_interval_seconds=30,
        )

        assert config.preview_size_chars == 1000
        assert config.max_fetch_size_chars == 3000
        assert config.cache_ttl_seconds == 300
        assert config.cleanup_interval_seconds == 30

    def test_env_override_preview_size(self):
        """Test CIDX_PREVIEW_SIZE_CHARS environment variable override."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        with patch.dict(os.environ, {"CIDX_PREVIEW_SIZE_CHARS": "3000"}):
            config = PayloadCacheConfig.from_env()
            assert config.preview_size_chars == 3000

    def test_env_override_max_fetch_size(self):
        """Test CIDX_MAX_FETCH_SIZE_CHARS environment variable override."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        with patch.dict(os.environ, {"CIDX_MAX_FETCH_SIZE_CHARS": "10000"}):
            config = PayloadCacheConfig.from_env()
            assert config.max_fetch_size_chars == 10000

    def test_env_override_cache_ttl(self):
        """Test CIDX_CACHE_TTL_SECONDS environment variable override."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        with patch.dict(os.environ, {"CIDX_CACHE_TTL_SECONDS": "1800"}):
            config = PayloadCacheConfig.from_env()
            assert config.cache_ttl_seconds == 1800

    def test_env_override_cleanup_interval(self):
        """Test CIDX_CLEANUP_INTERVAL_SECONDS environment variable override."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        with patch.dict(os.environ, {"CIDX_CLEANUP_INTERVAL_SECONDS": "120"}):
            config = PayloadCacheConfig.from_env()
            assert config.cleanup_interval_seconds == 120

    def test_env_override_invalid_values_use_defaults(self):
        """Test that invalid env values fall back to defaults."""
        from code_indexer.server.cache.payload_cache import PayloadCacheConfig

        with patch.dict(os.environ, {"CIDX_PREVIEW_SIZE_CHARS": "invalid"}):
            config = PayloadCacheConfig.from_env()
            assert config.preview_size_chars == 2000  # Default
