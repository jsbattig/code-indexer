"""
Unit tests for temporal status retrieval in repository details and refresh operations.

Tests that verify:
1. GET endpoint returns temporal status when temporal is enabled
2. GET endpoint returns temporal status as disabled when temporal is not enabled
3. Refresh operation preserves temporal configuration
"""

import os
import tempfile
from unittest.mock import patch

import pytest

from src.code_indexer.server.repositories.repository_listing_manager import (
    RepositoryListingManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import (
    GoldenRepoManager,
    GoldenRepo,
)
from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)


class TestTemporalStatusRetrieval:
    """Test suite for temporal status retrieval in repository details."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with test data."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add temporal-enabled repository
        temporal_repo_path = os.path.join(
            temp_data_dir, "golden-repos", "temporal-repo"
        )
        os.makedirs(temporal_repo_path, exist_ok=True)

        # Create .code-indexer directory structure
        code_indexer_dir = os.path.join(temporal_repo_path, ".code-indexer")
        os.makedirs(code_indexer_dir, exist_ok=True)

        # Create temporal index directory to simulate indexed temporal data
        temporal_index_dir = os.path.join(
            code_indexer_dir, "index", "code-indexer-temporal"
        )
        os.makedirs(temporal_index_dir, exist_ok=True)

        manager.golden_repos["temporal-repo"] = GoldenRepo(
            alias="temporal-repo",
            repo_url="https://github.com/user/temporal-repo.git",
            default_branch="main",
            clone_path=temporal_repo_path,
            created_at="2024-01-01T00:00:00+00:00",
            enable_temporal=True,
            temporal_options={
                "max_commits": 100,
                "diff_context": 10,
                "since_date": "2024-01-01",
            },
        )

        manager._save_metadata()
        return manager

    @pytest.fixture
    def activated_repo_manager(self, temp_data_dir):
        """Create ActivatedRepoManager instance."""
        return ActivatedRepoManager(data_dir=temp_data_dir)

    @pytest.fixture
    def repository_listing_manager(self, golden_repo_manager, activated_repo_manager):
        """Create RepositoryListingManager instance."""
        return RepositoryListingManager(
            golden_repo_manager=golden_repo_manager,
            activated_repo_manager=activated_repo_manager,
        )

    def test_get_repository_details_returns_temporal_status_when_enabled(
        self, repository_listing_manager
    ):
        """Test that get_repository_details returns temporal status when temporal is enabled."""
        # This test should FAIL initially because get_repository_details
        # doesn't populate enable_temporal and temporal_status fields

        result = repository_listing_manager.get_repository_details(
            alias="temporal-repo", username="testuser"
        )

        # Assert temporal fields are populated
        assert "enable_temporal" in result, "Missing enable_temporal field"
        assert result["enable_temporal"] is True, "enable_temporal should be True"

        assert "temporal_status" in result, "Missing temporal_status field"
        assert (
            result["temporal_status"] is not None
        ), "temporal_status should not be None"

        # Verify temporal_status structure
        temporal_status = result["temporal_status"]
        assert "enabled" in temporal_status, "temporal_status missing 'enabled' field"
        assert (
            temporal_status["enabled"] is True
        ), "temporal_status enabled should be True"

        assert (
            "diff_context" in temporal_status
        ), "temporal_status missing 'diff_context' field"
        assert temporal_status["diff_context"] == 10, "diff_context should be 10"

        # Optional fields
        if "max_commits" in temporal_status:
            assert temporal_status["max_commits"] == 100
        if "since_date" in temporal_status:
            assert temporal_status["since_date"] == "2024-01-01"

    def test_get_repository_details_returns_temporal_status_disabled_when_not_enabled(
        self, repository_listing_manager, golden_repo_manager
    ):
        """Test that get_repository_details returns temporal status as disabled when temporal is not enabled."""
        # Add non-temporal repository
        non_temporal_repo_path = os.path.join(
            golden_repo_manager.golden_repos_dir, "regular-repo"
        )
        os.makedirs(non_temporal_repo_path, exist_ok=True)

        golden_repo_manager.golden_repos["regular-repo"] = GoldenRepo(
            alias="regular-repo",
            repo_url="https://github.com/user/regular-repo.git",
            default_branch="main",
            clone_path=non_temporal_repo_path,
            created_at="2024-01-02T00:00:00+00:00",
            enable_temporal=False,
            temporal_options=None,
        )
        golden_repo_manager._save_metadata()

        result = repository_listing_manager.get_repository_details(
            alias="regular-repo", username="testuser"
        )

        # Assert temporal fields are populated with disabled status
        assert "enable_temporal" in result, "Missing enable_temporal field"
        assert result["enable_temporal"] is False, "enable_temporal should be False"

        assert "temporal_status" in result, "Missing temporal_status field"
        # temporal_status can be None or a dict with enabled=False
        if result["temporal_status"] is not None:
            assert (
                result["temporal_status"]["enabled"] is False
            ), "temporal_status enabled should be False"


class TestRefreshPreservesTemporalConfig:
    """Test suite for refresh operation preserving temporal configuration."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create GoldenRepoManager instance with temporal-enabled repo."""
        manager = GoldenRepoManager(data_dir=temp_data_dir)

        # Add temporal-enabled repository
        temporal_repo_path = os.path.join(
            temp_data_dir, "golden-repos", "temporal-refresh-repo"
        )
        os.makedirs(temporal_repo_path, exist_ok=True)

        # Create .code-indexer directory
        code_indexer_dir = os.path.join(temporal_repo_path, ".code-indexer")
        os.makedirs(code_indexer_dir, exist_ok=True)

        # Create a dummy .git directory to make it look like a real repo
        git_dir = os.path.join(temporal_repo_path, ".git")
        os.makedirs(git_dir, exist_ok=True)

        manager.golden_repos["temporal-refresh-repo"] = GoldenRepo(
            alias="temporal-refresh-repo",
            repo_url="/tmp/local-repo",  # Local path to avoid git operations
            default_branch="main",
            clone_path=temporal_repo_path,
            created_at="2024-01-01T00:00:00+00:00",
            enable_temporal=True,
            temporal_options={
                "max_commits": 50,
                "diff_context": 15,
            },
        )

        manager._save_metadata()
        return manager

    def test_refresh_golden_repo_preserves_temporal_configuration(
        self, golden_repo_manager
    ):
        """Test that refresh_golden_repo preserves temporal configuration."""
        # This test should FAIL initially because refresh_golden_repo
        # doesn't read and pass temporal configuration to _execute_post_clone_workflow

        alias = "temporal-refresh-repo"

        # Mock _execute_post_clone_workflow to capture the arguments
        with patch.object(
            golden_repo_manager, "_execute_post_clone_workflow"
        ) as mock_workflow:
            mock_workflow.return_value = None

            # Act - refresh the repository
            result = golden_repo_manager.refresh_golden_repo(alias)

            # Assert - verify workflow was called with temporal parameters
            assert result["success"] is True
            mock_workflow.assert_called_once()

            # Verify that enable_temporal and temporal_options were passed
            call_args = mock_workflow.call_args
            assert call_args is not None, "Workflow method was not called"

            kwargs = call_args[1]
            assert (
                "enable_temporal" in kwargs
            ), "enable_temporal parameter not passed to workflow"
            assert kwargs["enable_temporal"] is True, "enable_temporal should be True"

            assert (
                "temporal_options" in kwargs
            ), "temporal_options parameter not passed to workflow"
            assert (
                kwargs["temporal_options"] is not None
            ), "temporal_options should not be None"
            assert (
                kwargs["temporal_options"]["max_commits"] == 50
            ), "max_commits should be preserved"
            assert (
                kwargs["temporal_options"]["diff_context"] == 15
            ), "diff_context should be preserved"
