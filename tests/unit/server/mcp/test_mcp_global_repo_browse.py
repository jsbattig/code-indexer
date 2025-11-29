"""
Unit tests for MCP browse_directory handler with global repository support.

Tests that browse_directory handler supports global repositories with -global suffix,
using GlobalRegistry for path resolution.

CURRENT BUG: browse_directory has NO global repo support at all.
Error: "Repository 'cidx-meta-global' not found for user 'admin'"

EXPECTED: browse_directory should:
1. Detect -global suffix
2. Query GlobalRegistry for path
3. Use FileListingService with actual repo path
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
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


@pytest.fixture
def mock_golden_repos_dir(tmp_path):
    """Create realistic golden repos directory structure."""
    golden_dir = tmp_path / "golden-repos"
    golden_dir.mkdir(parents=True)

    # Meta-directory repo
    meta_dir = golden_dir / "cidx-meta"
    meta_index = meta_dir / ".code-indexer" / "index"
    meta_index.mkdir(parents=True)

    # Standard repos
    repos_dir = golden_dir / "repos"
    repos_dir.mkdir(parents=True)

    click_dir = repos_dir / "click"
    click_index = click_dir / ".code-indexer" / "index"
    click_index.mkdir(parents=True)

    return golden_dir


@pytest.fixture
def mock_global_registry_data(mock_golden_repos_dir):
    """Mock GlobalRegistry data with actual paths."""
    return [
        {
            "repo_name": "cidx-meta",
            "alias_name": "cidx-meta-global",
            "repo_url": None,
            "index_path": str(
                mock_golden_repos_dir / "cidx-meta" / ".code-indexer" / "index"
            ),
            "created_at": "2025-11-28T08:48:12.625104+00:00",
            "last_refresh": "2025-11-28T08:48:12.625104+00:00",
        },
        {
            "repo_name": "click",
            "alias_name": "click-global",
            "repo_url": "local:///path/to/repos/click",
            "index_path": str(
                mock_golden_repos_dir / "repos" / "click" / ".code-indexer" / "index"
            ),
            "created_at": "2025-11-28T21:01:20.090249+00:00",
            "last_refresh": "2025-11-28T21:01:20.090249+00:00",
        },
    ]


class TestBrowseDirectoryGlobalRepoSupport:
    """Test that browse_directory supports global repositories."""

    @pytest.mark.asyncio
    async def test_browse_directory_supports_global_repo_suffix(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that browse_directory detects -global suffix and uses GlobalRegistry.

        CURRENT: browse_directory fails with "Repository not found for user"
        EXPECTED: Should detect -global suffix and use GlobalRegistry lookup
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            # Mock app.state.golden_repos_dir to return the test directory
            mock_app.state.golden_repos_dir = str(mock_golden_repos_dir)

            # Mock GlobalRegistry
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            # Mock file_service for directory browsing
            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(
                files=[
                    Mock(
                        path="README.md",
                        size=1024,
                        modified_at="2025-11-28T10:00:00",
                        model_dump=lambda mode=None: {
                            "path": "README.md",
                            "size": 1024,
                            "modified_at": "2025-11-28T10:00:00",
                        },
                    )
                ]
            )
            mock_app.file_service = mock_file_service

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ) as mock_registry_class:

                params = {
                    "repository_alias": "cidx-meta-global",
                    "path": "",
                    "recursive": True,
                }

                result = await browse_directory(params, mock_user)

                # Verify: GlobalRegistry was instantiated
                mock_registry_class.assert_called_once_with(str(mock_golden_repos_dir))

                # Verify: list_global_repos was called to lookup path
                mock_registry.list_global_repos.assert_called_once()

                # Verify: Response is successful (not "repo not found")
                import json

                response_data = json.loads(result["content"][0]["text"])
                assert (
                    response_data["success"] is True
                ), "browse_directory should succeed for global repos"

    @pytest.mark.asyncio
    async def test_browse_directory_uses_registry_path_not_constructed_path(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that browse_directory uses GlobalRegistry path, not manual construction.

        Same bug as search_code: Must use registry's index_path, not golden_repos_dir / repo_name
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(files=[])
            mock_app.file_service = mock_file_service

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "repository_alias": "click-global",
                    "path": "src",
                    "recursive": False,
                }

                await browse_directory(params, mock_user)

                # Verify: file_service.list_files was called
                mock_file_service.list_files.assert_called_once()
                call_kwargs = mock_file_service.list_files.call_args.kwargs

                # Verify: repo_id passed to list_files is the ACTUAL path from registry
                # NOT the user-provided repository_alias
                repo_id = call_kwargs["repo_id"]

                # Expected: golden-repos/repos/click (from registry lookup)
                expected_repo_path = str(mock_golden_repos_dir / "repos" / "click")

                # The handler should pass the resolved path, not the alias
                assert repo_id == expected_repo_path or Path(repo_id) == Path(
                    expected_repo_path
                ), (
                    f"Handler should use registry-resolved path for file_service. "
                    f"Expected: {expected_repo_path}, Got: {repo_id}"
                )

    @pytest.mark.asyncio
    async def test_browse_directory_nonexistent_global_repo_returns_error(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that browsing non-existent global repo returns proper error."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_app.file_service = MagicMock()

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "repository_alias": "nonexistent-global",
                    "path": "",
                    "recursive": True,
                }

                result = await browse_directory(params, mock_user)

                # Verify: MCP error response
                import json

                response_data = json.loads(result["content"][0]["text"])

                assert response_data["success"] is False
                assert "not found" in response_data["error"].lower()
                assert "nonexistent-global" in response_data["error"]

    @pytest.mark.asyncio
    async def test_browse_directory_activated_repo_still_works(self, mock_user):
        """Test that non-global repos (activated) still use normal path resolution."""
        with patch("code_indexer.server.app") as mock_app:
            # Mock file_service for activated repos
            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(files=[])
            mock_app.file_service = mock_file_service

            params = {
                "repository_alias": "my-activated-repo",  # No -global suffix
                "path": "src",
                "recursive": True,
            }

            await browse_directory(params, mock_user)

            # Verify: file_service.list_files was called
            mock_file_service.list_files.assert_called_once()
            call_kwargs = mock_file_service.list_files.call_args.kwargs

            # Verify: repo_id is the original alias (activated repo path resolution)
            assert call_kwargs["repo_id"] == "my-activated-repo"

    @pytest.mark.asyncio
    async def test_browse_directory_passes_path_filter_correctly(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that browse_directory correctly builds path patterns for global repos."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(files=[])
            mock_app.file_service = mock_file_service

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "repository_alias": "click-global",
                    "path": "src/click",
                    "recursive": True,
                }

                await browse_directory(params, mock_user)

                # Verify: list_files was called with correct path pattern
                mock_file_service.list_files.assert_called_once()
                call_args = mock_file_service.list_files.call_args

                # Check query_params for path_pattern
                query_params = call_args.kwargs.get("query_params")
                assert query_params is not None, "query_params should be passed"

                # Path pattern should be "src/click/**/*" for recursive
                expected_pattern = "src/click/**/*"
                actual_pattern = query_params.path_pattern

                assert actual_pattern == expected_pattern, (
                    f"Path pattern should be built correctly. "
                    f"Expected: {expected_pattern}, Got: {actual_pattern}"
                )

    @pytest.mark.asyncio
    async def test_browse_directory_recursive_false_uses_single_level_pattern(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that recursive=False uses single-level glob pattern."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(files=[])
            mock_app.file_service = mock_file_service

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "repository_alias": "cidx-meta-global",
                    "path": "docs",
                    "recursive": False,
                }

                await browse_directory(params, mock_user)

                # Verify: Path pattern uses single-level glob
                call_args = mock_file_service.list_files.call_args
                query_params = call_args.kwargs.get("query_params")

                # Pattern should be "docs/*" (single level)
                expected_pattern = "docs/*"
                actual_pattern = query_params.path_pattern

                assert actual_pattern == expected_pattern, (
                    f"Non-recursive should use single-level pattern. "
                    f"Expected: {expected_pattern}, Got: {actual_pattern}"
                )

    @pytest.mark.asyncio
    async def test_browse_directory_empty_path_lists_root(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that empty path lists root directory of global repo."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_file_service = MagicMock()
            mock_file_service.list_files.return_value = Mock(files=[])
            mock_app.file_service = mock_file_service

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "repository_alias": "click-global",
                    "path": "",
                    "recursive": True,
                }

                result = await browse_directory(params, mock_user)

                # Verify: Response structure includes path="/"
                import json

                response_data = json.loads(result["content"][0]["text"])

                assert response_data["success"] is True
                structure = response_data["structure"]
                assert (
                    structure["path"] == "/" or structure["path"] == ""
                ), "Empty path should list root directory"
