"""
Unit tests for golden repository branch listing endpoint.

Tests the complete API endpoint for retrieving branch information from golden repositories.
Following TDD methodology - these are failing tests that define expected behavior.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from fastapi import status

from code_indexer.server.app import create_app
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.models.golden_repo_branch_models import (
    GoldenRepoBranchInfo,
    GoldenRepositoryBranchesResponse,
)


class TestGoldenRepositoryBranchListingEndpoint:
    """Test suite for the golden repository branch listing API endpoint."""

    def setup_method(self):
        """Set up test environment for each test."""
        self.app = create_app()

    def _setup_authenticated_user(self, username="admin_user", role="admin"):
        """Setup authentication with a mock user."""
        mock_user = Mock()
        mock_user.username = username
        mock_user.role = role

        # Override the dependency
        self.app.dependency_overrides[get_current_user] = lambda: mock_user

        # Create client after setting up dependencies
        self.client = TestClient(self.app)
        return mock_user

    def _setup_unauthenticated_client(self):
        """Setup client without authentication."""
        # Create client without overriding dependencies
        self.client = TestClient(self.app)

    @pytest.fixture
    def mock_admin_user(self):
        """Mock admin user for authentication."""
        user = Mock()
        user.username = "admin_user"
        user.role = "admin"
        return user

    @pytest.fixture
    def mock_regular_user(self):
        """Mock regular user for authentication."""
        user = Mock()
        user.username = "regular_user"
        user.role = "user"
        return user

    @pytest.fixture
    def sample_branch_data(self):
        """Sample branch data for testing."""
        return [
            GoldenRepoBranchInfo(
                name="main",
                is_default=True,
                last_commit_hash="abc123456",
                last_commit_timestamp=datetime.now(timezone.utc),
                last_commit_author="John Doe",
                branch_type="main",
            ),
            GoldenRepoBranchInfo(
                name="feature/authentication",
                is_default=False,
                last_commit_hash="def789012",
                last_commit_timestamp=datetime.now(timezone.utc),
                last_commit_author="Jane Smith",
                branch_type="feature",
            ),
            GoldenRepoBranchInfo(
                name="release/v2.0",
                is_default=False,
                last_commit_hash="ghi345678",
                last_commit_timestamp=datetime.now(timezone.utc),
                last_commit_author="Bob Johnson",
                branch_type="release",
            ),
        ]

    def test_list_golden_repository_branches_endpoint_exists(self):
        """Test that the golden repository branches endpoint exists and requires authentication."""
        self._setup_unauthenticated_client()
        response = self.client.get("/api/repos/golden/test-repo/branches")

        # Should return 401 for unauthenticated request per MCP spec (RFC 9728)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "www-authenticate" in response.headers

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_for_existing_golden_repository(
        self, mock_golden_repo_manager, sample_branch_data
    ):
        """Test listing branches for an existing golden repository returns correct data."""
        # Setup authentication
        self._setup_authenticated_user("admin_user", "admin")

        # Setup golden repo manager to return branch data
        mock_golden_repo_manager.get_golden_repo_branches = AsyncMock(
            return_value=sample_branch_data
        )
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=True
        )

        response = self.client.get("/api/repos/golden/test-repo/branches")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Verify response structure
        assert "repository_alias" in data
        assert "total_branches" in data
        assert "default_branch" in data
        assert "branches" in data
        assert "retrieved_at" in data

        # Verify content
        assert data["repository_alias"] == "test-repo"
        assert data["total_branches"] == 3
        assert data["default_branch"] == "main"
        assert len(data["branches"]) == 3

        # Verify branch structure
        main_branch = next(b for b in data["branches"] if b["name"] == "main")
        assert main_branch["is_default"] is True
        assert main_branch["branch_type"] == "main"
        assert main_branch["last_commit_hash"] == "abc123456"

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_for_nonexistent_golden_repository(
        self, mock_golden_repo_manager
    ):
        """Test listing branches for non-existent golden repository returns 404."""
        # Setup authentication
        self._setup_authenticated_user("admin_user", "admin")

        # Setup golden repo manager to indicate repo doesn't exist
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=False)

        response = self.client.get("/api/repos/golden/nonexistent-repo/branches")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
        assert "nonexistent-repo" in data["detail"]

    def test_list_branches_requires_authentication(self):
        """Test that endpoint requires valid authentication."""
        # Test without authentication
        self._setup_unauthenticated_client()

        response = self.client.get("/api/repos/golden/test-repo/branches")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "www-authenticate" in response.headers

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_regular_user_access(
        self, mock_golden_repo_manager, sample_branch_data
    ):
        """Test that regular users can access public golden repositories."""
        # Setup authentication with regular user
        self._setup_authenticated_user("regular_user", "user")

        # Setup golden repo manager
        mock_golden_repo_manager.get_golden_repo_branches = AsyncMock(
            return_value=sample_branch_data
        )
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=True
        )

        response = self.client.get("/api/repos/golden/test-repo/branches")

        assert response.status_code == status.HTTP_200_OK

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_unauthorized_access(self, mock_golden_repo_manager):
        """Test that users cannot access golden repositories they don't have permission for."""
        # Setup authentication with regular user
        self._setup_authenticated_user("regular_user", "user")

        # Setup golden repo manager to deny access
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=False
        )

        response = self.client.get("/api/repos/golden/private-repo/branches")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        data = response.json()
        assert "detail" in data
        assert "permission" in data["detail"].lower()

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_empty_repository(self, mock_golden_repo_manager):
        """Test listing branches for repository with no branches returns empty list gracefully."""
        # Setup authentication
        self._setup_authenticated_user("admin_user", "admin")

        # Setup golden repo manager to return empty branch list
        mock_golden_repo_manager.get_golden_repo_branches = AsyncMock(return_value=[])
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=True
        )

        response = self.client.get("/api/repos/golden/empty-repo/branches")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        assert data["repository_alias"] == "empty-repo"
        assert data["total_branches"] == 0
        assert data["default_branch"] is None
        assert data["branches"] == []

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_git_operation_error(self, mock_golden_repo_manager):
        """Test handling of git operation failures during branch listing."""
        # Setup authentication
        self._setup_authenticated_user("admin_user", "admin")

        # Setup golden repo manager to raise git error
        from code_indexer.server.repositories.golden_repo_manager import (
            GitOperationError,
        )

        mock_golden_repo_manager.get_golden_repo_branches = AsyncMock(
            side_effect=GitOperationError("Git operation failed")
        )
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=True
        )

        response = self.client.get("/api/repos/golden/broken-repo/branches")

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = response.json()
        assert "detail" in data
        assert "git operation" in data["detail"].lower()

    @patch("code_indexer.server.app.golden_repo_manager")
    def test_list_branches_performance_many_branches(self, mock_golden_repo_manager):
        """Test performance with repository containing many branches."""
        # Setup authentication
        self._setup_authenticated_user("admin_user", "admin")

        # Create many branches to test performance
        many_branches = []
        for i in range(150):  # Test with 150 branches
            branch = GoldenRepoBranchInfo(
                name=f"feature/branch-{i:03d}",
                is_default=(i == 0),
                last_commit_hash=f"hash{i:06d}",
                last_commit_timestamp=datetime.now(timezone.utc),
                last_commit_author=f"Author {i}",
                branch_type="feature",
            )
            many_branches.append(branch)

        mock_golden_repo_manager.get_golden_repo_branches = AsyncMock(
            return_value=many_branches
        )
        mock_golden_repo_manager.golden_repo_exists = MagicMock(return_value=True)
        mock_golden_repo_manager.user_can_access_golden_repo = MagicMock(
            return_value=True
        )

        response = self.client.get("/api/repos/golden/large-repo/branches")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_branches"] == 150
        assert len(data["branches"]) == 150

    def test_branch_classification_edge_cases(self):
        """Test branch classification with edge cases and unusual branch names."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        # Test various branch name patterns
        test_cases = [
            ("main", "main"),
            ("master", "main"),
            ("develop", "main"),
            ("development", "main"),
            ("feature/user-auth", "feature"),
            ("feat/new-api", "feature"),
            ("features/dashboard", "feature"),
            ("release/v1.2.3", "release"),
            ("rel/2024-q1", "release"),
            ("v1.0.0", "release"),
            ("hotfix/critical-bug", "hotfix"),
            ("fix/security-patch", "hotfix"),
            ("patch/urgent-fix", "hotfix"),
            ("bugfix/login-error", "hotfix"),
            ("experimental/new-tech", "other"),
            ("docs/api-guide", "other"),
            ("test/integration", "other"),
            ("chore/cleanup", "other"),
            ("", "other"),  # Empty string
            ("very-long-branch-name-that-exceeds-normal-expectations", "other"),
            ("branch-with-special.chars_and-dashes", "other"),
        ]

        for branch_name, expected_type in test_cases:
            result = classify_branch_type(branch_name)
            assert (
                result == expected_type
            ), f"Branch '{branch_name}' should be classified as '{expected_type}', got '{result}'"


class TestGoldenRepositoryBranchModels:
    """Test suite for golden repository branch data models."""

    def test_golden_repo_branch_info_model_validation(self):
        """Test that GoldenRepoBranchInfo model validates correctly."""
        from code_indexer.server.models.golden_repo_branch_models import (
            GoldenRepoBranchInfo,
        )

        # Valid branch info
        branch_info = GoldenRepoBranchInfo(
            name="main",
            is_default=True,
            last_commit_hash="abc123456789",
            last_commit_timestamp=datetime.now(timezone.utc),
            last_commit_author="John Doe",
            branch_type="main",
        )

        assert branch_info.name == "main"
        assert branch_info.is_default is True
        assert branch_info.branch_type == "main"
        assert len(branch_info.last_commit_hash) > 0

    def test_golden_repository_branches_response_model(self):
        """Test that GoldenRepositoryBranchesResponse model works correctly."""
        from code_indexer.server.models.golden_repo_branch_models import (
            GoldenRepoBranchInfo,
        )

        branch = GoldenRepoBranchInfo(
            name="main",
            is_default=True,
            last_commit_hash="abc123",
            last_commit_timestamp=datetime.now(timezone.utc),
            last_commit_author="Author",
            branch_type="main",
        )

        response = GoldenRepositoryBranchesResponse(
            repository_alias="test-repo",
            total_branches=1,
            default_branch="main",
            branches=[branch],
            retrieved_at=datetime.now(timezone.utc),
        )

        assert response.repository_alias == "test-repo"
        assert response.total_branches == 1
        assert response.default_branch == "main"
        assert len(response.branches) == 1

    def test_branch_info_optional_fields(self):
        """Test that optional fields in branch info work correctly."""
        from code_indexer.server.models.golden_repo_branch_models import (
            GoldenRepoBranchInfo,
        )

        # Branch info with minimal required fields
        branch_info = GoldenRepoBranchInfo(
            name="feature/test",
            is_default=False,
            last_commit_hash=None,  # Optional
            last_commit_timestamp=None,  # Optional
            last_commit_author=None,  # Optional
            branch_type=None,  # Optional
        )

        assert branch_info.name == "feature/test"
        assert branch_info.is_default is False
        assert branch_info.last_commit_hash is None
        assert branch_info.last_commit_timestamp is None
        assert branch_info.last_commit_author is None
        assert branch_info.branch_type is None


class TestBranchClassificationLogic:
    """Test suite for branch classification functionality."""

    def test_branch_classification_primary_branches(self):
        """Test classification of primary/main branches."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        primary_branches = ["main", "master", "develop", "development", "dev"]

        for branch in primary_branches:
            assert classify_branch_type(branch) == "main"

    def test_branch_classification_feature_branches(self):
        """Test classification of feature branches."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        feature_branches = [
            "feature/user-auth",
            "feat/api-redesign",
            "features/dashboard",
            "feature/integration-tests",
        ]

        for branch in feature_branches:
            assert classify_branch_type(branch) == "feature"

    def test_branch_classification_release_branches(self):
        """Test classification of release branches."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        release_branches = [
            "release/v1.2.3",
            "rel/2024-q1",
            "v1.0.0",
            "v2.1.0-beta",
            "release/milestone-1",
        ]

        for branch in release_branches:
            assert classify_branch_type(branch) == "release"

    def test_branch_classification_hotfix_branches(self):
        """Test classification of hotfix branches."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        hotfix_branches = [
            "hotfix/critical-bug",
            "fix/security-vulnerability",
            "patch/urgent-fix",
            "bugfix/login-error",
        ]

        for branch in hotfix_branches:
            assert classify_branch_type(branch) == "hotfix"

    def test_branch_classification_other_branches(self):
        """Test classification of miscellaneous branches."""
        from code_indexer.server.services.golden_repo_branch_service import (
            classify_branch_type,
        )

        other_branches = [
            "docs/api-documentation",
            "test/integration-suite",
            "chore/dependency-update",
            "experimental/new-framework",
            "random-branch-name",
        ]

        for branch in other_branches:
            assert classify_branch_type(branch) == "other"
