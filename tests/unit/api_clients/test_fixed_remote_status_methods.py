"""Test Coverage for Fixed RemoteStatusDisplayer Methods.

Tests the newly added get_repository_status() and check_staleness() methods
that were added to fix business logic integration test failures.
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from code_indexer.remote_status import RemoteStatusDisplayer
from code_indexer.remote.models import RepositoryStatus, StalenessInfo
from code_indexer.remote.services.repository_service import RemoteRepositoryService


class TestFixedRemoteStatusMethods:
    """Tests for newly added RemoteStatusDisplayer methods."""

    @pytest.fixture
    def mock_project_with_config(self, tmp_path):
        """Create a mock project with remote configuration."""
        project_root = tmp_path / "test_project"
        project_root.mkdir()

        config_dir = project_root / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / ".remote-config"

        remote_config = {
            "server_url": "http://localhost:8001",
            "encrypted_credentials": {
                "username": "test_user",
                "password": "test_password",
            },
            "repository_link": {
                "alias": "test-repo",
                "url": "https://github.com/test/repo.git",
                "branch": "main",
            },
        }

        with open(config_file, "w") as f:
            json.dump(remote_config, f)

        return project_root, config_file

    @pytest.fixture
    def status_displayer(self, mock_project_with_config):
        """Create RemoteStatusDisplayer with mock config."""
        # Create mock services for dependency injection
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )
        return RemoteStatusDisplayer(repository_service=mock_repository_service)

    @pytest.mark.asyncio
    async def test_get_repository_status_success(self, status_displayer):
        """Test get_repository_status returns expected structure."""
        repository_alias = "test-repo"

        # Configure mock repository service to return test data
        test_repository_details = {
            "status": "active",
            "last_updated": "2024-01-15T10:30:00Z",
            "branch": "main",
            "commit_count": 100,
            "last_commit_sha": "abc123def456",
            "indexing_progress": 100,
        }
        status_displayer.repository_service.get_repository_details = AsyncMock(
            return_value=test_repository_details
        )

        status = await status_displayer.get_repository_status(repository_alias)

        # Verify status is a proper RepositoryStatus Pydantic model
        assert isinstance(status, RepositoryStatus)

        # Verify values
        assert status.repository_alias == repository_alias
        assert status.status == "active"  # From mock data with completed indexing
        assert status.last_updated == "2024-01-15T10:30:00Z"  # From mock branch data

    @pytest.mark.asyncio
    async def test_get_repository_status_missing_config(self, tmp_path):
        """Test get_repository_status with missing repository."""
        # Create mock services that simulate missing repository
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )
        mock_repository_service.get_repository_details = AsyncMock(return_value=None)

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        from code_indexer.api_clients.repository_linking_client import (
            RepositoryNotFoundError,
        )

        with pytest.raises(
            RepositoryNotFoundError, match="Repository test-repo not found"
        ):
            await status_displayer.get_repository_status("test-repo")

    @pytest.mark.asyncio
    async def test_check_staleness_success(self, status_displayer):
        """Test check_staleness returns expected structure."""
        local_timestamp = "2024-01-15T10:30:00Z"
        repository_alias = "test-repo"

        # Configure mock repository service to return test data
        test_repository_details = {
            "status": "active",
            "last_updated": "2024-01-15T10:30:00Z",
            "branch": "main",
            "commit_count": 100,
            "last_commit_sha": "abc123def456",
            "indexing_progress": 100,
        }
        status_displayer.repository_service.get_repository_details = AsyncMock(
            return_value=test_repository_details
        )

        staleness_info = await status_displayer.check_staleness(
            local_timestamp=local_timestamp, repository_alias=repository_alias
        )

        # Verify staleness_info is a proper StalenessInfo Pydantic model
        assert isinstance(staleness_info, StalenessInfo)

        # Verify values
        assert isinstance(staleness_info.is_stale, bool)
        assert staleness_info.local_timestamp == local_timestamp
        assert (
            staleness_info.remote_timestamp == "2024-01-15T10:30:00Z"
        )  # From mock branch data
        # Since timestamps are equal, should not be stale
        assert staleness_info.is_stale is False

    @pytest.mark.asyncio
    async def test_check_staleness_missing_config(self, tmp_path):
        """Test check_staleness with missing repository."""
        # Create mock services that simulate missing repository
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )
        mock_repository_service.get_repository_details = AsyncMock(return_value=None)

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        from code_indexer.api_clients.repository_linking_client import (
            RepositoryNotFoundError,
        )

        with pytest.raises(
            RepositoryNotFoundError, match="Repository test-repo not found"
        ):
            await status_displayer.check_staleness(
                local_timestamp="2024-01-15T10:30:00Z", repository_alias="test-repo"
            )

    @pytest.mark.asyncio
    async def test_get_repository_status_corrupted_config(self, tmp_path):
        """Test get_repository_status with API client error."""
        # Create mock services that simulate API client error
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )
        # Simulate API error that might be caused by configuration issues
        from code_indexer.api_clients.base_client import APIClientError

        mock_repository_service.get_repository_details = AsyncMock(
            side_effect=APIClientError("Configuration error")
        )

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        with pytest.raises(APIClientError, match="Configuration error"):
            await status_displayer.get_repository_status("test-repo")

    @pytest.mark.asyncio
    async def test_check_staleness_corrupted_config(self, tmp_path):
        """Test check_staleness with API client error."""
        # Create mock services that simulate API client error
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )
        # Simulate API error that might be caused by configuration issues
        from code_indexer.api_clients.base_client import APIClientError

        mock_repository_service.get_repository_details = AsyncMock(
            side_effect=APIClientError("Configuration error")
        )

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        with pytest.raises(APIClientError, match="Configuration error"):
            await status_displayer.check_staleness(
                local_timestamp="2024-01-15T10:30:00Z", repository_alias="test-repo"
            )

    def test_remotestatusdisplayer_constructor_parameters(self, tmp_path):
        """Test RemoteStatusDisplayer constructor with correct parameters."""
        # Create mock repository service
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        assert status_displayer.repository_service == mock_repository_service

    def test_remotestatusdisplayer_constructor_wrong_parameters(self):
        """Test RemoteStatusDisplayer constructor rejects wrong parameters."""
        # Verify that the old incorrect constructor call fails
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            RemoteStatusDisplayer(
                server_url="http://localhost:8001",
                credentials={"username": "test", "password": "test"},
            )


class TestRemoteStatusDisplayerIntegration:
    """Integration tests for RemoteStatusDisplayer with real config scenarios."""

    @pytest.mark.asyncio
    async def test_complete_status_workflow(self, tmp_path):
        """Test complete workflow: get status, check staleness."""
        # Create mock services with test data
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )

        # Configure mock repository service to return test data
        test_repository_details = {
            "status": "active",
            "last_updated": "2024-01-15T10:00:00Z",
            "branch": "main",
            "commit_count": 50,
            "last_commit_sha": "workflow123",
            "indexing_progress": 100,
        }
        mock_repository_service.get_repository_details = AsyncMock(
            return_value=test_repository_details
        )

        # Test workflow with mocked services
        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        # Step 1: Get repository status
        status = await status_displayer.get_repository_status("workflow-repo")
        assert isinstance(status, RepositoryStatus)
        assert status.repository_alias == "workflow-repo"
        assert status.status == "active"

        # Step 2: Check staleness
        staleness_info = await status_displayer.check_staleness(
            local_timestamp="2024-01-15T09:00:00Z", repository_alias="workflow-repo"
        )
        assert isinstance(staleness_info, StalenessInfo)
        assert staleness_info.local_timestamp == "2024-01-15T09:00:00Z"
        assert isinstance(staleness_info.is_stale, bool)
        # Local is older (09:00) than remote (10:00), so should be stale
        assert staleness_info.is_stale is True

    @pytest.mark.asyncio
    async def test_different_repository_aliases(self, tmp_path):
        """Test methods work with different repository aliases."""
        # Create mock services
        mock_api_client = AsyncMock()
        mock_staleness_detector = MagicMock()
        mock_repository_service = RemoteRepositoryService(
            api_client=mock_api_client, staleness_detector=mock_staleness_detector
        )

        # Configure mock to return test data for any repository
        test_repository_details = {
            "status": "active",
            "last_updated": "2024-01-15T10:00:00Z",
            "branch": "main",
            "commit_count": 25,
            "last_commit_sha": "alias123",
            "indexing_progress": 100,
        }
        mock_repository_service.get_repository_details = AsyncMock(
            return_value=test_repository_details
        )

        status_displayer = RemoteStatusDisplayer(
            repository_service=mock_repository_service
        )

        # Test different aliases
        for alias in ["repo-1", "my-special-repo", "test_repo_123"]:
            status = await status_displayer.get_repository_status(alias)
            assert isinstance(status, RepositoryStatus)
            assert status.repository_alias == alias

            staleness = await status_displayer.check_staleness(
                "2024-01-15T10:00:00Z", alias
            )
            assert isinstance(staleness, StalenessInfo)
            assert staleness.local_timestamp == "2024-01-15T10:00:00Z"
            # Timestamps are equal, so should not be stale
            assert staleness.is_stale is False
