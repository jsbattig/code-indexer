"""
Unit tests for query routing in SemanticQueryManager.

Tests the detection of composite repositories and routing to appropriate
search handlers (single vs composite).
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    QueryResult,
)


class TestCompositeRepositoryDetection:
    """Test _is_composite_repository() detection method."""

    def test_detects_composite_repository_with_proxy_mode_true(self, tmp_path):
        """Test detection of composite repository with proxy_mode=true."""
        # Arrange: Create repo with proxy_mode config
        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"proxy_mode": True, "embedding_provider": "voyage-ai"}
        config_file.write_text(json.dumps(config_data))

        manager = SemanticQueryManager()

        # Act: Check if composite
        result = manager._is_composite_repository(repo_path)

        # Assert: Should detect as composite
        assert result is True

    def test_detects_single_repository_with_proxy_mode_false(self, tmp_path):
        """Test detection of single repository with proxy_mode=false."""
        # Arrange: Create repo with proxy_mode=false
        repo_path = tmp_path / "single-repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"proxy_mode": False, "embedding_provider": "voyage"}
        config_file.write_text(json.dumps(config_data))

        manager = SemanticQueryManager()

        # Act: Check if composite
        result = manager._is_composite_repository(repo_path)

        # Assert: Should detect as single repo
        assert result is False

    def test_detects_single_repository_with_missing_proxy_mode(self, tmp_path):
        """Test detection defaults to single repo when proxy_mode missing."""
        # Arrange: Create repo without proxy_mode in config
        repo_path = tmp_path / "single-repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        config_data = {"embedding_provider": "voyage"}
        config_file.write_text(json.dumps(config_data))

        manager = SemanticQueryManager()

        # Act: Check if composite
        result = manager._is_composite_repository(repo_path)

        # Assert: Should default to single repo
        assert result is False

    def test_handles_missing_config_file_gracefully(self, tmp_path):
        """Test graceful handling when config file doesn't exist."""
        # Arrange: Create repo without config file
        repo_path = tmp_path / "no-config-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Check if composite
        result = manager._is_composite_repository(repo_path)

        # Assert: Should default to single repo (False)
        assert result is False

    def test_handles_missing_code_indexer_directory(self, tmp_path):
        """Test graceful handling when .code-indexer directory doesn't exist."""
        # Arrange: Create repo without .code-indexer directory
        repo_path = tmp_path / "no-indexer-dir"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Check if composite
        result = manager._is_composite_repository(repo_path)

        # Assert: Should default to single repo (False)
        assert result is False

    def test_handles_invalid_json_in_config_file(self, tmp_path):
        """Test graceful handling of malformed JSON in config file."""
        # Arrange: Create repo with invalid JSON
        repo_path = tmp_path / "invalid-json-repo"
        repo_path.mkdir()
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"

        # Write invalid JSON
        config_file.write_text("{ invalid json }")

        manager = SemanticQueryManager()

        # Act & Assert: Should handle gracefully (either raise or return False)
        # For now, we expect it to raise - implementation will decide
        with pytest.raises((json.JSONDecodeError, Exception)):
            manager._is_composite_repository(repo_path)


class TestSearchRouting:
    """Test search() method routing logic."""

    @patch.object(SemanticQueryManager, "_is_composite_repository")
    @patch.object(SemanticQueryManager, "search_composite")
    async def test_routes_to_composite_handler_when_composite_repo(
        self, mock_search_composite, mock_is_composite, tmp_path
    ):
        """Test routing to search_composite() for composite repositories."""
        # Arrange: Setup mocks
        mock_is_composite.return_value = True
        mock_search_composite.return_value = []

        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Call search
        await manager.search(repo_path=repo_path, query="test query", limit=10)

        # Assert: Should route to search_composite
        mock_is_composite.assert_called_once_with(repo_path)
        mock_search_composite.assert_called_once_with(
            repo_path, "test query", limit=10, min_score=None, file_extensions=None
        )

    @patch.object(SemanticQueryManager, "_is_composite_repository")
    @patch.object(SemanticQueryManager, "search_single")
    async def test_routes_to_single_handler_when_single_repo(
        self, mock_search_single, mock_is_composite, tmp_path
    ):
        """Test routing to search_single() for single repositories."""
        # Arrange: Setup mocks
        mock_is_composite.return_value = False
        mock_search_single.return_value = []

        repo_path = tmp_path / "single-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Call search
        await manager.search(repo_path=repo_path, query="test query", limit=10)

        # Assert: Should route to search_single
        mock_is_composite.assert_called_once_with(repo_path)
        mock_search_single.assert_called_once_with(
            repo_path, "test query", limit=10, min_score=None, file_extensions=None
        )

    @patch.object(SemanticQueryManager, "_is_composite_repository")
    @patch.object(SemanticQueryManager, "search_single")
    async def test_passes_all_kwargs_to_single_handler(
        self, mock_search_single, mock_is_composite, tmp_path
    ):
        """Test that all keyword arguments are passed to search_single()."""
        # Arrange: Setup mocks
        mock_is_composite.return_value = False
        mock_search_single.return_value = []

        repo_path = tmp_path / "single-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Call search with multiple kwargs
        await manager.search(
            repo_path=repo_path,
            query="test query",
            limit=20,
            min_score=0.8,
            file_extensions=[".py", ".js"],
        )

        # Assert: All kwargs should be passed
        mock_search_single.assert_called_once_with(
            repo_path,
            "test query",
            limit=20,
            min_score=0.8,
            file_extensions=[".py", ".js"],
        )

    @patch.object(SemanticQueryManager, "_is_composite_repository")
    @patch.object(SemanticQueryManager, "search_composite")
    async def test_passes_all_kwargs_to_composite_handler(
        self, mock_search_composite, mock_is_composite, tmp_path
    ):
        """Test that all keyword arguments are passed to search_composite()."""
        # Arrange: Setup mocks
        mock_is_composite.return_value = True
        mock_search_composite.return_value = []

        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Call search with multiple kwargs
        await manager.search(
            repo_path=repo_path,
            query="test query",
            limit=20,
            min_score=0.8,
            file_extensions=[".py", ".js"],
        )

        # Assert: All kwargs should be passed
        mock_search_composite.assert_called_once_with(
            repo_path,
            "test query",
            limit=20,
            min_score=0.8,
            file_extensions=[".py", ".js"],
        )


class TestSearchSingleBackwardCompatibility:
    """Test search_single() maintains existing behavior."""

    @patch("code_indexer.server.services.search_service.SemanticSearchService")
    async def test_search_single_maintains_existing_behavior(
        self, mock_search_service_class, tmp_path
    ):
        """Test that search_single() maintains existing search behavior."""
        # Arrange: Setup mock search service
        mock_search_service = MagicMock()
        mock_search_service_class.return_value = mock_search_service

        # Mock search response
        mock_result = MagicMock()
        mock_result.file_path = "test.py"
        mock_result.line_start = 10
        mock_result.content = "def test(): pass"
        mock_result.score = 0.95

        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_search_service.search_repository_path.return_value = mock_response

        repo_path = tmp_path / "test-repo"
        repo_path.mkdir()

        manager = SemanticQueryManager()

        # Act: Call search_single (will be implemented)
        results = await manager.search_single(
            repo_path=repo_path,
            repository_alias="test-alias",
            query="test query",
            limit=10,
            min_score=None,
            file_extensions=None,
        )

        # Assert: Should return QueryResult objects
        assert len(results) == 1
        assert isinstance(results[0], QueryResult)
        assert results[0].file_path == "test.py"
        assert results[0].similarity_score == 0.95


class TestSearchCompositeStub:
    """Test search_composite() basic functionality."""

    async def test_search_composite_with_valid_config(self, tmp_path):
        """Test that search_composite() works with valid proxy config."""
        # Arrange: Create composite repo with proper config
        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()

        # Create .code-indexer directory with proxy config
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()

        # Create proxy config file
        proxy_config_file = config_dir / "proxy-config.json"
        proxy_config_file.write_text(
            json.dumps({"discovered_repos": []})  # Empty list - no repos to search
        )

        # Create main config
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"proxy_mode": True}))

        manager = SemanticQueryManager()

        # Act: Call search_composite with empty repos
        results = await manager.search_composite(
            repo_path=repo_path, query="test query", limit=10
        )

        # Assert: Should return empty list (no repos to search)
        assert results == []
        assert isinstance(results, list)

    async def test_search_composite_accepts_all_parameters(self, tmp_path):
        """Test that search_composite() accepts all expected parameters."""
        # Arrange: Create composite repo with proper config
        repo_path = tmp_path / "composite-repo"
        repo_path.mkdir()

        # Create .code-indexer directory with proxy config
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir()

        # Create proxy config file
        proxy_config_file = config_dir / "proxy-config.json"
        proxy_config_file.write_text(json.dumps({"discovered_repos": []}))  # Empty list

        # Create main config
        config_file = config_dir / "config.json"
        config_file.write_text(json.dumps({"proxy_mode": True}))

        manager = SemanticQueryManager()

        # Act: Call with all parameters (should not raise)
        results = await manager.search_composite(
            repo_path=repo_path,
            query="test query",
            limit=20,
            min_score=0.8,
            file_extensions=[".py"],
        )

        # Assert: Should accept parameters and return empty list
        assert results == []
