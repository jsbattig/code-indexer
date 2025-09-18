"""Tests for Exact Branch Matching for CIDX Remote Repository Linking Mode.

Comprehensive test suite covering local branch detection, exact branch matching priority,
repository discovery integration, and match confirmation/storage functionality.
"""

import json
import pytest
from unittest.mock import Mock, AsyncMock

from src.code_indexer.remote.repository_linking import (
    ExactBranchMatcher,
    RepositoryLink,
    RepositoryMatch,
    RepositoryDiscoveryResponse,
    RepositoryLinkingError,
    BranchMatchingError,
    NoMatchFoundError,
)
from src.code_indexer.services.git_topology_service import GitTopologyService
from src.code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryMatch as ClientRepositoryMatch,
    RepositoryDiscoveryResponse as ClientDiscoveryResponse,
)


class TestExactBranchMatcher:
    """Test suite for exact branch matching functionality."""

    @pytest.fixture
    def sample_git_repo(self, tmp_path):
        """Create a sample git repository for testing."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        # Create basic git structure
        (git_dir / "HEAD").write_text("ref: refs/heads/feature/auth-improvements\n")
        refs_heads = git_dir / "refs" / "heads"
        refs_heads.mkdir(parents=True)
        (refs_heads / "feature").mkdir()
        (refs_heads / "main").touch()
        (refs_heads / "feature" / "auth-improvements").touch()

        return tmp_path

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
    def sample_activated_repositories(self):
        """Sample activated repositories with different branches."""
        return [
            ClientRepositoryMatch(
                alias="repo-auth-user1",
                repository_type="activated",
                display_name="Authentication Service",
                description="User authentication and authorization service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=["main", "develop", "feature/auth-improvements"],
            ),
            ClientRepositoryMatch(
                alias="repo-payment-user1",
                repository_type="activated",
                display_name="Payment Service",
                description="Payment processing service",
                git_url="https://github.com/company/payment-service.git",
                available_branches=["main", "develop", "feature/payment-gateway"],
            ),
        ]

    @pytest.fixture
    def sample_golden_repositories(self):
        """Sample golden repositories with different branches."""
        return [
            ClientRepositoryMatch(
                alias="auth-service-golden",
                repository_type="golden",
                display_name="Authentication Service (Golden)",
                description="Golden repository for authentication service",
                git_url="https://github.com/company/auth-service.git",
                available_branches=[
                    "main",
                    "develop",
                    "feature/auth-improvements",
                    "release/v2.0",
                ],
            ),
            ClientRepositoryMatch(
                alias="analytics-service-golden",
                repository_type="golden",
                display_name="Analytics Service (Golden)",
                description="Golden repository for analytics service",
                git_url="https://github.com/company/analytics-service.git",
                available_branches=["main", "develop", "feature/reporting"],
            ),
        ]

    def test_exact_branch_matcher_initialization(self, mock_repository_linking_client):
        """Test ExactBranchMatcher initializes correctly."""
        from src.code_indexer.remote.repository_linking import ExactBranchMatcher

        matcher = ExactBranchMatcher(mock_repository_linking_client)

        assert matcher.repository_client == mock_repository_linking_client
        assert matcher.git_service is None  # Should be initialized on first use

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_with_activated_repository_priority(
        self,
        exact_branch_matcher,
        sample_git_repo,
        mock_git_topology_service,
        sample_activated_repositories,
        sample_golden_repositories,
    ):
        """Test exact branch matching prioritizes activated repositories."""
        # Mock local branch detection
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/auth-improvements"
        )
        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery response
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=sample_golden_repositories,
            activated_repositories=sample_activated_repositories,
            total_matches=4,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            sample_git_repo, "https://github.com/company/auth-service.git"
        )

        # Should prioritize activated repository over golden
        assert result is not None
        assert result.alias == "repo-auth-user1"  # Activated repository
        assert result.branch == "feature/auth-improvements"
        assert result.repository_type.value == "activated"

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_with_golden_repository_fallback(
        self,
        exact_branch_matcher,
        sample_git_repo,
        mock_git_topology_service,
        sample_golden_repositories,
    ):
        """Test exact branch matching falls back to golden repositories."""
        # Mock local branch detection
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/auth-improvements"
        )
        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery response with only golden repositories
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=sample_golden_repositories,
            activated_repositories=[],
            total_matches=2,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            sample_git_repo, "https://github.com/company/auth-service.git"
        )

        # Should find golden repository match
        assert result is not None
        assert result.alias == "auth-service-golden"
        assert result.branch == "feature/auth-improvements"
        assert result.repository_type.value == "golden"

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_no_matching_branch_with_fallback(
        self,
        exact_branch_matcher,
        sample_git_repo,
        mock_git_topology_service,
        sample_activated_repositories,
    ):
        """Test exact branch matching when no repositories have the exact branch but fallback succeeds."""
        # Mock local branch detection with branch not in any repository
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/non-existent-branch"
        )

        # Mock merge-base analysis to find main as parent
        mock_git_topology_service._get_merge_base.side_effect = (
            lambda branch1, branch2: ("abc123" if branch2 == "main" else None)
        )

        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery response
        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/auth-service.git",
            normalized_url="https://github.com/company/auth-service.git",
            golden_repositories=[],
            activated_repositories=sample_activated_repositories,
            total_matches=2,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            sample_git_repo, "https://github.com/company/auth-service.git"
        )

        # Should find fallback match to main branch
        assert result is not None
        assert result.branch == "main"  # Fell back to main branch
        assert result.match_reason is not None
        assert "feature/non-existent-branch" in result.match_reason
        assert "main" in result.match_reason
        assert result.parent_branch == "main"

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_no_fallback_possible(
        self,
        exact_branch_matcher,
        sample_git_repo,
        mock_git_topology_service,
        sample_activated_repositories,
    ):
        """Test exact branch matching when no fallback is possible."""
        # Mock local branch detection with branch not in any repository
        mock_git_topology_service.get_current_branch.return_value = (
            "feature/completely-isolated"
        )

        # Mock merge-base analysis to find no parents
        mock_git_topology_service._get_merge_base.return_value = None

        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock repository discovery response - repositories without main/develop
        repositories_without_common_branches = [
            ClientRepositoryMatch(
                alias="isolated-repo",
                repository_type="golden",
                display_name="Isolated Service",
                description="Service with different branching model",
                git_url="https://github.com/company/isolated.git",
                available_branches=["trunk", "staging"],  # No main, develop, or master
            )
        ]

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/isolated.git",
            normalized_url="https://github.com/company/isolated.git",
            golden_repositories=repositories_without_common_branches,
            activated_repositories=[],
            total_matches=1,
        )
        exact_branch_matcher.repository_client.discover_repositories.return_value = (
            discovery_response
        )

        # Execute the method
        result = await exact_branch_matcher.find_exact_branch_match(
            sample_git_repo, "https://github.com/company/isolated.git"
        )

        # Should return None when no exact match and no fallback possible
        assert result is None

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_detached_head_state(
        self,
        exact_branch_matcher,
        sample_git_repo,
        mock_git_topology_service,
        sample_activated_repositories,
    ):
        """Test exact branch matching handles detached HEAD state gracefully."""
        # Mock detached HEAD state
        mock_git_topology_service.get_current_branch.return_value = "detached-abc123"
        exact_branch_matcher.git_service = mock_git_topology_service

        # Execute the method - should raise BranchMatchingError for detached HEAD
        with pytest.raises(BranchMatchingError, match="Unable to detect local branch"):
            await exact_branch_matcher.find_exact_branch_match(
                sample_git_repo, "https://github.com/company/auth-service.git"
            )

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_git_error_handling(
        self, exact_branch_matcher, sample_git_repo, mock_git_topology_service
    ):
        """Test exact branch matching handles git errors gracefully."""
        # Mock git service error
        mock_git_topology_service.get_current_branch.return_value = None
        exact_branch_matcher.git_service = mock_git_topology_service

        # Execute the method - should raise BranchMatchingError when git returns None
        with pytest.raises(BranchMatchingError, match="Unable to detect local branch"):
            await exact_branch_matcher.find_exact_branch_match(
                sample_git_repo, "https://github.com/company/auth-service.git"
            )

    @pytest.mark.asyncio
    async def test_find_exact_branch_match_network_error_handling(
        self, exact_branch_matcher, sample_git_repo, mock_git_topology_service
    ):
        """Test exact branch matching handles network errors gracefully."""
        # Mock local branch detection
        mock_git_topology_service.get_current_branch.return_value = "main"
        exact_branch_matcher.git_service = mock_git_topology_service

        # Mock network error during repository discovery
        from src.code_indexer.api_clients.base_client import NetworkError

        exact_branch_matcher.repository_client.discover_repositories.side_effect = (
            NetworkError("Connection failed")
        )

        # Execute the method - should raise RepositoryLinkingError for network issues
        with pytest.raises(
            RepositoryLinkingError, match="Network error during repository discovery"
        ):
            await exact_branch_matcher.find_exact_branch_match(
                sample_git_repo, "https://github.com/company/auth-service.git"
            )

    def test_filter_exact_matches_activated_priority(
        self,
        exact_branch_matcher,
        sample_activated_repositories,
        sample_golden_repositories,
    ):
        """Test filtering exact matches prioritizes activated repositories."""
        target_branch = "feature/auth-improvements"

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/test-repo.git",
            normalized_url="https://github.com/company/test-repo.git",
            golden_repositories=sample_golden_repositories,
            activated_repositories=sample_activated_repositories,
            total_matches=4,
        )

        # Execute the method
        result = exact_branch_matcher._filter_exact_matches(
            discovery_response, target_branch
        )

        # Should return both matches but activated should have higher priority (lower number)
        assert len(result) == 2
        assert (
            result[0].repository_type.value == "activated"
        )  # First should be activated
        assert result[1].repository_type.value == "golden"  # Second should be golden
        assert result[0].priority < result[1].priority  # Activated has higher priority

    def test_filter_exact_matches_golden_only(
        self, exact_branch_matcher, sample_golden_repositories
    ):
        """Test filtering exact matches with only golden repositories."""
        target_branch = "feature/auth-improvements"

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/test-repo.git",
            normalized_url="https://github.com/company/test-repo.git",
            golden_repositories=sample_golden_repositories,
            activated_repositories=[],
            total_matches=2,
        )

        # Execute the method
        result = exact_branch_matcher._filter_exact_matches(
            discovery_response, target_branch
        )

        # Should return only the golden repository that has the target branch
        assert len(result) == 1
        assert result[0].repository_type.value == "golden"
        assert result[0].branch == target_branch

    def test_filter_exact_matches_no_matches(
        self, exact_branch_matcher, sample_activated_repositories
    ):
        """Test filtering exact matches when no repositories have the target branch."""
        target_branch = "feature/non-existent-branch"

        discovery_response = ClientDiscoveryResponse(
            query_url="https://github.com/company/test-repo.git",
            normalized_url="https://github.com/company/test-repo.git",
            golden_repositories=[],
            activated_repositories=sample_activated_repositories,
            total_matches=2,
        )

        # Execute the method
        result = exact_branch_matcher._filter_exact_matches(
            discovery_response, target_branch
        )

        # Should return empty list when no repositories have the target branch
        assert len(result) == 0

    def test_select_best_match_single_activated(self, exact_branch_matcher):
        """Test selecting best match with single activated repository."""
        from src.code_indexer.remote.repository_linking import (
            RepositoryType,
            MatchQuality,
        )

        exact_matches = [
            RepositoryMatch(
                alias="repo-auth-user1",
                repository_type=RepositoryType.ACTIVATED,
                branch="feature/auth-improvements",
                match_quality=MatchQuality.EXACT,
                priority=1,
                git_url="https://github.com/test/repo.git",
                display_name="Test Repo",
                description="Test repository",
                available_branches=["main", "feature/auth-improvements"],
                last_updated="2025-01-15T10:00:00Z",
                access_level="read",
            )
        ]

        # Execute the method
        result = exact_branch_matcher._select_best_match(exact_matches)

        # Should return the single match
        assert result is not None
        assert result.alias == "repo-auth-user1"
        assert result.repository_type == RepositoryType.ACTIVATED

    def test_select_best_match_multiple_activated(self, exact_branch_matcher):
        """Test selecting best match with multiple activated repositories."""
        from src.code_indexer.remote.repository_linking import (
            RepositoryType,
            MatchQuality,
        )

        exact_matches = [
            RepositoryMatch(
                alias="repo-auth-user2",
                repository_type=RepositoryType.ACTIVATED,
                branch="feature/auth-improvements",
                match_quality=MatchQuality.EXACT,
                priority=1,
                git_url="https://github.com/test/repo2.git",
                display_name="Test Repo 2",
                description="Test repository 2",
                available_branches=["main", "feature/auth-improvements"],
                last_updated="2025-01-15T11:00:00Z",
                access_level="read",
            ),
            RepositoryMatch(
                alias="repo-auth-user1",
                repository_type=RepositoryType.ACTIVATED,
                branch="feature/auth-improvements",
                match_quality=MatchQuality.EXACT,
                priority=1,
                git_url="https://github.com/test/repo1.git",
                display_name="Test Repo 1",
                description="Test repository 1",
                available_branches=["main", "feature/auth-improvements"],
                last_updated="2025-01-15T10:00:00Z",
                access_level="read",
            ),
        ]

        # Execute the method
        result = exact_branch_matcher._select_best_match(exact_matches)

        # Should return the first match (both have same priority)
        assert result is not None
        assert result.alias == "repo-auth-user2"

    def test_select_best_match_golden_fallback(self, exact_branch_matcher):
        """Test selecting best match falls back to golden repositories."""
        from src.code_indexer.remote.repository_linking import (
            RepositoryType,
            MatchQuality,
        )

        exact_matches = [
            RepositoryMatch(
                alias="auth-service-golden",
                repository_type=RepositoryType.GOLDEN,
                branch="feature/auth-improvements",
                match_quality=MatchQuality.EXACT,
                priority=2,
                git_url="https://github.com/test/auth-service.git",
                display_name="Auth Service Golden",
                description="Golden auth service repository",
                available_branches=["main", "feature/auth-improvements"],
                last_updated="2025-01-15T10:00:00Z",
                access_level="read",
            )
        ]

        # Execute the method
        result = exact_branch_matcher._select_best_match(exact_matches)

        # Should return the golden repository match
        assert result is not None
        assert result.alias == "auth-service-golden"
        assert result.repository_type == RepositoryType.GOLDEN

    def test_select_best_match_empty_list(self, exact_branch_matcher):
        """Test selecting best match with empty list returns None."""
        # Execute the method
        result = exact_branch_matcher._select_best_match([])

        # Should return None for empty list
        assert result is None


class TestRepositoryLinkStorage:
    """Test suite for repository link storage and retrieval."""

    @pytest.fixture
    def sample_repository_link(self):
        """Sample repository link for testing."""
        from src.code_indexer.remote.repository_linking import RepositoryType

        return RepositoryLink(
            alias="repo-auth-user1",
            git_url="https://github.com/company/auth-service.git",
            branch="feature/auth-improvements",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Auth Service",
            description="Authentication service repository",
            access_level="read",
        )

    def test_store_repository_link(self, tmp_path, sample_repository_link):
        """Test storing repository link in remote configuration."""
        from src.code_indexer.remote.repository_linking import store_repository_link

        store_repository_link(tmp_path, sample_repository_link)

        # Verify configuration file was created
        config_path = tmp_path / ".code-indexer" / ".remote-config"
        assert config_path.exists()

        # Verify configuration content
        with open(config_path, "r") as f:
            config_data = json.load(f)

        assert config_data["mode"] == "remote"
        assert config_data["repository_link"]["alias"] == "repo-auth-user1"
        assert config_data["repository_link"]["branch"] == "feature/auth-improvements"
        assert config_data["repository_link"]["repository_type"] == "activated"

    def test_load_repository_link(self, tmp_path, sample_repository_link):
        """Test loading repository link from remote configuration."""
        from src.code_indexer.remote.repository_linking import (
            store_repository_link,
            load_repository_link,
        )

        # Store first
        store_repository_link(tmp_path, sample_repository_link)

        # Then load
        loaded_link = load_repository_link(tmp_path)

        assert loaded_link is not None
        assert loaded_link.alias == sample_repository_link.alias
        assert loaded_link.branch == sample_repository_link.branch
        assert loaded_link.git_url == sample_repository_link.git_url
        assert loaded_link.repository_type == sample_repository_link.repository_type

    def test_load_repository_link_not_found(self, tmp_path):
        """Test loading repository link when configuration doesn't exist."""
        from src.code_indexer.remote.repository_linking import load_repository_link

        # Should return None when config doesn't exist
        result = load_repository_link(tmp_path)
        assert result is None

    def test_repository_link_configuration_format(
        self, tmp_path, sample_repository_link
    ):
        """Test repository link is stored in correct configuration format."""
        from src.code_indexer.remote.repository_linking import store_repository_link

        store_repository_link(tmp_path, sample_repository_link)

        config_path = tmp_path / ".code-indexer" / ".remote-config"
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # Verify complete structure
        assert "mode" in config_data
        assert "repository_link" in config_data

        link_data = config_data["repository_link"]
        required_fields = [
            "alias",
            "git_url",
            "branch",
            "repository_type",
            "server_url",
            "linked_at",
            "display_name",
            "description",
            "access_level",
        ]

        for field in required_fields:
            assert field in link_data, f"Missing required field: {field}"


class TestBranchMatchingIntegration:
    """Integration tests for branch matching with real git operations."""

    @pytest.fixture
    def real_git_repo(self, tmp_path):
        """Create a real git repository for integration testing."""
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

        # Create initial commit
        (tmp_path / "README.md").write_text("# Test Repository")
        subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True
        )

        # Create and switch to feature branch
        subprocess.run(
            ["git", "checkout", "-b", "feature/auth-improvements"],
            cwd=tmp_path,
            check=True,
        )

        return tmp_path

    @pytest.mark.asyncio
    async def test_exact_branch_matching_with_real_git(self, real_git_repo):
        """Test exact branch matching with real GitTopologyService."""
        from src.code_indexer.services.git_topology_service import GitTopologyService
        from src.code_indexer.remote.repository_linking import ExactBranchMatcher

        git_service = GitTopologyService(real_git_repo)
        current_branch = git_service.get_current_branch()

        # Verify we can detect the current branch
        assert current_branch == "feature/auth-improvements"

        # Create mock repository client
        mock_client = Mock(spec=RepositoryLinkingClient)
        mock_client.server_url = "https://cidx.example.com"

        # Create matcher and verify it can be initialized with real git
        matcher = ExactBranchMatcher(mock_client)
        matcher.git_service = git_service

        # Test branch detection
        detected_branch = matcher._detect_local_branch()
        assert detected_branch == "feature/auth-improvements"

    def test_git_topology_service_detached_head(self, real_git_repo):
        """Test GitTopologyService handles detached HEAD state."""
        import subprocess
        from src.code_indexer.services.git_topology_service import GitTopologyService

        # Create detached HEAD state
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=real_git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        commit_hash = result.stdout.strip()

        subprocess.run(["git", "checkout", commit_hash], cwd=real_git_repo, check=True)

        git_service = GitTopologyService(real_git_repo)
        current_branch = git_service.get_current_branch()

        # Should return detached-<hash> format
        assert current_branch is not None
        assert current_branch.startswith("detached-")

    def test_git_topology_service_no_git_repo(self, tmp_path):
        """Test GitTopologyService handles non-git directories gracefully."""
        from src.code_indexer.services.git_topology_service import GitTopologyService

        git_service = GitTopologyService(tmp_path)
        current_branch = git_service.get_current_branch()

        # Should return None for non-git directories
        assert current_branch is None


class TestExactBranchMatchingExceptions:
    """Test suite for exception handling in exact branch matching."""

    def test_repository_linking_error_inheritance(self):
        """Test RepositoryLinkingError exception inheritance."""
        from src.code_indexer.remote.repository_linking import RepositoryLinkingError

        error = RepositoryLinkingError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_branch_matching_error_inheritance(self):
        """Test BranchMatchingError exception inheritance."""
        from src.code_indexer.remote.repository_linking import (
            BranchMatchingError,
            RepositoryLinkingError,
        )

        error = BranchMatchingError("Branch matching failed")
        assert isinstance(error, RepositoryLinkingError)
        assert isinstance(error, Exception)
        assert str(error) == "Branch matching failed"

    def test_no_match_found_error_inheritance(self):
        """Test NoMatchFoundError exception inheritance."""
        from src.code_indexer.remote.repository_linking import BranchMatchingError

        error = NoMatchFoundError("No matching repositories found")
        assert isinstance(error, BranchMatchingError)
        assert isinstance(error, Exception)
        assert str(error) == "No matching repositories found"


class TestRepositoryDataModels:
    """Test suite for repository linking data models."""

    def test_repository_match_model_validation(self):
        """Test RepositoryMatch model validation."""
        from src.code_indexer.remote.repository_linking import (
            RepositoryType,
            MatchQuality,
        )

        match = RepositoryMatch(
            alias="test-repo",
            repository_type=RepositoryType.ACTIVATED,
            branch="main",
            match_quality=MatchQuality.EXACT,
            priority=1,
            git_url="https://github.com/test/repo.git",
            display_name="Test Repository",
            description="A test repository",
            available_branches=["main", "develop"],
            last_updated="2025-01-15T10:00:00Z",
            access_level="read",
        )

        assert match.alias == "test-repo"
        assert match.repository_type == RepositoryType.ACTIVATED
        assert match.branch == "main"
        assert match.match_quality == MatchQuality.EXACT

    def test_repository_link_model_validation(self):
        """Test RepositoryLink model validation."""
        from src.code_indexer.remote.repository_linking import RepositoryType

        link = RepositoryLink(
            alias="test-repo-user1",
            git_url="https://github.com/test/repo.git",
            branch="feature/auth",
            repository_type=RepositoryType.ACTIVATED,
            server_url="https://cidx.example.com",
            linked_at="2025-01-15T12:00:00Z",
            display_name="Test Repository",
            description="A test repository",
            access_level="read",
        )

        assert link.alias == "test-repo-user1"
        assert link.git_url == "https://github.com/test/repo.git"
        assert link.branch == "feature/auth"
        assert link.repository_type == RepositoryType.ACTIVATED

    def test_repository_discovery_response_model(self):
        """Test RepositoryDiscoveryResponse model validation."""

        response = RepositoryDiscoveryResponse(
            activated_repositories=[],
            golden_repositories=[],
            exact_matches=[],
            total_discovered=0,
            local_branch="main",
            match_strategy="exact_branch",
        )

        assert response.activated_repositories == []
        assert response.golden_repositories == []
        assert response.total_discovered == 0
        assert response.local_branch == "main"
