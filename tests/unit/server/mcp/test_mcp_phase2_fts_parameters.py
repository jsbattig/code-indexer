"""
Unit tests for Phase 2 MCP FTS parameters (Story #503).

Tests for:
- case_sensitive parameter validation
- fuzzy parameter validation
- edit_distance parameter validation and range constraints
- snippet_lines parameter validation and range constraints
- regex parameter validation and compatibility rules
"""

import pytest
from unittest.mock import Mock, patch
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


class TestCaseSensitiveParameter:
    """Test case_sensitive parameter."""

    @pytest.mark.asyncio
    async def test_case_sensitive_accepts_true(self, mock_user):
        """Test case_sensitive accepts True value."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "Authentication",
                "search_mode": "fts",
                "case_sensitive": True,
            }

            result = await search_code(params, mock_user)

            # Verify case_sensitive parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["case_sensitive"] is True

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_case_sensitive_defaults_to_false(self, mock_user):
        """Test case_sensitive defaults to False when not provided."""
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
                "search_mode": "fts",
            }

            await search_code(params, mock_user)

            # Verify case_sensitive defaults to False
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["case_sensitive"] is False


class TestFuzzyParameter:
    """Test fuzzy parameter."""

    @pytest.mark.asyncio
    async def test_fuzzy_accepts_true(self, mock_user):
        """Test fuzzy accepts True value."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "authentication",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "authenticat",  # Typo
                "search_mode": "fts",
                "fuzzy": True,
            }

            await search_code(params, mock_user)

            # Verify fuzzy parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["fuzzy"] is True

    @pytest.mark.asyncio
    async def test_fuzzy_defaults_to_false(self, mock_user):
        """Test fuzzy defaults to False when not provided."""
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
                "search_mode": "fts",
            }

            await search_code(params, mock_user)

            # Verify fuzzy defaults to False
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["fuzzy"] is False


class TestEditDistanceParameter:
    """Test edit_distance parameter."""

    @pytest.mark.asyncio
    async def test_edit_distance_accepts_valid_range(self, mock_user):
        """Test edit_distance accepts values 0-3."""
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

            # Test each valid value
            for distance in [0, 1, 2, 3]:
                params = {
                    "query_text": "test",
                    "search_mode": "fts",
                    "edit_distance": distance,
                }

                await search_code(params, mock_user)

                # Verify edit_distance parameter was passed
                call_kwargs = (
                    mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
                )
                assert call_kwargs["edit_distance"] == distance

    @pytest.mark.asyncio
    async def test_edit_distance_defaults_to_zero(self, mock_user):
        """Test edit_distance defaults to 0 when not provided."""
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
                "search_mode": "fts",
            }

            await search_code(params, mock_user)

            # Verify edit_distance defaults to 0
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["edit_distance"] == 0


class TestSnippetLinesParameter:
    """Test snippet_lines parameter."""

    @pytest.mark.asyncio
    async def test_snippet_lines_accepts_valid_range(self, mock_user):
        """Test snippet_lines accepts values 0-50."""
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

            # Test boundary values
            for lines in [0, 5, 25, 50]:
                params = {
                    "query_text": "test",
                    "search_mode": "fts",
                    "snippet_lines": lines,
                }

                await search_code(params, mock_user)

                # Verify snippet_lines parameter was passed
                call_kwargs = (
                    mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
                )
                assert call_kwargs["snippet_lines"] == lines

    @pytest.mark.asyncio
    async def test_snippet_lines_defaults_to_five(self, mock_user):
        """Test snippet_lines defaults to 5 when not provided."""
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
                "search_mode": "fts",
            }

            await search_code(params, mock_user)

            # Verify snippet_lines defaults to 5
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["snippet_lines"] == 5


class TestRegexParameter:
    """Test regex parameter."""

    @pytest.mark.asyncio
    async def test_regex_accepts_true_with_fts_mode(self, mock_user):
        """Test regex accepts True with search_mode='fts'."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "def.*auth",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "def.*auth",
                "search_mode": "fts",
                "regex": True,
            }

            await search_code(params, mock_user)

            # Verify regex parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["regex"] is True

    @pytest.mark.asyncio
    async def test_regex_accepts_true_with_hybrid_mode(self, mock_user):
        """Test regex accepts True with search_mode='hybrid'."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "def.*auth",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "def.*auth",
                "search_mode": "hybrid",
                "regex": True,
            }

            await search_code(params, mock_user)

            # Verify regex parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["regex"] is True

    @pytest.mark.asyncio
    async def test_regex_defaults_to_false(self, mock_user):
        """Test regex defaults to False when not provided."""
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
                "search_mode": "fts",
            }

            await search_code(params, mock_user)

            # Verify regex defaults to False
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["regex"] is False


class TestParameterCombinations:
    """Test combinations and validation rules for Phase 2 parameters."""

    @pytest.mark.asyncio
    async def test_all_phase2_parameters_together(self, mock_user):
        """Test all Phase 2 parameters can be used together (except incompatible ones)."""
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

            # Test case_sensitive + fuzzy + edit_distance + snippet_lines (no regex)
            params = {
                "query_text": "test",
                "search_mode": "fts",
                "case_sensitive": True,
                "fuzzy": True,
                "edit_distance": 2,
                "snippet_lines": 10,
                # regex=False (default, compatible with fuzzy)
            }

            await search_code(params, mock_user)

            # Verify all parameters were passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["case_sensitive"] is True
            assert call_kwargs["fuzzy"] is True
            assert call_kwargs["edit_distance"] == 2
            assert call_kwargs["snippet_lines"] == 10
            assert call_kwargs["regex"] is False

    @pytest.mark.asyncio
    async def test_regex_with_case_sensitive_and_snippet_lines(self, mock_user):
        """Test regex can be combined with case_sensitive and snippet_lines (not fuzzy/edit_distance)."""
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "def.*",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "def.*",
                "search_mode": "fts",
                "regex": True,
                "case_sensitive": True,
                "snippet_lines": 15,
                # fuzzy=False, edit_distance=0 (defaults, compatible with regex)
            }

            await search_code(params, mock_user)

            # Verify parameters were passed correctly
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["regex"] is True
            assert call_kwargs["case_sensitive"] is True
            assert call_kwargs["snippet_lines"] == 15
            assert call_kwargs["fuzzy"] is False
            assert call_kwargs["edit_distance"] == 0
