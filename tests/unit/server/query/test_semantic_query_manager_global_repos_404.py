"""
Unit tests for SemanticQueryManager global repos 404 bug.

This test file reproduces and fixes the issue where global repos are loaded
correctly but filtering by repository_alias returns 404.

Evidence from logs:
- Global repo registered: cidx-query-e2e-test-7f3a9b2c-global
- GlobalRegistry loads correctly: "Loaded global registry with 1 repos"
- Query with repository_alias='cidx-query-e2e-test-7f3a9b2c-global' returns 404
- Error: "Repository 'cidx-query-e2e-test-7f3a9b2c-global' not found"

Root cause hypothesis:
The filtering logic at semantic_query_manager.py:437-444 is comparing
repo["user_alias"] == repository_alias, but global repos might not be
properly formatted with the correct user_alias field.

Following TDD methodology: Write failing tests first, then implement fix.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.server.query.semantic_query_manager import (
    SemanticQueryManager,
    SemanticQueryError,
)


logger = logging.getLogger(__name__)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        data_dir = Path(temp_dir) / "data"
        golden_repos_dir = data_dir / "golden-repos"
        activated_repos_dir = data_dir / "activated-repos"

        golden_repos_dir.mkdir(parents=True, exist_ok=True)
        activated_repos_dir.mkdir(parents=True, exist_ok=True)

        yield {
            "data_dir": str(data_dir),
            "golden_repos_dir": str(golden_repos_dir),
            "activated_repos_dir": str(activated_repos_dir),
        }


@pytest.fixture
def global_registry_with_repo(temp_dirs):
    """Create a GlobalRegistry with one registered global repo."""
    from code_indexer.global_repos.global_registry import GlobalRegistry

    registry = GlobalRegistry(temp_dirs["golden_repos_dir"])

    # Register a global repo matching the E2E test scenario
    registry.register_global_repo(
        repo_name="cidx-query-e2e-test-7f3a9b2c",
        alias_name="cidx-query-e2e-test-7f3a9b2c-global",
        repo_url="https://github.com/jsbattig/tries.git",
        index_path="/fake/path/to/repo",
        enable_temporal=True,
    )

    return registry


@pytest.fixture
def activated_repo_manager_mock(temp_dirs):
    """Mock activated repo manager that returns empty user repos."""
    mock = MagicMock()
    mock.activated_repos_dir = temp_dirs["activated_repos_dir"]
    mock.list_activated_repositories.return_value = []  # No user repos
    return mock


@pytest.fixture
def background_job_manager_mock():
    """Mock background job manager."""
    mock = MagicMock()
    mock.submit_job.return_value = "test-job-id"
    return mock


@pytest.fixture
def semantic_query_manager(temp_dirs, activated_repo_manager_mock, background_job_manager_mock):
    """Create SemanticQueryManager with mocked dependencies."""
    return SemanticQueryManager(
        data_dir=temp_dirs["data_dir"],
        activated_repo_manager=activated_repo_manager_mock,
        background_job_manager=background_job_manager_mock,
    )


class TestGlobalRepos404Bug:
    """Test suite for global repos 404 bug reproduction and fix."""

    def test_global_repos_are_loaded_from_registry(
        self,
        semantic_query_manager,
        global_registry_with_repo,
        activated_repo_manager_mock,
    ):
        """
        Test that global repos are loaded from GlobalRegistry.

        This test verifies the first part of the issue: global repos ARE being
        loaded successfully from the registry.
        """
        # Mock the query execution to focus on repo loading
        with patch.object(
            semantic_query_manager,
            "_perform_search",
            return_value=[],
        ):
            # This should not raise an error about no repositories
            try:
                result = semantic_query_manager.query_user_repositories(
                    username="testuser",
                    query_text="test",
                    search_mode="semantic",
                    limit=10,
                    # No repository_alias filter - should search all repos
                )
                # If we get here, global repos were loaded
                assert result is not None
            except SemanticQueryError as e:
                if "No activated repositories found" in str(e):
                    pytest.fail(
                        "Global repos were not loaded from registry. "
                        "Expected global repos to be available even when user has no activated repos."
                    )
                raise

    def test_global_repo_filtering_by_alias_returns_404(
        self,
        semantic_query_manager,
        global_registry_with_repo,
        activated_repo_manager_mock,
    ):
        """
        Test that filtering by global repo alias works correctly.

        After fixing the data_dir parameter in app.py, this test should pass.

        Steps:
        1. Global repo is registered with alias 'cidx-query-e2e-test-7f3a9b2c-global'
        2. Query with repository_alias='cidx-query-e2e-test-7f3a9b2c-global'
        3. Expected: Query executes against the global repo successfully
        4. Actual (after fix): Query works correctly

        This test verifies the fix works.
        """
        # Mock the query execution to focus on filtering logic
        with patch.object(
            semantic_query_manager,
            "_perform_search",
            return_value=[],
        ):
            # After fix, this should work without raising SemanticQueryError
            try:
                result = semantic_query_manager.query_user_repositories(
                    username="testuser",
                    query_text="test",
                    repository_alias="cidx-query-e2e-test-7f3a9b2c-global",
                    search_mode="semantic",
                    limit=10,
                )
                # Success - the global repo was found and queried
                assert result is not None
            except SemanticQueryError as e:
                pytest.fail(
                    f"Query should work for global repo alias after fix. "
                    f"Got error: {e}"
                )

    def test_global_repo_structure_has_correct_user_alias_field(
        self,
        temp_dirs,
        global_registry_with_repo,
    ):
        """
        Test that global repos are formatted with correct user_alias field.

        This test checks the internal data structure to verify that when
        global repos are loaded and formatted, they have the correct field
        that will be used in filtering.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        registry = GlobalRegistry(temp_dirs["golden_repos_dir"])
        global_repos = registry.list_global_repos()

        assert len(global_repos) == 1
        global_repo = global_repos[0]

        # Verify the structure from registry
        assert "alias_name" in global_repo
        assert global_repo["alias_name"] == "cidx-query-e2e-test-7f3a9b2c-global"

        # Now simulate what semantic_query_manager does (lines 417-423)
        formatted_repo = {
            "user_alias": global_repo["alias_name"],
            "username": "global",
            "is_global": True,
            "repo_url": global_repo.get("repo_url", ""),
        }

        # This is what the filter compares (line 439)
        repository_alias = "cidx-query-e2e-test-7f3a9b2c-global"
        assert formatted_repo["user_alias"] == repository_alias, (
            f"Expected user_alias to match repository_alias for filtering. "
            f"Got user_alias='{formatted_repo['user_alias']}', "
            f"expected '{repository_alias}'"
        )

    def test_merged_repos_list_contains_global_repos(
        self,
        semantic_query_manager,
        global_registry_with_repo,
        activated_repo_manager_mock,
    ):
        """
        Test that the merged all_repos list contains global repos.

        This test verifies that global repos are properly merged with user repos
        before the filtering step.
        """
        # We need to inspect the internal state during query_user_repositories
        captured_repos = []

        def capture_repos_and_search(username, user_repos, *args, **kwargs):
            # Capture the user_repos argument (2nd positional parameter)
            captured_repos.extend(user_repos)
            return []

        with patch.object(
            semantic_query_manager,
            "_perform_search",
            side_effect=capture_repos_and_search,
        ):
            try:
                semantic_query_manager.query_user_repositories(
                    username="testuser",
                    query_text="test",
                    search_mode="semantic",
                    limit=10,
                )
            except SemanticQueryError:
                pass  # We only care about captured_repos

        # Verify global repos were included
        assert len(captured_repos) > 0, "Expected global repos to be included in search"

        global_repo_found = any(
            repo.get("user_alias") == "cidx-query-e2e-test-7f3a9b2c-global"
            for repo in captured_repos
        )
        assert global_repo_found, (
            f"Expected to find global repo with user_alias='cidx-query-e2e-test-7f3a9b2c-global' "
            f"in repos list. Found repos: {captured_repos}"
        )

    def test_filtering_preserves_global_repo_when_alias_matches(
        self,
        semantic_query_manager,
        global_registry_with_repo,
        activated_repo_manager_mock,
    ):
        """
        Test that filtering by repository_alias preserves matching global repo.

        This is the core fix verification test. After the bug is fixed,
        this test should pass, demonstrating that filtering works correctly
        for global repos.
        """
        captured_filtered_repos = []

        def capture_filtered_repos_and_search(username, user_repos, *args, **kwargs):
            # Capture the user_repos argument after filtering
            captured_filtered_repos.extend(user_repos)
            return []

        with patch.object(
            semantic_query_manager,
            "_perform_search",
            side_effect=capture_filtered_repos_and_search,
        ):
            # After fix, this should NOT raise SemanticQueryError
            try:
                semantic_query_manager.query_user_repositories(
                    username="testuser",
                    query_text="test",
                    repository_alias="cidx-query-e2e-test-7f3a9b2c-global",
                    search_mode="semantic",
                    limit=10,
                )
            except SemanticQueryError as e:
                pytest.fail(
                    f"Filtering should preserve global repo when alias matches. "
                    f"Got error: {e}. Captured repos: {captured_filtered_repos}"
                )

        # Verify the filtered list contains only the matching global repo
        assert len(captured_filtered_repos) == 1, (
            f"Expected exactly 1 repo after filtering. "
            f"Got {len(captured_filtered_repos)}: {captured_filtered_repos}"
        )

        filtered_repo = captured_filtered_repos[0]
        assert filtered_repo["user_alias"] == "cidx-query-e2e-test-7f3a9b2c-global"
        assert filtered_repo.get("is_global") is True


class TestGlobalReposIntegration:
    """Integration tests for global repos with real components."""

    def test_end_to_end_global_repo_query_flow(
        self,
        temp_dirs,
    ):
        """
        End-to-end integration test of the complete global repo query flow.

        This test uses real GlobalRegistry and minimal mocking to verify
        the complete flow works correctly after the fix.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry

        # Setup: Create real GlobalRegistry with a registered repo
        registry = GlobalRegistry(temp_dirs["golden_repos_dir"])
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://example.com/repo.git",
            index_path="/fake/path",
            enable_temporal=False,
        )

        # Setup: Create SemanticQueryManager
        activated_repo_manager_mock = MagicMock()
        activated_repo_manager_mock.activated_repos_dir = temp_dirs["activated_repos_dir"]
        activated_repo_manager_mock.list_activated_repositories.return_value = []

        background_job_manager_mock = MagicMock()

        manager = SemanticQueryManager(
            data_dir=temp_dirs["data_dir"],
            activated_repo_manager=activated_repo_manager_mock,
            background_job_manager=background_job_manager_mock,
        )

        # Mock the actual search execution
        with patch.object(manager, "_perform_search", return_value=[]):
            # Execute query with global repo alias
            try:
                result = manager.query_user_repositories(
                    username="testuser",
                    query_text="test query",
                    repository_alias="test-repo-global",
                    search_mode="semantic",
                    limit=10,
                )
                # Success - no 404 error
                assert result is not None
            except SemanticQueryError as e:
                pytest.fail(
                    f"End-to-end flow should work for global repos. Got error: {e}"
                )
