"""
Integration tests for DashboardService admin repo visibility (Bug #671).

Tests verify that:
- Admin users see all activated repositories across all users
- Regular users see only their own activated repositories

Following TDD methodology - tests written FIRST before implementation.
"""

import json
import os
import tempfile

import pytest

from src.code_indexer.server.services.dashboard_service import DashboardService
from src.code_indexer.server.repositories.activated_repo_manager import (
    ActivatedRepoManager,
)
from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager
from src.code_indexer.server.repositories.background_jobs import BackgroundJobManager


@pytest.mark.e2e
class TestDashboardServiceAdminRepoVisibility:
    """Integration tests for admin repository visibility in dashboard."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create golden repo manager instance."""
        return GoldenRepoManager(data_dir=temp_data_dir)

    @pytest.fixture
    def background_job_manager(self, temp_data_dir):
        """Create background job manager instance."""
        return BackgroundJobManager(storage_path=temp_data_dir)

    @pytest.fixture
    def activated_repo_manager(
        self, temp_data_dir, golden_repo_manager, background_job_manager
    ):
        """Create activated repo manager instance."""
        return ActivatedRepoManager(
            data_dir=temp_data_dir,
            golden_repo_manager=golden_repo_manager,
            background_job_manager=background_job_manager,
        )

    @pytest.fixture
    def setup_multi_user_repos(self, temp_data_dir):
        """
        Setup test data: Multiple users with activated repositories.

        Creates:
        - user1: 2 repos (user1-repo1, user1-repo2)
        - user2: 1 repo (user2-repo1)
        """
        # User1 has 2 repos
        user1_dir = os.path.join(temp_data_dir, "activated-repos", "user1")
        os.makedirs(user1_dir, exist_ok=True)

        user1_repo1 = {
            "user_alias": "user1-repo1",
            "golden_repo_alias": "golden1",
            "current_branch": "main",
            "collection_name": "user1-repo1-collection",
            "activated_at": "2024-01-01T12:00:00Z",
            "last_accessed": "2024-01-01T13:00:00Z",
        }

        user1_repo2 = {
            "user_alias": "user1-repo2",
            "golden_repo_alias": "golden2",
            "current_branch": "develop",
            "collection_name": "user1-repo2-collection",
            "activated_at": "2024-01-02T12:00:00Z",
            "last_accessed": "2024-01-02T13:00:00Z",
        }

        with open(os.path.join(user1_dir, "user1-repo1_metadata.json"), "w") as f:
            json.dump(user1_repo1, f)
        os.makedirs(os.path.join(user1_dir, "user1-repo1"))

        with open(os.path.join(user1_dir, "user1-repo2_metadata.json"), "w") as f:
            json.dump(user1_repo2, f)
        os.makedirs(os.path.join(user1_dir, "user1-repo2"))

        # User2 has 1 repo
        user2_dir = os.path.join(temp_data_dir, "activated-repos", "user2")
        os.makedirs(user2_dir, exist_ok=True)

        user2_repo1 = {
            "user_alias": "user2-repo1",
            "golden_repo_alias": "golden3",
            "current_branch": "main",
            "collection_name": "user2-repo1-collection",
            "activated_at": "2024-01-03T12:00:00Z",
            "last_accessed": "2024-01-03T13:00:00Z",
        }

        with open(os.path.join(user2_dir, "user2-repo1_metadata.json"), "w") as f:
            json.dump(user2_repo1, f)
        os.makedirs(os.path.join(user2_dir, "user2-repo1"))

    @pytest.fixture
    def dashboard_service_with_test_manager(self, activated_repo_manager):
        """
        Create dashboard service with injected test activated_repo_manager.

        Uses proper dependency injection by replacing _get_activated_repo_manager
        method to return our test manager instance.
        """
        dashboard_service = DashboardService()
        original_method = dashboard_service._get_activated_repo_manager
        dashboard_service._get_activated_repo_manager = lambda: activated_repo_manager

        yield dashboard_service

        # Restore original method
        dashboard_service._get_activated_repo_manager = original_method

    def test_admin_sees_all_activated_repos(
        self, dashboard_service_with_test_manager, setup_multi_user_repos
    ):
        """
        Test that admin users see all activated repositories across all users.

        Given: Multiple users have activated repositories
        When: Admin requests dashboard data with role='admin'
        Then: Dashboard shows ALL activated repos from ALL users
        """
        # Act: Admin user requests dashboard data with role='admin'
        dashboard_data = dashboard_service_with_test_manager.get_dashboard_data(
            username="admin_user", user_role="admin"
        )

        # Assert: Dashboard should show 3 total activated repos (2 from user1 + 1 from user2)
        assert (
            dashboard_data.repo_counts.activated == 3
        ), f"Admin should see 3 activated repos, got {dashboard_data.repo_counts.activated}"

    def test_regular_user_sees_only_own_repos(
        self, dashboard_service_with_test_manager, setup_multi_user_repos
    ):
        """
        Test that regular users see only their own activated repositories.

        Given: Multiple users have activated repositories
        When: Regular user requests dashboard data with role='user'
        Then: Dashboard shows ONLY repos activated by that specific user
        """
        # Act: user1 (regular user) requests dashboard data with role='user'
        dashboard_data = dashboard_service_with_test_manager.get_dashboard_data(
            username="user1", user_role="user"
        )

        # Assert: Dashboard should show only 2 repos from user1
        assert (
            dashboard_data.repo_counts.activated == 2
        ), f"user1 should see only 2 activated repos, got {dashboard_data.repo_counts.activated}"
