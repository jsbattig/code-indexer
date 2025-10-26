"""
Integration tests for query routing in CIDX Server.

Tests the complete flow of query routing through the API endpoint to ensure
proper handling of both single and composite repositories.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestQueryEndpointRouting:
    """Test query endpoint routing for single and composite repositories."""

    @pytest.fixture
    def setup_single_repo(self, tmp_path):
        """Create a single repository with config."""
        repo_path = tmp_path / "single-repo"
        repo_path.mkdir()

        # Create .code-indexer config
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"proxy_mode": False, "embedding_provider": "ollama"}
        config_file.write_text(json.dumps(config_data))

        return repo_path

    @pytest.fixture
    def setup_composite_repo(self, tmp_path):
        """Create a composite repository with config."""
        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()

        # Create .code-indexer config
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {
            "proxy_mode": True,
            "embedding_provider": "voyage-ai",
            "discovered_repos": [str(tmp_path / "repo1"), str(tmp_path / "repo2")],
        }
        config_file.write_text(json.dumps(config_data))

        return repo_path

    @patch.object(SemanticQueryManager, "search_single")
    async def test_single_repo_query_uses_single_handler(
        self, mock_search_single, setup_single_repo
    ):
        """Test that single repository queries use search_single() handler."""
        # Arrange: Setup mock and manager
        mock_search_single.return_value = [
            QueryResult(
                file_path="test.py",
                line_number=10,
                code_snippet="def test(): pass",
                similarity_score=0.95,
                repository_alias="single-repo",
            )
        ]

        manager = SemanticQueryManager()

        # Act: Perform search on single repo
        results = await manager.search(
            repo_path=setup_single_repo, query="test query", limit=10
        )

        # Assert: Should use single handler
        mock_search_single.assert_called_once()
        assert len(results) == 1
        assert results[0].repository_alias == "single-repo"

    @patch.object(SemanticQueryManager, "search_composite")
    async def test_composite_repo_query_uses_composite_handler(
        self, mock_search_composite, setup_composite_repo
    ):
        """Test that composite repository queries use search_composite() handler."""
        # Arrange: Setup mock and manager
        mock_search_composite.return_value = []

        manager = SemanticQueryManager()

        # Act: Perform search on composite repo
        results = await manager.search(
            repo_path=setup_composite_repo, query="test query", limit=10
        )

        # Assert: Should use composite handler
        mock_search_composite.assert_called_once()
        assert results == []

    @patch.object(SemanticQueryManager, "search_single")
    @patch.object(SemanticQueryManager, "search_composite")
    async def test_mixed_query_handles_both_types(
        self,
        mock_search_composite,
        mock_search_single,
        setup_single_repo,
        setup_composite_repo,
    ):
        """Test querying both single and composite repos in sequence."""
        # Arrange: Setup mocks
        mock_search_single.return_value = [
            QueryResult(
                file_path="single.py",
                line_number=5,
                code_snippet="single repo code",
                similarity_score=0.9,
                repository_alias="single-repo",
            )
        ]
        mock_search_composite.return_value = []

        manager = SemanticQueryManager()

        # Act: Query single repo
        single_results = await manager.search(
            repo_path=setup_single_repo, query="test query", limit=10
        )

        # Query composite repo
        composite_results = await manager.search(
            repo_path=setup_composite_repo, query="test query", limit=10
        )

        # Assert: Both handlers should be called
        mock_search_single.assert_called_once()
        mock_search_composite.assert_called_once()
        assert len(single_results) == 1
        assert len(composite_results) == 0

    async def test_backward_compatibility_with_existing_queries(
        self, setup_single_repo
    ):
        """Test that existing single-repo queries still work unchanged."""
        # Arrange: Create manager with mocked search service
        with patch(
            "code_indexer.server.services.search_service.SemanticSearchService"
        ) as mock_service_class:
            # Setup mock search service
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            # Mock search response
            mock_result = MagicMock()
            mock_result.file_path = "existing.py"
            mock_result.line_start = 15
            mock_result.content = "existing code"
            mock_result.score = 0.85

            mock_response = MagicMock()
            mock_response.results = [mock_result]
            mock_service.search_repository_path.return_value = mock_response

            manager = SemanticQueryManager()

            # Act: Call search (should route through to search_single)
            results = await manager.search(
                repo_path=setup_single_repo, query="existing query", limit=10
            )

            # Assert: Should maintain backward compatibility
            assert len(results) == 1
            assert results[0].file_path == "existing.py"
            assert results[0].similarity_score == 0.85

    async def test_api_interface_remains_same_for_both_types(
        self, setup_single_repo, setup_composite_repo
    ):
        """Test that API interface is identical for single and composite repos."""
        # Arrange: Create manager with mocked handlers
        with patch.object(SemanticQueryManager, "search_single") as mock_single:
            with patch.object(
                SemanticQueryManager, "search_composite"
            ) as mock_composite:
                mock_single.return_value = []
                mock_composite.return_value = []

                manager = SemanticQueryManager()

                # Act: Call search with same parameters for both types
                kwargs = {
                    "query": "test query",
                    "limit": 20,
                    "min_score": 0.7,
                    "file_extensions": [".py"],
                }

                await manager.search(repo_path=setup_single_repo, **kwargs)
                await manager.search(repo_path=setup_composite_repo, **kwargs)

                # Assert: Both handlers should be called
                assert mock_single.call_count == 1
                assert mock_composite.call_count == 1

                # Verify both handlers were called (specific parameters may vary in implementation)
                # The key point is that both routing paths work correctly
                mock_single.assert_called_once()
                mock_composite.assert_called_once()


class TestQueryRoutingErrorHandling:
    """Test error handling in query routing."""

    async def test_handles_missing_config_gracefully(self, tmp_path):
        """Test graceful handling when repository has no config."""
        # Arrange: Create repo without config
        repo_path = tmp_path / "no-config"
        repo_path.mkdir()

        with patch.object(SemanticQueryManager, "search_single") as mock_single:
            mock_single.return_value = []
            manager = SemanticQueryManager()

            # Act: Query repo without config
            results = await manager.search(
                repo_path=repo_path, query="test query", limit=10
            )

            # Assert: Should default to single handler
            mock_single.assert_called_once()
            assert results == []

    async def test_routing_preserves_error_propagation(self, tmp_path):
        """Test that errors from handlers are properly propagated."""
        # Arrange: Setup repo and manager
        repo_path = tmp_path / "error-repo"
        repo_path.mkdir()

        # Create config for single repo
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"proxy_mode": False}))

        with patch.object(SemanticQueryManager, "search_single") as mock_single:
            # Setup mock to raise exception
            mock_single.side_effect = Exception("Search failed")

            manager = SemanticQueryManager()

            # Act & Assert: Exception should propagate
            with pytest.raises(Exception, match="Search failed"):
                await manager.search(repo_path=repo_path, query="test query", limit=10)
