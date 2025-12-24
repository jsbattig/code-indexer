"""
Unit tests for browse_directory handler filtering parameters.

Tests the new filtering parameters added to browse_directory:
- path_pattern: Glob pattern to filter files (e.g., '*.py', 'src/**/*.java')
- language: Programming language filter (e.g., 'python', 'java')
- limit: Maximum files to return (1-500, default 500)
- sort_by: Sort by 'path', 'size', or 'modified_at' (default 'path')
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from code_indexer.server.mcp.handlers import browse_directory
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    user = Mock(spec=User)
    user.username = "testuser"
    user.role = UserRole.NORMAL_USER
    user.has_permission = Mock(return_value=True)
    return user


def create_mock_file_service():
    """Create a mock file service with standard test data."""
    mock_service = MagicMock()
    mock_service.list_files.return_value = Mock(
        files=[
            Mock(
                path="src/main.py",
                size=1024,
                modified_at="2025-11-28T10:00:00",
                language="python",
                model_dump=lambda mode=None: {
                    "path": "src/main.py",
                    "size": 1024,
                    "modified_at": "2025-11-28T10:00:00",
                    "language": "python",
                },
            ),
            Mock(
                path="src/utils.py",
                size=512,
                modified_at="2025-11-29T10:00:00",
                language="python",
                model_dump=lambda mode=None: {
                    "path": "src/utils.py",
                    "size": 512,
                    "modified_at": "2025-11-29T10:00:00",
                    "language": "python",
                },
            ),
        ]
    )
    return mock_service


class TestBrowseDirectoryFilterParameters:
    """Tests for the new browse_directory filtering parameters."""

    @pytest.mark.asyncio
    async def test_path_pattern_filter_without_path(self, mock_user):
        """Test that path_pattern filter is passed correctly when no path specified."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path_pattern": "*.py",
            }

            await browse_directory(params, mock_user)

            mock_file_service.list_files.assert_called_once()
            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # path_pattern should be used directly when no path is specified
            assert query_params.path_pattern == "*.py"

    @pytest.mark.asyncio
    async def test_path_pattern_combined_with_path_recursive(self, mock_user):
        """Test path_pattern is combined with path correctly in recursive mode."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "path_pattern": "*.py",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Pattern should be "src/**/*.py" for recursive
            assert query_params.path_pattern == "src/**/*.py"

    @pytest.mark.asyncio
    async def test_path_pattern_combined_with_path_non_recursive(self, mock_user):
        """Test path_pattern is combined with path correctly in non-recursive mode."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "path_pattern": "*.java",
                "recursive": False,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Pattern should be "src/*.java" for non-recursive
            assert query_params.path_pattern == "src/*.java"

    @pytest.mark.asyncio
    async def test_language_filter_passed_correctly(self, mock_user):
        """Test that language filter is passed to FileListQueryParams."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "language": "python",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.language == "python"

    @pytest.mark.asyncio
    async def test_limit_parameter_passed_correctly(self, mock_user):
        """Test that limit parameter is passed to FileListQueryParams."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "limit": 50,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.limit == 50

    @pytest.mark.asyncio
    async def test_limit_default_is_500(self, mock_user):
        """Test that limit defaults to 500 when not specified."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.limit == 500

    @pytest.mark.asyncio
    async def test_limit_clamped_to_minimum(self, mock_user):
        """Test that limit below 1 is clamped to 1."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "limit": 0,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.limit == 1

    @pytest.mark.asyncio
    async def test_limit_clamped_to_maximum(self, mock_user):
        """Test that limit above 500 is clamped to 500."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "limit": 1000,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.limit == 500

    @pytest.mark.asyncio
    async def test_sort_by_parameter_passed_correctly(self, mock_user):
        """Test that sort_by parameter is passed to FileListQueryParams."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "sort_by": "modified_at",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.sort_by == "modified_at"

    @pytest.mark.asyncio
    async def test_sort_by_default_is_path(self, mock_user):
        """Test that sort_by defaults to 'path' when not specified."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.sort_by == "path"

    @pytest.mark.asyncio
    async def test_sort_by_invalid_value_defaults_to_path(self, mock_user):
        """Test that invalid sort_by value defaults to 'path'."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "sort_by": "invalid_sort",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.sort_by == "path"

    @pytest.mark.asyncio
    async def test_sort_by_size_accepted(self, mock_user):
        """Test that sort_by='size' is accepted."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "sort_by": "size",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.sort_by == "size"

    @pytest.mark.asyncio
    async def test_all_filter_parameters_combined(self, mock_user):
        """Test that all filter parameters work together."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "path_pattern": "*.py",
                "language": "python",
                "limit": 25,
                "sort_by": "modified_at",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.path_pattern == "src/**/*.py"
            assert query_params.language == "python"
            assert query_params.limit == 25
            assert query_params.sort_by == "modified_at"

    @pytest.mark.asyncio
    async def test_path_without_path_pattern_uses_base_pattern(self, mock_user):
        """Test that path without path_pattern uses the standard base pattern."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Without path_pattern, should use "src/**/*"
            assert query_params.path_pattern == "src/**/*"

    @pytest.mark.asyncio
    async def test_no_path_no_pattern_returns_all_files(self, mock_user):
        """Test that omitting both path and path_pattern returns all files."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # No path and no pattern should result in None (all files)
            assert query_params.path_pattern is None

    @pytest.mark.asyncio
    async def test_complex_path_pattern_supported(self, mock_user):
        """Test that complex glob patterns are supported."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path_pattern": "**/*.{py,java,ts}",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.path_pattern == "**/*.{py,java,ts}"

    @pytest.mark.asyncio
    async def test_negative_limit_clamped_to_minimum(self, mock_user):
        """Test that negative limit values are clamped to 1."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "limit": -5,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            assert query_params.limit == 1

    @pytest.mark.asyncio
    async def test_path_with_trailing_slash_normalized(self, mock_user):
        """Test that path with trailing slash is normalized correctly."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src/",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Trailing slash should be removed, resulting in "src/**/*"
            assert query_params.path_pattern == "src/**/*"

    @pytest.mark.asyncio
    async def test_empty_string_path_pattern_behaves_like_none(self, mock_user):
        """Test that empty string path_pattern behaves like None."""
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path_pattern": "",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Empty string should behave like None (all files)
            assert query_params.path_pattern is None


class TestBrowseDirectoryFilterParametersResponseFormat:
    """Tests verifying the response format includes filter results correctly."""

    @pytest.mark.asyncio
    async def test_response_includes_total_count(self, mock_user):
        """Test that response includes total count of files."""
        import json

        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "language": "python",
            }

            result = await browse_directory(params, mock_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert "structure" in response_data
            assert "total" in response_data["structure"]
            assert response_data["structure"]["total"] == 2  # Two mock files

    @pytest.mark.asyncio
    async def test_response_success_with_filters(self, mock_user):
        """Test that response is successful when using filters."""
        import json

        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path_pattern": "*.py",
                "language": "python",
                "limit": 10,
                "sort_by": "size",
            }

            result = await browse_directory(params, mock_user)

            response_data = json.loads(result["content"][0]["text"])
            assert response_data["success"] is True
            assert "files" in response_data["structure"]
