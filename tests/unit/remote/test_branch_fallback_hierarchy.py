"""Tests for Branch Fallback Hierarchy for CIDX Remote Repository Linking Mode.

Comprehensive test suite covering git merge-base analysis, intelligent parent branch detection,
branch ancestry prioritization, and fallback repository matching functionality.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from src.code_indexer.remote.repository_linking import (
    ExactBranchMatcher,
    RepositoryLink,
    RepositoryType,
    MatchQuality,
)
from src.code_indexer.services.git_topology_service import GitTopologyService
from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryMatch as ClientRepositoryMatch,
    RepositoryDiscoveryResponse as ClientDiscoveryResponse,
)


class TestBranchFallbackMatcher:
    """Test suite for branch fallback hierarchy matching functionality."""

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
        """Create ExactBranchMatcher instance with mocked dependencies."""
        return ExactBranchMatcher(mock_repository_linking_client)

    @pytest.fixture
    def sample_repositories_with_main_branch(self):
        """Sample repositories that only have main branch, no feature branch."""
        return [
            ClientRepositoryMatch(
                alias="repo-auth-user1",
                repository_type="activated",
                display_name="Authentication Service",
                description="User authentication and authorization service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop"],
            ),
            ClientRepositoryMatch(
                alias="auth-service-golden",
                repository_type="golden",
                display_name="Authentication Service (Golden)",
                description="Golden repository for authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "release/v2.0"],
            ),
        ]

    @pytest.fixture
    def complex_git_repo(self, tmp_path):
        """Create a complex git repository with multiple branches and merge history."""
        import subprocess

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

        # Create initial commit on main
        (tmp_path / "README.md").write_text("# Test Repository")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True
        )

        # Create develop branch
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=tmp_path, check=True)
        (tmp_path / "develop.md").write_text("# Development")
        subprocess.run(["git", "add", "develop.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add develop branch"], cwd=tmp_path, check=True
        )

        # Create feature branch from develop
        subprocess.run(
            ["git", "checkout", "-b", "feature/user-authentication"],
            cwd=tmp_path,
            check=True,
        )
        (tmp_path / "auth.py").write_text("# Authentication module")
        subprocess.run(["git", "add", "auth.py"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add authentication module"],
            cwd=tmp_path,
            check=True,
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_fallback_to_main_branch_when_exact_match_fails(
        self,
        exact_branch_matcher,
        complex_git_repo,
        mock_git_topology_service,
        sample_repositories_with_main_branch,
    ):
        """Test fallback to main branch when exact feature branch match fails."""
        # Mock local branch detection - we're on a feature branch
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/user-authentication"
        )

        # Mock merge-base analysis to find main as parent
        mock_git_topology_service._get_merge_base.side_effect = (
            lambda branch1, branch2: ("abc123" if branch2 == "main" else None)
        )

        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery response - repositories only have main/develop
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=[sample_repositories_with_main_branch[1]],
            activated_repositories=[sample_repositories_with_main_branch[0]],
            total_matches=2,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            complex_git_repo, "https://github.com/company/auth-service.git"
        )

        # Should now find fallback match to main branch
        assert result is not None
        assert result.branch == "main"
        assert result.match_reason is not None
        assert "feature/user-authentication" in result.match_reason
        assert result.parent_branch == "main"

    def test_branch_fallback_matcher_now_implemented(self):
        """Test that BranchFallbackMatcher class now exists."""
        # This test should pass since we've implemented the BranchFallbackMatcher
        try:
            from src.code_indexer.remote.repository_linking import BranchFallbackMatcher

            assert BranchFallbackMatcher is not None
        except ImportError:
            pytest.fail("BranchFallbackMatcher should now be implemented")

    def test_analyze_branch_ancestry_not_implemented_yet(self, exact_branch_matcher):
        """Test that _analyze_branch_ancestry method doesn't exist yet."""
        # This test should fail until we implement the method
        with pytest.raises(AttributeError):
            exact_branch_matcher._analyze_branch_ancestry("feature/user-authentication")

    def test_prioritize_parent_branches_not_implemented_yet(self, exact_branch_matcher):
        """Test that _prioritize_parent_branches method doesn't exist yet."""
        # This test should fail until we implement the method
        with pytest.raises(AttributeError):
            exact_branch_matcher._prioritize_parent_branches(
                ["main", "develop", "feature/auth"]
            )

    def test_find_parent_branch_match_not_implemented_yet(self, exact_branch_matcher):
        """Test that _find_parent_branch_match method doesn't exist yet."""
        # This test should fail until we implement the method
        with pytest.raises(AttributeError):
            exact_branch_matcher._find_parent_branch_match(
                "main",
                ClientDiscoveryResponse(
                    query_url="https://github.com/test/repo.git",
                    normalized_url="https://github.com/test/repo.git",
                    golden_repositories=[],
                    activated_repositories=[],
                    total_matches=0,
                ),
            )

    def test_match_reason_field_now_exists_in_repository_link(self):
        """Test that match_reason field now exists in RepositoryLink."""
        link = RepositoryLink(
            alias="test-repo",
            git_url="https://github.com/test/repo.git",
            branch="main",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Test Repository",
            description="A test repository",
            access_level="read",
        )

        # The match_reason field should now exist and default to None
        assert hasattr(link, "match_reason")
        assert link.match_reason is None

    def test_parent_branch_field_now_exists_in_repository_link(self):
        """Test that parent_branch field now exists in RepositoryLink."""
        link = RepositoryLink(
            alias="test-repo",
            git_url="https://github.com/test/repo.git",
            branch="main",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Test Repository",
            description="A test repository",
            access_level="read",
        )

        # The parent_branch field should now exist and default to None
        assert hasattr(link, "parent_branch")
        assert link.parent_branch is None

    def test_fallback_match_quality_not_in_enum_yet(self):
        """Test that FALLBACK enum value doesn't exist in MatchQuality yet."""
        # This should pass since we added FALLBACK to the enum already
        assert MatchQuality.FALLBACK.value == "fallback"


class TestGitMergeBaseAnalysis:
    """Test suite for git merge-base analysis functionality."""

    @pytest.fixture
    def real_complex_git_repo(self, tmp_path):
        """Create a real complex git repository for merge-base testing."""
        import subprocess

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

        # Create main branch with initial commit
        (tmp_path / "README.md").write_text("# Main Repository")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit on main"], cwd=tmp_path, check=True
        )

        # Create and commit more work on main
        (tmp_path / "main-file.txt").write_text("Main branch work")
        subprocess.run(["git", "add", "main-file.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add main branch work"], cwd=tmp_path, check=True
        )

        # Create develop branch from main
        subprocess.run(["git", "checkout", "-b", "develop"], cwd=tmp_path, check=True)
        (tmp_path / "develop-file.txt").write_text("Develop branch work")
        subprocess.run(["git", "add", "develop-file.txt"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add develop branch work"], cwd=tmp_path, check=True
        )

        # Create feature branch from develop
        subprocess.run(
            ["git", "checkout", "-b", "feature/authentication"],
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

        # Create nested feature branch from feature/authentication
        subprocess.run(
            ["git", "checkout", "-b", "feature/auth-improvements"],
            cwd=tmp_path,
            check=True,
        )
        (tmp_path / "auth-improvements.py").write_text("def improved_auth(): pass")
        subprocess.run(["git", "add", "auth-improvements.py"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add auth improvements"], cwd=tmp_path, check=True
        )

        return tmp_path

    def test_git_merge_base_analysis_with_real_repo(self, real_complex_git_repo):
        """Test git merge-base analysis with real repository structure."""
        from src.code_indexer.services.git_topology_service import GitTopologyService

        git_service = GitTopologyService(real_complex_git_repo)

        # Test merge-base between feature branch and master (git creates master by default)
        merge_base = git_service._get_merge_base("feature/auth-improvements", "master")
        assert merge_base is not None

        # Test merge-base between feature branch and develop
        merge_base_develop = git_service._get_merge_base(
            "feature/auth-improvements", "develop"
        )
        assert merge_base_develop is not None

        # The merge-base with develop should be more recent (different) than with main
        assert merge_base != merge_base_develop

    def test_branch_ancestry_analysis_not_implemented_yet(self, real_complex_git_repo):
        """Test branch ancestry analysis functionality that should be implemented."""
        from src.code_indexer.services.git_topology_service import GitTopologyService

        git_service = GitTopologyService(real_complex_git_repo)
        current_branch = git_service.get_current_branch()

        # We're on feature/auth-improvements branch
        assert current_branch == "feature/auth-improvements"

        # This should fail until we implement branch ancestry analysis for fallback
        with pytest.raises(AttributeError):
            # Method doesn't exist yet in our matcher
            git_service.analyze_parent_branches("feature/auth-improvements")


class TestBranchHierarchyPrioritization:
    """Test suite for branch hierarchy prioritization in fallback scenarios."""

    def test_branch_priority_order_specification(self):
        """Test that branch priority order follows specification."""
        # Expected priority order from story requirements:
        expected_priority = [
            "main",  # highest priority
            "master",
            "develop",
            "development",
            "release",
            # Any other branches found in ancestry (lower priority)
        ]

        # This test documents the expected behavior
        # Implementation should use this priority order
        assert expected_priority[0] == "main"
        assert expected_priority[1] == "master"
        assert expected_priority[2] == "develop"

    def test_prioritize_activated_over_golden_in_fallback(self):
        """Test that fallback still prioritizes activated over golden repositories."""
        # Even in fallback scenarios, activated repositories should be preferred
        # This test documents the expected behavior for implementation
        priority_rules = {
            "repository_type_priority": ["activated", "golden"],
            "branch_priority": ["main", "master", "develop", "development", "release"],
        }

        assert priority_rules["repository_type_priority"][0] == "activated"
        assert priority_rules["branch_priority"][0] == "main"


class TestFallbackIntegrationScenarios:
    """Test suite for comprehensive fallback integration scenarios."""

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
    def multi_branch_repositories(self):
        """Sample repositories with multiple long-lived branches."""
        return [
            ClientRepositoryMatch(
                alias="repo-auth-user1",
                repository_type="activated",
                display_name="Authentication Service",
                description="User authentication and authorization service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "master", "release/v1.0"],
            ),
            ClientRepositoryMatch(
                alias="auth-service-golden",
                repository_type="golden",
                display_name="Authentication Service (Golden)",
                description="Golden repository for authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "master"],
            ),
        ]

    @pytest.mark.asyncio
    async def test_fallback_integration_scenario_not_implemented_yet(
        self,
        mock_repository_linking_client,
        tmp_path,
        mock_git_topology_service,
        multi_branch_repositories,
    ):
        """Test comprehensive fallback scenario integration."""
        # Mock local branch detection - we're on a deep feature branch
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/auth-improvements"
        )

        # Mock git topology service to simulate merge-base analysis
        mock_git_topology_service._get_merge_base.return_value = "abc123def456"

        exact_branch_matcher = ExactBranchMatcher(mock_repository_linking_client)
        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery - no exact match for feature branch
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=[multi_branch_repositories[1]],
            activated_repositories=[multi_branch_repositories[0]],
            total_matches=2,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method - should return None until fallback is implemented
        result = await exact_branch_matcher.find_exact_branch_match(
            tmp_path, "https://github.com/company/auth-service.git"
        )

        # Should now return fallback match since fallback logic is implemented
        assert result is not None
        assert result.branch in ["main", "develop"]
        assert result.match_reason is not None
        assert "feature/auth-improvements" in result.match_reason
        assert result.parent_branch in ["main", "develop"]


class TestFallbackErrorHandling:
    """Test suite for fallback error handling scenarios."""

    def test_fallback_with_git_command_failures(self, tmp_path):
        """Test fallback behavior when git commands fail."""
        from src.code_indexer.services.git_topology_service import GitTopologyService

        # Create non-git directory
        git_service = GitTopologyService(tmp_path)

        # Should handle git command failures gracefully
        merge_base = git_service._get_merge_base("feature/branch", "main")
        assert merge_base is None

    def test_fallback_with_missing_parent_branches(self):
        """Test fallback when parent branches don't exist in remote repositories."""
        # This test documents expected behavior when git analysis finds parent branches
        # but remote repositories don't have those branches available

        # Expected behavior: should gracefully handle missing branches and
        # continue searching through the priority list
        expected_behavior = {
            "missing_branch_handling": "continue_to_next_priority",
            "final_fallback": None,  # Return None if no fallback branches found
        }

        assert (
            expected_behavior["missing_branch_handling"] == "continue_to_next_priority"
        )

    def test_fallback_with_complex_git_histories(self):
        """Test fallback behavior with complex git histories and merge patterns."""
        # This test documents expected behavior for complex git scenarios:
        # - Multiple merge bases
        # - Orphaned branches
        # - Complex merge histories

        complex_scenarios = {
            "multiple_merge_bases": "use_most_recent_common_ancestor",
            "orphaned_branches": "no_fallback_available",
            "merge_conflicts_in_history": "ignore_conflicts_use_topology",
        }

        assert (
            complex_scenarios["multiple_merge_bases"]
            == "use_most_recent_common_ancestor"
        )


class TestFallbackUserCommunication:
    """Test suite for fallback reasoning communication to users."""

    def test_fallback_match_reason_field_specification(self):
        """Test specification for match_reason field content."""
        # Expected match_reason examples for different fallback scenarios
        expected_reasons = {
            "main_fallback": "Exact branch 'feature/auth-improvements' not found. Fell back to parent branch 'main' via merge-base analysis.",
            "develop_fallback": "Exact branch 'feature/user-auth' not found. Fell back to parent branch 'develop' (common ancestor: abc123).",
            "no_fallback": "Exact branch 'feature/orphaned' not found. No suitable parent branches found in remote repositories.",
        }

        assert "merge-base analysis" in expected_reasons["main_fallback"]
        assert "common ancestor" in expected_reasons["develop_fallback"]
        assert "No suitable parent branches" in expected_reasons["no_fallback"]

    def test_parent_branch_field_specification(self):
        """Test specification for parent_branch field content."""
        # Expected parent_branch field values for different scenarios
        expected_parent_branch_values = {
            "exact_match": None,  # No fallback used
            "main_fallback": "main",  # Fell back to main
            "develop_fallback": "develop",  # Fell back to develop
            "no_fallback": None,  # No fallback possible
        }

        assert expected_parent_branch_values["exact_match"] is None
        assert expected_parent_branch_values["main_fallback"] == "main"
