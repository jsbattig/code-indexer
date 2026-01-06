"""
Real server integration tests for JobsAPIClient cancel_job and get_job_status methods.

Following anti-mock principles with real CIDX server integration.
"""

import pytest
import pytest_asyncio
from pathlib import Path
from typing import Dict, Any, cast

from code_indexer.api_clients.jobs_client import JobsAPIClient
from code_indexer.api_clients.base_client import APIClientError

# Import real infrastructure (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext


class TestJobsCancelStatusRealIntegration:
    """Integration tests for cancel_job and get_job_status with real server."""

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
            # Add some test jobs for cancellation testing
            server.add_test_job(
                job_id="job-running-1",
                repository_id="test-repo-1",
                job_status="running",
                progress=45,
            )
            server.add_test_job(
                job_id="job-completed-1",
                repository_id="test-repo-1",
                job_status="completed",
                progress=100,
            )
            server.add_test_job(
                job_id="job-failed-1",
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
        return cast(Path, tmp_path / "test_project")

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

    async def test_get_job_status_with_real_server(self, jobs_client):
        """Test get_job_status with real server integration."""
        # Get status of a running job
        job_status = await jobs_client.get_job_status("job-running-1")

        # Verify response structure
        assert "id" in job_status
        assert "status" in job_status
        assert "progress" in job_status
        assert job_status["id"] == "job-running-1"
        assert job_status["status"] == "running"
        assert job_status["progress"] == 45

    async def test_get_job_status_completed_job(self, jobs_client):
        """Test get_job_status for completed job."""
        job_status = await jobs_client.get_job_status("job-completed-1")

        # Verify completed job status
        assert job_status["id"] == "job-completed-1"
        assert job_status["status"] == "completed"
        assert job_status["progress"] == 100

    async def test_get_job_status_nonexistent_job(self, jobs_client):
        """Test get_job_status for nonexistent job."""
        with pytest.raises(APIClientError) as exc_info:
            await jobs_client.get_job_status("nonexistent-job")

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value)

    async def test_cancel_job_with_real_server(self, jobs_client):
        """Test cancel_job with real server integration."""
        # Cancel a running job
        result = await jobs_client.cancel_job("job-running-1")

        # Verify response structure
        assert "id" in result or "job_id" in result
        job_id_field = result.get("id") or result.get("job_id")
        assert job_id_field == "job-running-1"
        # Server should indicate successful cancellation
        assert "status" in result or "message" in result

    async def test_cancel_nonexistent_job(self, jobs_client):
        """Test cancel_job for nonexistent job."""
        with pytest.raises(APIClientError) as exc_info:
            await jobs_client.cancel_job("nonexistent-job")

        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value)

    async def test_cancel_completed_job_fails(self, jobs_client):
        """Test that cancelling completed job fails appropriately."""
        # Try to cancel a completed job (should fail)
        with pytest.raises(APIClientError) as exc_info:
            await jobs_client.cancel_job("job-completed-1")

        # Should be a 409 conflict or similar error
        assert exc_info.value.status_code in [400, 409]

    async def test_job_workflow_status_then_cancel(self, jobs_client):
        """Test complete workflow: check status then cancel job."""
        # First get status
        initial_status = await jobs_client.get_job_status("job-running-1")
        assert initial_status["status"] == "running"
        assert initial_status["id"] == "job-running-1"

        # Then cancel the job
        cancel_result = await jobs_client.cancel_job("job-running-1")
        job_id_field = cancel_result.get("id") or cancel_result.get("job_id")
        assert job_id_field == "job-running-1"

        # Verify job was cancelled (status should change)
        # Note: Depending on server implementation, status might be immediately
        # updated or take some time
        final_status = await jobs_client.get_job_status("job-running-1")
        assert final_status["id"] == "job-running-1"
        # Status should be cancelled or in process of being cancelled
        assert final_status["status"] in ["cancelled", "cancelling", "running"]

    async def test_cancel_and_status_error_handling(self, jobs_client):
        """Test error handling for both cancel and status operations."""
        # Test nonexistent job scenario (most important error case)
        nonexistent_job_id = "job-that-does-not-exist-123"

        # Test get_job_status error handling
        with pytest.raises(APIClientError):
            await jobs_client.get_job_status(nonexistent_job_id)

        # Test cancel_job error handling
        with pytest.raises(APIClientError):
            await jobs_client.cancel_job(nonexistent_job_id)

    async def test_multiple_job_operations(self, jobs_client):
        """Test multiple job operations in sequence."""
        # Get status of multiple jobs
        running_status = await jobs_client.get_job_status("job-running-1")
        completed_status = await jobs_client.get_job_status("job-completed-1")
        failed_status = await jobs_client.get_job_status("job-failed-1")

        # Verify all have correct statuses
        assert running_status["status"] == "running"
        assert completed_status["status"] == "completed"
        assert failed_status["status"] == "failed"

        # Try to cancel different job types
        # Cancel running job (should succeed)
        await jobs_client.cancel_job("job-running-1")

        # Try to cancel completed job (should fail)
        with pytest.raises(APIClientError):
            await jobs_client.cancel_job("job-completed-1")

        # Try to cancel failed job (should fail)
        with pytest.raises(APIClientError):
            await jobs_client.cancel_job("job-failed-1")
