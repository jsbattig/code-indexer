"""
Unit tests for SCIP Resolution Queue (Story #645 AC4).

Tests serialized FIFO queue for processing SCIP project resolution attempts
one at a time to prevent conflicts.

AC4: Serialized Execution Queue
- Only one Claude Code invocation runs at any time
- Queued projects wait until current resolution completes
- FIFO processing order
- Queue status observable
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from code_indexer.server.services.scip_resolution_queue import (
    SCIPResolutionQueue,
)


class TestSCIPResolutionQueueAC4:
    """Test AC4: Serialized Execution Queue."""

    @pytest.fixture
    def mock_self_healing_service(self):
        """Create mock SCIPSelfHealingService."""
        service = Mock()
        service.invoke_claude_code = AsyncMock(return_value=Mock(status="progress"))
        service.handle_project_response = AsyncMock()
        return service

    @pytest.fixture
    def queue(self, mock_self_healing_service):
        """Create SCIPResolutionQueue instance."""
        return SCIPResolutionQueue(self_healing_service=mock_self_healing_service)

    @pytest.mark.asyncio
    async def test_enqueue_project_adds_to_queue(self, queue):
        """Test AC4: Verify project added to queue when enqueued."""
        # Enqueue a project
        await queue.enqueue_project(
            job_id="job-123",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="ModuleNotFoundError: No module named 'requests'",
        )

        # Verify queue has 1 pending project
        status = queue.get_status()
        assert status["pending_count"] == 1
        assert status["is_running"] is False

    @pytest.mark.asyncio
    async def test_fifo_order_processing(self, queue, mock_self_healing_service):
        """Test AC4: Verify projects processed in FIFO order."""
        # Enqueue 3 projects
        await queue.enqueue_project(
            job_id="job-1",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="Error 1",
        )
        await queue.enqueue_project(
            job_id="job-2",
            project_path="frontend/",
            language="typescript",
            build_system="npm",
            stderr="Error 2",
        )
        await queue.enqueue_project(
            job_id="job-3",
            project_path="services/",
            language="java",
            build_system="maven",
            stderr="Error 3",
        )

        # Start worker (will process queue)
        await queue.start_worker()

        # Give time for processing
        await asyncio.sleep(0.1)

        # Verify invoke_claude_code called in FIFO order
        calls = mock_self_healing_service.invoke_claude_code.call_args_list
        assert len(calls) >= 1
        # First call should be for backend/ (job-1)
        first_call_kwargs = calls[0].kwargs
        assert first_call_kwargs["project_path"] == "backend/"
        assert first_call_kwargs["job_id"] == "job-1"

        await queue.stop_worker()

    @pytest.mark.asyncio
    async def test_serialization_one_project_at_a_time(
        self, queue, mock_self_healing_service
    ):
        """Test AC4: Verify only one project processes at a time (serialized)."""
        # Make invoke_claude_code take time
        async def slow_invoke(*args, **kwargs):
            await asyncio.sleep(0.2)
            return Mock(status="progress")

        mock_self_healing_service.invoke_claude_code.side_effect = slow_invoke

        # Enqueue 2 projects
        await queue.enqueue_project(
            job_id="job-1",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="Error 1",
        )
        await queue.enqueue_project(
            job_id="job-2",
            project_path="frontend/",
            language="typescript",
            build_system="npm",
            stderr="Error 2",
        )

        # Start worker
        await queue.start_worker()

        # Check status during processing
        await asyncio.sleep(0.05)  # Small delay to let first project start
        status = queue.get_status()

        # Verify: 1 project currently processing, 1 pending
        assert status["current_project"] is not None
        assert status["current_project"]["project_path"] == "backend/"
        assert status["pending_count"] == 1  # Second project still pending
        assert status["is_running"] is True

        await queue.stop_worker()

    @pytest.mark.asyncio
    async def test_get_status_returns_correct_info(self, queue):
        """Test AC4: Verify get_status() returns pending count, current project, is_running."""
        # Initially empty
        status = queue.get_status()
        assert status["pending_count"] == 0
        assert status["current_project"] is None
        assert status["is_running"] is False

        # Enqueue project
        await queue.enqueue_project(
            job_id="job-1",
            project_path="backend/",
            language="python",
            build_system="poetry",
            stderr="Error",
        )

        status = queue.get_status()
        assert status["pending_count"] == 1
        assert status["is_running"] is False

    @pytest.mark.asyncio
    async def test_worker_lifecycle_start_and_stop(
        self, queue, mock_self_healing_service
    ):
        """Test AC4: Verify start_worker() and stop_worker() manage worker lifecycle."""
        # Initially not running
        assert queue.is_running is False
        assert queue.worker_task is None

        # Start worker
        await queue.start_worker()
        assert queue.is_running is True
        assert queue.worker_task is not None

        # Stop worker
        await queue.stop_worker()
        assert queue.is_running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
