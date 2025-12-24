"""TDD tests for ReposAPIClient implementation - Corrected Version.

This test file implements comprehensive TDD tests for the repository discovery
and browsing functionality as defined in Story 4.
"""

import pytest
from unittest.mock import Mock, patch

from src.code_indexer.api_clients.repos_client import (
    ReposAPIClient,
    ActivatedRepository,
    GoldenRepository,
    RepositoryDiscoveryResult,
    RepositoryStatusSummary,
)
from src.code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestReposAPIClientInitialization:
    """Test ReposAPIClient initialization and configuration."""

    def test_repos_client_inherits_from_base_client(self):
        """Test that ReposAPIClient properly inherits from CIDXRemoteAPIClient."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            client = ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )
            assert hasattr(client, "server_url")
            assert hasattr(client, "credentials")

    def test_repos_client_initialization_with_credentials(self):
        """Test ReposAPIClient initialization with project credentials."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            from pathlib import Path

            client = ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
                project_root=Path("/test/project"),
            )
            assert client is not None


class TestActivatedRepositoryOperations:
    """Test operations for managing activated repositories."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            return ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )

    @pytest.mark.asyncio
    async def test_list_activated_repositories_success(self, mock_client):
        """Test successful listing of activated repositories."""
        # Mock HTTP response
        mock_response_data = {
            "repositories": [
                {
                    "alias": "web-app",
                    "current_branch": "main",
                    "sync_status": "synced",
                    "last_sync": "2024-01-15T10:30:00Z",
                    "activation_date": "2024-01-10T14:20:00Z",
                    "conflict_details": None,
                },
                {
                    "alias": "api-service",
                    "current_branch": "feature/v2",
                    "sync_status": "needs_sync",
                    "last_sync": "2024-01-14T08:15:00Z",
                    "activation_date": "2024-01-12T09:45:00Z",
                    "conflict_details": None,
                },
            ],
            "total_count": 2,
        }

        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            repositories = await mock_client.list_activated_repositories()

        assert len(repositories) == 2
        assert repositories[0].alias == "web-app"
        assert repositories[0].sync_status == "synced"
        assert repositories[1].alias == "api-service"
        assert repositories[1].sync_status == "needs_sync"

    @pytest.mark.asyncio
    async def test_list_activated_repositories_with_filter(self, mock_client):
        """Test listing activated repositories with filter parameter."""
        mock_response_data = {
            "repositories": [
                {
                    "alias": "web-app",
                    "current_branch": "main",
                    "sync_status": "synced",
                    "last_sync": "2024-01-15T10:30:00Z",
                    "activation_date": "2024-01-10T14:20:00Z",
                    "conflict_details": None,
                }
            ],
            "total_count": 1,
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            repositories = await mock_client.list_activated_repositories(
                filter_pattern="web"
            )

        # Verify the request was made with correct parameters
        mock_request.assert_called_once_with(
            "GET", "/api/repos", params={"filter": "web"}
        )

        assert len(repositories) == 1
        assert repositories[0].alias == "web-app"

    @pytest.mark.asyncio
    async def test_list_activated_repositories_empty_response(self, mock_client):
        """Test handling of empty repository list."""
        mock_response_data = {"repositories": [], "total_count": 0}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            repositories = await mock_client.list_activated_repositories()

        assert len(repositories) == 0

    @pytest.mark.asyncio
    async def test_list_activated_repositories_authentication_error(self, mock_client):
        """Test handling of authentication errors during repository listing."""
        with patch.object(
            mock_client,
            "_authenticated_request",
            side_effect=AuthenticationError("Token expired"),
        ):
            with pytest.raises(AuthenticationError, match="Token expired"):
                await mock_client.list_activated_repositories()

    @pytest.mark.asyncio
    async def test_list_activated_repositories_network_error(self, mock_client):
        """Test handling of network errors during repository listing."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError, match="Failed to list repositories"):
                await mock_client.list_activated_repositories()


class TestGoldenRepositoryOperations:
    """Test operations for browsing golden repositories."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            return ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )

    @pytest.mark.asyncio
    async def test_list_available_repositories_success(self, mock_client):
        """Test successful listing of available golden repositories."""
        mock_response_data = {
            "repositories": [
                {
                    "alias": "web-framework",
                    "description": "Modern web application framework",
                    "default_branch": "main",
                    "indexed_branches": ["main", "develop", "feature/auth"],
                    "is_activated": False,
                    "last_updated": "2024-01-15T12:00:00Z",
                },
                {
                    "alias": "data-pipeline",
                    "description": "ETL data processing pipeline",
                    "default_branch": "master",
                    "indexed_branches": ["master", "staging"],
                    "is_activated": True,
                    "last_updated": "2024-01-14T16:30:00Z",
                },
            ],
            "total_count": 2,
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            repositories = await mock_client.list_available_repositories()

        assert len(repositories) == 2
        assert repositories[0].alias == "web-framework"
        assert repositories[0].is_activated is False
        assert repositories[1].alias == "data-pipeline"
        assert repositories[1].is_activated is True

    @pytest.mark.asyncio
    async def test_list_available_repositories_with_search(self, mock_client):
        """Test listing available repositories with search parameter."""
        mock_response_data = {
            "repositories": [
                {
                    "alias": "web-framework",
                    "description": "Modern web application framework",
                    "default_branch": "main",
                    "indexed_branches": ["main"],
                    "is_activated": False,
                    "last_updated": "2024-01-15T12:00:00Z",
                }
            ],
            "total_count": 1,
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ) as mock_request:
            repositories = await mock_client.list_available_repositories(
                search_term="web"
            )

        # Verify the request was made with correct parameters
        mock_request.assert_called_once_with(
            "GET", "/api/repos/available", params={"search": "web"}
        )

        assert len(repositories) == 1
        assert repositories[0].alias == "web-framework"

    @pytest.mark.asyncio
    async def test_list_available_repositories_empty_response(self, mock_client):
        """Test handling of empty available repositories list."""
        mock_response_data = {"repositories": [], "total_count": 0}

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            repositories = await mock_client.list_available_repositories()

        assert len(repositories) == 0


class TestRepositoryDiscoveryOperations:
    """Test repository discovery from remote sources."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            return ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )

    @pytest.mark.asyncio
    async def test_discover_repositories_github_org_success(self, mock_client):
        """Test successful repository discovery from GitHub organization."""
        mock_response_data = {
            "discovered_repositories": [
                {
                    "name": "awesome-project",
                    "url": "https://github.com/myorg/awesome-project",
                    "description": "An awesome open source project",
                    "is_available": False,
                    "is_accessible": True,
                    "default_branch": "main",
                    "last_updated": "2024-01-15T10:00:00Z",
                },
                {
                    "name": "internal-tool",
                    "url": "https://github.com/myorg/internal-tool",
                    "description": "Internal development tool",
                    "is_available": True,
                    "is_accessible": True,
                    "default_branch": "master",
                    "last_updated": "2024-01-14T14:30:00Z",
                },
            ],
            "source": "github.com/myorg",
            "total_discovered": 2,
            "access_errors": [],
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            result = await mock_client.discover_repositories("github.com/myorg")

        assert len(result.discovered_repositories) == 2
        assert result.source == "github.com/myorg"
        assert result.total_discovered == 2
        assert result.discovered_repositories[0].name == "awesome-project"
        assert result.discovered_repositories[0].is_available is False
        assert result.discovered_repositories[1].name == "internal-tool"
        assert result.discovered_repositories[1].is_available is True

    @pytest.mark.asyncio
    async def test_discover_repositories_direct_url(self, mock_client):
        """Test repository discovery from direct Git URL."""
        mock_response_data = {
            "discovered_repositories": [
                {
                    "name": "custom-repo",
                    "url": "https://git.example.com/user/custom-repo.git",
                    "description": "Custom repository",
                    "is_available": False,
                    "is_accessible": True,
                    "default_branch": "main",
                    "last_updated": "2024-01-15T15:00:00Z",
                }
            ],
            "source": "https://git.example.com/user/custom-repo.git",
            "total_discovered": 1,
            "access_errors": [],
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            result = await mock_client.discover_repositories(
                "https://git.example.com/user/custom-repo.git"
            )

        assert len(result.discovered_repositories) == 1
        assert result.discovered_repositories[0].name == "custom-repo"

    @pytest.mark.asyncio
    async def test_discover_repositories_with_access_errors(self, mock_client):
        """Test repository discovery with some access errors."""
        mock_response_data = {
            "discovered_repositories": [
                {
                    "name": "public-repo",
                    "url": "https://github.com/org/public-repo",
                    "description": "Public repository",
                    "is_available": False,
                    "is_accessible": True,
                    "default_branch": "main",
                    "last_updated": "2024-01-15T10:00:00Z",
                }
            ],
            "source": "github.com/org",
            "total_discovered": 1,
            "access_errors": [
                "Repository 'private-repo' requires authentication",
                "Repository 'archived-repo' is archived and cannot be accessed",
            ],
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            result = await mock_client.discover_repositories("github.com/org")

        assert len(result.discovered_repositories) == 1
        assert len(result.access_errors) == 2
        assert "requires authentication" in result.access_errors[0]

    @pytest.mark.asyncio
    async def test_discover_repositories_invalid_source(self, mock_client):
        """Test repository discovery with invalid source."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"detail": "Invalid source format"}

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError, match="Failed to discover repositories"):
                await mock_client.discover_repositories("invalid-source")


class TestRepositoryStatusOperations:
    """Test repository status summary operations."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            return ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )

    @pytest.mark.asyncio
    async def test_get_repository_status_summary_success(self, mock_client):
        """Test successful retrieval of repository status summary."""
        mock_response_data = {
            "activated_repositories": {
                "total_count": 3,
                "synced_count": 1,
                "needs_sync_count": 1,
                "conflict_count": 1,
                "recent_activations": [
                    {"alias": "new-project", "activation_date": "2024-01-15T10:00:00Z"}
                ],
            },
            "available_repositories": {"total_count": 10, "not_activated_count": 7},
            "recent_activity": {
                "recent_syncs": [
                    {
                        "alias": "web-app",
                        "sync_date": "2024-01-15T09:30:00Z",
                        "status": "success",
                    }
                ]
            },
            "recommendations": [
                "Consider syncing 'api-service' (last sync 3 days ago)",
                "Resolve conflicts in 'mobile-app' repository",
            ],
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            summary = await mock_client.get_repository_status_summary()

        assert summary.activated_repositories.total_count == 3
        assert summary.activated_repositories.synced_count == 1
        assert summary.activated_repositories.needs_sync_count == 1
        assert summary.activated_repositories.conflict_count == 1
        assert summary.available_repositories.total_count == 10
        assert len(summary.recommendations) == 2

    @pytest.mark.asyncio
    async def test_get_repository_status_summary_empty_state(self, mock_client):
        """Test repository status summary with no repositories."""
        mock_response_data = {
            "activated_repositories": {
                "total_count": 0,
                "synced_count": 0,
                "needs_sync_count": 0,
                "conflict_count": 0,
                "recent_activations": [],
            },
            "available_repositories": {"total_count": 5, "not_activated_count": 5},
            "recent_activity": {"recent_syncs": []},
            "recommendations": [
                "No repositories activated yet. Use 'cidx repos available' to browse and activate repositories."
            ],
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            summary = await mock_client.get_repository_status_summary()

        assert summary.activated_repositories.total_count == 0
        assert summary.available_repositories.total_count == 5
        assert len(summary.recommendations) == 1
        assert "No repositories activated" in summary.recommendations[0]


class TestDataModels:
    """Test the data models used by ReposAPIClient."""

    def test_activated_repository_model_creation(self):
        """Test ActivatedRepository model creation and validation."""
        repo_data = {
            "alias": "test-repo",
            "current_branch": "main",
            "sync_status": "synced",
            "last_sync": "2024-01-15T10:30:00Z",
            "activation_date": "2024-01-10T14:20:00Z",
            "conflict_details": None,
        }

        repo = ActivatedRepository(**repo_data)

        assert repo.alias == "test-repo"
        assert repo.current_branch == "main"
        assert repo.sync_status == "synced"
        assert repo.conflict_details is None

    def test_golden_repository_model_creation(self):
        """Test GoldenRepository model creation and validation."""
        repo_data = {
            "alias": "golden-repo",
            "description": "A golden repository",
            "default_branch": "main",
            "indexed_branches": ["main", "develop"],
            "is_activated": False,
            "last_updated": "2024-01-15T12:00:00Z",
        }

        repo = GoldenRepository(**repo_data)

        assert repo.alias == "golden-repo"
        assert repo.description == "A golden repository"
        assert repo.default_branch == "main"
        assert len(repo.indexed_branches) == 2
        assert repo.is_activated is False

    def test_repository_discovery_result_model_creation(self):
        """Test RepositoryDiscoveryResult model creation and validation."""
        discovery_data = {
            "discovered_repositories": [
                {
                    "name": "discovered-repo",
                    "url": "https://github.com/user/discovered-repo",
                    "description": "A discovered repository",
                    "is_available": False,
                    "is_accessible": True,
                    "default_branch": "main",
                    "last_updated": "2024-01-15T10:00:00Z",
                }
            ],
            "source": "github.com/user",
            "total_discovered": 1,
            "access_errors": [],
        }

        result = RepositoryDiscoveryResult(**discovery_data)

        assert len(result.discovered_repositories) == 1
        assert result.source == "github.com/user"
        assert result.total_discovered == 1
        assert len(result.access_errors) == 0

    def test_repository_status_summary_model_creation(self):
        """Test RepositoryStatusSummary model creation and validation."""
        summary_data = {
            "activated_repositories": {
                "total_count": 2,
                "synced_count": 1,
                "needs_sync_count": 1,
                "conflict_count": 0,
                "recent_activations": [],
            },
            "available_repositories": {"total_count": 8, "not_activated_count": 6},
            "recent_activity": {"recent_syncs": []},
            "recommendations": ["Test recommendation"],
        }

        summary = RepositoryStatusSummary(**summary_data)

        assert summary.activated_repositories.total_count == 2
        assert summary.available_repositories.total_count == 8
        assert len(summary.recommendations) == 1


class TestErrorHandling:
    """Test comprehensive error handling scenarios."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock ReposAPIClient for testing."""
        with patch("src.code_indexer.api_clients.repos_client.CIDXRemoteAPIClient"):
            return ReposAPIClient(
                server_url="https://test.example.com",
                credentials={"username": "test", "password": "test"},
            )

    @pytest.mark.asyncio
    async def test_malformed_response_handling(self, mock_client):
        """Test handling of malformed API responses."""
        # Missing required fields
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"incomplete": "data"}

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError, match="Invalid response format"):
                await mock_client.list_activated_repositories()

    @pytest.mark.asyncio
    async def test_server_error_handling(self, mock_client):
        """Test handling of server errors."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"detail": "Internal server error"}

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError, match="Failed to list repositories"):
                await mock_client.list_activated_repositories()

    @pytest.mark.asyncio
    async def test_rate_limit_error_handling(self, mock_client):
        """Test handling of rate limit errors."""
        mock_response = Mock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"detail": "Rate limit exceeded"}

        with patch.object(
            mock_client, "_authenticated_request", return_value=mock_response
        ):
            with pytest.raises(APIClientError, match="Failed to get repository status"):
                await mock_client.get_repository_status_summary()
