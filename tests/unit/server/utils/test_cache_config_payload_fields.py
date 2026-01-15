"""
Unit tests for CacheConfig payload cache fields.

Story #679: Add Payload Cache Settings to Web UI Config Screen

Tests that CacheConfig dataclass has the new payload cache fields
and that they work correctly with ServerConfig serialization/deserialization.
"""

import json

from code_indexer.server.utils.config_manager import (
    CacheConfig,
    ServerConfig,
    ServerConfigManager,
)


class TestCacheConfigPayloadFields:
    """Tests for payload cache fields in CacheConfig."""

    def test_cache_config_has_payload_preview_size_chars_default(self):
        """Test that CacheConfig has payload_preview_size_chars with default 2000."""
        config = CacheConfig()
        assert config.payload_preview_size_chars == 2000

    def test_cache_config_has_payload_max_fetch_size_chars_default(self):
        """Test that CacheConfig has payload_max_fetch_size_chars with default 5000."""
        config = CacheConfig()
        assert config.payload_max_fetch_size_chars == 5000

    def test_cache_config_has_payload_cache_ttl_seconds_default(self):
        """Test that CacheConfig has payload_cache_ttl_seconds with default 900."""
        config = CacheConfig()
        assert config.payload_cache_ttl_seconds == 900

    def test_cache_config_has_payload_cleanup_interval_seconds_default(self):
        """Test that CacheConfig has payload_cleanup_interval_seconds with default 60."""
        config = CacheConfig()
        assert config.payload_cleanup_interval_seconds == 60

    def test_cache_config_accepts_custom_payload_values(self):
        """Test that CacheConfig accepts custom payload cache values."""
        config = CacheConfig(
            payload_preview_size_chars=3000,
            payload_max_fetch_size_chars=8000,
            payload_cache_ttl_seconds=1800,
            payload_cleanup_interval_seconds=120,
        )

        assert config.payload_preview_size_chars == 3000
        assert config.payload_max_fetch_size_chars == 8000
        assert config.payload_cache_ttl_seconds == 1800
        assert config.payload_cleanup_interval_seconds == 120


class TestServerConfigPayloadFieldsPersistence:
    """Tests for payload cache field persistence in ServerConfig."""

    def test_server_config_default_cache_config_has_payload_fields(self, tmp_path):
        """Test that ServerConfig's default CacheConfig has payload fields."""
        config = ServerConfig(server_dir=str(tmp_path))

        # cache_config is auto-created by __post_init__
        assert config.cache_config is not None
        assert config.cache_config.payload_preview_size_chars == 2000
        assert config.cache_config.payload_max_fetch_size_chars == 5000
        assert config.cache_config.payload_cache_ttl_seconds == 900
        assert config.cache_config.payload_cleanup_interval_seconds == 60

    def test_server_config_saves_payload_fields_to_json(self, tmp_path):
        """Test that payload cache fields are saved to config.json."""
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.create_default_config()

        # Set custom payload cache values
        config.cache_config.payload_preview_size_chars = 4000
        config.cache_config.payload_max_fetch_size_chars = 10000
        config.cache_config.payload_cache_ttl_seconds = 600
        config.cache_config.payload_cleanup_interval_seconds = 30

        config_manager.save_config(config)

        # Verify saved JSON
        config_file = tmp_path / "config.json"
        with open(config_file) as f:
            saved_config = json.load(f)

        assert saved_config["cache_config"]["payload_preview_size_chars"] == 4000
        assert saved_config["cache_config"]["payload_max_fetch_size_chars"] == 10000
        assert saved_config["cache_config"]["payload_cache_ttl_seconds"] == 600
        assert saved_config["cache_config"]["payload_cleanup_interval_seconds"] == 30

    def test_server_config_loads_payload_fields_from_json(self, tmp_path):
        """Test that payload cache fields are loaded from config.json."""
        # Create config file with custom payload cache values
        config_data = {
            "server_dir": str(tmp_path),
            "cache_config": {
                "index_cache_ttl_minutes": 10.0,
                "index_cache_cleanup_interval": 60,
                "fts_cache_ttl_minutes": 10.0,
                "fts_cache_cleanup_interval": 60,
                "fts_cache_reload_on_access": True,
                "payload_preview_size_chars": 5000,
                "payload_max_fetch_size_chars": 15000,
                "payload_cache_ttl_seconds": 1200,
                "payload_cleanup_interval_seconds": 90,
            },
        }

        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Load config
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.load_config()

        assert config is not None
        assert config.cache_config is not None
        assert config.cache_config.payload_preview_size_chars == 5000
        assert config.cache_config.payload_max_fetch_size_chars == 15000
        assert config.cache_config.payload_cache_ttl_seconds == 1200
        assert config.cache_config.payload_cleanup_interval_seconds == 90

    def test_server_config_backward_compatible_without_payload_fields(self, tmp_path):
        """Test that old config files without payload fields use defaults."""
        # Create config file WITHOUT payload cache fields (old format)
        config_data = {
            "server_dir": str(tmp_path),
            "cache_config": {
                "index_cache_ttl_minutes": 10.0,
                "index_cache_cleanup_interval": 60,
                "fts_cache_ttl_minutes": 10.0,
                "fts_cache_cleanup_interval": 60,
                "fts_cache_reload_on_access": True,
                # No payload fields - simulating old config file
            },
        }

        config_file = tmp_path / "config.json"
        with open(config_file, "w") as f:
            json.dump(config_data, f)

        # Load config - should use defaults for missing payload fields
        config_manager = ServerConfigManager(str(tmp_path))
        config = config_manager.load_config()

        assert config is not None
        assert config.cache_config is not None
        # Should use defaults for missing fields
        assert config.cache_config.payload_preview_size_chars == 2000
        assert config.cache_config.payload_max_fetch_size_chars == 5000
        assert config.cache_config.payload_cache_ttl_seconds == 900
        assert config.cache_config.payload_cleanup_interval_seconds == 60
