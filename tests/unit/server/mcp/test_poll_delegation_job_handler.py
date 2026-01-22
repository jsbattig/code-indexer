"""
Unit tests for poll_delegation_job MCP tool handler.

Story #720: Poll Delegation Job with Progress Feedback

Tests follow TDD methodology - tests written FIRST before implementation.
"""

import json
from datetime import datetime, timezone

import pytest

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
    """
    Tests for poll_delegation_job handler basic validation.

    Note: Story #720 changed poll_delegation_job from polling Claude Server
    to callback-based completion. See TestPollDelegationJobCallbackBased for
    tests of the callback-based behavior.
    """

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


class TestPollDelegationJobCallbackBased:
    """Tests for callback-based job completion (Story #720)."""

    @pytest.fixture(autouse=True)
    def reset_tracker_singleton(self):
        """Reset DelegationJobTracker singleton between tests."""
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        DelegationJobTracker._instance = None
        yield
        DelegationJobTracker._instance = None

    @pytest.mark.asyncio
    async def test_poll_waits_for_callback_and_returns_result(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job waits on tracker Future and returns result.

        Given a job is registered in the tracker
        When callback completes the job
        Then poll_delegation_job returns the result from the callback
        """
        import asyncio
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        # Register job in tracker
        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("callback-job-123")

        # Simulate callback completing the job after a short delay
        async def complete_after_delay():
            await asyncio.sleep(0.05)
            result = JobResult(
                job_id="callback-job-123",
                status="completed",
                output="The authentication uses OAuth2 with JWT tokens.",
                exit_code=0,
                error=None,
            )
            await tracker.complete_job(result)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            # Run callback completion and poll concurrently
            complete_task = asyncio.create_task(complete_after_delay())
            poll_task = asyncio.create_task(
                handle_poll_delegation_job(
                    {"job_id": "callback-job-123", "timeout": 5.0},
                    test_user,
                )
            )

            await complete_task
            response = await poll_task

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "completed"
        assert "OAuth2" in data["result"]
        assert data["continue_polling"] is False

    @pytest.mark.asyncio
    async def test_poll_returns_failed_result_from_callback(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job returns failed result from callback.

        Given a job is registered in the tracker
        When callback completes the job with failed status
        Then poll_delegation_job returns the error from the callback
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        # Register and immediately complete with failure
        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("failed-job-456")

        result = JobResult(
            job_id="failed-job-456",
            status="failed",
            output="Repository clone failed: authentication denied",
            exit_code=1,
            error="Repository clone failed: authentication denied",
        )
        await tracker.complete_job(result)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "failed-job-456", "timeout_seconds": 1.0},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "failed"
        assert "clone failed" in data["error"]
        assert data["continue_polling"] is False

    @pytest.mark.asyncio
    async def test_poll_returns_waiting_when_callback_not_received(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job returns waiting status when timeout occurs (Story #720 fix).

        Given a job is registered but callback hasn't arrived yet
        When poll_delegation_job timeout expires
        Then it returns status=waiting with continue_polling=True
        So the caller can decide to poll again
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        # Register job but don't complete it
        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("timeout-job-789")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "timeout-job-789", "timeout_seconds": 0.05},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "waiting"
        assert (
            "still running" in data["message"].lower()
            or "not yet received" in data["message"].lower()
        )
        # Key fix: continue_polling should be True so caller can retry
        assert data["continue_polling"] is True

        # Job should still exist in tracker (caller can poll again)
        assert await tracker.has_job("timeout-job-789") is True

    @pytest.mark.asyncio
    async def test_can_retry_poll_after_timeout(
        self, test_user, mock_delegation_config
    ):
        """
        Caller can poll again after timeout and get result (Story #720 fix).

        Given a job times out on first poll
        When callback arrives and caller polls again
        Then the second poll returns the completed result
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("retry-job-001")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            # First poll times out
            response1 = await handle_poll_delegation_job(
                {"job_id": "retry-job-001", "timeout_seconds": 0.05},
                test_user,
            )

            data1 = json.loads(response1["content"][0]["text"])
            assert data1["status"] == "waiting"
            assert data1["continue_polling"] is True

            # Now callback arrives (simulating Claude Server posting back)
            job_result = JobResult(
                job_id="retry-job-001",
                status="completed",
                output="The authentication module uses JWT tokens with RSA-256 signing.",
                exit_code=0,
                error=None,
            )
            await tracker.complete_job(job_result)

            # Second poll gets the result
            response2 = await handle_poll_delegation_job(
                {"job_id": "retry-job-001", "timeout_seconds": 1.0},
                test_user,
            )

            data2 = json.loads(response2["content"][0]["text"])
            assert data2["status"] == "completed"
            assert "JWT tokens" in data2["result"]
            assert data2["continue_polling"] is False

    @pytest.mark.asyncio
    async def test_poll_returns_error_for_job_not_in_tracker(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job returns error when job not found in tracker.

        Given a job_id that is not registered in the tracker
        When poll_delegation_job is called
        Then it returns an error indicating job not found
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "nonexistent-tracker-job", "timeout_seconds": 1.0},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert (
            "not found" in data["error"].lower()
            or "already completed" in data["error"].lower()
        )


class TestPollDelegationJobTimeoutParameter:
    """Tests for timeout_seconds parameter (Story #720)."""

    @pytest.fixture(autouse=True)
    def reset_tracker_singleton(self):
        """Reset DelegationJobTracker singleton between tests."""
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        DelegationJobTracker._instance = None
        yield
        DelegationJobTracker._instance = None

    @pytest.mark.asyncio
    async def test_timeout_seconds_uses_default_45_when_not_specified(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job uses 45 seconds default timeout when not specified.

        Given timeout_seconds is not provided
        When poll_delegation_job is called
        Then it should use 45 seconds default (below MCP's 60s)
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-default-timeout")

        # Complete job immediately so we don't wait
        result = JobResult(
            job_id="job-default-timeout",
            status="completed",
            output="Test",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(result)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-default-timeout"},  # No timeout_seconds
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_timeout_seconds_accepts_valid_value(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job accepts timeout_seconds between 5 and 300.

        Given a valid timeout_seconds value (e.g., 60)
        When poll_delegation_job is called
        Then it should use that timeout value
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
            JobResult,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-custom-timeout")

        # Complete job immediately so we don't wait
        result = JobResult(
            job_id="job-custom-timeout",
            status="completed",
            output="Test",
            exit_code=0,
            error=None,
        )
        await tracker.complete_job(result)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-custom-timeout", "timeout_seconds": 60},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_timeout_seconds_rejects_below_minimum(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job rejects timeout_seconds below 0.01.

        Given timeout_seconds = 0.005 (below minimum 0.01)
        When poll_delegation_job is called
        Then it should return error
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-low-timeout")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-low-timeout", "timeout_seconds": 0.005},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "timeout_seconds" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_timeout_seconds_rejects_above_maximum(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job rejects timeout_seconds above 300.

        Given timeout_seconds = 500 (above maximum 300)
        When poll_delegation_job is called
        Then it should return error
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-high-timeout")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-high-timeout", "timeout_seconds": 500},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "timeout_seconds" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_timeout_seconds_rejects_non_numeric(
        self, test_user, mock_delegation_config
    ):
        """
        poll_delegation_job rejects non-numeric timeout_seconds.

        Given timeout_seconds = "fast" (not a number)
        When poll_delegation_job is called
        Then it should return error
        """
        from code_indexer.server.mcp.handlers import handle_poll_delegation_job
        from code_indexer.server.services.delegation_job_tracker import (
            DelegationJobTracker,
        )

        tracker = DelegationJobTracker.get_instance()
        await tracker.register_job("job-string-timeout")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "code_indexer.server.mcp.handlers._get_delegation_config",
                lambda: mock_delegation_config,
            )

            response = await handle_poll_delegation_job(
                {"job_id": "job-string-timeout", "timeout_seconds": "fast"},
                test_user,
            )

        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "timeout_seconds" in data["error"].lower()
