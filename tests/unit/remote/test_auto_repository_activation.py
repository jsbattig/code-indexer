"""Test suite for Auto Repository Activation functionality.

Tests automatic repository activation when only golden repositories match branch criteria,
following TDD principles with comprehensive coverage of acceptance criteria.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from code_indexer.remote.repository_linking import (
    RepositoryType,
    MatchQuality,
    RepositoryMatch,
    AutoRepositoryActivator,
    UserCancelledActivationError,
    RepositoryActivationError,
)
from code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    ActivatedRepository,
    ActivationError,
)


class TestAutoRepositoryActivator:
    """Test auto repository activation functionality."""

    @pytest.fixture
    def mock_repository_client(self):
        """Create mock repository linking client."""
        client = MagicMock(spec=RepositoryLinkingClient)
        client.server_url = "https://test.cidx-server.com"
        return client

    @pytest.fixture
    def mock_project_context(self, tmp_path):
        """Create mock project context path."""
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        return project_path

    @pytest.fixture
    def golden_repository_match(self):
        """Create golden repository match for testing."""
        return RepositoryMatch(
            alias="test-repo-golden",
            repository_type=RepositoryType.GOLDEN,
            branch="feature/api-client",
            match_quality=MatchQuality.EXACT,
            priority=2,
            git_url="https://github.com/test/repo.git",
            display_name="Test Repository Golden",
            description="Golden repository for testing",
            available_branches=["main", "develop", "feature/api-client"],
            last_updated="2024-01-15T10:30:00Z",
            access_level="read",
        )

    @pytest.fixture
    def auto_activator(self, mock_repository_client):
        """Create AutoRepositoryActivator instance."""
        return AutoRepositoryActivator(mock_repository_client)

    def test_auto_repository_activator_initialization(self, mock_repository_client):
        """Test AutoRepositoryActivator proper initialization."""
        activator = AutoRepositoryActivator(mock_repository_client)

        assert activator.repository_client == mock_repository_client
        assert hasattr(activator, "auto_activate_golden_repository")
        assert hasattr(activator, "_generate_user_alias")
        assert hasattr(activator, "_ensure_unique_alias")
        assert hasattr(activator, "_confirm_activation")
        assert hasattr(activator, "_display_activation_success")

    @pytest.mark.asyncio
    async def test_auto_activate_golden_repository_success(
        self, auto_activator, golden_repository_match, mock_project_context
    ):
        """Test successful auto-activation of golden repository."""
        # Mock user confirmation as accepted
        auto_activator._confirm_activation = MagicMock(return_value=True)

        # Mock unique alias generation
        expected_user_alias = "test-project-feature-api-client-20240115"
        auto_activator._generate_user_alias = MagicMock(
            return_value="test-project-feature-api-client"
        )
        auto_activator._ensure_unique_alias = AsyncMock(
            return_value=expected_user_alias
        )

        # Mock successful repository activation
        mock_activated_repo = ActivatedRepository(
            activation_id="act_123456789",
            golden_alias="test-repo-golden",
            user_alias=expected_user_alias,
            branch="feature/api-client",
            status="active",
            activated_at="2024-01-15T11:00:00Z",
            access_permissions=["read", "query"],
            query_endpoint=f"/api/v1/repositories/{expected_user_alias}/query",
            expires_at="2024-01-22T11:00:00Z",
            usage_limits={"daily_queries": 1000, "concurrent_queries": 10},
        )

        auto_activator.repository_client.activate_repository = AsyncMock(
            return_value=mock_activated_repo
        )
        auto_activator._display_activation_success = MagicMock()

        # Execute auto-activation
        result = await auto_activator.auto_activate_golden_repository(
            golden_repository_match, mock_project_context
        )

        # Verify result
        assert isinstance(result, ActivatedRepository)
        assert result.golden_alias == "test-repo-golden"
        assert result.user_alias == expected_user_alias
        assert result.branch == "feature/api-client"
        assert result.status == "active"

        # Verify method calls
        auto_activator._generate_user_alias.assert_called_once_with(
            golden_repository_match, mock_project_context
        )
        auto_activator._ensure_unique_alias.assert_called_once_with(
            "test-project-feature-api-client"
        )
        auto_activator._confirm_activation.assert_called_once_with(
            golden_repository_match, expected_user_alias
        )
        auto_activator.repository_client.activate_repository.assert_called_once_with(
            "test-repo-golden", "feature/api-client", expected_user_alias
        )
        auto_activator._display_activation_success.assert_called_once_with(result)

    @pytest.mark.asyncio
    async def test_auto_activate_golden_repository_user_cancellation(
        self, auto_activator, golden_repository_match, mock_project_context
    ):
        """Test auto-activation when user cancels confirmation."""
        # Mock user confirmation as rejected
        auto_activator._confirm_activation = MagicMock(return_value=False)
        auto_activator._generate_user_alias = MagicMock(
            return_value="test-project-feature-api-client"
        )
        auto_activator._ensure_unique_alias = AsyncMock(
            return_value="test-project-feature-api-client-20240115"
        )

        # Execute auto-activation and expect cancellation exception
        with pytest.raises(UserCancelledActivationError) as exc_info:
            await auto_activator.auto_activate_golden_repository(
                golden_repository_match, mock_project_context
            )

        assert "cancelled" in str(exc_info.value).lower()

        # Verify activation was not attempted
        auto_activator.repository_client.activate_repository.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_activate_golden_repository_activation_failure(
        self, auto_activator, golden_repository_match, mock_project_context
    ):
        """Test auto-activation when repository activation fails."""
        # Mock user confirmation as accepted
        auto_activator._confirm_activation = MagicMock(return_value=True)
        auto_activator._generate_user_alias = MagicMock(
            return_value="test-project-feature-api-client"
        )
        auto_activator._ensure_unique_alias = AsyncMock(
            return_value="test-project-feature-api-client-20240115"
        )

        # Mock activation failure
        auto_activator.repository_client.activate_repository = AsyncMock(
            side_effect=ActivationError("Repository activation failed: quota exceeded")
        )

        # Execute auto-activation and expect activation exception
        with pytest.raises(RepositoryActivationError) as exc_info:
            await auto_activator.auto_activate_golden_repository(
                golden_repository_match, mock_project_context
            )

        assert "activation failed" in str(exc_info.value).lower()
        assert "quota exceeded" in str(exc_info.value)

    def test_generate_user_alias_basic(
        self, auto_activator, golden_repository_match, mock_project_context
    ):
        """Test user alias generation with basic project and branch context."""
        result = auto_activator._generate_user_alias(
            golden_repository_match, mock_project_context
        )

        # Verify project name is included
        assert "test-project" in result

        # Verify branch components are included (normalized)
        assert "feature" in result
        assert "api" in result
        assert "client" in result

    def test_generate_user_alias_complex_branch(
        self, auto_activator, mock_project_context
    ):
        """Test user alias generation with complex branch names."""
        # Test with complex branch name
        complex_branch_match = RepositoryMatch(
            alias="complex-repo-golden",
            repository_type=RepositoryType.GOLDEN,
            branch="feature/complex-feature-name_with_underscores-123",
            match_quality=MatchQuality.EXACT,
            priority=2,
            git_url="https://github.com/test/complex.git",
            display_name="Complex Repository",
            description="Complex branch testing",
            available_branches=[
                "main",
                "feature/complex-feature-name_with_underscores-123",
            ],
            last_updated="2024-01-15T10:30:00Z",
            access_level="read",
        )

        result = auto_activator._generate_user_alias(
            complex_branch_match, mock_project_context
        )

        # Should normalize special characters and maintain readability
        assert "test-project" in result
        assert "feature" in result
        assert "complex" in result
        # Should not contain special characters like / or _
        assert "/" not in result
        assert "_" not in result

    def test_generate_user_alias_special_project_path(
        self, auto_activator, golden_repository_match, tmp_path
    ):
        """Test user alias generation with special characters in project path."""
        # Create project path with special characters
        special_project = tmp_path / "my_special-project.test"
        special_project.mkdir()

        result = auto_activator._generate_user_alias(
            golden_repository_match, special_project
        )

        # Should normalize project name and handle special characters
        assert "my" in result
        assert "special" in result
        assert "project" in result
        assert "feature" in result
        assert "api" in result
        assert "client" in result
        # Should not contain dots or underscores
        assert "." not in result
        assert "_" not in result

    @pytest.mark.asyncio
    async def test_ensure_unique_alias_no_conflicts(self, auto_activator):
        """Test alias uniqueness when no conflicts exist."""
        # Mock no existing repositories
        auto_activator.repository_client.list_user_repositories = AsyncMock(
            return_value=[]
        )

        base_alias = "test-project-feature-api-client"
        result = await auto_activator._ensure_unique_alias(base_alias)

        # Should return the original alias with timestamp
        assert result.startswith(base_alias)
        assert len(result) > len(base_alias)  # Should have timestamp appended

    @pytest.mark.asyncio
    async def test_ensure_unique_alias_with_conflicts(self, auto_activator):
        """Test alias uniqueness when conflicts exist."""
        base_alias = "test-project-feature-api-client"
        conflicting_timestamp = "20240115"
        conflicting_alias = f"{base_alias}-{conflicting_timestamp}"

        # Mock existing repository with conflicting alias
        existing_repo = ActivatedRepository(
            activation_id="act_existing",
            golden_alias="some-repo",
            user_alias=conflicting_alias,
            branch="main",
            status="active",
            activated_at="2024-01-15T10:00:00Z",
            access_permissions=["read"],
            query_endpoint="/api/v1/query",
            expires_at="2024-01-22T10:00:00Z",
            usage_limits={},
        )

        auto_activator.repository_client.list_user_repositories = AsyncMock(
            return_value=[existing_repo]
        )

        result = await auto_activator._ensure_unique_alias(base_alias)

        # Should return different alias to avoid conflict
        assert result != conflicting_alias
        assert result.startswith(base_alias)
        assert result != base_alias  # Should have suffix

    def test_confirm_activation_user_interface(
        self, auto_activator, golden_repository_match
    ):
        """Test activation confirmation user interface components."""
        # Mock console input as accepted
        with patch("builtins.input", return_value="y"):
            result = auto_activator._confirm_activation(
                golden_repository_match, "test-alias"
            )
            assert result is True

        # Mock console input as rejected
        with patch("builtins.input", return_value="n"):
            result = auto_activator._confirm_activation(
                golden_repository_match, "test-alias"
            )
            assert result is False

        # Mock console input as invalid then accepted
        with patch("builtins.input", side_effect=["invalid", "yes"]):
            result = auto_activator._confirm_activation(
                golden_repository_match, "test-alias"
            )
            assert result is True

    def test_confirm_activation_displays_repository_details(
        self, auto_activator, golden_repository_match
    ):
        """Test that activation confirmation displays relevant repository details."""
        with (
            patch("builtins.input", return_value="y"),
            patch("builtins.print") as mock_print,
        ):

            auto_activator._confirm_activation(golden_repository_match, "test-alias")

            # Verify repository information is displayed
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            printed_text = " ".join(print_calls)

            assert "test-repo-golden" in printed_text
            assert "feature/api-client" in printed_text
            assert "test-alias" in printed_text

    def test_display_activation_success_rich_output(self, auto_activator):
        """Test activation success display with Rich console formatting."""
        mock_activated_repo = ActivatedRepository(
            activation_id="act_123456789",
            golden_alias="test-repo-golden",
            user_alias="test-project-feature-api-client-20240115",
            branch="feature/api-client",
            status="active",
            activated_at="2024-01-15T11:00:00Z",
            access_permissions=["read", "query"],
            query_endpoint="/api/v1/repositories/test-project-feature-api-client-20240115/query",
            expires_at="2024-01-22T11:00:00Z",
            usage_limits={"daily_queries": 1000},
        )

        with patch("builtins.print") as mock_print:
            auto_activator._display_activation_success(mock_activated_repo)

            # Verify success information is displayed
            print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
            printed_text = " ".join(print_calls)

            assert "activated" in printed_text.lower()
            assert "test-repo-golden" in printed_text
            assert "test-project-feature-api-client-20240115" in printed_text
            assert "feature/api-client" in printed_text


class TestAutoRepositoryActivatorIntegration:
    """Test auto repository activator integration with existing matchers."""

    @pytest.fixture
    def mock_repository_client(self):
        """Create mock repository linking client."""
        client = MagicMock(spec=RepositoryLinkingClient)
        client.server_url = "https://test.cidx-server.com"
        return client

    @pytest.fixture
    def mock_project_context(self, tmp_path):
        """Create mock project context path."""
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        return project_path

    def test_auto_activator_exception_hierarchy(self):
        """Test that auto-activation exceptions inherit from appropriate base classes."""
        from code_indexer.remote.repository_linking import RepositoryLinkingError

        # Test UserCancelledActivationError inheritance
        try:
            raise UserCancelledActivationError("User cancelled")
        except RepositoryLinkingError:
            pass  # Should inherit from RepositoryLinkingError

        # Test RepositoryActivationError inheritance
        try:
            raise RepositoryActivationError("Activation failed")
        except RepositoryLinkingError:
            pass  # Should inherit from RepositoryLinkingError

    @pytest.mark.asyncio
    async def test_auto_activation_with_exact_branch_matcher_integration(
        self, mock_repository_client, mock_project_context
    ):
        """Test auto-activation integration with ExactBranchMatcher when only golden repositories match."""
        from code_indexer.remote.repository_linking import ExactBranchMatcher
        from code_indexer.services.git_topology_service import GitTopologyService

        # Create ExactBranchMatcher instance
        exact_matcher = ExactBranchMatcher(mock_repository_client)

        # Mock git service to return a valid local branch
        mock_git_service = MagicMock(spec=GitTopologyService)
        mock_git_service.get_current_branch.return_value = "feature/test-branch"
        exact_matcher.git_service = mock_git_service

        # Mock repository discovery with only golden repositories
        golden_repo_match = {
            "alias": "test-repo-golden",
            "display_name": "Test Repository Golden",
            "description": "Golden test repository",
            "git_url": "https://github.com/test/repo.git",
            "default_branch": "main",
            "available_branches": ["main", "develop", "feature/test-branch"],
            "last_updated": "2024-01-15T10:30:00Z",
            "access_level": "read",
        }

        discovery_response = AsyncMock()
        # Set up the proper structure that the code expects
        discovery_response.golden_repositories = [MagicMock(**golden_repo_match)]
        discovery_response.activated_repositories = []  # Empty list - only golden repos

        mock_repository_client.discover_repositories.return_value = discovery_response

        # Mock auto-activation success
        mock_activated_repo = ActivatedRepository(
            activation_id="act_123456789",
            golden_alias="test-repo-golden",
            user_alias="test-project-feature-test-branch-20240115",
            branch="feature/test-branch",
            status="active",
            activated_at="2024-01-15T11:00:00Z",
            access_permissions=["read", "query"],
            query_endpoint="/api/v1/repositories/test-project-feature-test-branch-20240115/query",
            expires_at="2024-01-22T11:00:00Z",
            usage_limits={"daily_queries": 1000},
        )

        # Mock the auto-activator's confirm_activation to return True
        with patch("builtins.input", return_value="y"):
            mock_repository_client.list_user_repositories.return_value = []
            mock_repository_client.activate_repository.return_value = (
                mock_activated_repo
            )

            # Execute exact branch matching - should trigger auto-activation
            result = await exact_matcher.find_exact_branch_match(
                mock_project_context, "https://github.com/test/repo.git"
            )

            # Verify auto-activation was triggered and successful
            assert result is not None
            assert (
                result.repository_type.value == "activated"
            )  # Should be activated, not golden
            assert (
                result.alias == "test-project-feature-test-branch-20240115"
            )  # User alias
            assert result.branch == "feature/test-branch"

    @pytest.mark.asyncio
    async def test_auto_activation_with_branch_fallback_matcher_integration(
        self, mock_repository_client, mock_project_context
    ):
        """Test auto-activation integration with BranchFallbackMatcher when only golden repositories match."""
        from code_indexer.remote.repository_linking import ExactBranchMatcher
        from code_indexer.services.git_topology_service import GitTopologyService

        # Create ExactBranchMatcher instance (which uses BranchFallbackMatcher)
        exact_matcher = ExactBranchMatcher(mock_repository_client)

        # Mock git service to return a feature branch with no exact match
        mock_git_service = MagicMock(spec=GitTopologyService)
        mock_git_service.get_current_branch.return_value = "feature/no-exact-match"
        mock_git_service._get_merge_base.return_value = (
            "abc123"  # Has merge base with main
        )
        exact_matcher.git_service = mock_git_service

        # Mock repository discovery with golden repository that has main but not feature branch
        golden_repo_match = {
            "alias": "test-repo-golden",
            "display_name": "Test Repository Golden",
            "description": "Golden test repository",
            "git_url": "https://github.com/test/repo.git",
            "default_branch": "main",
            "available_branches": ["main", "develop"],  # No feature/no-exact-match
            "last_updated": "2024-01-15T10:30:00Z",
            "access_level": "read",
        }

        discovery_response = AsyncMock()
        # Set up the proper structure that the code expects
        discovery_response.golden_repositories = [MagicMock(**golden_repo_match)]
        discovery_response.activated_repositories = []  # Empty list - only golden repos

        mock_repository_client.discover_repositories.return_value = discovery_response

        # Mock auto-activation success for fallback branch (main)
        mock_activated_repo = ActivatedRepository(
            activation_id="act_987654321",
            golden_alias="test-repo-golden",
            user_alias="test-project-main-20240115",
            branch="main",  # Fallback branch
            status="active",
            activated_at="2024-01-15T11:00:00Z",
            access_permissions=["read", "query"],
            query_endpoint="/api/v1/repositories/test-project-main-20240115/query",
            expires_at="2024-01-22T11:00:00Z",
            usage_limits={"daily_queries": 1000},
        )

        # Mock the auto-activator's confirm_activation to return True
        with patch("builtins.input", return_value="y"):
            mock_repository_client.list_user_repositories.return_value = []
            mock_repository_client.activate_repository.return_value = (
                mock_activated_repo
            )

            # Execute exact branch matching - should fail exact match but succeed with fallback + auto-activation
            result = await exact_matcher.find_exact_branch_match(
                mock_project_context, "https://github.com/test/repo.git"
            )

            # Verify fallback + auto-activation was triggered and successful
            assert result is not None
            assert result.repository_type.value == "activated"  # Should be activated
            assert (
                result.alias == "test-project-main-20240115"
            )  # User alias for activated repo
            assert result.branch == "main"  # Fallback branch
            # Should have fallback-specific fields
            assert result.match_reason is not None
            assert result.parent_branch is not None


class TestAutoRepositoryActivatorErrorHandling:
    """Test error handling scenarios for auto repository activation."""

    @pytest.fixture
    def mock_repository_client(self):
        """Create mock repository linking client."""
        client = MagicMock(spec=RepositoryLinkingClient)
        client.server_url = "https://test.cidx-server.com"
        return client

    @pytest.fixture
    def auto_activator(self, mock_repository_client):
        """Create AutoRepositoryActivator instance."""
        return AutoRepositoryActivator(mock_repository_client)

    @pytest.fixture
    def mock_project_context(self, tmp_path):
        """Create mock project context path."""
        project_path = tmp_path / "test-project"
        project_path.mkdir()
        return project_path

    @pytest.mark.asyncio
    async def test_auto_activate_network_error_handling(
        self, auto_activator, mock_project_context
    ):
        """Test auto-activation handles network errors gracefully."""
        from code_indexer.api_clients.base_client import NetworkError

        golden_match = RepositoryMatch(
            alias="test-repo-golden",
            repository_type=RepositoryType.GOLDEN,
            branch="main",
            match_quality=MatchQuality.EXACT,
            priority=2,
            git_url="https://github.com/test/repo.git",
            display_name="Test Repository",
            description="Test repository",
            available_branches=["main"],
            last_updated="2024-01-15T10:30:00Z",
            access_level="read",
        )

        # Mock user confirmation as accepted
        auto_activator._confirm_activation = MagicMock(return_value=True)
        auto_activator._generate_user_alias = MagicMock(return_value="test-alias")
        auto_activator._ensure_unique_alias = AsyncMock(return_value="test-alias-123")

        # Mock network error during activation
        auto_activator.repository_client.activate_repository = AsyncMock(
            side_effect=NetworkError("Connection timeout")
        )

        with pytest.raises(RepositoryActivationError) as exc_info:
            await auto_activator.auto_activate_golden_repository(
                golden_match, mock_project_context
            )

        assert (
            "network" in str(exc_info.value).lower()
            or "connection" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_auto_activate_api_client_error_handling(
        self, auto_activator, mock_project_context
    ):
        """Test auto-activation handles various API client errors gracefully."""
        from code_indexer.api_clients.base_client import APIClientError

        golden_match = RepositoryMatch(
            alias="test-repo-golden",
            repository_type=RepositoryType.GOLDEN,
            branch="main",
            match_quality=MatchQuality.EXACT,
            priority=2,
            git_url="https://github.com/test/repo.git",
            display_name="Test Repository",
            description="Test repository",
            available_branches=["main"],
            last_updated="2024-01-15T10:30:00Z",
            access_level="read",
        )

        # Mock user confirmation as accepted
        auto_activator._confirm_activation = MagicMock(return_value=True)
        auto_activator._generate_user_alias = MagicMock(return_value="test-alias")
        auto_activator._ensure_unique_alias = AsyncMock(return_value="test-alias-123")

        # Mock API client error during activation
        auto_activator.repository_client.activate_repository = AsyncMock(
            side_effect=APIClientError("Invalid API response")
        )

        with pytest.raises(RepositoryActivationError) as exc_info:
            await auto_activator.auto_activate_golden_repository(
                golden_match, mock_project_context
            )

        assert (
            "api" in str(exc_info.value).lower()
            or "invalid" in str(exc_info.value).lower()
        )
