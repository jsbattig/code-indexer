"""Test suite for Repository Linking Client.

Tests repository discovery, golden repository management, and activation functionality
following TDD principles with no mocks.
"""

import pytest
from unittest.mock import AsyncMock, patch

from code_indexer.api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryDiscoveryResponse,
    BranchInfo,
    ActivatedRepository,
    RepositoryNotFoundError,
    BranchNotFoundError,
    ActivationError,
)


class TestRepositoryLinkingClientDiscovery:
    """Test repository discovery functionality."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest.fixture
    def linking_client(self, mock_credentials):
        """Create repository linking client for testing."""
        return RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

    @pytest.mark.asyncio
    async def test_discover_repositories_success(self, linking_client):
        """Test successful repository discovery by git origin URL."""
        mock_discovery_response = {
            "query_url": "https://github.com/example/cidx.git",
            "normalized_url": "https://github.com/example/cidx.git",
            "golden_repositories": [
                {
                    "alias": "cidx-main",
                    "repository_type": "golden",
                    "display_name": "CIDX Main Repository",
                    "description": "Main CIDX codebase",
                    "git_url": "https://github.com/example/cidx.git",
                    "default_branch": "master",
                    "available_branches": ["master", "develop", "feature/api"],
                    "last_indexed": "2024-01-15T10:30:00Z",
                },
                {
                    "alias": "cidx-docs",
                    "repository_type": "golden",
                    "display_name": "CIDX Documentation",
                    "description": "Documentation repository",
                    "git_url": "https://github.com/example/cidx-docs.git",
                    "default_branch": "main",
                    "available_branches": ["main", "staging"],
                    "last_indexed": "2024-01-14T15:45:00Z",
                },
            ],
            "activated_repositories": [],
            "total_matches": 2,
        }

        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=200, json=lambda: mock_discovery_response
            ),
        ):
            result = await linking_client.discover_repositories(
                "https://github.com/example/cidx.git"
            )

            assert isinstance(result, RepositoryDiscoveryResponse)
            assert len(result.golden_repositories) == 2
            assert len(result.activated_repositories) == 0
            assert result.total_matches == 2
            assert result.query_url == "https://github.com/example/cidx.git"
            assert result.normalized_url == "https://github.com/example/cidx.git"

            # Verify first repository details
            first_repo = result.golden_repositories[0]
            assert first_repo.alias == "cidx-main"
            assert first_repo.display_name == "CIDX Main Repository"
            assert first_repo.git_url == "https://github.com/example/cidx.git"
            assert first_repo.default_branch == "master"
            assert "master" in first_repo.available_branches
            assert first_repo.repository_type == "golden"

    @pytest.mark.asyncio
    async def test_discover_repositories_no_matches(self, linking_client):
        """Test repository discovery when no repositories match."""
        mock_empty_response = {
            "query_url": "https://github.com/nonexistent/repo.git",
            "normalized_url": "https://github.com/nonexistent/repo.git",
            "golden_repositories": [],
            "activated_repositories": [],
            "total_matches": 0,
        }

        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(status_code=200, json=lambda: mock_empty_response),
        ):
            result = await linking_client.discover_repositories(
                "https://github.com/nonexistent/repo.git"
            )

            assert isinstance(result, RepositoryDiscoveryResponse)
            assert len(result.golden_repositories) == 0
            assert len(result.activated_repositories) == 0
            assert result.total_matches == 0
            assert result.query_url == "https://github.com/nonexistent/repo.git"
            assert result.normalized_url == "https://github.com/nonexistent/repo.git"

    @pytest.mark.asyncio
    async def test_discover_repositories_invalid_url(self, linking_client):
        """Test repository discovery with invalid git URL."""
        invalid_urls = [
            "not-a-url",
            "https://example.com/not-git",
            "",
            "git@github.com:user/repo.git",  # SSH format not supported
        ]

        for invalid_url in invalid_urls:
            with pytest.raises(ValueError) as exc_info:
                await linking_client.discover_repositories(invalid_url)

            assert "Invalid git URL" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_discover_repositories_server_error(self, linking_client):
        """Test repository discovery when server returns error."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=500, json=lambda: {"detail": "Internal server error"}
            ),
        ):
            with pytest.raises(RepositoryNotFoundError) as exc_info:
                await linking_client.discover_repositories(
                    "https://github.com/example/repo.git"
                )

            assert "Internal server error" in str(exc_info.value)


class TestRepositoryLinkingClientBranches:
    """Test golden repository branch management."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest.fixture
    def linking_client(self, mock_credentials):
        """Create repository linking client for testing."""
        return RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

    @pytest.mark.asyncio
    async def test_get_golden_repository_branches_success(self, linking_client):
        """Test successful retrieval of golden repository branches."""
        mock_branches_response = {
            "repository_alias": "cidx-main",
            "branches": [
                {
                    "name": "master",
                    "is_default": True,
                    "last_commit_sha": "abc123def456",
                    "last_commit_message": "Add feature X",
                    "last_updated": "2024-01-15T10:30:00Z",
                    "indexing_status": "completed",
                    "total_files": 1247,
                    "indexed_files": 1247,
                },
                {
                    "name": "develop",
                    "is_default": False,
                    "last_commit_sha": "def456ghi789",
                    "last_commit_message": "Work in progress",
                    "last_updated": "2024-01-15T09:15:00Z",
                    "indexing_status": "in_progress",
                    "total_files": 1250,
                    "indexed_files": 1100,
                },
                {
                    "name": "feature/api-client",
                    "is_default": False,
                    "last_commit_sha": "ghi789jkl012",
                    "last_commit_message": "Implement API client",
                    "last_updated": "2024-01-14T14:20:00Z",
                    "indexing_status": "pending",
                    "total_files": 1255,
                    "indexed_files": 0,
                },
            ],
        }

        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=200, json=lambda: mock_branches_response
            ),
        ):
            branches = await linking_client.get_golden_repository_branches("cidx-main")

            assert len(branches) == 3
            assert all(isinstance(branch, BranchInfo) for branch in branches)

            # Verify master branch details
            master_branch = next(b for b in branches if b.name == "master")
            assert master_branch.is_default is True
            assert master_branch.last_commit_sha == "abc123def456"
            assert master_branch.indexing_status == "completed"
            assert master_branch.total_files == 1247
            assert master_branch.indexed_files == 1247

            # Verify develop branch details
            develop_branch = next(b for b in branches if b.name == "develop")
            assert develop_branch.is_default is False
            assert develop_branch.indexing_status == "in_progress"
            assert develop_branch.indexed_files < develop_branch.total_files

    @pytest.mark.asyncio
    async def test_get_golden_repository_branches_not_found(self, linking_client):
        """Test branch retrieval for non-existent repository."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=404, json=lambda: {"detail": "Repository not found"}
            ),
        ):
            with pytest.raises(RepositoryNotFoundError) as exc_info:
                await linking_client.get_golden_repository_branches("nonexistent-repo")

            assert "Repository not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_golden_repository_branches_empty(self, linking_client):
        """Test branch retrieval for repository with no branches."""
        mock_empty_response = {"repository_alias": "empty-repo", "branches": []}

        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(status_code=200, json=lambda: mock_empty_response),
        ):
            branches = await linking_client.get_golden_repository_branches("empty-repo")

            assert len(branches) == 0


class TestRepositoryLinkingClientActivation:
    """Test repository activation functionality."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest.fixture
    def linking_client(self, mock_credentials):
        """Create repository linking client for testing."""
        return RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

    @pytest.mark.asyncio
    async def test_activate_repository_success(self, linking_client):
        """Test successful repository activation."""
        mock_activation_response = {
            "activation_id": "act_123456789",
            "golden_alias": "cidx-main",
            "user_alias": "cidx-main-testuser",
            "branch": "master",
            "status": "active",
            "activated_at": "2024-01-15T11:00:00Z",
            "access_permissions": ["read", "query"],
            "query_endpoint": "/api/v1/repositories/cidx-main-testuser/query",
            "expires_at": "2024-01-22T11:00:00Z",
            "usage_limits": {"daily_queries": 1000, "concurrent_queries": 10},
        }

        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=201, json=lambda: mock_activation_response
            ),
        ):
            result = await linking_client.activate_repository(
                golden_alias="cidx-main",
                branch="master",
                user_alias="cidx-main-testuser",
            )

            assert isinstance(result, ActivatedRepository)
            assert result.activation_id == "act_123456789"
            assert result.golden_alias == "cidx-main"
            assert result.user_alias == "cidx-main-testuser"
            assert result.branch == "master"
            assert result.status == "active"
            assert (
                result.query_endpoint == "/api/v1/repositories/cidx-main-testuser/query"
            )
            assert "read" in result.access_permissions
            assert "query" in result.access_permissions

    @pytest.mark.asyncio
    async def test_activate_repository_invalid_branch(self, linking_client):
        """Test repository activation with invalid branch."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=400,
                json=lambda: {"detail": "Branch 'nonexistent' not found"},
            ),
        ):
            with pytest.raises(BranchNotFoundError) as exc_info:
                await linking_client.activate_repository(
                    golden_alias="cidx-main",
                    branch="nonexistent",
                    user_alias="cidx-main-testuser",
                )

            assert "Branch 'nonexistent' not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_activate_repository_access_denied(self, linking_client):
        """Test repository activation when access is denied."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=403,
                json=lambda: {"detail": "Insufficient permissions for repository"},
            ),
        ):
            with pytest.raises(ActivationError) as exc_info:
                await linking_client.activate_repository(
                    golden_alias="private-repo",
                    branch="master",
                    user_alias="private-repo-testuser",
                )

            assert "Insufficient permissions" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_activate_repository_conflict(self, linking_client):
        """Test repository activation when activation already exists."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=409,
                json=lambda: {
                    "detail": "Repository already activated",
                    "existing_activation_id": "act_existing_123",
                },
            ),
        ):
            with pytest.raises(ActivationError) as exc_info:
                await linking_client.activate_repository(
                    golden_alias="cidx-main",
                    branch="master",
                    user_alias="cidx-main-testuser",
                )

            assert "Repository already activated" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_activate_repository_quota_exceeded(self, linking_client):
        """Test repository activation when user quota is exceeded."""
        with patch.object(
            linking_client,
            "_authenticated_request",
            return_value=AsyncMock(
                status_code=429,
                json=lambda: {
                    "detail": "Repository activation quota exceeded",
                    "current_activations": 5,
                    "max_activations": 5,
                },
            ),
        ):
            with pytest.raises(ActivationError) as exc_info:
                await linking_client.activate_repository(
                    golden_alias="another-repo",
                    branch="master",
                    user_alias="another-repo-testuser",
                )

            assert "quota exceeded" in str(exc_info.value)


class TestRepositoryLinkingClientInputValidation:
    """Test input validation for repository linking operations."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest.fixture
    def linking_client(self, mock_credentials):
        """Create repository linking client for testing."""
        return RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

    @pytest.mark.asyncio
    async def test_discover_repositories_url_validation(self, linking_client):
        """Test URL validation for repository discovery."""
        invalid_inputs = [
            None,
            "",
            "   ",
            "not-a-url",
            "ftp://example.com/repo.git",
            "https://example.com",  # Missing .git
        ]

        for invalid_input in invalid_inputs:
            with pytest.raises(ValueError):
                await linking_client.discover_repositories(invalid_input)

    @pytest.mark.asyncio
    async def test_get_branches_alias_validation(self, linking_client):
        """Test alias validation for branch retrieval."""
        invalid_aliases = [
            None,
            "",
            "   ",
            "alias with spaces",
            "alias/with/slashes",
            "alias-with-$pecial-chars",
        ]

        for invalid_alias in invalid_aliases:
            with pytest.raises(ValueError):
                await linking_client.get_golden_repository_branches(invalid_alias)

    @pytest.mark.asyncio
    async def test_activate_repository_parameter_validation(self, linking_client):
        """Test parameter validation for repository activation."""
        # Test invalid golden_alias
        with pytest.raises(ValueError):
            await linking_client.activate_repository(
                golden_alias="", branch="master", user_alias="valid-alias"
            )

        # Test invalid branch
        with pytest.raises(ValueError):
            await linking_client.activate_repository(
                golden_alias="valid-alias", branch="", user_alias="valid-alias"
            )

        # Test invalid user_alias
        with pytest.raises(ValueError):
            await linking_client.activate_repository(
                golden_alias="valid-alias", branch="master", user_alias=""
            )

    def test_repository_linking_client_inheritance(self, mock_credentials):
        """Test that RepositoryLinkingClient properly inherits from base client."""
        from code_indexer.api_clients.base_client import CIDXRemoteAPIClient

        client = RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

        assert isinstance(client, CIDXRemoteAPIClient)
        assert hasattr(client, "_authenticated_request")
        assert hasattr(client, "_get_valid_token")
        assert hasattr(client, "close")


class TestRepositoryLinkingClientResponseModels:
    """Test response model parsing and validation."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock encrypted credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
            "server_url": "https://test.example.com",
        }

    @pytest.fixture
    def linking_client(self, mock_credentials):
        """Create repository linking client for testing."""
        return RepositoryLinkingClient(
            server_url="https://test.example.com", credentials=mock_credentials
        )

    def test_repository_discovery_response_model(self):
        """Test RepositoryDiscoveryResponse model validation."""
        valid_data = {
            "query_url": "https://github.com/test/repo.git",
            "normalized_url": "https://github.com/test/repo.git",
            "golden_repositories": [
                {
                    "alias": "test-repo",
                    "repository_type": "golden",
                    "display_name": "Test Repository",
                    "description": "A test repository",
                    "git_url": "https://github.com/test/repo.git",
                    "default_branch": "main",
                    "available_branches": ["main", "develop"],
                    "last_indexed": "2024-01-15T10:30:00Z",
                }
            ],
            "activated_repositories": [],
            "total_matches": 1,
        }

        response = RepositoryDiscoveryResponse.model_validate(valid_data)
        assert len(response.golden_repositories) == 1
        assert len(response.activated_repositories) == 0
        assert response.total_matches == 1
        assert response.golden_repositories[0].alias == "test-repo"
        assert response.query_url == "https://github.com/test/repo.git"
        assert response.normalized_url == "https://github.com/test/repo.git"

    def test_branch_info_model(self):
        """Test BranchInfo model validation."""
        valid_data = {
            "name": "master",
            "is_default": True,
            "last_commit_sha": "abc123",
            "last_commit_message": "Initial commit",
            "last_updated": "2024-01-15T10:30:00Z",
            "indexing_status": "completed",
            "total_files": 100,
            "indexed_files": 100,
        }

        branch = BranchInfo.model_validate(valid_data)
        assert branch.name == "master"
        assert branch.is_default is True
        assert branch.indexing_status == "completed"

    def test_activated_repository_model(self):
        """Test ActivatedRepository model validation."""
        valid_data = {
            "activation_id": "act_123",
            "golden_alias": "test-repo",
            "user_alias": "test-repo-user",
            "branch": "master",
            "status": "active",
            "activated_at": "2024-01-15T11:00:00Z",
            "access_permissions": ["read", "query"],
            "query_endpoint": "/api/v1/query",
            "expires_at": "2024-01-22T11:00:00Z",
            "usage_limits": {"daily_queries": 1000},
        }

        repo = ActivatedRepository.model_validate(valid_data)
        assert repo.activation_id == "act_123"
        assert repo.status == "active"
        assert "read" in repo.access_permissions
