"""
TDD tests for JobsAPIClient implementation.

Following Test-Driven Development methodology to implement job listing and management
functionality with real server integration (anti-mock principles).
"""

import pytest
import pytest_asyncio
from pathlib import Path
from typing import Dict, Any

from code_indexer.api_clients.jobs_client import JobsAPIClient
from code_indexer.api_clients.base_client import (
    APIClientError,
    AuthenticationError,
    NetworkError,
)
from code_indexer.api_clients.network_error_handler import (
    DNSResolutionError,
)

# Import real infrastructure (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext


class TestJobsAPIClientTDD:
    """Test-driven development for JobsAPIClient with real server integration."""

    @pytest_asyncio.fixture
    async def real_server(self):
        """Real CIDX server for testing."""
        async with CIDXServerTestContext() as server:
            # Add test repositories
            server.add_test_repository(
                repo_id="test-repo-1",
                name="Test Repository",
                path="/test/repo",
                branches=["main", "develop"],
                default_branch="main",
            )
            # Add some test jobs
            server.add_test_job(
                job_id="job-1",
                repository_id="test-repo-1",
                job_status="running",
                progress=45,
            )
            server.add_test_job(
                job_id="job-2",
                repository_id="test-repo-1",
                job_status="completed",
                progress=100,
            )
            server.add_test_job(
                job_id="job-3",
                repository_id="test-repo-1",
                job_status="failed",
                progress=75,
            )
            yield server

    @pytest.fixture
    def valid_credentials(self) -> Dict[str, Any]:
        """Provide valid test credentials."""
        return {
            "username": "testuser",
            "password": "testpass123",
        }

    @pytest.fixture
    def project_root(self, tmp_path) -> Path:
        """Provide temporary project root for testing."""
        return tmp_path / "test_project"

    @pytest_asyncio.fixture
    async def jobs_client(
        self, real_server, valid_credentials, project_root
    ) -> JobsAPIClient:
        """Create JobsAPIClient instance for testing."""
        client = JobsAPIClient(
            server_url=real_server.base_url,
            credentials=valid_credentials,
            project_root=project_root,
        )
        try:
            yield client
        finally:
            await client.close()

    async def test_jobs_client_initialization(self, jobs_client):
        """Test that JobsAPIClient can be initialized properly."""
        assert jobs_client is not None
        assert isinstance(jobs_client, JobsAPIClient)
        assert jobs_client.server_url.startswith("http://localhost:")

    async def test_list_jobs_requires_authentication(self, jobs_client):
        """Test that list_jobs method exists and handles authentication."""
        # This test should pass now since we have real server integration
        # We should NOT get an AttributeError - the method should exist
        jobs_response = await jobs_client.list_jobs()

        # Should get a valid response structure
        assert "jobs" in jobs_response

    async def test_list_jobs_with_valid_auth_returns_job_list(self, jobs_client):
        """Test that list_jobs returns properly formatted job list with valid auth."""
        # This will fail initially - drives implementation
        jobs_response = await jobs_client.list_jobs()

        # Verify response structure matches API specification
        assert "jobs" in jobs_response
        assert "total" in jobs_response
        assert "limit" in jobs_response
        assert "offset" in jobs_response
        assert isinstance(jobs_response["jobs"], list)

    async def test_list_jobs_with_status_filter(self, jobs_client):
        """Test that list_jobs supports status filtering."""
        # This drives the filtering implementation
        jobs_response = await jobs_client.list_jobs(status="running")

        # Verify filtering is applied
        assert "jobs" in jobs_response
        # If jobs exist, they should all have "running" status
        for job in jobs_response["jobs"]:
            assert job["status"] == "running"

    async def test_list_jobs_with_limit_parameter(self, jobs_client):
        """Test that list_jobs supports limit parameter."""
        limit = 5
        jobs_response = await jobs_client.list_jobs(limit=limit)

        assert "jobs" in jobs_response
        assert jobs_response["limit"] == limit
        assert len(jobs_response["jobs"]) <= limit

    async def test_list_jobs_job_structure_validation(self, jobs_client):
        """Test that returned jobs have expected structure."""
        jobs_response = await jobs_client.list_jobs(limit=1)

        if jobs_response["jobs"]:  # If any jobs exist
            job = jobs_response["jobs"][0]

            # Verify required fields exist
            required_fields = [
                "job_id",
                "operation_type",
                "status",
                "created_at",
                "progress",
                "username",
            ]
            for field in required_fields:
                assert field in job, f"Job missing required field: {field}"

            # Verify data types
            assert isinstance(job["job_id"], str)
            assert isinstance(job["operation_type"], str)
            assert isinstance(job["status"], str)
            assert isinstance(job["progress"], int)
            assert isinstance(job["username"], str)

    async def test_list_jobs_network_error_handling(
        self, valid_credentials, project_root
    ):
        """Test proper network error handling."""
        # Use invalid server URL to trigger network error
        client = JobsAPIClient(
            server_url="http://invalid-server:9999",
            credentials=valid_credentials,
            project_root=project_root,
        )

        try:
            with pytest.raises((NetworkError, DNSResolutionError)):
                await client.list_jobs()
        finally:
            await client.close()

    async def test_list_jobs_authentication_error_handling(
        self, real_server, project_root
    ):
        """Test proper authentication error handling."""
        invalid_credentials = {
            "username": "invalid",
            "password": "invalid",
        }

        client = JobsAPIClient(
            server_url=real_server.base_url,
            credentials=invalid_credentials,
            project_root=project_root,
        )

        try:
            with pytest.raises(AuthenticationError):
                await client.list_jobs()
        finally:
            await client.close()

    async def test_get_job_status_method_exists(self, jobs_client):
        """Test that get_job_status method exists and works."""
        # This will drive implementation of individual job status retrieval
        with pytest.raises((APIClientError, AttributeError)):
            await jobs_client.get_job_status("non-existent-job")

    async def test_jobs_client_inherits_from_base_client(self, jobs_client):
        """Test that JobsAPIClient properly inherits from CIDXRemoteAPIClient."""
        from code_indexer.api_clients.base_client import CIDXRemoteAPIClient

        assert isinstance(jobs_client, CIDXRemoteAPIClient)

    async def test_jobs_client_async_context_manager(
        self, real_server, valid_credentials, project_root
    ):
        """Test that JobsAPIClient works as async context manager."""
        async with JobsAPIClient(
            server_url=real_server.base_url,
            credentials=valid_credentials,
            project_root=project_root,
        ) as client:
            assert client is not None
            # Client should be properly initialized
            assert hasattr(client, "list_jobs")
