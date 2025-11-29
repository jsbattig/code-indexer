"""
Unit tests for MCP global repository query support.

Tests that global repositories (ending with -global suffix) can be queried
directly via MCP search_code handler without requiring activation.

Global repos live in ~/.code-indexer/golden-repos/ and should be accessible
to all users without per-user activation.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from code_indexer.server.mcp.handlers import search_code
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


@pytest.fixture
def mock_global_repo_path(tmp_path):
    """Create a mock global repository directory structure."""
    # Create global repos directory
    golden_repos_dir = tmp_path / "golden-repos"
    golden_repos_dir.mkdir(parents=True)

    # Create cidx-meta global repo directory
    cidx_meta_dir = golden_repos_dir / "cidx-meta"
    cidx_meta_dir.mkdir(parents=True)

    # Create index directory to make it look like a real indexed repo
    index_dir = cidx_meta_dir / ".code-indexer" / "index"
    index_dir.mkdir(parents=True)

    return golden_repos_dir


class TestGlobalRepoQuery:
    """Test MCP search_code handler with global repository queries."""

    @pytest.mark.asyncio
    async def test_global_repo_query_success(self, mock_user, mock_global_repo_path):
        """Test successful query of global repository ending with -global suffix."""
        # Setup: Mock semantic_query_manager with _perform_search
        with (
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_global_repo_path)}),
            patch("code_indexer.server.mcp.handlers.semantic_query_manager") as mock_query_manager,
        ):

            # Create mock QueryResult objects
            mock_result = Mock()
            mock_result.to_dict.return_value = {
                "file_path": "test-file.md",
                "chunk_text": "Test content about authentication",
                "score": 0.95,
                "language": "markdown",
            }

            # Mock _perform_search to return QueryResult list
            mock_query_manager._perform_search.return_value = [mock_result]

            # Mock GlobalRegistry for path lookup
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = [
                {
                    "repo_name": "cidx-meta",
                    "alias_name": "cidx-meta-global",
                    "repo_url": None,
                    "index_path": str(mock_global_repo_path / "cidx-meta" / ".code-indexer" / "index"),
                    "created_at": "2025-11-28T08:48:12.625104+00:00",
                    "last_refresh": "2025-11-28T08:48:12.625104+00:00",
                }
            ]

            # Test parameters with global repo alias
            params = {
                "query_text": "authentication",
                "repository_alias": "cidx-meta-global",
                "limit": 10,
            }

            # Execute with GlobalRegistry mock
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await search_code(params, mock_user)

            # Verify: _perform_search was called for global repo
            mock_query_manager._perform_search.assert_called_once()
            call_kwargs = mock_query_manager._perform_search.call_args.kwargs

            # Verify correct parameters were passed
            assert call_kwargs["query_text"] == "authentication"
            assert call_kwargs["limit"] == 10
            assert len(call_kwargs["user_repos"]) == 1
            assert "cidx-meta" in call_kwargs["user_repos"][0]["repo_path"]

            # Verify query_user_repositories was NOT called (global repos bypass activation)
            mock_query_manager.query_user_repositories.assert_not_called()

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_activated_repo_query_still_works(self, mock_user):
        """Test that activated repositories (non-global) still use query_user_repositories."""
        with patch("code_indexer.server.mcp.handlers.semantic_query_manager") as mock_query_manager:
            # Mock semantic_query_manager for activated repos
            mock_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            # Test parameters with non-global repo alias
            params = {
                "query_text": "test",
                "repository_alias": "my-activated-repo",  # No -global suffix
                "limit": 10,
            }

            # Execute
            await search_code(params, mock_user)

            # Verify: query_user_repositories was called for activated repo
            mock_query_manager.query_user_repositories.assert_called_once()

    @pytest.mark.asyncio
    async def test_global_repo_not_found_error(self, mock_user, tmp_path):
        """Test error handling when global repository doesn't exist."""
        # Setup: Empty golden repos directory
        empty_golden_dir = tmp_path / "empty-golden-repos"
        empty_golden_dir.mkdir(parents=True)

        with patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(empty_golden_dir)}):

            # Test parameters with non-existent global repo
            params = {
                "query_text": "test",
                "repository_alias": "nonexistent-global",
                "limit": 10,
            }

            # Execute
            result = await search_code(params, mock_user)

            # Verify: MCP error response format
            assert "content" in result
            assert len(result["content"]) == 1
            content_text = result["content"][0]["text"]
            assert "success" in content_text.lower()
            assert "false" in content_text.lower()

    @pytest.mark.asyncio
    async def test_global_repo_with_all_query_parameters(
        self, mock_user, mock_global_repo_path
    ):
        """Test that global repo queries support all search parameters."""
        with (
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_global_repo_path)}),
            patch("code_indexer.server.mcp.handlers.semantic_query_manager") as mock_query_manager,
        ):

            # Mock _perform_search
            mock_query_manager._perform_search.return_value = []

            # Mock GlobalRegistry for path lookup
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = [
                {
                    "repo_name": "cidx-meta",
                    "alias_name": "cidx-meta-global",
                    "repo_url": None,
                    "index_path": str(mock_global_repo_path / "cidx-meta" / ".code-indexer" / "index"),
                    "created_at": "2025-11-28T08:48:12.625104+00:00",
                    "last_refresh": "2025-11-28T08:48:12.625104+00:00",
                }
            ]

            # Test parameters with all filter options
            params = {
                "query_text": "auth",
                "repository_alias": "cidx-meta-global",
                "limit": 20,
                "min_score": 0.8,
                "language": "python",
                "exclude_language": "javascript",
                "path_filter": "*/src/*",
                "exclude_path": "*/tests/*",
                "accuracy": "high",
                "file_extensions": [".py", ".md"],
            }

            # Execute with GlobalRegistry mock
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                await search_code(params, mock_user)

            # Verify: _perform_search was called
            mock_query_manager._perform_search.assert_called_once()

            # Verify: All parameters were passed through
            call_kwargs = mock_query_manager._perform_search.call_args.kwargs
            assert call_kwargs["query_text"] == "auth"
            assert call_kwargs["limit"] == 20
            assert call_kwargs["min_score"] == 0.8
            assert call_kwargs["language"] == "python"
            assert call_kwargs["exclude_language"] == "javascript"
            assert call_kwargs["path_filter"] == "*/src/*"
            assert call_kwargs["exclude_path"] == "*/tests/*"
            assert call_kwargs["accuracy"] == "high"
            assert call_kwargs["file_extensions"] == [".py", ".md"]

    @pytest.mark.asyncio
    async def test_query_without_repository_alias_uses_activated_repos(self, mock_user):
        """Test that queries without repository_alias still use activated repos."""
        with patch("code_indexer.server.mcp.handlers.semantic_query_manager") as mock_query_manager:
            # Mock semantic_query_manager
            mock_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 0,
                    "timeout_occurred": False,
                },
            }

            # Test parameters WITHOUT repository_alias
            params = {
                "query_text": "test",
                "limit": 10,
            }

            # Execute
            await search_code(params, mock_user)

            # Verify: query_user_repositories was called
            mock_query_manager.query_user_repositories.assert_called_once()
