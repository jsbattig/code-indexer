"""Test fixed-size chunker integration with configuration.

Tests to verify:
1. Fixed-size chunker works with IndexingConfig
2. Configuration values are available but chunker uses its own constants per Epic Story 3
3. No semantic chunking configuration references remain
"""

from code_indexer.config import IndexingConfig, Config
from code_indexer.indexing.fixed_size_chunker import FixedSizeChunker


class TestFixedSizeChunkerConfigIntegration:
    """Test fixed-size chunker integration with configuration system."""

    def test_chunker_accepts_indexing_config(self):
        """Verify chunker can be created with IndexingConfig."""
        config = IndexingConfig()
        chunker = FixedSizeChunker(config)

        # Should store the config
        assert chunker.config == config
        assert chunker.config.chunk_size == 1500  # default
        assert chunker.config.chunk_overlap == 150  # default

    def test_chunker_uses_model_aware_chunk_sizes(self):
        """Verify chunker uses model-aware chunk sizes, not config values."""
        # With IndexingConfig only, should use default (1000) for backward compatibility

        config = IndexingConfig(chunk_size=2000, chunk_overlap=500)  # Different values
        chunker = FixedSizeChunker(config)

        # With IndexingConfig only, should use default size
        assert chunker.chunk_size == 1000  # Default for IndexingConfig
        assert chunker.overlap_size == 150  # 15% of 1000
        assert chunker.step_size == 850  # 1000 - 150

        # Config values should be preserved but not used by model-aware chunker
        assert chunker.config.chunk_size == 2000
        assert chunker.config.chunk_overlap == 500

    def test_chunker_produces_fixed_size_chunks_regardless_of_config(self):
        """Verify chunker produces 1000-character chunks regardless of config values."""
        # Test with different config values
        config1 = IndexingConfig(chunk_size=500, chunk_overlap=50)
        config2 = IndexingConfig(chunk_size=2000, chunk_overlap=300)

        chunker1 = FixedSizeChunker(config1)
        chunker2 = FixedSizeChunker(config2)

        # Create test text longer than 2000 characters
        test_text = "x" * 2500

        chunks1 = chunker1.chunk_text(test_text)
        chunks2 = chunker2.chunk_text(test_text)

        # Both should produce the same chunk structure (except last chunk)
        assert len(chunks1) == len(chunks2)

        # All chunks except the last should be exactly 1000 characters
        for i, (chunk1, chunk2) in enumerate(zip(chunks1[:-1], chunks2[:-1])):
            assert len(chunk1["text"]) == 1000
            assert len(chunk2["text"]) == 1000
            assert chunk1["text"] == chunk2["text"]  # Same chunking pattern

    def test_config_validation_still_works(self):
        """Verify configuration validation still works for other settings."""
        config = IndexingConfig(
            chunk_size=1500,
            chunk_overlap=150,
            max_file_size=2097152,
            index_comments=True,
        )

        chunker = FixedSizeChunker(config)

        # Config validation should still work for other fields
        assert config.max_file_size == 2097152
        assert config.index_comments is True

        # Chunker should have access to all config settings
        assert chunker.config.max_file_size == 2097152
        assert chunker.config.index_comments is True


class TestConfigurationCleanness:
    """Test that configuration system is clean of semantic references."""

    def test_indexing_config_has_no_semantic_fields(self):
        """Verify IndexingConfig has no semantic chunking fields."""
        config = IndexingConfig()

        # Get all field names
        field_names = set(config.model_fields.keys())

        # Should not have any semantic-related fields
        semantic_fields = [
            field for field in field_names if "semantic" in field.lower()
        ]
        assert len(semantic_fields) == 0, f"Found semantic fields: {semantic_fields}"

        # Should have expected chunking fields
        assert "chunk_size" in field_names
        assert "chunk_overlap" in field_names

        # Should not have use_semantic_chunking
        assert "use_semantic_chunking" not in field_names

    def test_main_config_has_no_semantic_fields(self):
        """Verify main Config has no semantic chunking fields."""
        config = Config()

        # Get all field names from all sections
        all_field_names = set()

        # Check main config fields
        all_field_names.update(config.model_fields.keys())

        # Check nested config fields
        all_field_names.update(config.indexing.model_fields.keys())
        all_field_names.update(config.qdrant.model_fields.keys())
        all_field_names.update(config.ollama.model_fields.keys())
        all_field_names.update(config.voyage_ai.model_fields.keys())

        # Should not have any semantic-related fields
        semantic_fields = [
            field for field in all_field_names if "semantic" in field.lower()
        ]
        assert len(semantic_fields) == 0, f"Found semantic fields: {semantic_fields}"

        # Should not have use_semantic_chunking anywhere
        assert "use_semantic_chunking" not in all_field_names


class TestBackwardsCompatibility:
    """Test that old configuration files work correctly."""

    def test_config_ignores_unknown_semantic_fields(self):
        """Verify that loading config with old semantic fields works gracefully."""
        # This mimics loading an old config file with semantic options
        config_data = {
            "chunk_size": 1200,
            "chunk_overlap": 200,
            "max_file_size": 2097152,
            "index_comments": True,
            # Old semantic options that should be ignored
            "use_semantic_chunking": True,
            "semantic_parser_type": "tree-sitter",
            "ast_parsing_enabled": False,
        }

        # Should create config successfully, ignoring unknown fields
        config = IndexingConfig(**config_data)

        # Should have the valid fields
        assert config.chunk_size == 1200
        assert config.chunk_overlap == 200
        assert config.max_file_size == 2097152
        assert config.index_comments is True

        # Should not have semantic fields
        assert not hasattr(config, "use_semantic_chunking")
        assert not hasattr(config, "semantic_parser_type")
        assert not hasattr(config, "ast_parsing_enabled")

    def test_chunker_works_with_legacy_config_values(self):
        """Verify chunker works correctly even with legacy config values."""
        # Create config with values that might come from old config files
        config = IndexingConfig(
            chunk_size=800,  # Old semantic chunking size
            chunk_overlap=100,  # Old semantic chunking overlap
        )

        chunker = FixedSizeChunker(config)

        # Should still use fixed constants
        test_text = "a" * 3000
        chunks = chunker.chunk_text(test_text)

        # Should produce chunks according to fixed-size algorithm
        assert len(chunks[0]["text"]) == 1000  # Not 800 from config
        assert chunks[1]["text"].startswith(
            chunks[0]["text"][-150:]
        )  # 150-char overlap, not 100

        # Config values should be preserved for other uses
        assert chunker.config.chunk_size == 800
        assert chunker.config.chunk_overlap == 100


class TestDocumentationConsistency:
    """Test that configuration documentation is consistent."""

    def test_chunk_size_and_overlap_still_documented(self):
        """Verify chunk_size and chunk_overlap are still available in config."""
        # These settings should remain available even though the fixed-size
        # chunker doesn't use them, for future flexibility and compatibility

        config = IndexingConfig()

        # Should have these fields for future use
        assert hasattr(config, "chunk_size")
        assert hasattr(config, "chunk_overlap")

        # Should have reasonable defaults
        assert config.chunk_size > 0
        assert config.chunk_overlap >= 0
        assert config.chunk_overlap < config.chunk_size


class TestModelAwareChunking:
    """Test model-aware chunk size selection."""

    def test_voyage_code_3_uses_4096_chunk_size(self):
        """Verify voyage-code-3 uses optimized 4096 character chunks."""
        config = Config()
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-3"

        chunker = FixedSizeChunker(config)

        assert chunker.chunk_size == 4096  # Optimized for voyage-code-3
        assert chunker.overlap_size == 614  # 15% of 4096
        assert chunker.step_size == 3482  # 4096 - 614

    def test_nomic_embed_text_uses_2048_chunk_size(self):
        """Verify nomic-embed-text uses 2048 character chunks."""
        config = Config()
        config.embedding_provider = "ollama"
        config.ollama.model = "nomic-embed-text"

        chunker = FixedSizeChunker(config)

        assert chunker.chunk_size == 2048  # Optimized for nomic-embed-text
        assert chunker.overlap_size == 307  # 15% of 2048
        assert chunker.step_size == 1741  # 2048 - 307

    def test_unknown_model_uses_default_size(self):
        """Verify unknown models use default 1000 character chunks."""
        config = Config()
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "unknown-model"

        chunker = FixedSizeChunker(config)

        assert chunker.chunk_size == 1000  # Default fallback
        assert chunker.overlap_size == 150  # 15% of 1000
        assert chunker.step_size == 850  # 1000 - 150

    def test_backward_compatibility_with_indexing_config(self):
        """Verify IndexingConfig still works with default chunk size."""
        config = IndexingConfig()
        chunker = FixedSizeChunker(config)

        assert chunker.chunk_size == 1000  # Default for backward compatibility
        assert chunker.overlap_size == 150  # 15% of 1000
        assert chunker.step_size == 850  # 1000 - 150

    def test_model_aware_chunking_actually_produces_different_sizes(self):
        """Verify that different models actually produce different chunk sizes."""
        test_text = "a" * 10000  # Large enough for multiple chunks

        # VoyageAI config
        config_voyage = Config()
        config_voyage.embedding_provider = "voyage-ai"
        config_voyage.voyage_ai.model = "voyage-code-3"
        chunker_voyage = FixedSizeChunker(config_voyage)

        # Ollama config
        config_ollama = Config()
        config_ollama.embedding_provider = "ollama"
        config_ollama.ollama.model = "nomic-embed-text"
        chunker_ollama = FixedSizeChunker(config_ollama)

        # Get chunks from both
        voyage_chunks = chunker_voyage.chunk_text(test_text)
        ollama_chunks = chunker_ollama.chunk_text(test_text)

        # VoyageAI should produce larger chunks
        assert len(voyage_chunks[0]["text"]) == 4096
        assert len(ollama_chunks[0]["text"]) == 2048

        # VoyageAI should produce fewer total chunks (larger chunk size)
        assert len(voyage_chunks) < len(ollama_chunks)
