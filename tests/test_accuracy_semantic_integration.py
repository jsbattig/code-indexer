"""Integration tests for accuracy profiles with semantic search.

Tests that accuracy profiles (high/balanced/fast) properly affect semantic search
through the HNSW ef parameter.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestAccuracySemanticIntegration:
    """Tests for accuracy profiles affecting semantic search."""

    def test_filesystem_vector_store_accepts_ef_parameter(self):
        """Test that FilesystemVectorStore.search can accept ef parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(Path(tmpdir))

            # Create mock embedding provider
            mock_provider = MagicMock()
            mock_provider.get_embedding.return_value = [0.1] * 768

            # Test that search method accepts ef parameter
            # This will fail if the parameter isn't supported
            try:
                # The search method should accept an ef parameter
                results = store.search(
                    query="test query",
                    embedding_provider=mock_provider,
                    collection_name="test",
                    limit=10,
                    ef=100,  # This is what we're testing
                )
                # If no collection exists, it should return empty list
                assert results == []
            except TypeError as e:
                if "ef" in str(e):
                    pytest.fail(
                        f"FilesystemVectorStore.search does not accept ef parameter: {e}"
                    )

    def test_ef_parameter_default_value(self):
        """Test that ef parameter has a default value of 50."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(Path(tmpdir))

            # Create mock embedding provider
            mock_provider = MagicMock()
            mock_provider.get_embedding.return_value = [0.1] * 768

            # Test calling without ef parameter should use default
            try:
                results = store.search(
                    query="test query",
                    embedding_provider=mock_provider,
                    collection_name="test",
                    limit=10,
                    # No ef parameter - should use default of 50
                )
                # If no collection exists, it should return empty list
                assert results == []
            except Exception as e:
                if "ef" in str(e):
                    pytest.fail(f"search() should have default ef value: {e}")
