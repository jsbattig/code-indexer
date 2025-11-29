"""
Unit tests for MCP list_repositories handler with global repo support.

Tests that list_repositories returns both activated repos AND global repos
from the golden-repos directory, with global repos properly marked.

Per Epic #520 requirement: Global repos should be visible without activation.
"""

import pytest
import os
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from code_indexer.server.mcp.handlers import list_repositories
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
def mock_global_registry_data():
    """Mock global registry data structure."""
    return {
        "cidx-meta-global": {
            "repo_name": "cidx-meta",
            "alias_name": "cidx-meta-global",
            "repo_url": None,
            "index_path": "/home/testuser/.code-indexer/golden-repos/cidx-meta",
            "created_at": "2025-11-28T08:48:12.625104+00:00",
            "last_refresh": "2025-11-28T08:48:12.625104+00:00",
        },
        "click-global": {
            "repo_name": "click",
            "alias_name": "click-global",
            "repo_url": "local:///home/testuser/.code-indexer/golden-repos/repos/click",
            "index_path": "/home/testuser/.code-indexer/golden-repos/repos/click/.code-indexer/index",
            "created_at": "2025-11-28T21:01:20.090249+00:00",
            "last_refresh": "2025-11-28T21:01:20.090249+00:00",
        },
        "pytest-global": {
            "repo_name": "pytest",
            "alias_name": "pytest-global",
            "repo_url": "local:///home/testuser/.code-indexer/golden-repos/repos/pytest",
            "index_path": "/home/testuser/.code-indexer/golden-repos/repos/pytest/.code-indexer/index",
            "created_at": "2025-11-28T21:01:27.116257+00:00",
            "last_refresh": "2025-11-28T21:01:27.116257+00:00",
        },
    }


@pytest.fixture
def mock_activated_repos():
    """Mock activated repository data."""
    return [
        {
            "user_alias": "my-project",
            "golden_repo_alias": "code-indexer",
            "branch_name": "main",
            "activated_at": "2025-11-28T10:00:00+00:00",
        },
        {
            "user_alias": "auth-lib",
            "golden_repo_alias": "test-auth-lib",
            "branch_name": "develop",
            "activated_at": "2025-11-28T11:00:00+00:00",
        },
    ]


class TestListRepositoriesWithGlobalRepos:
    """Test MCP list_repositories handler includes global repos."""

    @pytest.mark.asyncio
    async def test_global_repos_appear_in_list(
        self, mock_user, mock_global_registry_data, mock_activated_repos
    ):
        """Test that global repos from registry appear in list_repositories response."""
        with patch("code_indexer.server.app") as mock_app:
            # Mock activated repo manager
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                mock_activated_repos
            )

            # Mock GlobalRegistry to return global repos
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = list(
                mock_global_registry_data.values()
            )

            # Patch GlobalRegistry instantiation
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                # Execute
                result = await list_repositories({}, mock_user)

                # Verify: Response contains content
                assert "content" in result
                assert len(result["content"]) == 1
                assert result["content"][0]["type"] == "text"

                # Parse the JSON response
                import json

                response_data = json.loads(result["content"][0]["text"])

                # Verify: Response is successful
                assert response_data["success"] is True
                assert "repositories" in response_data

                repos = response_data["repositories"]

                # Verify: Total count includes activated + global repos
                # 2 activated + 3 global = 5 total
                assert len(repos) == 5

                # Verify: Global repos are present with -global suffix
                global_repo_aliases = [
                    repo["alias_name"]
                    for repo in repos
                    if repo.get("is_global") is True
                ]
                assert "cidx-meta-global" in global_repo_aliases
                assert "click-global" in global_repo_aliases
                assert "pytest-global" in global_repo_aliases

                # Verify: Activated repos are present
                activated_aliases = [
                    repo["user_alias"]
                    for repo in repos
                    if repo.get("is_global") is not True
                ]
                assert "my-project" in activated_aliases
                assert "auth-lib" in activated_aliases

    @pytest.mark.asyncio
    async def test_global_repos_marked_with_is_global_true(
        self, mock_user, mock_global_registry_data, mock_activated_repos
    ):
        """Test that global repos have is_global: true field."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                mock_activated_repos
            )

            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = list(
                mock_global_registry_data.values()
            )

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])
                repos = response_data["repositories"]

                # Verify: All global repos have is_global: true
                for repo in repos:
                    if repo.get("alias_name", "").endswith("-global"):
                        assert repo["is_global"] is True, (
                            f"Global repo {repo['alias_name']} missing is_global=True"
                        )

                # Verify: Activated repos do NOT have is_global: true
                for repo in repos:
                    if not repo.get("alias_name", "").endswith("-global"):
                        assert repo.get("is_global") is not True, (
                            f"Activated repo should not have is_global=True"
                        )

    @pytest.mark.asyncio
    async def test_global_repos_include_metadata(
        self, mock_user, mock_global_registry_data
    ):
        """Test that global repos include repo name, last update time, and index path."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                []
            )

            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = list(
                mock_global_registry_data.values()
            )

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])
                repos = response_data["repositories"]

                # Verify: Each global repo has required metadata
                for repo in repos:
                    if repo.get("is_global") is True:
                        assert "repo_name" in repo, "Global repo missing repo_name"
                        assert "alias_name" in repo, "Global repo missing alias_name"
                        assert "last_refresh" in repo, (
                            "Global repo missing last_refresh"
                        )
                        assert "index_path" in repo, "Global repo missing index_path"

                        # Verify alias_name has -global suffix
                        assert repo["alias_name"].endswith("-global")

    @pytest.mark.asyncio
    async def test_empty_global_registry_handled_gracefully(
        self, mock_user, mock_activated_repos
    ):
        """Test that empty golden-repos directory is handled without errors."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                mock_activated_repos
            )

            # Mock empty global registry
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = []

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])

                # Verify: Response is successful
                assert response_data["success"] is True

                # Verify: Only activated repos are returned
                repos = response_data["repositories"]
                assert len(repos) == 2  # Only the 2 activated repos
                assert all(
                    repo.get("is_global") is not True for repo in repos
                ), "Should not have any global repos"

    @pytest.mark.asyncio
    async def test_only_global_repos_no_activated_repos(
        self, mock_user, mock_global_registry_data
    ):
        """Test list_repositories when user has no activated repos but global repos exist."""
        with patch("code_indexer.server.app") as mock_app:
            # No activated repos
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                []
            )

            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = list(
                mock_global_registry_data.values()
            )

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])
                repos = response_data["repositories"]

                # Verify: Only global repos returned
                assert len(repos) == 3
                assert all(
                    repo["is_global"] is True for repo in repos
                ), "All repos should be global"

    @pytest.mark.asyncio
    async def test_global_registry_error_does_not_break_activated_list(self, mock_user):
        """Test that global registry errors don't prevent listing activated repos."""
        with patch("code_indexer.server.app") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = [
                {
                    "user_alias": "my-project",
                    "golden_repo_alias": "code-indexer",
                    "branch_name": "main",
                }
            ]

            # Mock GlobalRegistry to raise exception
            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                side_effect=Exception("Registry load failed"),
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])

                # Verify: Response is successful (activated repos still listed)
                assert response_data["success"] is True
                repos = response_data["repositories"]

                # Verify: Activated repo is still returned
                assert len(repos) >= 1
                assert any(
                    repo.get("user_alias") == "my-project" for repo in repos
                ), "Activated repo should still be listed despite global registry error"

    @pytest.mark.asyncio
    async def test_golden_repos_dir_from_environment(self, mock_user, tmp_path):
        """Test that golden_repos_dir is loaded from environment variable."""
        # Create temporary golden repos directory
        temp_golden_dir = tmp_path / "test-golden-repos"
        temp_golden_dir.mkdir(parents=True)

        with (
            patch("code_indexer.server.app") as mock_app,
            patch.dict(os.environ, {"GOLDEN_REPOS_DIR": str(temp_golden_dir)}),
        ):
            # Mock app.state.golden_repos_dir to return the test directory
            mock_app.state.golden_repos_dir = str(temp_golden_dir)

            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                []
            )

            # Mock GlobalRegistry
            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = []

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ) as mock_registry_class:
                await list_repositories({}, mock_user)

                # Verify: GlobalRegistry was instantiated with app.state.golden_repos_dir
                mock_registry_class.assert_called_once_with(str(temp_golden_dir))

    @pytest.mark.asyncio
    async def test_duplicate_alias_names_handled(
        self, mock_user, mock_global_registry_data
    ):
        """Test that duplicate alias names between activated and global repos are handled."""
        # Create activated repo with same name as global repo
        duplicate_activated = [
            {
                "user_alias": "click-global",  # Same as global repo alias
                "golden_repo_alias": "click",
                "branch_name": "main",
            }
        ]

        with patch("code_indexer.server.app") as mock_app:
            mock_app.activated_repo_manager.list_activated_repositories.return_value = (
                duplicate_activated
            )

            mock_registry = MagicMock()
            mock_registry.list_global_repos.return_value = [
                mock_global_registry_data["click-global"]
            ]

            with patch(
                "code_indexer.server.mcp.handlers.GlobalRegistry",
                return_value=mock_registry,
            ):
                result = await list_repositories({}, mock_user)

                import json

                response_data = json.loads(result["content"][0]["text"])
                repos = response_data["repositories"]

                # Verify: Both entries exist (activated and global)
                # This tests that we don't accidentally deduplicate
                assert len(repos) == 2

                # Verify: One is marked as global, one is not
                global_count = sum(1 for repo in repos if repo.get("is_global") is True)
                activated_count = sum(
                    1 for repo in repos if repo.get("is_global") is not True
                )

                assert global_count == 1, "Should have 1 global repo"
                assert activated_count == 1, "Should have 1 activated repo"
