"""
Unit tests for delegation callback receiver endpoint.

Story #720: Callback-Based Delegation Job Completion

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI


@pytest.fixture
def reset_tracker_singleton():
    """Reset the DelegationJobTracker singleton between tests."""
    from code_indexer.server.services.delegation_job_tracker import (
        DelegationJobTracker,
    )

    DelegationJobTracker._instance = None
    yield
    DelegationJobTracker._instance = None


@pytest.fixture
def app_with_callback_router(reset_tracker_singleton):
    """Create a FastAPI app with the delegation callbacks router."""
    from code_indexer.server.routers.delegation_callbacks import router

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app_with_callback_router):
    """Create a test client for the callback router."""
    return TestClient(app_with_callback_router)


class TestDelegationCallbackEndpoint:
    """Tests for the delegation callback receiver endpoint."""

    def test_callback_endpoint_exists(self, client):
        """
        POST /api/delegation/callback/{job_id} endpoint exists.

        Given the router is mounted
        When a POST request is made to the callback endpoint
        Then the endpoint should respond (not 404)
        """
        response = client.post(
            "/api/delegation/callback/test-job-id",
            json={
                "JobId": "test-job-id",
                "Status": "completed",
                "Output": "Test output",
                "ExitCode": 0,
            },
        )
        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_callback_receives_completed_job(self, client, reset_tracker_singleton):
        """
        Callback receives completed job and calls complete_job on tracker.

        Given a job is registered in the tracker
        When the callback endpoint receives a completed job payload
        Then it should call complete_job on the tracker
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )
        import asyncio

        tracker = DelegationJobTracker.get_instance()
        # Register the job
        asyncio.get_event_loop().run_until_complete(tracker.register_job("job-12345"))

        response = client.post(
            "/api/delegation/callback/job-12345",
            json={
                "JobId": "job-12345",
                "Status": "completed",
                "Output": "The authentication uses JWT tokens.",
                "ExitCode": 0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["received"] is True

        # Verify the future was completed
        assert tracker._pending_jobs["job-12345"].done()
        result = tracker._pending_jobs["job-12345"].result()
        assert result.output == "The authentication uses JWT tokens."
        assert result.status == "completed"

    def test_callback_receives_failed_job(self, client, reset_tracker_singleton):
        """
        Callback receives failed job with error field.

        Given a job is registered in the tracker
        When the callback endpoint receives a failed job payload
        Then it should store the error in the JobResult
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )
        import asyncio

        tracker = DelegationJobTracker.get_instance()
        asyncio.get_event_loop().run_until_complete(tracker.register_job("job-99999"))

        response = client.post(
            "/api/delegation/callback/job-99999",
            json={
                "JobId": "job-99999",
                "Status": "failed",
                "Output": "Repository clone failed",
                "ExitCode": 1,
            },
        )

        assert response.status_code == 200

        result = tracker._pending_jobs["job-99999"].result()
        assert result.status == "failed"
        assert result.exit_code == 1
        # Output field may contain the error message for failed jobs
        assert result.output == "Repository clone failed"

    def test_callback_handles_unknown_job(self, client, reset_tracker_singleton):
        """
        Callback handles unknown job_id gracefully.

        Given a job_id that is not registered
        When the callback endpoint receives a payload for that job
        Then it should return 200 with received=true but acknowledge job not found
        """
        response = client.post(
            "/api/delegation/callback/unknown-job",
            json={
                "JobId": "unknown-job",
                "Status": "completed",
                "Output": "Output for unknown job",
                "ExitCode": 0,
            },
        )

        # Endpoint should still return 200 to acknowledge receipt
        # (Claude Server needs to know the callback was received)
        assert response.status_code == 200
        data = response.json()
        # But should indicate the job was not found in tracker
        assert "job_found" in data or "received" in data

    def test_callback_uses_job_id_from_path(self, client, reset_tracker_singleton):
        """
        Callback uses job_id from URL path, not payload.

        Given a job is registered with a specific job_id
        When the callback payload has a different JobId
        Then the path job_id should be used
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )
        import asyncio

        tracker = DelegationJobTracker.get_instance()
        asyncio.get_event_loop().run_until_complete(tracker.register_job("path-job-id"))

        response = client.post(
            "/api/delegation/callback/path-job-id",
            json={
                "JobId": "payload-job-id",  # Different from path
                "Status": "completed",
                "Output": "Test output",
                "ExitCode": 0,
            },
        )

        assert response.status_code == 200
        # The path job_id should be completed, not the payload JobId
        assert tracker._pending_jobs["path-job-id"].done()

    def test_callback_payload_fields_match_claude_server(
        self, client, reset_tracker_singleton
    ):
        """
        Callback accepts full Claude Server JobCallbackPayload fields.

        Given a job is registered
        When the callback receives the full Claude Server payload
        Then it should parse all relevant fields correctly
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )
        import asyncio

        tracker = DelegationJobTracker.get_instance()
        asyncio.get_event_loop().run_until_complete(
            tracker.register_job("full-payload-job")
        )

        # Full Claude Server payload (matching JobCallbackPayload in C#)
        response = client.post(
            "/api/delegation/callback/full-payload-job",
            json={
                "JobId": "full-payload-job",
                "Status": "completed",
                "Title": "Semantic search job",
                "Username": "testuser",
                "Repository": "main-app",
                "CreatedAt": "2025-01-14T10:00:00Z",
                "StartedAt": "2025-01-14T10:00:05Z",
                "CompletedAt": "2025-01-14T10:05:30Z",
                "ExitCode": 0,
                "Output": "The system uses JWT tokens for authentication.",
                "ReferenceId": "ref-12345",
                "AffinityToken": "aff-token",
            },
        )

        assert response.status_code == 200
        result = tracker._pending_jobs["full-payload-job"].result()
        assert result.output == "The system uses JWT tokens for authentication."
        assert result.exit_code == 0

    def test_callback_handles_missing_optional_fields(
        self, client, reset_tracker_singleton
    ):
        """
        Callback handles payload with missing optional fields.

        Given a job is registered
        When the callback receives payload with only required fields
        Then it should process successfully
        """
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )
        import asyncio

        tracker = DelegationJobTracker.get_instance()
        asyncio.get_event_loop().run_until_complete(tracker.register_job("minimal-job"))

        # Minimal payload - only JobId, Status, Output
        response = client.post(
            "/api/delegation/callback/minimal-job",
            json={
                "JobId": "minimal-job",
                "Status": "completed",
                "Output": "Minimal output",
            },
        )

        assert response.status_code == 200
        result = tracker._pending_jobs["minimal-job"].result()
        assert result.output == "Minimal output"

    def test_callback_handles_invalid_json(self, client):
        """
        Callback returns 422 for invalid JSON payload.

        Given an invalid JSON payload
        When the callback endpoint receives it
        Then it should return 422 Unprocessable Entity
        """
        response = client.post(
            "/api/delegation/callback/test-job",
            data="not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422

    def test_callback_handles_missing_required_fields(self, client):
        """
        Callback returns 422 for missing required fields.

        Given a payload missing required fields (Status, Output)
        When the callback endpoint receives it
        Then it should return 422 Unprocessable Entity
        """
        response = client.post(
            "/api/delegation/callback/test-job",
            json={
                "JobId": "test-job",
                # Missing Status and Output
            },
        )

        assert response.status_code == 422
