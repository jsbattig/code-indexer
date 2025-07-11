"""
Integration test for semantic chunking.
Tests that semantic chunking works end-to-end in the indexing pipeline.
"""

import tempfile
from pathlib import Path

import pytest

from code_indexer.config import Config, IndexingConfig
from code_indexer.indexing.processor import DocumentProcessor


class TestSemanticChunkingIntegration:
    """Test semantic chunking integration with the indexing pipeline."""

    @pytest.fixture
    def temp_codebase(self):
        """Create a temporary directory with Python files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            python_file = Path(tmpdir) / "example.py"
            python_file.write_text(
                '''
def hello_world():
    """Say hello to the world."""
    print("Hello, World!")
    return True

class Calculator:
    """A simple calculator class."""
    
    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b
    
    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        return a - b
'''.strip()
            )

            yield Path(tmpdir)

    def test_semantic_chunking_in_processor(self, temp_codebase):
        """Test that semantic chunking works in the document processor."""
        # Create config with semantic chunking enabled
        config = Config(
            codebase_dir=temp_codebase,
            indexing=IndexingConfig(
                chunk_size=2000, chunk_overlap=200, use_semantic_chunking=True
            ),
        )

        # Create mock services
        class MockQdrantClient:
            def __init__(self):
                self.indexed_chunks = []

            def index_chunks(self, chunks):
                self.indexed_chunks.extend(chunks)

        class MockEmbeddingProvider:
            def get_embeddings(self, texts):
                # Return fake embeddings
                return [[0.1] * 768 for _ in texts]

        qdrant_client = MockQdrantClient()
        embedding_provider = MockEmbeddingProvider()

        # Create processor
        processor = DocumentProcessor(config, embedding_provider, qdrant_client)

        # Process the Python file
        python_file = temp_codebase / "example.py"
        chunks = processor.text_chunker.chunk_file(python_file)

        # Verify semantic chunking was used
        assert len(chunks) > 0

        # Check that chunks have semantic metadata
        for chunk in chunks:
            if chunk.get("semantic_chunking", False):
                assert "semantic_type" in chunk
                assert "semantic_name" in chunk
                assert "semantic_path" in chunk

        # Verify we got separate chunks for function and class
        chunk_types = [
            c.get("semantic_type") for c in chunks if c.get("semantic_chunking")
        ]
        assert "function" in chunk_types
        assert "class" in chunk_types

        # Verify semantic names
        chunk_names = [
            c.get("semantic_name") for c in chunks if c.get("semantic_chunking")
        ]
        assert "hello_world" in chunk_names
        assert "Calculator" in chunk_names

    def test_semantic_chunking_disabled(self, temp_codebase):
        """Test that semantic chunking can be disabled."""
        # Create config with semantic chunking disabled
        config = Config(
            codebase_dir=temp_codebase,
            indexing=IndexingConfig(
                chunk_size=500,  # Small chunk size to force multiple chunks
                chunk_overlap=50,
                use_semantic_chunking=False,
            ),
        )

        # Create processor
        processor = DocumentProcessor(config, None, None)

        # Process the Python file
        python_file = temp_codebase / "example.py"
        chunks = processor.text_chunker.chunk_file(python_file)

        # Verify text chunking was used
        assert len(chunks) > 0

        # Check that chunks don't have semantic metadata
        for chunk in chunks:
            assert not chunk.get("semantic_chunking", False)
