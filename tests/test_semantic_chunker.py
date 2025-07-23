"""
Tests for the SemanticChunker infrastructure.
Following TDD approach - writing tests first.
"""

from code_indexer.config import IndexingConfig
from code_indexer.indexing.chunker import TextChunker


class TestSemanticChunkerInfrastructure:
    """Test the base SemanticChunker class and infrastructure."""

    def test_semantic_chunker_exists(self):
        """Test that SemanticChunker class can be imported."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        assert SemanticChunker is not None

    def test_semantic_chunker_initialization(self):
        """Test SemanticChunker can be initialized with config."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        config = IndexingConfig(
            chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
        )

        chunker = SemanticChunker(config)
        assert chunker.config == config
        assert isinstance(chunker.text_chunker, TextChunker)
        assert hasattr(chunker, "parsers")

    def test_semantic_chunker_language_support(self):
        """Test SemanticChunker supports expected languages."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        config = IndexingConfig(use_semantic_chunking=True)
        chunker = SemanticChunker(config)

        expected_languages = ["python", "javascript", "typescript", "java", "go"]
        for lang in expected_languages:
            assert lang in chunker.parsers

    def test_semantic_chunker_fallback_to_text(self):
        """Test fallback to text chunking for unsupported files."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        config = IndexingConfig(use_semantic_chunking=True)
        chunker = SemanticChunker(config)

        # Test with truly unsupported file types (no semantic parsers available)
        test_cases = [
            ("test.txt", "This is a plain text file.\nWith multiple lines."),
            ("data.csv", "name,age\nJohn,30\nJane,25"),
            ("script.sh", "#!/bin/bash\necho 'Hello World'"),
            ("unknown.xyz", "Some content in an unknown format with actual text"),
            ("config.ini", "[section]\nkey=value\nother=setting"),
        ]

        for filename, content in test_cases:
            chunks = chunker.chunk_content(content, filename)
            assert len(chunks) > 0, f"Should produce chunks for {filename}"
            assert (
                chunks[0]["semantic_chunking"] is False
            ), f"Should fall back to text chunking for {filename}"

    def test_semantic_chunker_respects_config_flag(self):
        """Test that semantic chunking is disabled when config flag is False."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        config = IndexingConfig(use_semantic_chunking=False)
        chunker = SemanticChunker(config)

        # Even with a Python file, should use text chunking
        content = "def hello():\n    print('Hello')"
        chunks = chunker.chunk_content(content, "test.py")

        assert chunks[0]["semantic_chunking"] is False

    def test_semantic_chunk_metadata_structure(self):
        """Test that semantic chunks have required metadata fields."""
        from code_indexer.indexing.semantic_chunker import SemanticChunk

        chunk = SemanticChunk(
            text="def hello(): pass",
            chunk_index=0,
            total_chunks=1,
            size=17,
            file_path="test.py",
            file_extension=".py",
            line_start=1,
            line_end=1,
            semantic_chunking=True,
            semantic_type="function",
            semantic_name="hello",
            semantic_path="hello",
            semantic_signature="def hello():",
            semantic_parent=None,
            semantic_context={},
            semantic_scope="global",
            semantic_language_features=[],
        )

        # Check all required fields exist
        required_fields = [
            "text",
            "chunk_index",
            "total_chunks",
            "size",
            "file_path",
            "file_extension",
            "line_start",
            "line_end",
            "semantic_chunking",
            "semantic_type",
            "semantic_name",
            "semantic_path",
            "semantic_signature",
        ]

        for field in required_fields:
            assert hasattr(chunk, field)

    def test_semantic_chunker_error_handling(self):
        """Test that parser errors fall back to text chunking gracefully."""
        from code_indexer.indexing.semantic_chunker import SemanticChunker

        config = IndexingConfig(use_semantic_chunking=True)
        chunker = SemanticChunker(config)

        # Malformed Python that should fail AST parsing
        content = "def broken_function(\n    # Missing closing paren and body"
        chunks = chunker.chunk_content(content, "broken.py")

        # Should fall back to text chunking
        assert len(chunks) > 0
        assert chunks[0]["semantic_chunking"] is False
