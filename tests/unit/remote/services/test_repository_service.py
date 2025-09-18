"""Tests for RemoteRepositoryService using real implementations."""

import pytest
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock

from src.code_indexer.remote.services.repository_service import (
    RemoteRepositoryService,
    RepositoryInfo,
    RepositoryAnalysis,
)
from src.code_indexer.remote.staleness_detector import StalenessDetector


class TestResponse:
    """Test response class that mimics httpx.Response behavior."""

    def __init__(self, status_code: int, json_data: Dict[str, Any]):
        self.status_code = status_code
        self._json_data = json_data

    def json(self) -> Dict[str, Any]:
        return self._json_data


class TestAPIClient:
    """Test API client that provides real responses without mocking."""

    def __init__(self):
        # Predefined responses for different endpoints
        self._responses = {
            "/repositories": TestResponse(
                200,
                {
                    "repositories": [
                        {
                            "name": "repo1",
                            "url": "https://github.com/user/repo1.git",
                            "is_active": True,
                        },
                        {
                            "name": "repo2",
                            "url": "https://github.com/user/repo2.git",
                            "is_active": False,
                        },
                        {
                            "name": "repo3",
                            "url": "https://github.com/other/repo3.git",
                            "is_active": False,
                        },
                    ]
                },
            ),
            "/repositories/repo1": TestResponse(
                200,
                {
                    "name": "repo1",
                    "status": "active",
                    "last_updated": "2024-01-01T10:00:00Z",
                },
            ),
            "/repositories/repo1/branches": TestResponse(
                200, {"branches": ["main", "develop", "feature/test"]}
            ),
            "/repositories/repo1/branches/main/timestamps": TestResponse(
                200,
                {
                    "local_timestamp": "2024-01-01T10:00:00Z",
                    "remote_timestamp": "2024-01-01T11:00:00Z",
                },
            ),
            "/repositories/repo2/branches/main/timestamps": TestResponse(
                200,
                {
                    "local_timestamp": "2024-01-01T10:00:00Z",
                    "remote_timestamp": "2024-01-01T09:00:00Z",
                },
            ),
        }
        self._fallback_response = TestResponse(404, {"error": "Not found"})

    async def get(self, endpoint: str, **kwargs) -> TestResponse:
        """Get response for endpoint."""
        return self._responses.get(endpoint, self._fallback_response)


class TestRemoteRepositoryService:
    """Test suite for RemoteRepositoryService."""

    @pytest.fixture
    def test_api_client(self):
        """Create test API client with real implementation."""
        return TestAPIClient()

    @pytest.fixture
    def test_staleness_detector(self):
        """Create test staleness detector with real implementation."""
        return StalenessDetector()

    @pytest.fixture
    def mock_api_client(self):
        """Create async mock API client for testing error scenarios."""
        return AsyncMock()

    @pytest.fixture
    def mock_staleness_detector(self):
        """Create mock staleness detector for testing."""
        return Mock()

    @pytest.fixture
    def repository_service(self, test_api_client, test_staleness_detector):
        """Create repository service with real dependencies."""
        return RemoteRepositoryService(test_api_client, test_staleness_detector)

    @pytest.fixture
    def sample_repositories_data(self):
        """Sample repository data from server."""
        return [
            {
                "name": "repo1",
                "url": "https://github.com/user/repo1.git",
                "is_active": True,
            },
            {
                "name": "repo2",
                "url": "https://github.com/user/repo2.git",
                "is_active": False,
            },
            {
                "name": "repo3",
                "url": "https://github.com/other/repo3.git",
                "is_active": False,
            },
        ]

    def test_initialization(self, test_api_client, test_staleness_detector):
        """Test service initialization."""
        service = RemoteRepositoryService(test_api_client, test_staleness_detector)

        assert service.api_client == test_api_client
        assert service.staleness_detector == test_staleness_detector

    @pytest.mark.asyncio
    async def test_fetch_repositories_success(self, repository_service):
        """Test successful repository fetching."""
        # Execute - no mocking, uses real TestAPIClient
        repositories = await repository_service._fetch_repositories()

        # Verify - real data from TestAPIClient
        assert len(repositories) == 3
        assert repositories[0]["name"] == "repo1"
        assert repositories[0]["url"] == "https://github.com/user/repo1.git"
        assert repositories[0]["is_active"] is True

    @pytest.mark.asyncio
    async def test_fetch_repositories_failure(
        self, test_staleness_detector, mock_api_client
    ):
        """Test repository fetching failure."""
        # Create service with mock API client
        service = RemoteRepositoryService(mock_api_client, test_staleness_detector)

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_api_client.get.return_value = mock_response

        # Execute
        repositories = await service._fetch_repositories()

        # Verify empty list returned on failure
        assert repositories == []

    @pytest.mark.asyncio
    async def test_fetch_repositories_exception(
        self, test_staleness_detector, mock_api_client
    ):
        """Test repository fetching with exception."""
        # Create service with mock API client
        service = RemoteRepositoryService(mock_api_client, test_staleness_detector)

        # Setup exception
        mock_api_client.get.side_effect = Exception("Network error")

        # Execute
        repositories = await service._fetch_repositories()

        # Verify empty list returned on exception
        assert repositories == []

    def test_categorize_repositories(self, repository_service):
        """Test repository categorization by URL matching."""
        repositories = [
            RepositoryInfo("repo1", "https://github.com/user/repo1.git", True),
            RepositoryInfo("repo2", "https://github.com/user/repo2.git", False),
            RepositoryInfo("repo3", "https://github.com/other/repo3.git", False),
        ]
        local_repo_url = "git@github.com:user/repo1.git"

        # Execute
        matching, non_matching = repository_service._categorize_repositories(
            repositories, local_repo_url
        )

        # Verify
        assert len(matching) == 1
        assert matching[0].name == "repo1"
        assert len(non_matching) == 2
        assert {repo.name for repo in non_matching} == {"repo2", "repo3"}

    def test_urls_match_https_and_ssh(self, repository_service):
        """Test URL matching between HTTPS and SSH formats."""
        https_url = "https://github.com/user/repo.git"
        ssh_url = "git@github.com:user/repo.git"

        assert repository_service._urls_match(https_url, ssh_url)
        assert repository_service._urls_match(ssh_url, https_url)

    def test_urls_match_with_trailing_slash(self, repository_service):
        """Test URL matching with trailing slashes."""
        url1 = "https://github.com/user/repo.git/"
        url2 = "https://github.com/user/repo.git"

        assert repository_service._urls_match(url1, url2)
        assert repository_service._urls_match(url2, url1)

    def test_urls_match_case_insensitive(self, repository_service):
        """Test URL matching is case insensitive."""
        url1 = "https://GitHub.com/User/Repo.git"
        url2 = "https://github.com/user/repo.git"

        assert repository_service._urls_match(url1, url2)

    def test_normalize_url_ssh_conversion(self, repository_service):
        """Test SSH URL normalization to HTTPS format."""
        ssh_url = "git@github.com:user/repo.git"
        expected = "https://github.com/user/repo"

        normalized = repository_service._normalize_url(ssh_url)
        assert normalized == expected

    def test_normalize_url_https_cleanup(self, repository_service):
        """Test HTTPS URL cleanup."""
        https_url = "https://GitHub.com/User/Repo.git/"
        expected = "https://github.com/user/repo"

        normalized = repository_service._normalize_url(https_url)
        assert normalized == expected

    @pytest.mark.asyncio
    async def test_calculate_staleness_for_repos(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test staleness calculation for repositories."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup repositories
        repositories = [
            RepositoryInfo("repo1", "https://github.com/user/repo1.git", True),
            RepositoryInfo("repo2", "https://github.com/user/repo2.git", False),
        ]

        # Setup mock API responses
        def mock_get_side_effect(endpoint):
            mock_response = Mock()
            if "repo1" in endpoint:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "local_timestamp": "2024-01-01T10:00:00Z",
                    "remote_timestamp": "2024-01-01T11:00:00Z",
                }
            elif "repo2" in endpoint:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "local_timestamp": "2024-01-01T10:00:00Z",
                    "remote_timestamp": "2024-01-01T09:00:00Z",
                }
            return mock_response

        mock_api_client.get.side_effect = mock_get_side_effect

        # Execute
        await repository_service._calculate_staleness_for_repos(repositories, "main")

        # Verify timestamps were set and basic staleness calculation occurred
        assert repositories[0].local_timestamp == "2024-01-01T10:00:00Z"
        assert repositories[0].remote_timestamp == "2024-01-01T11:00:00Z"
        assert repositories[0].staleness_info is not None
        assert repositories[0].staleness_info["is_stale"] is True  # Remote is newer

        assert repositories[1].local_timestamp == "2024-01-01T10:00:00Z"
        assert repositories[1].remote_timestamp == "2024-01-01T09:00:00Z"
        assert repositories[1].staleness_info is not None
        assert repositories[1].staleness_info["is_stale"] is False  # Local is newer

    @pytest.mark.asyncio
    async def test_get_repository_timestamps_success(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test successful timestamp retrieval."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "local_timestamp": "2024-01-01T10:00:00Z",
            "remote_timestamp": "2024-01-01T11:00:00Z",
        }
        mock_api_client.get.return_value = mock_response

        # Execute
        timestamps = await repository_service._get_repository_timestamps(
            "repo1", "main"
        )

        # Verify
        assert timestamps is not None
        assert timestamps["local_timestamp"] == "2024-01-01T10:00:00Z"
        assert timestamps["remote_timestamp"] == "2024-01-01T11:00:00Z"
        mock_api_client.get.assert_called_once_with(
            "/repositories/repo1/branches/main/timestamps"
        )

    @pytest.mark.asyncio
    async def test_get_repository_timestamps_not_found(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test timestamp retrieval when not found."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_api_client.get.return_value = mock_response

        # Execute
        timestamps = await repository_service._get_repository_timestamps(
            "repo1", "main"
        )

        # Verify
        assert timestamps is None

    def test_generate_staleness_summary(self, repository_service):
        """Test staleness summary generation."""
        # Setup repositories with staleness info
        repositories = [
            RepositoryInfo("repo1", "url1", True),
            RepositoryInfo("repo2", "url2", False),
            RepositoryInfo("repo3", "url3", False),
        ]

        # Set staleness info
        repositories[0].staleness_info = {"is_stale": True}
        repositories[1].staleness_info = {"is_stale": False}
        repositories[2].staleness_info = None

        # Execute
        summary = repository_service._generate_staleness_summary(repositories)

        # Verify
        assert summary["total_repositories"] == 3
        assert summary["stale_count"] == 1
        assert summary["fresh_count"] == 1
        assert summary["unknown_count"] == 1
        assert summary["stale_repositories"] == ["repo1"]
        assert summary["fresh_repositories"] == ["repo2"]
        assert summary["unknown_repositories"] == ["repo3"]

    @pytest.mark.asyncio
    async def test_get_repository_analysis_full_flow(
        self,
        mock_api_client,
        mock_staleness_detector,
        sample_repositories_data,
    ):
        """Test complete repository analysis flow."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mocks
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"repositories": sample_repositories_data}
        mock_api_client.get.return_value = mock_response

        # Execute
        analysis = await repository_service.get_repository_analysis(
            "https://github.com/user/repo1.git", "main"
        )

        # Verify
        assert isinstance(analysis, RepositoryAnalysis)
        assert len(analysis.repositories) == 3
        assert analysis.active_repo is not None
        assert analysis.active_repo.name == "repo1"
        assert len(analysis.matching_repos) == 1  # Only repo1 matches exactly
        assert len(analysis.non_matching_repos) == 2  # repo2 and repo3 don't match
        assert isinstance(analysis.staleness_summary, dict)

    @pytest.mark.asyncio
    async def test_get_repository_details_success(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test successful repository details retrieval."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "repo1",
            "status": "active",
            "last_updated": "2024-01-01T10:00:00Z",
        }
        mock_api_client.get.return_value = mock_response

        # Execute
        details = await repository_service.get_repository_details("repo1")

        # Verify
        assert details is not None
        assert details["name"] == "repo1"
        assert details["status"] == "active"
        mock_api_client.get.assert_called_once_with("/repositories/repo1")

    @pytest.mark.asyncio
    async def test_get_repository_details_not_found(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test repository details when not found."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_api_client.get.return_value = mock_response

        # Execute
        details = await repository_service.get_repository_details("repo1")

        # Verify
        assert details is None

    @pytest.mark.asyncio
    async def test_get_repository_branches_success(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test successful repository branches retrieval."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "branches": ["main", "develop", "feature/test"]
        }
        mock_api_client.get.return_value = mock_response

        # Execute
        branches = await repository_service.get_repository_branches("repo1")

        # Verify
        assert branches == ["main", "develop", "feature/test"]
        mock_api_client.get.assert_called_once_with("/repositories/repo1/branches")

    @pytest.mark.asyncio
    async def test_get_repository_branches_failure(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test repository branches retrieval failure."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_api_client.get.return_value = mock_response

        # Execute
        branches = await repository_service.get_repository_branches("repo1")

        # Verify
        assert branches == []

    @pytest.mark.asyncio
    async def test_get_repository_branches_exception(
        self, mock_api_client, mock_staleness_detector
    ):
        """Test repository branches retrieval with exception."""
        # Create service with mock clients
        repository_service = RemoteRepositoryService(
            mock_api_client, mock_staleness_detector
        )

        # Setup exception
        mock_api_client.get.side_effect = Exception("Network error")

        # Execute
        branches = await repository_service.get_repository_branches("repo1")

        # Verify
        assert branches == []


class TestRepositoryInfo:
    """Test suite for RepositoryInfo dataclass."""

    def test_repository_info_creation(self):
        """Test RepositoryInfo creation with required fields."""
        repo_info = RepositoryInfo(
            name="test-repo", url="https://github.com/user/repo.git", is_active=True
        )

        assert repo_info.name == "test-repo"
        assert repo_info.url == "https://github.com/user/repo.git"
        assert repo_info.is_active is True
        assert repo_info.local_timestamp is None
        assert repo_info.remote_timestamp is None
        assert repo_info.staleness_info is None

    def test_repository_info_with_optional_fields(self):
        """Test RepositoryInfo creation with optional fields."""
        staleness_info = {"is_stale": True, "difference": "1 hour"}

        repo_info = RepositoryInfo(
            name="test-repo",
            url="https://github.com/user/repo.git",
            is_active=False,
            local_timestamp="2024-01-01T10:00:00Z",
            remote_timestamp="2024-01-01T11:00:00Z",
            staleness_info=staleness_info,
        )

        assert repo_info.local_timestamp == "2024-01-01T10:00:00Z"
        assert repo_info.remote_timestamp == "2024-01-01T11:00:00Z"
        assert repo_info.staleness_info == staleness_info


class TestRepositoryAnalysis:
    """Test suite for RepositoryAnalysis dataclass."""

    def test_repository_analysis_creation(self):
        """Test RepositoryAnalysis creation."""
        repositories = [
            RepositoryInfo("repo1", "url1", True),
            RepositoryInfo("repo2", "url2", False),
        ]
        active_repo = repositories[0]
        matching_repos = [repositories[0]]
        non_matching_repos = [repositories[1]]
        staleness_summary = {"total": 2, "stale": 0, "fresh": 1}

        analysis = RepositoryAnalysis(
            repositories=repositories,
            active_repo=active_repo,
            matching_repos=matching_repos,
            non_matching_repos=non_matching_repos,
            staleness_summary=staleness_summary,
        )

        assert analysis.repositories == repositories
        assert analysis.active_repo == active_repo
        assert analysis.matching_repos == matching_repos
        assert analysis.non_matching_repos == non_matching_repos
        assert analysis.staleness_summary == staleness_summary
