"""
Unit tests for MCP FTS search_mode bug fix.

This test file validates that the search_mode parameter is properly passed
through the MCP handler chain and correctly triggers FTS search instead of
semantic search.

Bug Description:
- MCP `search_code` tool accepts `search_mode: "fts"` parameter but ignores it
- Always runs semantic search regardless of search_mode value
- FTS only works in REST API endpoint, not in MCP

Root Cause:
- `semantic_query_manager._perform_search()` had NO `search_mode` parameter
- MCP handler called `_perform_search` without passing `search_mode`
- FTS parameters (case_sensitive, fuzzy, regex) were passed but never used
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
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


class TestMCPFTSSearchModeBugFix:
    """Test that search_mode parameter is properly handled in MCP."""

    @pytest.mark.asyncio
    async def test_search_mode_fts_passed_to_query_user_repositories(self, mock_user):
        """Test that search_mode='fts' is passed to query_user_repositories."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "class",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "class",
                "search_mode": "fts",
                "limit": 3,
            }

            result = await search_code(params, mock_user)

            # Verify query_user_repositories was called with search_mode parameter
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )

            # After fix, search_mode is passed
            assert (
                "search_mode" in call_kwargs
            ), "search_mode parameter must be passed to query_user_repositories"
            assert (
                call_kwargs["search_mode"] == "fts"
            ), f"Expected search_mode='fts', got search_mode='{call_kwargs.get('search_mode')}'"

    @pytest.mark.asyncio
    async def test_search_mode_semantic_is_default(self, mock_user):
        """Test that search_mode defaults to 'semantic' when not specified."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "test",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "test",
                # No search_mode specified
            }

            result = await search_code(params, mock_user)

            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )

            # Default should be semantic
            assert call_kwargs.get("search_mode") == "semantic"

    @pytest.mark.asyncio
    async def test_search_mode_hybrid_passed_correctly(self, mock_user):
        """Test that search_mode='hybrid' is passed correctly."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 15,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "authentication",
                "search_mode": "hybrid",
            }

            result = await search_code(params, mock_user)

            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )

            assert "search_mode" in call_kwargs
            assert call_kwargs["search_mode"] == "hybrid"

    def test_global_repo_path_has_search_mode_in_handler_code(self):
        """Test that handlers.py code passes search_mode in global repo path.

        This test inspects the actual code rather than mocking since the
        global repo path has complex mocking requirements. The important
        behavior is verified by reading the source code.
        """
        import inspect
        from code_indexer.server.mcp import handlers

        # Get the source code of search_code function
        source = inspect.getsource(handlers.search_code)

        # Verify that search_mode is passed to _perform_search in the global repo code path
        # The code should have: search_mode=params.get("search_mode", "semantic")
        assert (
            "search_mode=params.get" in source
        ), "search_code handler must pass search_mode parameter to _perform_search"
        assert (
            'search_mode=params.get("search_mode"' in source
        ), "search_mode must be extracted from params in the global repo path"


class TestSemanticQueryManagerSearchMode:
    """Test search_mode handling in SemanticQueryManager."""

    def test_query_user_repositories_accepts_search_mode_parameter(self):
        """Test that query_user_repositories signature includes search_mode."""
        from code_indexer.server.query.semantic_query_manager import (
            SemanticQueryManager,
        )
        import inspect

        sig = inspect.signature(SemanticQueryManager.query_user_repositories)
        params = list(sig.parameters.keys())

        # After fix, search_mode should be in the parameter list
        assert (
            "search_mode" in params
        ), "query_user_repositories must accept search_mode parameter"

    def test_perform_search_accepts_search_mode_parameter(self):
        """Test that _perform_search signature includes search_mode."""
        from code_indexer.server.query.semantic_query_manager import (
            SemanticQueryManager,
        )
        import inspect

        sig = inspect.signature(SemanticQueryManager._perform_search)
        params = list(sig.parameters.keys())

        # After fix, search_mode should be in the parameter list
        assert (
            "search_mode" in params
        ), "_perform_search must accept search_mode parameter"
