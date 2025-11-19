"""
Unit tests for Phase 3 MCP temporal filtering parameters (Story #503).

Tests for:
- diff_type parameter validation (single and comma-separated values)
- author parameter validation
- chunk_type parameter validation (commit_message/commit_diff)
- Parameter combinations
- Parameter defaults
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


class TestDiffTypeParameter:
    """Test diff_type parameter."""

    @pytest.mark.asyncio
    async def test_diff_type_accepts_single_value(self, mock_user):
        """Test diff_type accepts single value."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "diff_type": "added",
            }

            result = await search_code(params, mock_user)

            # Verify diff_type parameter was passed
            mock_app.semantic_query_manager.query_user_repositories.assert_called_once()
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["diff_type"] == "added"

            # Verify MCP response format
            assert "content" in result
            assert len(result["content"]) == 1
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_diff_type_accepts_comma_separated_values(self, mock_user):
        """Test diff_type accepts comma-separated multiple values."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "diff_type": "added,modified",
            }

            result = await search_code(params, mock_user)

            # Verify diff_type parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["diff_type"] == "added,modified"

    @pytest.mark.asyncio
    async def test_diff_type_accepts_all_valid_values(self, mock_user):
        """Test diff_type accepts all valid values (added/modified/deleted/renamed/binary)."""
        with patch("code_indexer.server.app") as mock_app:
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

            valid_values = ["added", "modified", "deleted", "renamed", "binary"]
            for value in valid_values:
                params = {
                    "query_text": "test",
                    "time_range": "2024-01-01..2024-12-31",
                    "diff_type": value,
                }

                result = await search_code(params, mock_user)

                # Verify diff_type parameter was passed
                call_kwargs = mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
                assert call_kwargs["diff_type"] == value

    @pytest.mark.asyncio
    async def test_diff_type_defaults_to_none(self, mock_user):
        """Test diff_type defaults to None when not provided."""
        with patch("code_indexer.server.app") as mock_app:
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
                "time_range": "2024-01-01..2024-12-31",
            }

            result = await search_code(params, mock_user)

            # Verify diff_type defaults to None
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["diff_type"] is None


class TestAuthorParameter:
    """Test author parameter."""

    @pytest.mark.asyncio
    async def test_author_accepts_email(self, mock_user):
        """Test author accepts email address."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "author": "dev@example.com",
            }

            result = await search_code(params, mock_user)

            # Verify author parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["author"] == "dev@example.com"

    @pytest.mark.asyncio
    async def test_author_accepts_name(self, mock_user):
        """Test author accepts developer name."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "author": "John Doe",
            }

            result = await search_code(params, mock_user)

            # Verify author parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["author"] == "John Doe"

    @pytest.mark.asyncio
    async def test_author_defaults_to_none(self, mock_user):
        """Test author defaults to None when not provided."""
        with patch("code_indexer.server.app") as mock_app:
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
                "time_range": "2024-01-01..2024-12-31",
            }

            result = await search_code(params, mock_user)

            # Verify author defaults to None
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["author"] is None


class TestChunkTypeParameter:
    """Test chunk_type parameter."""

    @pytest.mark.asyncio
    async def test_chunk_type_accepts_commit_message(self, mock_user):
        """Test chunk_type accepts 'commit_message' value."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "fix bug",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "fix bug",
                "time_range": "2024-01-01..2024-12-31",
                "chunk_type": "commit_message",
            }

            result = await search_code(params, mock_user)

            # Verify chunk_type parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["chunk_type"] == "commit_message"

    @pytest.mark.asyncio
    async def test_chunk_type_accepts_commit_diff(self, mock_user):
        """Test chunk_type accepts 'commit_diff' value."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "chunk_type": "commit_diff",
            }

            result = await search_code(params, mock_user)

            # Verify chunk_type parameter was passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["chunk_type"] == "commit_diff"

    @pytest.mark.asyncio
    async def test_chunk_type_defaults_to_none(self, mock_user):
        """Test chunk_type defaults to None when not provided."""
        with patch("code_indexer.server.app") as mock_app:
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
                "time_range": "2024-01-01..2024-12-31",
            }

            result = await search_code(params, mock_user)

            # Verify chunk_type defaults to None
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["chunk_type"] is None


class TestParameterCombinations:
    """Test combinations of Phase 3 temporal parameters."""

    @pytest.mark.asyncio
    async def test_all_phase3_parameters_together(self, mock_user):
        """Test all Phase 3 temporal parameters can be used together."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                "time_range": "2024-01-01..2024-12-31",
                "diff_type": "added,modified",
                "author": "dev@example.com",
                "chunk_type": "commit_diff",
            }

            result = await search_code(params, mock_user)

            # Verify all Phase 3 parameters were passed
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["diff_type"] == "added,modified"
            assert call_kwargs["author"] == "dev@example.com"
            assert call_kwargs["chunk_type"] == "commit_diff"

    @pytest.mark.asyncio
    async def test_phase3_with_phase1_and_phase2_parameters(self, mock_user):
        """Test Phase 3 parameters work alongside Phase 1 and Phase 2 parameters."""
        with patch("code_indexer.server.app") as mock_app:
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
                "query_text": "authentication",
                # Phase 1 parameters
                "language": "python",
                "exclude_path": "*/tests/*",
                "accuracy": "high",
                # Temporal parameters (Story #446)
                "time_range": "2024-01-01..2024-12-31",
                # Phase 2 FTS parameters
                "search_mode": "fts",
                "case_sensitive": True,
                "snippet_lines": 10,
                # Phase 3 temporal filtering parameters
                "diff_type": "modified",
                "author": "dev@example.com",
                "chunk_type": "commit_diff",
            }

            result = await search_code(params, mock_user)

            # Verify all parameters were passed correctly
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            # Phase 1
            assert call_kwargs["language"] == "python"
            assert call_kwargs["exclude_path"] == "*/tests/*"
            assert call_kwargs["accuracy"] == "high"
            # Temporal base
            assert call_kwargs["time_range"] == "2024-01-01..2024-12-31"
            # Phase 2
            assert call_kwargs["case_sensitive"] is True
            assert call_kwargs["snippet_lines"] == 10
            # Phase 3
            assert call_kwargs["diff_type"] == "modified"
            assert call_kwargs["author"] == "dev@example.com"
            assert call_kwargs["chunk_type"] == "commit_diff"

    @pytest.mark.asyncio
    async def test_diff_type_with_chunk_type_commit_message(self, mock_user):
        """Test diff_type can be combined with chunk_type='commit_message'."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.semantic_query_manager.query_user_repositories.return_value = {
                "results": [],
                "total_results": 0,
                "query_metadata": {
                    "query_text": "fix bug",
                    "execution_time_ms": 10,
                    "repositories_searched": 1,
                    "timeout_occurred": False,
                },
            }

            params = {
                "query_text": "fix bug",
                "time_range": "2024-01-01..2024-12-31",
                "diff_type": "added",
                "chunk_type": "commit_message",
            }

            result = await search_code(params, mock_user)

            # Verify parameters were passed correctly
            call_kwargs = (
                mock_app.semantic_query_manager.query_user_repositories.call_args.kwargs
            )
            assert call_kwargs["diff_type"] == "added"
            assert call_kwargs["chunk_type"] == "commit_message"
