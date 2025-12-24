"""
Real server integration tests for JobsAPIClient cancel_job method.

Following anti-mock principles with comprehensive real CIDX server integration.
Tests job cancellation functionality with real authentication and HTTP endpoints.
"""

import pytest
import pytest_asyncio
from pathlib import Path
from typing import Dict, Any

from code_indexer.api_clients.jobs_client import JobsAPIClient
from code_indexer.api_clients.base_client import APIClientError, AuthenticationError

# Import real infrastructure (no mocks)
from tests.infrastructure.test_cidx_server import CIDXServerTestContext


class TestJobsAPIClientCancelRealServer:
    """Real server integration tests for JobsAPIClient cancel_job method."""

    @pytest_asyncio.fixture
    async def real_server(self):
        """Real CIDX server for testing."""
        async with CIDXServerTestContext() as server:
            # Add test repositories
            server.add_test_repository(
                repo_id="test-repo-cancel",
                name="Cancel Test Repository",
                path="/test/cancel/repo",
                branches=["main", "develop"],
                default_branch="main",
            )
            # Add test jobs for cancellation scenarios
            server.add_test_job(
                job_id="job-cancellable-1",
                repository_id="test-repo-cancel",
                job_status="running",
                progress=30,
            )
            server.add_test_job(
                job_id="job-completed-2",
                repository_id="test-repo-cancel",
                job_status="completed",
                progress=100,
            )
            server.add_test_job(
                job_id="job-failed-3",
                repository_id="test-repo-cancel",
                job_status="failed",
                progress=50,
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
    async def api_client(
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

    def test_cancel_job_method_exists(self, api_client):
        """Test that cancel_job method exists and is callable."""
        assert hasattr(api_client, "cancel_job")
        assert callable(getattr(api_client, "cancel_job"))

    async def test_cancel_job_success(self, api_client):
        """Test successful job cancellation with real server."""
        job_id = "job-cancellable-1"

        # Cancel a running job using real API
        result = await api_client.cancel_job(job_id)

        # Verify response structure from real server
        assert "id" in result or "job_id" in result
        job_id_field = result.get("id") or result.get("job_id")
        assert job_id_field == job_id
        # Real server should provide status or message
        assert "status" in result or "message" in result

    async def test_cancel_job_not_found(self, api_client):
        """Test job cancellation when job not found with real server."""
        job_id = "nonexistent-job-999"

        # Try to cancel nonexistent job using real API
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job(job_id)

        # Verify real server response
        assert exc_info.value.status_code == 404
        assert "Job not found" in str(exc_info.value)

    async def test_cancel_job_already_completed(self, api_client):
        """Test job cancellation when job already completed with real server."""
        job_id = "job-completed-2"

        # Try to cancel completed job using real API
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job(job_id)

        # Real server should return conflict error
        assert exc_info.value.status_code in [400, 409]
        assert "cancel" in str(exc_info.value).lower()

    async def test_cancel_job_authentication_error(self, real_server, project_root):
        """Test job cancellation with authentication failure using real server."""
        # Create client with invalid credentials
        invalid_credentials = {
            "username": "invalid_user",
            "password": "wrong_password",
        }

        client = JobsAPIClient(
            server_url=real_server.base_url,
            credentials=invalid_credentials,
            project_root=project_root,
        )

        try:
            job_id = "job-cancellable-1"
            # Real authentication failure
            with pytest.raises(AuthenticationError):
                await client.cancel_job(job_id)
        finally:
            await client.close()

    async def test_cancel_job_with_failed_job(self, api_client):
        """Test job cancellation with failed job using real server."""
        job_id = "job-failed-3"

        # Try to cancel failed job using real API
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job(job_id)

        # Real server should indicate job cannot be cancelled
        assert exc_info.value.status_code in [400, 409]
        error_message = str(exc_info.value).lower()
        assert "cancel" in error_message or "failed" in error_message

    async def test_multiple_cancel_operations(self, api_client):
        """Test multiple job cancellation operations with real server."""
        # Test cancelling the same running job twice
        job_id = "job-cancellable-1"

        # First cancellation should succeed
        result = await api_client.cancel_job(job_id)
        job_id_field = result.get("id") or result.get("job_id")
        assert job_id_field == job_id

        # Second cancellation might fail or succeed depending on server implementation
        # Just verify we get a proper response (no unhandled exceptions)
        try:
            await api_client.cancel_job(job_id)
        except APIClientError as e:
            # Acceptable outcome - job already cancelled
            assert e.status_code in [400, 404, 409]

    def test_cancel_job_input_validation(self, api_client):
        """Test cancel_job method signature and parameters."""
        import inspect

        # Get method signature
        sig = inspect.signature(api_client.cancel_job)
        params = list(sig.parameters.keys())

        # Should have job_id parameter
        assert "job_id" in params

        # job_id should be required (no default)
        job_id_param = sig.parameters["job_id"]
        assert job_id_param.default == inspect.Parameter.empty

        # Should only have job_id parameter (no reason parameter)
        assert len(params) == 1

    async def test_comprehensive_cancel_workflow(self, api_client):
        """Test comprehensive job cancellation workflow with real server."""
        # Test the complete workflow: list jobs, get status, cancel job

        # First, list jobs to see what's available
        jobs_response = await api_client.list_jobs()
        assert "jobs" in jobs_response or "items" in jobs_response

        # Get status of cancellable job
        job_id = "job-cancellable-1"
        status_response = await api_client.get_job_status(job_id)
        assert status_response["id"] == job_id
        assert status_response["status"] == "running"

        # Cancel the job
        cancel_response = await api_client.cancel_job(job_id)
        job_id_field = cancel_response.get("id") or cancel_response.get("job_id")
        assert job_id_field == job_id

        # Verify status may have changed (depending on server implementation)
        final_status = await api_client.get_job_status(job_id)
        assert final_status["id"] == job_id
        # Status should be cancelled, cancelling, or still running (server-dependent)
        assert final_status["status"] in ["cancelled", "cancelling", "running"]

    async def test_real_error_handling_scenarios(self, api_client):
        """Test real error handling scenarios with actual server responses."""
        # Test various error scenarios with real server

        # 1. Nonexistent job
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job("job-does-not-exist-999")
        assert exc_info.value.status_code == 404

        # 2. Completed job
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job("job-completed-2")
        assert exc_info.value.status_code in [400, 409]

        # 3. Failed job
        with pytest.raises(APIClientError) as exc_info:
            await api_client.cancel_job("job-failed-3")
        assert exc_info.value.status_code in [400, 409]

        # All errors should be properly classified APIClientErrors
        # with appropriate status codes from real server responses
