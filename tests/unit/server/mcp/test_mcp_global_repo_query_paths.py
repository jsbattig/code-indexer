"""
Unit tests for MCP global repository query path resolution.

Tests that search_code handler correctly resolves global repo paths using
GlobalRegistry instead of manual path construction.

ROOT CAUSE: Handler manually constructs path as golden_repos_dir / repo_name
instead of looking up actual path from GlobalRegistry.index_path field.

EXPECTED: Handler should query GlobalRegistry and use index_path to get actual
repo location (e.g., /path/to/golden-repos/repos/click/.code-indexer/index).
"""

import pytest
import os
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


@pytest.fixture
def mock_golden_repos_dir(tmp_path):
    """
    Create realistic golden repos directory structure.

    Structure:
        golden-repos/
            cidx-meta/              # Meta-directory repo (no repos/ prefix)
            repos/                  # Standard repos subdirectory
                click/              # Actual click repo location
                    .code-indexer/
                        index/
                pytest/             # Actual pytest repo location
                    .code-indexer/
                        index/
    """
    golden_dir = tmp_path / "golden-repos"
    golden_dir.mkdir(parents=True)

    # Create meta-directory repo (special case, no repos/ prefix)
    meta_dir = golden_dir / "cidx-meta"
    meta_index = meta_dir / ".code-indexer" / "index"
    meta_index.mkdir(parents=True)

    # Create repos subdirectory for standard repos
    repos_dir = golden_dir / "repos"
    repos_dir.mkdir(parents=True)

    # Create click repo
    click_dir = repos_dir / "click"
    click_index = click_dir / ".code-indexer" / "index"
    click_index.mkdir(parents=True)

    # Create pytest repo
    pytest_dir = repos_dir / "pytest"
    pytest_index = pytest_dir / ".code-indexer" / "index"
    pytest_index.mkdir(parents=True)

    return golden_dir


@pytest.fixture
def mock_global_registry_data(mock_golden_repos_dir):
    """
    Mock GlobalRegistry data with ACTUAL paths from registry.

    Key insight: index_path points to .code-indexer/index directory,
    so repo path is index_path.parent.parent
    """
    return [
        {
            "repo_name": "cidx-meta",
            "alias_name": "cidx-meta-global",
            "repo_url": None,
            "index_path": str(mock_golden_repos_dir / "cidx-meta" / ".code-indexer" / "index"),
            "created_at": "2025-11-28T08:48:12.625104+00:00",
            "last_refresh": "2025-11-28T08:48:12.625104+00:00",
        },
        {
            "repo_name": "click",
            "alias_name": "click-global",
            "repo_url": "local:///path/to/repos/click",
            "index_path": str(mock_golden_repos_dir / "repos" / "click" / ".code-indexer" / "index"),
            "created_at": "2025-11-28T21:01:20.090249+00:00",
            "last_refresh": "2025-11-28T21:01:20.090249+00:00",
        },
        {
            "repo_name": "pytest",
            "alias_name": "pytest-global",
            "repo_url": "local:///path/to/repos/pytest",
            "index_path": str(mock_golden_repos_dir / "repos" / "pytest" / ".code-indexer" / "index"),
            "created_at": "2025-11-28T21:01:27.116257+00:00",
            "last_refresh": "2025-11-28T21:01:27.116257+00:00",
        },
    ]


class TestGlobalRepoPathResolution:
    """Test that search_code uses GlobalRegistry for path lookup."""

    @pytest.mark.asyncio
    async def test_search_code_uses_registry_for_path_lookup(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that search_code queries GlobalRegistry for path instead of constructing it.

        CURRENT BUG: Handler does Path(golden_repos_dir) / repo_name
        EXPECTED: Handler queries GlobalRegistry.list_global_repos() and uses index_path
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            # Mock GlobalRegistry
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            # Mock semantic_query_manager
            mock_query_manager = MagicMock()
            mock_result = Mock()
            mock_result.to_dict.return_value = {
                "file_path": "test.py",
                "chunk_text": "test content",
                "score": 0.95,
            }
            mock_query_manager._perform_search.return_value = [mock_result]
            mock_app.semantic_query_manager = mock_query_manager

            # Patch GlobalRegistry instantiation
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ) as mock_registry_class:

                # Execute query for click-global
                params = {
                    "query_text": "authentication",
                    "repository_alias": "click-global",
                    "limit": 10,
                }

                result = await search_code(params, mock_user)

                # Verify: GlobalRegistry was instantiated
                mock_registry_class.assert_called_once_with(str(mock_golden_repos_dir))

                # Verify: list_global_repos was called to lookup path
                mock_registry.list_global_repos.assert_called_once()

                # Verify: _perform_search was called with CORRECT path from registry
                mock_query_manager._perform_search.assert_called_once()
                call_kwargs = mock_query_manager._perform_search.call_args.kwargs

                # Extract actual repo_path passed to _perform_search
                user_repos = call_kwargs["user_repos"]
                assert len(user_repos) == 1
                actual_repo_path = Path(user_repos[0]["repo_path"])

                # Expected path: golden-repos/repos/click (from index_path.parent.parent)
                expected_repo_path = mock_golden_repos_dir / "repos" / "click"

                assert actual_repo_path == expected_repo_path, (
                    f"Handler should use registry's index_path to derive repo path. "
                    f"Expected: {expected_repo_path}, Got: {actual_repo_path}"
                )

    @pytest.mark.asyncio
    async def test_click_global_resolves_to_repos_subdirectory(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that click-global resolves to golden-repos/repos/click, not golden-repos/click.

        This is the ACTUAL bug: Handler constructs golden-repos/click instead of
        looking up golden-repos/repos/click from GlobalRegistry.
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            # Mock GlobalRegistry with real registry data
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            # Mock semantic_query_manager
            mock_query_manager = MagicMock()
            mock_query_manager._perform_search.return_value = []
            mock_app.semantic_query_manager = mock_query_manager

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "query_text": "test",
                    "repository_alias": "click-global",
                    "limit": 10,
                }

                result = await search_code(params, mock_user)

                # Verify: _perform_search was called
                mock_query_manager._perform_search.assert_called_once()
                call_kwargs = mock_query_manager._perform_search.call_args.kwargs

                # Extract repo_path
                user_repos = call_kwargs["user_repos"]
                repo_path = Path(user_repos[0]["repo_path"])

                # CRITICAL: Path should be golden-repos/repos/click (from registry)
                # NOT golden-repos/click (from manual construction)
                assert "repos" in repo_path.parts, (
                    f"Path should include 'repos' subdirectory. Got: {repo_path}"
                )
                assert repo_path.name == "click", f"Path should end with 'click'. Got: {repo_path}"

                # Explicit check: Should NOT be golden-repos/click
                wrong_path = mock_golden_repos_dir / "click"
                assert repo_path != wrong_path, (
                    f"Handler is constructing wrong path! "
                    f"Should use registry lookup, not golden_repos_dir / repo_name"
                )

    @pytest.mark.asyncio
    async def test_nonexistent_global_repo_returns_error(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that querying non-existent global repo returns proper error."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            # Mock GlobalRegistry with known repos
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_app.semantic_query_manager = MagicMock()

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "query_text": "test",
                    "repository_alias": "nonexistent-global",
                    "limit": 10,
                }

                result = await search_code(params, mock_user)

                # Verify: MCP error response
                assert "content" in result
                import json
                response_data = json.loads(result["content"][0]["text"])

                assert response_data["success"] is False
                assert "not found" in response_data["error"].lower()
                assert "nonexistent-global" in response_data["error"]

    @pytest.mark.asyncio
    async def test_pytest_global_resolves_correctly(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """Test that pytest-global also resolves to correct repos/ subdirectory."""
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_query_manager = MagicMock()
            mock_query_manager._perform_search.return_value = []
            mock_app.semantic_query_manager = mock_query_manager

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "query_text": "fixture",
                    "repository_alias": "pytest-global",
                    "limit": 10,
                }

                result = await search_code(params, mock_user)

                # Verify: Correct path resolution
                call_kwargs = mock_query_manager._perform_search.call_args.kwargs
                user_repos = call_kwargs["user_repos"]
                repo_path = Path(user_repos[0]["repo_path"])

                expected_path = mock_golden_repos_dir / "repos" / "pytest"
                assert repo_path == expected_path, (
                    f"pytest-global should resolve to repos/pytest. "
                    f"Expected: {expected_path}, Got: {repo_path}"
                )

    @pytest.mark.asyncio
    async def test_meta_directory_global_resolves_without_repos_prefix(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that cidx-meta-global resolves correctly (special case: no repos/ prefix).

        Meta-directory is stored at golden-repos/cidx-meta, not golden-repos/repos/cidx-meta.
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_query_manager = MagicMock()
            mock_query_manager._perform_search.return_value = []
            mock_app.semantic_query_manager = mock_query_manager

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                params = {
                    "query_text": "repository discovery",
                    "repository_alias": "cidx-meta-global",
                    "limit": 10,
                }

                result = await search_code(params, mock_user)

                # Verify: Correct path resolution for meta-directory
                call_kwargs = mock_query_manager._perform_search.call_args.kwargs
                user_repos = call_kwargs["user_repos"]
                repo_path = Path(user_repos[0]["repo_path"])

                # Meta-directory is at golden-repos/cidx-meta (no repos/ subdirectory)
                expected_path = mock_golden_repos_dir / "cidx-meta"
                assert repo_path == expected_path, (
                    f"cidx-meta-global should resolve to cidx-meta (no repos/ prefix). "
                    f"Expected: {expected_path}, Got: {repo_path}"
                )

                # Explicit check: Should NOT include 'repos' in path
                assert "repos" not in repo_path.parts, (
                    "Meta-directory should NOT be under repos/ subdirectory"
                )

    @pytest.mark.asyncio
    async def test_registry_lookup_happens_before_path_construction(
        self, mock_user, mock_golden_repos_dir, mock_global_registry_data
    ):
        """
        Test that handler ALWAYS queries GlobalRegistry, never constructs paths manually.

        This test verifies the PROCESS, not just the outcome.
        """
        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(mock_golden_repos_dir)}),
        ):
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = mock_global_registry_data

            mock_query_manager = MagicMock()
            mock_query_manager._perform_search.return_value = []
            mock_app.semantic_query_manager = mock_query_manager

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ) as mock_registry_class:

                params = {
                    "query_text": "test",
                    "repository_alias": "click-global",
                    "limit": 10,
                }

                await search_code(params, mock_user)

                # Verify: GlobalRegistry was instantiated (lookup step)
                assert mock_registry_class.called, "Handler must instantiate GlobalRegistry"

                # Verify: list_global_repos was called (lookup step)
                assert mock_registry.list_global_repos.called, (
                    "Handler must call list_global_repos() to lookup repo"
                )

                # Verify: Both calls happened BEFORE _perform_search
                call_order = [
                    call[0] for call in [
                        ("registry_init", mock_registry_class.call_count > 0),
                        ("list_repos", mock_registry.list_global_repos.call_count > 0),
                        ("perform_search", mock_query_manager._perform_search.call_count > 0),
                    ] if call[1]
                ]

                assert call_order == ["registry_init", "list_repos", "perform_search"], (
                    "Handler must: 1) Init registry, 2) List repos, 3) Perform search"
                )
