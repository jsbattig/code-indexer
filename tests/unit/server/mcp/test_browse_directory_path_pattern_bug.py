"""
Unit tests for browse_directory path + path_pattern combination bug.

Bug: When both path and path_pattern are provided, the code incorrectly combines
them when path_pattern is absolute (contains '/' or starts with repo base path).

Example failure:
- Input: path="code/src/dms/.../access", path_pattern="code/src/**/*.java"
- Current: "code/src/dms/.../access/**/code/src/**/*.java" (WRONG)
- Expected: "code/src/**/*.java" (use absolute pattern directly)
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
                path="code/src/Main.java",
                size=1024,
                modified_at="2025-11-28T10:00:00",
                language="java",
                model_dump=lambda mode=None: {
                    "path": "code/src/Main.java",
                    "size": 1024,
                    "modified_at": "2025-11-28T10:00:00",
                    "language": "java",
                },
            ),
        ]
    )
    return mock_service


class TestBrowseDirectoryPathPatternCombination:
    """Tests for absolute vs relative path_pattern handling."""

    @pytest.mark.asyncio
    async def test_absolute_path_pattern_not_combined_with_path(self, mock_user):
        """
        Test that absolute path_pattern is NOT combined with path parameter.

        When path_pattern contains '/' (indicating it's an absolute pattern),
        it should be used directly, ignoring the path parameter.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "code/src/dms/core/access",  # This should be IGNORED
                "path_pattern": "code/src/**/*.java",  # Absolute pattern
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should use absolute pattern directly, NOT combine with path
            assert query_params.path_pattern == "code/src/**/*.java"

    @pytest.mark.asyncio
    async def test_relative_path_pattern_combined_with_path(self, mock_user):
        """
        Test that relative path_pattern IS combined with path parameter.

        When path_pattern is simple (like '*.py'), it should be combined
        with the path parameter.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "path_pattern": "*.py",  # Relative pattern
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should combine path + pattern
            assert query_params.path_pattern == "src/**/*.py"

    @pytest.mark.asyncio
    async def test_path_pattern_with_glob_stars_is_absolute(self, mock_user):
        """
        Test that path_pattern containing '**/' is treated as absolute.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "ignore/this/path",  # Should be ignored
                "path_pattern": "**/*.java",  # Absolute pattern (glob from root)
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should use pattern directly
            assert query_params.path_pattern == "**/*.java"

    @pytest.mark.asyncio
    async def test_original_failing_case(self, mock_user):
        """
        Test the exact failing case from the bug report.

        Input: path="code/src/dms/.../access", path_pattern="code/src/**/*.java"
        Expected: "code/src/**/*.java" (NOT "code/src/dms/.../access/**/code/src/**/*.java")
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "code/src/dms/core/access",
                "path_pattern": "code/src/**/*.java",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should NOT duplicate the base path
            assert query_params.path_pattern == "code/src/**/*.java"
            assert (
                "code/src/dms/core/access/**/code/src" not in query_params.path_pattern
            )

    @pytest.mark.asyncio
    async def test_path_pattern_without_path_unchanged(self, mock_user):
        """
        Test that path_pattern without path parameter is used directly.

        This is the existing behavior that should continue working.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path_pattern": "code/src/**/*.java",
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should use pattern exactly as provided
            assert query_params.path_pattern == "code/src/**/*.java"

    @pytest.mark.asyncio
    async def test_simple_filename_pattern_is_relative(self, mock_user):
        """
        Test that simple filename patterns (no slashes) are treated as relative.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src/utils",
                "path_pattern": "*.py",  # Simple pattern, no slashes
                "recursive": False,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should combine with path
            assert query_params.path_pattern == "src/utils/*.py"

    @pytest.mark.asyncio
    async def test_pattern_with_subdirectory_is_absolute(self, mock_user):
        """
        Test that patterns with subdirectories (containing '/') are absolute.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "ignore/me",
                "path_pattern": "src/main/*.py",  # Contains '/', so absolute
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should use pattern directly, ignore path
            assert query_params.path_pattern == "src/main/*.py"

    @pytest.mark.asyncio
    async def test_non_recursive_with_absolute_pattern(self, mock_user):
        """
        Test non-recursive mode with absolute pattern (should still use pattern directly).
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "wrong/path",
                "path_pattern": "code/src/*.java",  # Absolute, non-recursive
                "recursive": False,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should use pattern directly
            assert query_params.path_pattern == "code/src/*.java"

    @pytest.mark.asyncio
    async def test_brace_expansion_pattern_is_relative(self, mock_user):
        """
        Test that brace expansion patterns without '/' are treated as relative.
        """
        mock_file_service = create_mock_file_service()
        with patch("code_indexer.server.mcp.handlers.app_module") as mock_app_module:
            mock_app_module.file_service = mock_file_service

            params = {
                "repository_alias": "test-repo",
                "path": "src",
                "path_pattern": "*.{py,java}",  # No '/', so relative
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            call_kwargs = mock_file_service.list_files.call_args.kwargs
            query_params = call_kwargs["query_params"]

            # Should combine with path
            assert query_params.path_pattern == "src/**/*.{py,java}"
