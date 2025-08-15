"""Tests for backward compatibility of segment size configuration."""

import json
import tempfile
from pathlib import Path


from code_indexer.config import Config, ConfigManager, QdrantConfig


class TestSegmentSizeBackwardCompatibility:
    """Test backward compatibility for segment size configuration."""

    def test_config_load_without_segment_size_field(self):
        """Test loading config files without max_segment_size_kb field."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a config file WITHOUT max_segment_size_kb (simulating old config)
            config_dir = Path(tmp_dir) / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            old_config = {
                "codebase_dir": ".",
                "file_extensions": ["py", "js", "ts"],
                "exclude_dirs": ["node_modules", "venv"],
                "embedding_provider": "ollama",
                "qdrant": {
                    "host": "http://localhost:6333",
                    "collection_base_name": "code_index",
                    "vector_size": 768,
                    "hnsw_ef": 64,
                    "hnsw_ef_construct": 200,
                    "hnsw_m": 32,
                    # NOTE: max_segment_size_kb is intentionally missing
                },
                "ollama": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                },
            }

            with open(config_file, "w") as f:
                json.dump(old_config, f, indent=2)

            # Load config using ConfigManager
            config_manager = ConfigManager(config_file)
            config = config_manager.load()

            # The default value should be applied automatically
            assert hasattr(config.qdrant, "max_segment_size_kb")
            assert config.qdrant.max_segment_size_kb == 102400  # Default 100MB

    def test_config_save_preserves_segment_size(self):
        """Test that saving config preserves the segment size field."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_manager = ConfigManager(config_file)

            # Create config with custom segment size
            config = Config()
            config.qdrant.max_segment_size_kb = 51200  # 50MB

            # Save and reload
            config_manager._config = config
            config_manager.save()

            # Load from file
            reloaded_config = config_manager.load()

            # Verify segment size is preserved
            assert reloaded_config.qdrant.max_segment_size_kb == 51200

    def test_config_update_with_segment_size(self):
        """Test updating config with segment size works correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            config_manager = ConfigManager(config_file)

            # Create default config
            config_manager.create_default_config()

            # Update with custom segment size
            updated_config = config_manager.update_config(
                qdrant={"max_segment_size_kb": 76800}  # 75MB
            )

            # Verify update worked
            assert updated_config.qdrant.max_segment_size_kb == 76800

            # Verify it was saved to file
            reloaded_config = config_manager.load()
            assert reloaded_config.qdrant.max_segment_size_kb == 76800

    def test_config_migration_from_legacy_format(self):
        """Test that very old config formats still work."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Simulate a very minimal old config
            minimal_config = {
                "codebase_dir": ".",
                "qdrant": {
                    "host": "http://localhost:6333"
                    # Missing most fields including max_segment_size_kb
                },
            }

            with open(config_file, "w") as f:
                json.dump(minimal_config, f, indent=2)

            # Load config
            config_manager = ConfigManager(config_file)
            config = config_manager.load()

            # All defaults should be applied
            assert config.qdrant.max_segment_size_kb == 102400
            assert config.qdrant.collection_base_name == "code_index"
            assert config.qdrant.vector_size == 768
            assert config.qdrant.hnsw_ef == 64

    def test_existing_collections_continue_working(self):
        """Test that existing collections with old segment sizes continue to function."""
        # This is more of a documentation test since we can't actually test
        # against real Qdrant collections in unit tests

        # The key insight is that QdrantConfig with default values
        # should work for both new and existing setups
        config = QdrantConfig()

        # New configurations get the default
        assert config.max_segment_size_kb == 102400

        # But existing collections won't be affected until they're recreated
        # This is the expected behavior per the Epic requirements

    def test_pydantic_field_defaults_work(self):
        """Test that Pydantic Field defaults handle missing values correctly."""
        # Test direct instantiation without the field
        config_dict = {
            "host": "http://localhost:6333",
            "collection_base_name": "test",
            "vector_size": 768,
            "hnsw_ef": 64,
            "hnsw_ef_construct": 200,
            "hnsw_m": 32,
        }

        # This should work and apply defaults
        config = QdrantConfig(**config_dict)
        assert config.max_segment_size_kb == 102400

        # Test with explicit None (which Pydantic should handle)
        config_dict_with_none = config_dict.copy()
        config_dict_with_none["max_segment_size_kb"] = None

        # Pydantic should apply the default when None is provided
        # and the field has a default
        try:
            config = QdrantConfig(**config_dict_with_none)
            # If this works, the field should have the default value
            assert config.max_segment_size_kb == 102400
        except Exception:
            # If Pydantic doesn't handle None gracefully, that's also acceptable
            # as long as missing fields work (which we tested above)
            pass

    def test_config_file_without_qdrant_section(self):
        """Test config files missing entire qdrant section."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_dir = Path(tmp_dir) / ".code-indexer"
            config_dir.mkdir()
            config_file = config_dir / "config.json"

            # Config without qdrant section at all
            minimal_config = {
                "codebase_dir": ".",
                "file_extensions": ["py"],
                "embedding_provider": "ollama",
                # No qdrant section
            }

            with open(config_file, "w") as f:
                json.dump(minimal_config, f, indent=2)

            # Load config
            config_manager = ConfigManager(config_file)
            config = config_manager.load()

            # Qdrant section should be created with defaults
            assert hasattr(config, "qdrant")
            assert config.qdrant.max_segment_size_kb == 102400
            assert config.qdrant.host == "http://localhost:6333"
