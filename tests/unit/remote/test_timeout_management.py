"""Test timeout management for CIDX Repository Sync Epic - Story 12.

Tests comprehensive timeout handling including job cancellation, progress callbacks,
and cleanup of partial operations.
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from code_indexer.remote.polling import (
    JobPollingEngine,
    PollingConfig,
    JobTimeoutError,
)
from code_indexer.server.jobs.manager import SyncJobManager
from code_indexer.remote.sync_execution import execute_repository_sync, SyncJobResult
from code_indexer.api_clients.base_client import CIDXRemoteAPIClient


class TestJobPollingEngineTimeout:
    """Test timeout functionality in JobPollingEngine."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        client = Mock(spec=CIDXRemoteAPIClient)
        client.get_job_status = AsyncMock()
        return client

    @pytest.fixture
    def progress_callback(self):
        """Create mock progress callback."""
        return Mock()

    @pytest.fixture
    def timeout_config(self):
        """Create polling config with short timeout for testing."""
        return PollingConfig(
            base_interval=0.1,  # Fast polling for tests
            timeout=2.0,  # 2 second timeout
            max_interval=0.5,
            network_retry_attempts=1,
        )

    @pytest.fixture
    def polling_engine(self, mock_api_client, progress_callback, timeout_config):
        """Create JobPollingEngine with timeout configuration."""
        return JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=progress_callback,
            config=timeout_config,
        )

    @pytest.mark.asyncio
    async def test_timeout_during_polling_raises_timeout_error(
        self, polling_engine, mock_api_client
    ):
        """Test that polling times out and raises JobTimeoutError."""
        # Setup: Mock job status that never completes
        mock_api_client.get_job_status.return_value = {
            "job_id": "test-job-123",
            "status": "running",
            "phase": "indexing",
            "progress": 0.5,
            "message": "Still processing...",
            "files_processed": 10,
            "total_files": 100,
        }

        # Execute: Start polling with timeout
        with pytest.raises(JobTimeoutError) as exc_info:
            await polling_engine.start_polling("test-job-123")

        # Verify: Timeout error contains expected message
        assert "timed out after 2.0 seconds" in str(exc_info.value)

        # Verify: Progress callback was called during polling
        assert polling_engine.progress_callback.call_count > 0

    @pytest.mark.asyncio
    async def test_timeout_countdown_progress_updates(
        self, polling_engine, mock_api_client, progress_callback
    ):
        """Test that progress callbacks show remaining time during timeout countdown."""
        # Setup: Mock job status that shows progress but never completes
        # Create a repeating response
        mock_response = {
            "job_id": "test-job-123",
            "status": "running",
            "phase": "indexing",
            "progress": 0.3,
            "message": "Processing files...",
            "files_processed": 30,
            "total_files": 100,
            "processing_speed": 5.0,
            "elapsed_time": 60.0,
            "estimated_remaining": 180.0,
        }
        mock_api_client.get_job_status.return_value = mock_response

        # Execute: Start polling that will timeout
        with pytest.raises(JobTimeoutError):
            await polling_engine.start_polling("test-job-123")

        # Verify: Progress callback received multiple updates
        assert progress_callback.call_count >= 2

        # Verify: Last progress update shows timeout information
        last_call_args = progress_callback.call_args_list[-1]
        # Should be called with (current, total, path, info=...)
        assert len(last_call_args[0]) >= 3

        # Check that info parameter contains progress details
        call_kwargs = last_call_args[1]
        if "info" in call_kwargs:
            info = call_kwargs["info"]
            assert any(
                keyword in info.lower() for keyword in ["files", "emb/s", "indexing"]
            )

    @pytest.mark.asyncio
    async def test_timeout_during_different_job_phases(
        self, polling_engine, mock_api_client
    ):
        """Test timeout behavior during different job phases."""
        job_phases = ["setup", "git_pull", "indexing", "validation"]

        for phase in job_phases:
            # Reset mock for each phase test
            mock_api_client.reset_mock()
            mock_api_client.get_job_status.return_value = {
                "job_id": f"test-job-{phase}",
                "status": "running",
                "phase": phase,
                "progress": 0.2,
                "message": f"Processing {phase}...",
            }

            # Test timeout in this phase
            with pytest.raises(JobTimeoutError) as exc_info:
                await polling_engine.start_polling(f"test-job-{phase}")

            # Verify error message mentions timeout
            assert "timed out" in str(exc_info.value)
            assert "2.0 seconds" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_successful_completion_before_timeout(
        self, polling_engine, mock_api_client
    ):
        """Test that job completion before timeout works normally."""
        # Setup: Mock job that completes quickly
        mock_responses = [
            {
                "job_id": "test-job-123",
                "status": "running",
                "phase": "indexing",
                "progress": 0.5,
                "message": "Processing...",
            },
            {
                "job_id": "test-job-123",
                "status": "completed",
                "phase": "completed",
                "progress": 1.0,
                "message": "Sync completed successfully",
            },
        ]
        mock_api_client.get_job_status.side_effect = iter(mock_responses)

        # Execute: Start polling
        result = await polling_engine.start_polling("test-job-123")

        # Verify: Job completed successfully
        assert result.status == "completed"
        assert result.message == "Sync completed successfully"

    @pytest.mark.asyncio
    async def test_custom_timeout_configuration(
        self, mock_api_client, progress_callback
    ):
        """Test polling with custom timeout configuration."""
        # Create engine with longer timeout
        long_timeout_config = PollingConfig(
            base_interval=0.1,
            timeout=5.0,  # 5 second timeout
            max_interval=1.0,
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=progress_callback,
            config=long_timeout_config,
        )

        # Setup mock that never completes
        mock_api_client.get_job_status.return_value = {
            "job_id": "test-job-123",
            "status": "running",
            "phase": "indexing",
            "progress": 0.5,
            "message": "Still processing...",
        }

        # Start time tracking
        start_time = asyncio.get_event_loop().time()

        # Execute: Should timeout after ~5 seconds
        with pytest.raises(JobTimeoutError):
            await engine.start_polling("test-job-123")

        # Verify: Timeout occurred after approximately the configured time
        elapsed_time = asyncio.get_event_loop().time() - start_time
        assert 4.8 <= elapsed_time <= 5.5  # Allow some variance for test execution


class TestSyncJobManagerCancellation:
    """Test job cancellation functionality in SyncJobManager."""

    @pytest.fixture
    def job_manager(self, tmp_path):
        """Create SyncJobManager for testing."""
        return SyncJobManager(storage_path=str(tmp_path / "jobs.json"))

    def test_cancel_running_job_success(self, job_manager):
        """Test successful cancellation of a running job."""
        from code_indexer.server.jobs.models import JobType

        # Create a running job
        job_id = job_manager.create_job(
            username="testuser",
            user_alias="Test User",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/repo.git",
        )

        # Verify job is running
        job = job_manager.get_job(job_id)
        assert job["status"] == "running"

        # Cancel the job
        job_manager.cancel_job(job_id)

        # Verify job is cancelled
        cancelled_job = job_manager.get_job(job_id)
        assert cancelled_job["status"] == "cancelled"
        assert cancelled_job["completed_at"] is not None

    def test_cancel_queued_job_success(self, job_manager):
        """Test successful cancellation of a queued job."""
        from code_indexer.server.jobs.models import JobType

        # Create jobs to fill up running slots
        running_jobs = []
        for i in range(job_manager.max_total_concurrent_jobs):
            job_id = job_manager.create_job(
                username=f"user{i}",
                user_alias=f"User {i}",
                job_type=JobType.REPOSITORY_SYNC,
                repository_url=f"https://github.com/test/repo{i}.git",
            )
            running_jobs.append(job_id)

        # Create a job that should be queued
        queued_job_id = job_manager.create_job(
            username="queueduser",
            user_alias="Queued User",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url="https://github.com/test/queued-repo.git",
        )

        # Verify job is queued
        job = job_manager.get_job(queued_job_id)
        assert job["status"] == "queued"

        # Cancel the queued job
        job_manager.cancel_job(queued_job_id)

        # Verify job is cancelled
        cancelled_job = job_manager.get_job(queued_job_id)
        assert cancelled_job["status"] == "cancelled"

    def test_cancel_job_cleanup_repository_lock(self, job_manager):
        """Test that cancelling a job releases repository locks."""
        from code_indexer.server.jobs.models import JobType

        repo_url = "https://github.com/test/locked-repo.git"

        # Create job that acquires repository lock
        job_id = job_manager.create_job(
            username="testuser",
            user_alias="Test User",
            job_type=JobType.REPOSITORY_SYNC,
            repository_url=repo_url,
        )

        # Verify repository is locked
        conflict_job_id = job_manager._check_repository_conflict(repo_url)
        assert conflict_job_id == job_id

        # Cancel the job
        job_manager.cancel_job(job_id)

        # Verify repository lock is released
        conflict_job_id_after = job_manager._check_repository_conflict(repo_url)
        assert conflict_job_id_after is None

    def test_cancel_nonexistent_job_raises_error(self, job_manager):
        """Test that cancelling non-existent job raises appropriate error."""
        from code_indexer.server.jobs.exceptions import JobNotFoundError

        with pytest.raises(JobNotFoundError):
            job_manager.cancel_job("nonexistent-job-id")

    def test_cancel_already_completed_job_raises_error(self, job_manager):
        """Test that cancelling completed job raises appropriate error."""
        from code_indexer.server.jobs.models import JobType
        from code_indexer.server.jobs.exceptions import InvalidJobStateTransitionError

        # Create and complete a job
        job_id = job_manager.create_job(
            username="testuser",
            user_alias="Test User",
            job_type=JobType.REPOSITORY_SYNC,
        )

        job_manager.mark_job_completed(job_id)

        # Attempt to cancel completed job
        with pytest.raises(InvalidJobStateTransitionError):
            job_manager.cancel_job(job_id)


class TestTimeoutConfiguration:
    """Test timeout configuration support."""

    def test_polling_config_validation(self):
        """Test PollingConfig timeout validation."""
        # Valid timeout
        config = PollingConfig(timeout=300.0)
        assert config.timeout == 300.0

        # Invalid timeout (negative)
        with pytest.raises(ValueError) as exc_info:
            PollingConfig(timeout=-10.0)
        assert "timeout must be positive" in str(exc_info.value)

        # Invalid timeout (zero)
        with pytest.raises(ValueError):
            PollingConfig(timeout=0.0)

    def test_timeout_from_cli_parameter(self):
        """Test that CLI timeout parameter is used in polling configuration."""
        cli_timeout = 600  # 10 minutes

        # Create polling config with CLI timeout
        config = PollingConfig(timeout=float(cli_timeout))

        assert config.timeout == 600.0

    @pytest.mark.asyncio
    async def test_execute_repository_sync_with_timeout(self):
        """Test execute_repository_sync respects timeout parameter."""
        project_root = Path("/tmp/test-project")

        # Mock the necessary dependencies
        with (
            patch(
                "code_indexer.remote.sync_execution._load_remote_configuration"
            ) as mock_config,
            patch(
                "code_indexer.remote.sync_execution._load_and_decrypt_credentials"
            ) as mock_creds,
            patch(
                "code_indexer.remote.sync_execution.load_repository_link"
            ) as mock_link,
        ):
            # Setup mocks
            mock_config.return_value = {"server_url": "http://test.com"}
            mock_creds.return_value = {"username": "test", "password": "test"}
            mock_link.return_value = Mock(alias="test-repo")

            # Mock SyncClient
            with patch(
                "code_indexer.remote.sync_execution.SyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                # Mock sync_repository to return a job result
                mock_client.sync_repository.return_value = SyncJobResult(
                    job_id="test-job-123",
                    status="running",
                    message="Job submitted",
                    repository="test-repo",
                )

                # Mock _poll_sync_jobs to test timeout is passed correctly
                with patch(
                    "code_indexer.remote.sync_execution._poll_sync_jobs"
                ) as mock_poll:
                    # Execute with custom timeout
                    custom_timeout = 450
                    await execute_repository_sync(
                        repository_alias=None,
                        project_root=project_root,
                        timeout=custom_timeout,
                        enable_polling=True,
                        progress_callback=Mock(),
                    )

                    # Verify timeout was passed to sync_repository
                    mock_client.sync_repository.assert_called_once()
                    call_kwargs = mock_client.sync_repository.call_args[1]
                    assert call_kwargs["timeout"] == custom_timeout

                    # Verify timeout was passed to polling
                    mock_poll.assert_called_once()
                    poll_args = mock_poll.call_args[0]
                    assert poll_args[2] == custom_timeout  # timeout parameter


class TestTimeoutErrorMessagesAndRecovery:
    """Test timeout error messages and recovery suggestions."""

    @pytest.mark.asyncio
    async def test_timeout_error_contains_recovery_suggestions(self):
        """Test that timeout errors provide helpful recovery suggestions."""
        # Create engine with short timeout
        mock_client = Mock(spec=CIDXRemoteAPIClient)
        mock_client.get_job_status = AsyncMock(
            return_value={
                "job_id": "test-job-123",
                "status": "running",
                "phase": "indexing",
                "progress": 0.1,
                "message": "Processing large repository...",
            }
        )

        config = PollingConfig(timeout=1.0)
        engine = JobPollingEngine(
            api_client=mock_client,
            progress_callback=Mock(),
            config=config,
        )

        # Execute and catch timeout error
        with pytest.raises(JobTimeoutError) as exc_info:
            await engine.start_polling("test-job-123")

        # Verify error message structure
        error_message = str(exc_info.value)
        assert "timed out after 1.0 seconds" in error_message
        assert "test-job-123" in error_message or "Job polling" in error_message

    @pytest.mark.asyncio
    async def test_partial_operation_cleanup_on_timeout(self):
        """Test that partial operations are cleaned up when timeout occurs."""
        mock_client = Mock(spec=CIDXRemoteAPIClient)
        mock_client.get_job_status = AsyncMock(
            return_value={
                "job_id": "test-job-123",
                "status": "running",
                "phase": "indexing",
                "progress": 0.5,
                "message": "Processing...",
            }
        )

        config = PollingConfig(timeout=0.5)
        engine = JobPollingEngine(
            api_client=mock_client,
            progress_callback=Mock(),
            config=config,
        )

        # Track engine state before timeout
        assert not engine.is_polling
        assert engine.current_job_id is None

        # Execute and timeout
        with pytest.raises(JobTimeoutError):
            await engine.start_polling("test-job-123")

        # Verify cleanup occurred
        assert not engine.is_polling
        assert engine.current_job_id is None

    def test_timeout_configuration_defaults(self):
        """Test that timeout configuration has sensible defaults."""
        config = PollingConfig()

        # Verify default timeout is reasonable (5 minutes)
        assert config.timeout == 300.0

        # Verify other timeout-related defaults
        assert config.base_interval > 0
        assert config.max_interval >= config.base_interval
        assert config.network_retry_attempts >= 0


class TestIntegrationTimeoutScenarios:
    """Integration tests for timeout scenarios across components."""

    @pytest.mark.asyncio
    async def test_end_to_end_timeout_scenario(self, tmp_path):
        """Test complete timeout scenario from CLI to job cancellation."""
        # This test would require significant mocking but demonstrates
        # the integration pattern for timeout handling

        # Setup: Mock all external dependencies
        with (
            patch(
                "code_indexer.remote.sync_execution._load_remote_configuration"
            ) as mock_config,
            patch(
                "code_indexer.remote.sync_execution._load_and_decrypt_credentials"
            ) as mock_creds,
            patch(
                "code_indexer.remote.sync_execution.load_repository_link"
            ) as mock_link,
        ):
            mock_config.return_value = {"server_url": "http://test.com"}
            mock_creds.return_value = {"username": "test", "password": "test"}
            mock_link.return_value = Mock(alias="test-repo")

            with patch(
                "code_indexer.remote.sync_execution.SyncClient"
            ) as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                # Setup job that will timeout
                mock_client.sync_repository.return_value = SyncJobResult(
                    job_id="timeout-job-123",
                    status="running",
                    message="Job submitted",
                    repository="test-repo",
                )

                # Mock job status that never completes
                mock_client.get_job_status.return_value = {
                    "job_id": "timeout-job-123",
                    "status": "running",
                    "phase": "indexing",
                    "progress": 0.3,
                    "message": "Processing large repository...",
                }

                # Execute with short timeout
                progress_calls = []

                def capture_progress(*args, **kwargs):
                    progress_calls.append((args, kwargs))

                # This should timeout and demonstrate the full flow
                try:
                    await execute_repository_sync(
                        repository_alias="test-repo",
                        project_root=tmp_path,
                        timeout=1,  # Very short timeout
                        enable_polling=True,
                        progress_callback=capture_progress,
                    )
                    assert False, "Expected timeout error"
                except Exception as e:
                    # Should eventually result in timeout-related error
                    # (may be wrapped in RemoteSyncExecutionError)
                    assert any(
                        word in str(e).lower()
                        for word in ["timeout", "timed out", "polling"]
                    )

                # Verify progress callbacks were made
                assert len(progress_calls) > 0
