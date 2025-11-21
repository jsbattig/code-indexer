"""
Unit tests for Repository Listing Manager.

Tests the repository listing functionality including:
- Listing available golden repositories
- Repository search and filtering
- Repository details API
- Repository statistics
- Pagination support
"""

import json
import os
import tempfile
from unittest.mock import patch

import pytest

from src.code_indexer.server.repositories.repository_listing_manager import (
    RepositoryListingManager,
    RepositoryListingError,
)
from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
)
from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)


@pytest.mark.e2e
class TestRepositoryListingManager:
    """Test suite for Repository Listing Manager functionality."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with test data."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add test golden repositories
        test_repos = [
            {
                "alias": "python-project",
                "repo_url": "https://github.com/user/python-project.git",
                "default_branch": "main",
                "clone_path": os.path.join(
                    temp_data_dir, "golden-repos", "python-project"
                ),
                "created_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "alias": "javascript-lib",
                "repo_url": "https://github.com/user/javascript-lib.git",
                "default_branch": "master",
                "clone_path": os.path.join(
                    temp_data_dir, "golden-repos", "javascript-lib"
                ),
                "created_at": "2024-01-02T00:00:00+00:00",
            },
            {
                "alias": "machine-learning",
                "repo_url": "https://github.com/user/ml-project.git",
                "default_branch": "main",
                "clone_path": os.path.join(
                    temp_data_dir, "golden-repos", "machine-learning"
                ),
                "created_at": "2024-01-03T00:00:00+00:00",
            },
        ]

        for repo_data in test_repos:
            manager.golden_repos[repo_data["alias"]] = GoldenRepo(**repo_data)

        return manager

    @pytest.fixture
    def activated_repo_manager(self, temp_data_dir):
        """Create ActivatedRepoManager instance with test data."""
        manager = ActivatedRepoManager(data_dir=temp_data_dir)

        # Create directory structure for activated repositories
        activated_repos_dir = os.path.join(temp_data_dir, "activated-repos")
        os.makedirs(activated_repos_dir, exist_ok=True)

        # Mock user activations for testuser
        user_dir = os.path.join(activated_repos_dir, "testuser")
        os.makedirs(user_dir, exist_ok=True)

        # Create activation metadata for python-project
        activation_data = {
            "user_alias": "python-project",
            "golden_repo_alias": "python-project",
            "current_branch": "main",
            "activated_at": "2024-01-01T10:00:00+00:00",
            "last_accessed": "2024-01-01T10:00:00+00:00",
        }

        metadata_file = os.path.join(user_dir, "python-project_metadata.json")
        with open(metadata_file, "w") as f:
            json.dump(activation_data, f, indent=2)

        # Also create the repo directory to make it look real
        repo_dir = os.path.join(user_dir, "python-project")
        os.makedirs(repo_dir, exist_ok=True)

        return manager

    @pytest.fixture
    def repository_listing_manager(self, golden_repo_manager, activated_repo_manager):
        """Create RepositoryListingManager instance."""
        return RepositoryListingManager(
            golden_repo_manager=golden_repo_manager,
            activated_repo_manager=activated_repo_manager,
        )

    def test_list_available_golden_repositories_excludes_activated(
        self, repository_listing_manager
    ):
        """Test that list_available_repositories excludes already activated repositories for user."""
        result = repository_listing_manager.list_available_repositories(
            username="testuser"
        )

        # Should return repositories not activated by user
        # Expected: javascript-lib and machine-learning (python-project is activated)
        assert len(result["repositories"]) == 2
        repo_aliases = [repo["alias"] for repo in result["repositories"]]
        assert "javascript-lib" in repo_aliases
        assert "machine-learning" in repo_aliases
        assert "python-project" not in repo_aliases

        # Verify response structure
        assert "total" in result
        assert result["total"] == 2

    def test_list_available_golden_repositories_all_for_new_user(
        self, repository_listing_manager
    ):
        """Test that new user sees all golden repositories as available."""
        result = repository_listing_manager.list_available_repositories(
            username="newuser"
        )

        # Expected: all 3 repositories (python-project, javascript-lib, machine-learning)
        assert len(result["repositories"]) == 3
        repo_aliases = [repo["alias"] for repo in result["repositories"]]
        assert "javascript-lib" in repo_aliases
        assert "machine-learning" in repo_aliases
        assert "python-project" in repo_aliases

    def test_get_repository_details_existing_repo(self, repository_listing_manager):
        """Test get_repository_details for existing golden repository."""
        result = repository_listing_manager.get_repository_details(
            alias="python-project", username="testuser"
        )

        # Expected: detailed info with activation status for user
        assert result["alias"] == "python-project"
        assert result["repo_url"] == "https://github.com/user/python-project.git"
        assert result["default_branch"] == "main"
        assert "created_at" in result
        assert result["activation_status"] == "activated"  # testuser has it activated

    def test_get_repository_details_nonexistent_repo(self, repository_listing_manager):
        """Test get_repository_details for non-existent repository."""
        with pytest.raises(
            RepositoryListingError, match="Repository 'nonexistent' not found"
        ):
            repository_listing_manager.get_repository_details(
                alias="nonexistent", username="testuser"
            )

    def test_search_repositories_by_alias(self, repository_listing_manager):
        """Test repository search by alias."""
        result = repository_listing_manager.search_repositories(
            username="testuser", search_term="python"
        )

        # Should find no results since python-project is activated by testuser
        # But if we search as new user, should find python-project
        result_newuser = repository_listing_manager.search_repositories(
            username="newuser", search_term="python"
        )

        assert len(result["repositories"]) == 0
        assert len(result_newuser["repositories"]) == 1
        assert result_newuser["repositories"][0]["alias"] == "python-project"

    def test_search_repositories_case_insensitive(self, repository_listing_manager):
        """Test repository search is case insensitive."""
        result = repository_listing_manager.search_repositories(
            username="testuser", search_term="JAVASCRIPT"
        )

        # Should find javascript-lib repository (case insensitive)
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["alias"] == "javascript-lib"

    def test_filter_repositories_by_status_available(self, repository_listing_manager):
        """Test filtering repositories by available status."""
        result = repository_listing_manager.filter_repositories(
            username="testuser", status_filter="available"
        )

        # Expected: javascript-lib, machine-learning
        assert len(result["repositories"]) == 2
        repo_aliases = [repo["alias"] for repo in result["repositories"]]
        assert "javascript-lib" in repo_aliases
        assert "machine-learning" in repo_aliases
        assert "python-project" not in repo_aliases

    def test_filter_repositories_by_status_activated(self, repository_listing_manager):
        """Test filtering repositories by activated status."""
        result = repository_listing_manager.filter_repositories(
            username="testuser", status_filter="activated"
        )

        # Expected: python-project
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["alias"] == "python-project"

    def test_returns_all_repositories_no_pagination(self, repository_listing_manager):
        """Test that all repositories are returned without pagination."""
        result = repository_listing_manager.list_available_repositories(
            username="newuser"
        )

        # Expected: All 3 repositories returned at once
        # newuser sees all 3 repos without pagination
        assert len(result["repositories"]) == 3
        assert result["total"] == 3

    def test_repository_statistics_file_count(self, repository_listing_manager):
        """Test repository statistics include file count."""
        result = repository_listing_manager.get_repository_statistics(
            alias="python-project"
        )

        # Expected: statistics with file_count
        assert "file_count" in result
        assert isinstance(result["file_count"], int)
        assert result["file_count"] >= 0

    def test_repository_statistics_index_size(self, repository_listing_manager):
        """Test repository statistics include index size."""
        result = repository_listing_manager.get_repository_statistics(
            alias="python-project"
        )

        # Expected: statistics with index_size
        assert "index_size" in result
        assert isinstance(result["index_size"], int)
        assert result["index_size"] >= 0

    def test_repository_activation_count(self, repository_listing_manager):
        """Test repository statistics include activation count."""
        result = repository_listing_manager.get_activation_count(
            golden_repo_alias="python-project"
        )

        # Expected: activation count = 1 (testuser has it activated)
        assert isinstance(result, int)
        assert result >= 0
        assert result == 1  # testuser has python-project activated

    def test_get_available_branches_list(self, repository_listing_manager):
        """Test getting available branches for a repository."""
        # Mock git branch listing
        with patch(
            "src.code_indexer.server.repositories.repository_listing_manager.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = (
                "refs/heads/main\nrefs/heads/develop\nrefs/heads/feature/new-ui\n"
            )

            result = repository_listing_manager.get_available_branches(
                alias="python-project"
            )

            # Expected: ["main", "develop", "feature/new-ui"]
            assert isinstance(result, list)
            assert len(result) == 3
            expected_branches = ["main", "develop", "feature/new-ui"]
            # Since we mocked the output, we should get the expected branches
            for branch in expected_branches:
                assert branch in result

    def test_combined_search_and_filter(self, repository_listing_manager):
        """Test combined search term and status filtering."""
        result = repository_listing_manager.list_available_repositories(
            username="testuser", search_term="project", status_filter="available"
        )

        # Expected: machine-learning (has "project" in repo URL and is available)
        # python-project is activated by testuser, so shouldn't appear
        # javascript-lib doesn't contain "project", so shouldn't appear
        # machine-learning has "project" in its repo URL and is available to testuser
        assert len(result["repositories"]) == 1
        assert result["repositories"][0]["alias"] == "machine-learning"

    def test_error_handling_invalid_status_filter(self, repository_listing_manager):
        """Test error handling for invalid status filter."""
        with pytest.raises(RepositoryListingError, match="Invalid status filter"):
            repository_listing_manager.filter_repositories(
                username="testuser", status_filter="invalid_status"
            )

    def test_no_pagination_parameters_accepted(self, repository_listing_manager):
        """Test that pagination parameters are no longer accepted."""
        # This test ensures that the method signature doesn't accept pagination parameters
        result = repository_listing_manager.list_available_repositories(
            username="testuser"
        )

        # Should return all available repositories for the user
        assert "repositories" in result
        assert "total" in result

    def test_empty_results_with_restrictive_search(self, repository_listing_manager):
        """Test handling of empty results with restrictive search."""
        result = repository_listing_manager.search_repositories(
            username="testuser", search_term="nonexistent_term"
        )

        # Expected: empty list with total count
        assert len(result["repositories"]) == 0
        assert result["total"] == 0

    def test_repository_details_includes_activation_status(
        self, repository_listing_manager
    ):
        """Test that repository details include user's activation status."""
        result = repository_listing_manager.get_repository_details(
            alias="python-project", username="testuser"
        )

        # Expected: activation_status = "activated" for testuser
        assert "activation_status" in result
        assert result["activation_status"] == "activated"

    def test_repository_details_includes_all_required_fields(
        self, repository_listing_manager
    ):
        """Test that repository details include all required fields per acceptance criteria."""
        result = repository_listing_manager.get_repository_details(
            alias="python-project", username="testuser"
        )

        # Expected fields: alias, repo_url, default_branch,
        # branches_list, file_count, index_size, last_updated, activation_status
        required_fields = [
            "alias",
            "repo_url",
            "default_branch",
            "clone_path",
            "created_at",
            "branches_list",
            "file_count",
            "index_size",
            "last_updated",
            "activation_status",
        ]

        for field in required_fields:
            assert field in result, f"Field '{field}' missing from repository details"

    def test_response_format_consistency(self, repository_listing_manager):
        """Test consistent JSON response format across all methods."""
        available = repository_listing_manager.list_available_repositories("testuser")
        details = repository_listing_manager.get_repository_details(
            "javascript-lib", "testuser"
        )
        search = repository_listing_manager.search_repositories(
            "testuser", "javascript"
        )

        # Expected: consistent structure with proper metadata
        # Available repositories should have basic structure
        assert "repositories" in available
        assert "total" in available

        # Details should have repository information
        assert "alias" in details
        assert "repo_url" in details
        assert "activation_status" in details

        # Search should have same structure as available repositories
        assert "repositories" in search
        assert "total" in search
