"""
Unit tests for SemanticSearchService with FilesystemVectorStore parameter correctness.

Tests that SemanticSearchService calls FilesystemVectorStore.search() with correct parameters:
- query (string) not query_vector
- embedding_provider (service) for parallel execution

Following CLAUDE.md Foundation #1: Real systems only, no mocks (except for external services).
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.code_indexer.server.services.search_service import SemanticSearchService
from src.code_indexer.server.models.api_models import SemanticSearchRequest
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestSearchServiceFilesystemParameters:
    """Test SemanticSearchService passes correct parameters to FilesystemVectorStore.search()."""

    @pytest.fixture
    def test_repo_with_filesystem_backend(self):
        """Create test repository with filesystem backend configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_path = Path(temp_dir) / "test_repo"
            repo_path.mkdir()

            # Create .code-indexer directory
            config_dir = repo_path / ".code-indexer"
            config_dir.mkdir()

            # Create config.json with filesystem backend
            config_file = config_dir / "config.json"
            import json

            config_data = {
                "embedding": {
                    "provider": "voyage",
                    "model": "voyage-3-large",
                    "dimensions": 1024,
                },
                "vector_store": {"provider": "filesystem"},
                "chunking": {
                    "chunk_size": 512,
                    "chunk_overlap": 128,
                    "tree_sitter_config": {"python": {"enabled": True}},
                },
            }
            config_file.write_text(json.dumps(config_data, indent=2))

            # Create index directory (required for FilesystemVectorStore)
            index_dir = config_dir / "index"
            index_dir.mkdir()

            yield str(repo_path)

    def test_filesystem_vector_store_search_receives_query_not_query_vector(
        self, test_repo_with_filesystem_backend
    ):
        """
        CRITICAL TEST: Verify FilesystemVectorStore.search() receives query string and embedding_provider.

        Bug: search_service.py was calling:
            vector_store_client.search(query_vector=query_embedding, ...)

        But FilesystemVectorStore.search() expects:
            vector_store_client.search(query=query_string, embedding_provider=provider, ...)

        This test MUST fail before fix, pass after fix.
        """
        repo_path = test_repo_with_filesystem_backend
        search_service = SemanticSearchService()

        # Mock embedding service (avoid external API calls)
        mock_embedding_service = MagicMock()
        mock_embedding_service.get_embedding.return_value = [0.1] * 1024

        # Track parameters passed to FilesystemVectorStore.search()
        search_call_params = {}

        def tracked_search(self, *args, **kwargs):
            """Capture parameters passed to search() for verification."""
            nonlocal search_call_params
            search_call_params = kwargs.copy()
            # Return empty results to avoid index loading issues
            return [], {}

        with patch.object(FilesystemVectorStore, "search", tracked_search):
            with patch(
                "src.code_indexer.server.services.search_service.EmbeddingProviderFactory.create",
                return_value=mock_embedding_service,
            ):
                search_request = SemanticSearchRequest(
                    query="authentication logic", limit=5, include_source=True
                )

                try:
                    search_service.search_repository_path(repo_path, search_request)
                except Exception:
                    # Some exceptions are expected (index may not exist, etc.)
                    # But we still capture the search() call parameters before the exception
                    pass

        # CRITICAL ASSERTIONS: After fix, parameters must be correct
        assert "query" in search_call_params, (
            "FilesystemVectorStore.search() MUST receive 'query' parameter (string). "
            f"Received parameters: {search_call_params.keys()}"
        )

        assert "embedding_provider" in search_call_params, (
            "FilesystemVectorStore.search() MUST receive 'embedding_provider' parameter. "
            f"Received parameters: {search_call_params.keys()}"
        )

        assert "query_vector" not in search_call_params, (
            "FilesystemVectorStore.search() MUST NOT receive 'query_vector' parameter. "
            "It expects 'query' (string) and 'embedding_provider' for parallel execution. "
            f"Received parameters: {search_call_params.keys()}"
        )

        # Verify correct values
        assert (
            search_call_params["query"] == "authentication logic"
        ), f"Expected query='authentication logic', got query='{search_call_params['query']}'"

        assert (
            search_call_params["embedding_provider"] is mock_embedding_service
        ), "Expected embedding_provider to be the EmbeddingProviderFactory instance"
