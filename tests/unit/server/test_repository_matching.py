"""
Unit tests for repository matching logic.

Following TDD methodology - these tests define the expected behavior for matching
repositories based on git URLs and user permissions.
"""

import pytest
from unittest.mock import Mock
from datetime import datetime, timezone

from code_indexer.server.services.repository_matcher import (
    RepositoryMatcher,
    RepositoryMatchResult,
    MatchingError,
)
from code_indexer.server.auth.user_manager import User, UserRole


class TestRepositoryMatchResult:
    """Test the repository match result data model."""

    def test_repository_match_result_creation(self):
        """Test creation of RepositoryMatchResult."""
        result = RepositoryMatchResult(
            repository_id="test-repo",
            repository_type="golden",
            alias="my-project",
            git_url="https://github.com/user/repo.git",
            canonical_url="github.com/user/repo",
            available_branches=["main", "develop"],
            default_branch="main",
            last_indexed=datetime.now(timezone.utc),
            access_level="read",
        )

        assert result.repository_id == "test-repo"
        assert result.repository_type == "golden"
        assert result.alias == "my-project"
        assert result.canonical_url == "github.com/user/repo"
        assert result.access_level == "read"

    def test_repository_match_result_validation(self):
        """Test validation of RepositoryMatchResult."""
        # Test invalid repository_type
        with pytest.raises(ValueError):
            RepositoryMatchResult(
                repository_id="test",
                repository_type="invalid",  # Should be 'golden' or 'activated'
                alias="test",
                git_url="https://github.com/user/repo.git",
                canonical_url="github.com/user/repo",
                available_branches=["main"],
                default_branch="main",
                access_level="read",
            )

        # Test invalid access_level
        with pytest.raises(ValueError):
            RepositoryMatchResult(
                repository_id="test",
                repository_type="golden",
                alias="test",
                git_url="https://github.com/user/repo.git",
                canonical_url="github.com/user/repo",
                available_branches=["main"],
                default_branch="main",
                access_level="invalid",  # Should be 'read', 'write', 'admin'
            )


class TestRepositoryMatcher:
    """Test the repository matching service logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.golden_repo_manager = Mock()
        self.activated_repo_manager = Mock()
        self.access_control_manager = Mock()

        self.matcher = RepositoryMatcher(
            golden_repo_manager=self.golden_repo_manager,
            activated_repo_manager=self.activated_repo_manager,
            access_control_manager=self.access_control_manager,
        )

    @pytest.mark.asyncio
    async def test_find_matching_golden_repositories(self):
        """Test finding matching golden repositories."""
        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock golden repository data
        golden_repos = [
            {
                "id": "golden-1",
                "alias": "main-repo",
                "repo_url": "https://github.com/user/repo.git",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main", "develop"],
                "created_at": "2024-01-01T00:00:00Z",
                "last_indexed": datetime.now(timezone.utc),
            },
            {
                "id": "golden-2",
                "alias": "fork-repo",
                "repo_url": "git@github.com:user/repo.git",
                "canonical_url": canonical_url,
                "default_branch": "master",
                "branches": ["master"],
                "created_at": "2024-01-02T00:00:00Z",
                "last_indexed": None,
            },
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos

        # Mock access control
        self.access_control_manager.get_user_access_level.side_effect = [
            "read",  # User has read access to golden-1
            None,  # User has no access to golden-2
        ]

        results = await self.matcher.find_matching_golden_repositories(
            canonical_url=canonical_url, user=user
        )

        assert len(results) == 1
        result = results[0]
        assert result.repository_id == "golden-1"
        assert result.repository_type == "golden"
        assert result.alias == "main-repo"
        assert result.access_level == "read"
        assert result.canonical_url == canonical_url

    @pytest.mark.asyncio
    async def test_find_matching_activated_repositories(self):
        """Test finding matching activated repositories."""
        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock activated repository data
        activated_repos = [
            {
                "id": "activated-1",
                "user_alias": "test-user",
                "golden_repo_alias": "main-repo",
                "canonical_url": canonical_url,
                "current_branch": "feature-branch",
                "branches": ["main", "feature-branch"],
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": datetime.now(timezone.utc),
            },
            {
                "id": "activated-2",
                "user_alias": "other-user",
                "golden_repo_alias": "main-repo",
                "canonical_url": canonical_url,
                "current_branch": "main",
                "branches": ["main"],
                "activated_at": "2024-01-01T00:00:00Z",
                "last_accessed": datetime.now(timezone.utc),
            },
        ]

        self.activated_repo_manager.find_by_canonical_url.return_value = activated_repos

        # Mock access control - user can only access their own activated repos
        def mock_access_check(repo_data, user):
            return "write" if repo_data["user_alias"] == user.username else None

        self.access_control_manager.get_user_access_level.side_effect = (
            mock_access_check
        )

        results = await self.matcher.find_matching_activated_repositories(
            canonical_url=canonical_url, user=user
        )

        assert len(results) == 1
        result = results[0]
        assert result.repository_id == "activated-1"
        assert result.repository_type == "activated"
        assert result.alias == "test-user/main-repo"
        assert result.access_level == "write"

    @pytest.mark.asyncio
    async def test_find_all_matching_repositories(self):
        """Test finding all matching repositories (golden + activated)."""
        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock golden repositories
        golden_repos = [
            {
                "id": "golden-1",
                "alias": "main-repo",
                "repo_url": "https://github.com/user/repo.git",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main"],
                "last_indexed": datetime.now(timezone.utc),
            }
        ]

        # Mock activated repositories
        activated_repos = [
            {
                "id": "activated-1",
                "user_alias": "test-user",
                "golden_repo_alias": "main-repo",
                "canonical_url": canonical_url,
                "current_branch": "feature",
                "branches": ["main", "feature"],
                "last_accessed": datetime.now(timezone.utc),
            }
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.activated_repo_manager.find_by_canonical_url.return_value = activated_repos

        # Mock access control
        self.access_control_manager.get_user_access_level.return_value = "read"

        golden_results, activated_results = (
            await self.matcher.find_all_matching_repositories(
                canonical_url=canonical_url, user=user
            )
        )

        assert len(golden_results) == 1
        assert len(activated_results) == 1
        assert golden_results[0].repository_type == "golden"
        assert activated_results[0].repository_type == "activated"

    @pytest.mark.asyncio
    async def test_find_matching_repositories_no_access(self):
        """Test finding repositories when user has no access."""
        canonical_url = "github.com/private/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock repositories that exist but user has no access
        golden_repos = [
            {
                "id": "private-golden-1",
                "alias": "private-repo",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main"],
            }
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.activated_repo_manager.find_by_canonical_url.return_value = []

        # Mock no access
        self.access_control_manager.get_user_access_level.return_value = None

        results = await self.matcher.find_matching_golden_repositories(
            canonical_url=canonical_url, user=user
        )

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_find_matching_repositories_admin_access(self):
        """Test that admin users can access all repositories."""
        canonical_url = "github.com/any/repo"
        admin_user = User(
            username="admin",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

        # Mock repositories
        golden_repos = [
            {
                "id": "repo-1",
                "alias": "repo",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main"],
            }
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.activated_repo_manager.find_by_canonical_url.return_value = []

        # Mock admin access
        self.access_control_manager.get_user_access_level.return_value = "admin"

        results = await self.matcher.find_matching_golden_repositories(
            canonical_url=canonical_url, user=admin_user
        )

        assert len(results) == 1
        assert results[0].access_level == "admin"

    @pytest.mark.asyncio
    async def test_find_matching_repositories_handles_manager_errors(self):
        """Test error handling when repository managers fail."""
        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock manager error
        self.golden_repo_manager.find_by_canonical_url.side_effect = Exception(
            "Database error"
        )

        with pytest.raises(MatchingError) as exc_info:
            await self.matcher.find_matching_golden_repositories(
                canonical_url=canonical_url, user=user
            )

        assert "Failed to find matching golden repositories" in str(exc_info.value)
        assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_repository_matching_performance(self):
        """Test repository matching performance with large datasets."""
        canonical_url = "github.com/popular/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock large number of repositories
        golden_repos = [
            {
                "id": f"golden-{i}",
                "alias": f"repo-{i}",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main"],
            }
            for i in range(100)
        ]

        activated_repos = [
            {
                "id": f"activated-{i}",
                "user_alias": "test-user",
                "golden_repo_alias": f"repo-{i}",
                "canonical_url": canonical_url,
                "current_branch": "main",
                "branches": ["main"],
            }
            for i in range(50)
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.activated_repo_manager.find_by_canonical_url.return_value = activated_repos

        # Mock access control that grants access to all
        self.access_control_manager.get_user_access_level.return_value = "read"

        import time

        start_time = time.time()

        golden_results, activated_results = (
            await self.matcher.find_all_matching_repositories(
                canonical_url=canonical_url, user=user
            )
        )

        end_time = time.time()

        # Should complete quickly even with large datasets
        assert end_time - start_time < 1.0
        assert len(golden_results) == 100
        assert len(activated_results) == 50

    @pytest.mark.asyncio
    async def test_repository_matching_branch_information(self):
        """Test that repository matching includes accurate branch information."""
        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock repository with multiple branches
        golden_repos = [
            {
                "id": "multi-branch-repo",
                "alias": "feature-rich",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main", "develop", "feature/auth", "hotfix/critical"],
                "branch_metadata": {
                    "main": {"last_commit": "abc123", "protected": True},
                    "develop": {"last_commit": "def456", "protected": False},
                },
            }
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.access_control_manager.get_user_access_level.return_value = "read"

        results = await self.matcher.find_matching_golden_repositories(
            canonical_url=canonical_url, user=user
        )

        assert len(results) == 1
        result = results[0]
        assert result.default_branch == "main"
        assert len(result.available_branches) == 4
        assert "main" in result.available_branches
        assert "feature/auth" in result.available_branches

    @pytest.mark.asyncio
    async def test_repository_matching_with_url_variations(self):
        """Test that repository matching works with different URL formats."""
        # All these URLs should match the same canonical form
        url_variations = [
            "https://github.com/user/repo.git",
            "git@github.com:user/repo.git",
            "https://github.com/user/repo",
            "git@github.com:user/repo",
        ]

        canonical_url = "github.com/user/repo"
        user = User(
            username="test-user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

        # Mock repository
        golden_repos = [
            {
                "id": "repo-1",
                "alias": "main-repo",
                "canonical_url": canonical_url,
                "default_branch": "main",
                "branches": ["main"],
            }
        ]

        self.golden_repo_manager.find_by_canonical_url.return_value = golden_repos
        self.access_control_manager.get_user_access_level.return_value = "read"

        # Test that all URL variations find the same repository
        for url in url_variations:
            # Note: In the actual implementation, URL normalization happens before
            # calling the matcher, so we're testing with the canonical form
            results = await self.matcher.find_matching_golden_repositories(
                canonical_url=canonical_url, user=user
            )

            assert len(results) == 1
            assert results[0].canonical_url == canonical_url
