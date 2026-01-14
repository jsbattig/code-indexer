"""
Unit tests for poll_delegation_job MCP tool handler.

Story #720: Poll Delegation Job with Progress Feedback

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import json
from datetime import datetime, timezone

import pytest
from pytest_httpx import HTTPXMock

from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def test_user():
    """Create a test user."""
    return User(
        username="testuser",
        password_hash="hashed",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_delegation_config():
    """Create mock delegation config."""
    from code_indexer.server.config.delegation_config import ClaudeDelegationConfig

    return ClaudeDelegationConfig(
        function_repo_alias="test-repo",
        claude_server_url="https://claude-server.example.com",
        claude_server_username="service_user",
        claude_server_credential="service_pass",
    )


class TestPollDelegationJobHandler:
    """Tests for poll_delegation_job handler."""

    @pytest.mark.asyncio
    async def test_poll_returns_in_progress_with_phase(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job returns in_progress status with phase info.

        Given a job that is in progress (JOB_RUNNING phase)
        When poll_delegation_job is called
        Then it returns status=in_progress, phase, progress, continue_polling=true
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/job-12345",
            json={
                "job_id": "job-12345",
                "status": "in_progress",
                "repositories": [
                    {"alias": "repo1", "registered": True, "cloned": True, "indexed": True}
                ],
                "exchange_count": 5,
                "tool_use_count": 12,
            },
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-12345"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "in_progress"
        assert data["phase"] == "job_running"
        assert data["progress"]["exchange_count"] == 5
        assert data["progress"]["tool_use_count"] == 12
        assert data["continue_polling"] is True

    @pytest.mark.asyncio
    async def test_poll_returns_completed_with_result(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job returns completed status with result from conversation.

        Given a job that has completed successfully
        When poll_delegation_job is called
        Then it fetches the conversation and extracts the final assistant message
        And returns status=completed, result, continue_polling=false
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        # Job status endpoint - output field is for errors/metadata, not Claude's response
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/job-12345",
            json={
                "job_id": "job-12345",
                "status": "completed",
                "output": "",  # Empty - actual response is in conversation
            },
        )
        # Conversation endpoint - contains the actual Claude response
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/job-12345/conversation",
            json={
                "jobId": "job-12345",
                "sessions": [
                    {
                        "sessionId": "session-1",
                        "exchanges": [
                            {
                                "userMessage": "What authentication does the system use?",
                                "assistantMessage": "The authentication system uses JWT tokens for secure user sessions.",
                            }
                        ],
                    }
                ],
            },
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-12345"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "completed"
        assert data["phase"] == "done"
        assert "JWT tokens" in data["result"]
        assert data["continue_polling"] is False

    @pytest.mark.asyncio
    async def test_poll_returns_error_for_nonexistent_job(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job returns error for non-existent job.

        Given a job ID that does not exist
        When poll_delegation_job is called
        Then it returns an error with "Job not found"
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/nonexistent-job",
            json={"detail": "Job not found"},
            status_code=404,
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "nonexistent-job"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_poll_returns_failed_with_error(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job returns failed status with error.

        Given a job that has failed
        When poll_delegation_job is called
        Then it returns status=failed, error, continue_polling=false
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/job-12345",
            json={
                "job_id": "job-12345",
                "status": "failed",
                "error": "Repository clone failed",
            },
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-12345"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "failed"
        assert data["phase"] == "done"
        assert "clone failed" in data["error"]
        assert data["continue_polling"] is False

    @pytest.mark.asyncio
    async def test_poll_returns_error_when_not_configured(self, test_user):
        """
        poll_delegation_job returns error when delegation not configured.

        Given delegation is not configured
        When poll_delegation_job is called
        Then it returns error indicating not configured
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: None,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-12345"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "not configured" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_poll_handles_network_error(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job returns error on network failure.

        Given a network connectivity issue
        When poll_delegation_job is called
        Then it returns success=False with error message
        """
        import httpx

        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        # Auth succeeds
        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        # Job status fails with connection error
        httpx_mock.add_exception(httpx.ConnectError("Connection refused"))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-12345"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "error" in data

    @pytest.mark.asyncio
    async def test_poll_error_includes_job_id(
        self, test_user, mock_delegation_config, httpx_mock: HTTPXMock
    ):
        """
        poll_delegation_job error response includes job_id for traceability.

        Given a job ID that does not exist
        When poll_delegation_job is called
        Then the error response includes the job_id
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        httpx_mock.add_response(
            method="POST",
            url="https://claude-server.example.com/auth/login",
            json={"access_token": "token", "token_type": "bearer"},
        )
        httpx_mock.add_response(
            method="GET",
            url="https://claude-server.example.com/jobs/specific-job-id-123",
            json={"detail": "Job not found"},
            status_code=404,
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "specific-job-id-123"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        # The error should include the job_id for traceability
        assert "specific-job-id-123" in data["error"]
