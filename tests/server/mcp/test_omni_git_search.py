"""Tests for omni-git-search polymorphic repo_identifier in git tools.

Story #570: Omni-Git-Search for Commits and History

Tests that git_search_commits and git_log correctly route to single-repo
or omni-search based on repo_identifier type (string vs array).
"""

import pytest
from unittest.mock import MagicMock, patch
from code_indexer.server.mcp.handlers import handle_git_search_commits
from code_indexer.server.auth.user_manager import User, UserRole
from datetime import datetime


@pytest.fixture
def test_user():
    """Create a test user for handler testing."""
    return User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(),
    )


class TestGitSearchCommitsPolymorphic:
    """Test git_search_commits polymorphic repo_identifier routing."""

    @pytest.mark.asyncio
    async def test_string_repo_identifier_routes_to_single_repo(
        self, test_user, tmp_path
    ):
        """String repo_identifier routes to single-repo git_search_commits."""
        # Setup: Create mock git operations service
        with patch(
            "code_indexer.server.mcp.handlers._resolve_repo_path"
        ) as mock_resolve, patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_dir, patch(
            "code_indexer.global_repos.git_operations.GitOperationsService"
        ) as mock_service_class:

            mock_get_dir.return_value = str(tmp_path)
            mock_resolve.return_value = str(tmp_path / "repo1")

            # Mock service result
            mock_result = MagicMock()
            mock_result.query = "fix bug"
            mock_result.is_regex = False
            mock_result.matches = []
            mock_result.total_matches = 0
            mock_result.truncated = False
            mock_result.search_time_ms = 123

            mock_service = MagicMock()
            mock_service.search_commits.return_value = mock_result
            mock_service_class.return_value = mock_service

            # Execute: Call with string repo_identifier
            result = await handle_git_search_commits(
                {"repo_identifier": "repo1-global", "query": "fix bug"}, test_user
            )

            # Assert: Should call GitOperationsService.search_commits (not omni-search)
            assert mock_service.search_commits.called
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_array_repo_identifier_routes_to_omni_search(self, test_user):
        """Array repo_identifier routes to omni-git-search."""
        # Execute: Call with array repo_identifier
        result = await handle_git_search_commits(
            {"repo_identifier": ["repo1-global", "repo2-global"], "query": "fix bug"},
            test_user,
        )

        # Assert: Should return omni-search stub response
        import json

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert "repos_searched" in response_data
        assert "errors" in response_data
        assert isinstance(response_data["matches"], list)


class TestGitLogPolymorphic:
    """Test git_log polymorphic repo_identifier routing."""

    @pytest.mark.asyncio
    async def test_string_repo_identifier_routes_to_single_repo(
        self, test_user, tmp_path
    ):
        """String repo_identifier routes to single-repo git_log."""
        # Setup: Create mock git operations service
        with patch(
            "code_indexer.server.mcp.handlers._resolve_repo_path"
        ) as mock_resolve, patch(
            "code_indexer.server.mcp.handlers._get_golden_repos_dir"
        ) as mock_get_dir, patch(
            "code_indexer.global_repos.git_operations.GitOperationsService"
        ) as mock_service_class:

            mock_get_dir.return_value = str(tmp_path)
            mock_resolve.return_value = str(tmp_path / "repo1")

            # Mock service result
            mock_result = MagicMock()
            mock_result.commits = []
            mock_result.total_count = 0
            mock_result.truncated = False

            mock_service = MagicMock()
            mock_service.get_log.return_value = mock_result
            mock_service_class.return_value = mock_service

            # Execute: Call with string repo_identifier
            from code_indexer.server.mcp.handlers import handle_git_log
            result = await handle_git_log(
                {"repo_identifier": "repo1-global", "limit": 10}, test_user
            )

            # Assert: Should call GitOperationsService.get_log (not omni-search)
            assert mock_service.get_log.called
            assert result["content"][0]["type"] == "text"

    @pytest.mark.asyncio
    async def test_array_repo_identifier_routes_to_omni_log(self, test_user):
        """Array repo_identifier routes to omni-git-log."""
        # Execute: Call with array repo_identifier
        from code_indexer.server.mcp.handlers import handle_git_log
        result = await handle_git_log(
            {"repo_identifier": ["repo1-global", "repo2-global"], "limit": 10},
            test_user,
        )

        # Assert: Should return omni-log stub response
        import json

        response_data = json.loads(result["content"][0]["text"])
        assert response_data["success"] is True
        assert "repos_searched" in response_data
        assert "errors" in response_data
        assert isinstance(response_data["commits"], list)
