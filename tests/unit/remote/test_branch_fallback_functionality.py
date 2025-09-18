"""Tests for Branch Fallback Hierarchy Functionality.

Comprehensive test suite covering the actual functionality of branch fallback
hierarchy matching, git merge-base analysis, and parent branch detection.
"""

import subprocess
import pytest
from unittest.mock import Mock, AsyncMock
from pathlib import Path

from src.code_indexer.remote.repository_linking import (
    ExactBranchMatcher,
    BranchFallbackMatcher,
    RepositoryLink,
    RepositoryType,
)
from src.code_indexer.services.git_topology_service import GitTopologyService
from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryMatch as ClientRepositoryMatch,
    RepositoryDiscoveryResponse as ClientDiscoveryResponse,
)


class TestBranchFallbackFunctionality:
    """Test suite for actual branch fallback functionality."""

    @pytest.fixture
    def real_git_repo_with_branches(self, tmp_path):
        """Create a real git repository with complex branch structure."""

        # Initialize git repository
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=tmp_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True
        )

        # Create initial commit on master (default branch)
        (tmp_path / "README.md").write_text("# Main Repository")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True
        )

        # Create develop branch
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=tmp_path, check=True)
        (tmp_path / "develop.txt").write_text("Develop branch work")
        subprocess.run(["git", "add", "develop.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add develop branch work"], cwd=tmp_path, check=True
        )

        # Create feature branch from develop
        subprocess.run(
            ["git", "checkout", "-b", "feature/user-auth"],
            cwd=tmp_path,
            check=True,
        )
        (tmp_path / "auth.py").write_text("def authenticate(): pass")
        subprocess.run(["git", "add", "auth.py"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add authentication feature"],
            cwd=tmp_path,
            check=True,
        )

        return tmp_path

    @pytest.fixture
    def git_topology_service(self, real_git_repo_with_branches):
        """Create real GitTopologyService with the test repository."""
        return GitTopologyService(real_git_repo_with_branches)

    @pytest.fixture
    def fallback_matcher(self, git_topology_service):
        """Create BranchFallbackMatcher with real git service."""
        return BranchFallbackMatcher(git_topology_service)

    @pytest.fixture
    def sample_repositories_with_main_develop(self):
        """Sample repositories that have main and develop branches but no feature branches."""
        return [
            ClientRepositoryMatch(
                alias="repo-auth-user1",
                repository_type="activated",
                display_name="Authentication Service",
                description="User authentication and authorization service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "master"],
            ),
            ClientRepositoryMatch(
                alias="auth-service-golden",
                repository_type="golden",
                display_name="Authentication Service (Golden)",
                description="Golden repository for authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "master", "release/v1.0"],
            ),
        ]

    def test_branch_fallback_matcher_initialization(self, git_topology_service):
        """Test BranchFallbackMatcher initializes correctly."""
        matcher = BranchFallbackMatcher(git_topology_service)

        assert matcher.git_service == git_topology_service
        assert matcher.PRIORITY_BRANCHES == [
            "main",
            "master",
            "develop",
            "development",
            "release",
        ]

    def test_analyze_branch_ancestry_with_real_git(self, fallback_matcher):
        """Test branch ancestry analysis with real git repository."""
        # We're on feature/user-auth branch, should find ancestry with master and develop
        ancestry = fallback_matcher._analyze_branch_ancestry("feature/user-auth")

        # Should find merge-base with master and develop
        assert "master" in ancestry  # git creates master by default
        assert "develop" in ancestry

        # main won't be found because it doesn't exist in this repo (master is the default)
        assert "main" not in ancestry

    def test_prioritize_parent_branches_correct_order(self, fallback_matcher):
        """Test that parent branches are prioritized in correct order."""
        # Test with mixed branches
        ancestry = ["develop", "master", "release"]

        prioritized = fallback_matcher._prioritize_parent_branches(ancestry)

        # Should be ordered by priority: master before develop before release
        expected_order = ["master", "develop", "release"]
        assert prioritized == expected_order

    def test_prioritize_parent_branches_with_main_first(self, fallback_matcher):
        """Test that main branch has highest priority."""
        ancestry = ["develop", "main", "master", "release"]

        prioritized = fallback_matcher._prioritize_parent_branches(ancestry)

        # main should be first, then master, develop, release
        expected_order = ["main", "master", "develop", "release"]
        assert prioritized == expected_order

    def test_find_parent_branch_match_activated_priority(
        self, fallback_matcher, sample_repositories_with_main_develop
    ):
        """Test finding parent branch match prioritizes activated repositories."""
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=[sample_repositories_with_main_develop[1]],
            activated_repositories=[sample_repositories_with_main_develop[0]],
            total_matches=2,
        )

        # Look for develop branch match
        result = fallback_matcher._find_parent_branch_match(
            "develop", discovery_response
        )

        assert result is not None
        assert result.branch == "develop"
        assert result.alias == "repo-auth-user1"  # Activated repository should be first
        assert result.repository_type == RepositoryType.ACTIVATED

    def test_find_parent_branch_match_golden_fallback(self, fallback_matcher):
        """Test finding parent branch match falls back to golden repositories."""
        # Only golden repository available
        golden_only_repos = [
            ClientRepositoryMatch(
                alias="auth-service-golden",
                repository_type="golden",
                display_name="Authentication Service (Golden)",
                description="Golden repository for authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop"],
            )
        ]

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=golden_only_repos,
            activated_repositories=[],
            total_matches=1,
        )

        result = fallback_matcher._find_parent_branch_match("main", discovery_response)

        assert result is not None
        assert result.branch == "main"
        assert result.alias == "auth-service-golden"
        assert result.repository_type == RepositoryType.GOLDEN

    def test_find_parent_branch_match_no_match(
        self, fallback_matcher, sample_repositories_with_main_develop
    ):
        """Test finding parent branch match when branch doesn't exist."""
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/test-repo.git",
            normalized_url="https://github.com/company/test-repo.git",
            golden_repositories=[sample_repositories_with_main_develop[1]],
            activated_repositories=[sample_repositories_with_main_develop[0]],
            total_matches=2,
        )

        # Look for branch that doesn't exist in any repository
        result = fallback_matcher._find_parent_branch_match(
            "nonexistent", discovery_response
        )

        assert result is None

    def test_create_match_reason_format(self, fallback_matcher):
        """Test creation of match reason with correct format."""
        reason = fallback_matcher._create_match_reason("feature/user-auth", "develop")

        expected_reason = (
            "Exact branch 'feature/user-auth' not found. "
            "Fell back to parent branch 'develop' via merge-base analysis."
        )
        assert reason == expected_reason

    def test_find_fallback_branch_match_success(
        self,
        fallback_matcher,
        real_git_repo_with_branches,
        sample_repositories_with_main_develop,
    ):
        """Test successful fallback branch matching."""
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/test-repo.git",
            normalized_url="https://github.com/company/test-repo.git",
            golden_repositories=[sample_repositories_with_main_develop[1]],
            activated_repositories=[sample_repositories_with_main_develop[0]],
            total_matches=2,
        )

        # Should find fallback match for feature branch
        result = fallback_matcher.find_fallback_branch_match(
            real_git_repo_with_branches, discovery_response
        )

        assert result is not None
        assert result.branch in [
            "master",
            "develop",
        ]  # Should match one of the parent branches
        assert result.match_reason is not None
        assert "feature/user-auth" in result.match_reason
        assert "merge-base analysis" in result.match_reason
        assert result.parent_branch in ["master", "develop"]

    def test_find_fallback_branch_match_no_ancestry(self, git_topology_service):
        """Test fallback matching when no branch ancestry is found."""
        # Mock git service to return no merge-base results
        git_service_mock = Mock(spec=GitTopologyService)
        git_service_mock.get_current_branch.return_value = "orphan-branch"
        git_service_mock._get_merge_base.return_value = None

        fallback_matcher = BranchFallbackMatcher(git_service_mock)

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/test/repo.git",
            normalized_url="https://github.com/test/repo.git",
            golden_repositories=[],
            activated_repositories=[],
            total_matches=0,
        )

        result = fallback_matcher.find_fallback_branch_match(
            Path("/tmp"), discovery_response
        )

        assert result is None

    def test_find_fallback_branch_match_detached_head(self, git_topology_service):
        """Test fallback matching handles detached HEAD gracefully."""
        # Mock git service to simulate detached HEAD
        git_service_mock = Mock(spec=GitTopologyService)
        git_service_mock.get_current_branch.return_value = "detached-abc123"

        fallback_matcher = BranchFallbackMatcher(git_service_mock)

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/test/repo.git",
            normalized_url="https://github.com/test/repo.git",
            golden_repositories=[],
            activated_repositories=[],
            total_matches=0,
        )

        result = fallback_matcher.find_fallback_branch_match(
            Path("/tmp"), discovery_response
        )

        assert result is None


class TestExactBranchMatcherFallbackIntegration:
    """Test suite for ExactBranchMatcher fallback integration."""

    @pytest.fixture
    def mock_repository_linking_client(self):
        """Create mock repository linking client."""
        client = Mock(spec=RepositoryLinkingClient)
        client.discover_repositories = AsyncMock()
        client.server_url = "https://cidx.example.com"
        return client

    @pytest.fixture
    def mock_git_topology_service(self):
        """Create mock git topology service."""
        service = Mock(spec=GitTopologyService)
        return service

    @pytest.fixture
    def exact_branch_matcher(self, mock_repository_linking_client):
        """Create ExactBranchMatcher instance."""
        return ExactBranchMatcher(mock_repository_linking_client)

    @pytest.fixture
    def repositories_with_main_only(self):
        """Repositories that only have main branch, no feature branches."""
        return [
            ClientRepositoryMatch(
                alias="repo-auth-user1",
                repository_type="activated",
                display_name="Authentication Service",
                description="User authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop"],
            )
        ]

    @pytest.mark.asyncio
    async def test_exact_branch_matcher_with_fallback_success(
        self,
        exact_branch_matcher,
        mock_git_topology_service,
        repositories_with_main_only,
        tmp_path,
    ):
        """Test ExactBranchMatcher successfully falls back when exact match fails."""
        # Mock local branch detection - we're on feature branch
        mock_git_topology_service.get_current_branch.return_value = "feature/user-auth"

        # Mock merge-base analysis to find main as parent
        mock_git_topology_service._get_merge_base.side_effect = (
            lambda branch1, branch2: ("abc123" if branch2 == "main" else None)
        )

        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery - no exact match for feature branch
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=[],
            activated_repositories=repositories_with_main_only,
            total_matches=1,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            tmp_path, "https://github.com/company/auth-service.git"
        )

        # Should find fallback match
        assert result is not None
        assert result.branch == "main"  # Fell back to main branch
        assert result.alias == "repo-auth-user1"
        assert result.match_reason is not None
        assert "feature/user-auth" in result.match_reason
        assert "main" in result.match_reason
        assert result.parent_branch == "main"

    @pytest.mark.asyncio
    async def test_exact_branch_matcher_fallback_priority_activated_over_golden(
        self,
        exact_branch_matcher,
        mock_git_topology_service,
        tmp_path,
    ):
        """Test fallback prioritizes activated repositories over golden."""
        # Mock local branch detection
        mock_git_topology_service.get_current_branch.return_value = "feature/payments"

        # Mock merge-base analysis
        mock_git_topology_service._get_merge_base.side_effect = (
            lambda branch1, branch2: ("def456" if branch2 == "main" else None)
        )

        exact_branch_matcher.git_service = mock_git_topology_service

        # Both activated and golden repositories available with main branch
        mixed_repositories = [
            ClientRepositoryMatch(
                alias="payments-golden",  # Golden repository
                repository_type="golden",
                display_name="Payments Service (Golden)",
                description="Golden payments service",
                git_url="https://github.com/company/payments.git",
                available_branches=["main", "develop"],
            ),
            ClientRepositoryMatch(
                alias="payments-user1",  # Activated repository
                repository_type="activated",
                display_name="Payments Service",
                description="User payments service",
                git_url="https://github.com/company/payments.git",
                available_branches=["main", "develop"],
            ),
        ]

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/payments.git",
            normalized_url="https://github.com/company/payments.git",
            golden_repositories=[mixed_repositories[0]],
            activated_repositories=[mixed_repositories[1]],
            total_matches=2,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            tmp_path, "https://github.com/company/payments.git"
        )

        # Should prioritize activated repository in fallback
        assert result is not None
        assert result.branch == "main"
        assert result.alias == "payments-user1"  # Activated repository
        assert result.repository_type == RepositoryType.ACTIVATED

    @pytest.mark.asyncio
    async def test_exact_branch_matcher_no_fallback_match(
        self,
        exact_branch_matcher,
        mock_git_topology_service,
        tmp_path,
    ):
        """Test when neither exact nor fallback matching succeeds."""
        # Mock local branch detection
        mock_git_topology_service.get_current_branch.return_value = "feature/isolated"

        # Mock merge-base analysis to find no parents
        mock_git_topology_service._get_merge_base.return_value = None

        exact_branch_matcher.git_service = mock_git_topology_service

        # Repository with branches that don't match ancestry
        no_match_repositories = [
            ClientRepositoryMatch(
                alias="different-repo",
                repository_type="golden",
                display_name="Different Service",
                description="Unrelated service",
                git_url="https://github.com/company/different.git",
                available_branches=["master", "staging"],
            )
        ]

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/different.git",
            normalized_url="https://github.com/company/different.git",
            golden_repositories=no_match_repositories,
            activated_repositories=[],
            total_matches=1,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            tmp_path, "https://github.com/company/different.git"
        )

        # Should return None when no fallback match possible
        assert result is None


class TestRepositoryLinkEnhancedFields:
    """Test suite for enhanced RepositoryLink fields."""

    def test_repository_link_with_fallback_fields(self):
        """Test RepositoryLink with fallback-specific fields."""
        link = RepositoryLink(
            alias="test-repo-user1",
            git_url="https://github.com/test/repo.git",
            branch="main",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Test Repository",
            description="A test repository",
            access_level="read",
            match_reason="Exact branch 'feature/test' not found. Fell back to parent branch 'main' via merge-base analysis.",
            parent_branch="main",
        )

        assert link.match_reason is not None
        assert "merge-base analysis" in link.match_reason
        assert link.parent_branch == "main"

    def test_repository_link_without_fallback_fields(self):
        """Test RepositoryLink without fallback fields (exact match case)."""
        link = RepositoryLink(
            alias="test-repo-user1",
            git_url="https://github.com/test/repo.git",
            branch="feature/exact-match",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Test Repository",
            description="A test repository",
            access_level="read",
        )

        assert link.match_reason is None
        assert link.parent_branch is None
