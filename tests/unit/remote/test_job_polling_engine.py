"""Tests for JobPollingEngine - Story 11: Polling Loop Engine.

Comprehensive test suite for intelligent job status polling with network resilience,
progress display integration, and keyboard interrupt handling.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock

from code_indexer.remote.polling import (
    JobPollingEngine,
    JobStatus,
    PollingConfig,
    JobPollingError,
    NetworkConnectionError,
    JobTimeoutError,
    InterruptedPollingError,
)
from code_indexer.api_clients.base_client import (
    CIDXRemoteAPIClient,
    APIClientError,
    AuthenticationError,
    NetworkError,
)


@pytest.fixture
def mock_api_client():
    """Create mock API client for testing."""
    client = AsyncMock(spec=CIDXRemoteAPIClient)
    client.get_job_status = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_progress_callback():
    """Create mock progress callback."""
    return Mock()


@pytest.fixture
def polling_config():
    """Create polling configuration for testing."""
    return PollingConfig(
        base_interval=0.1,  # Fast for tests
        max_interval=2.0,
        max_backoff_multiplier=4.0,
        timeout=10.0,
        network_retry_attempts=3,
    )


@pytest.fixture
def sample_job_status():
    """Create sample job status for testing."""
    return JobStatus(
        job_id="test-job-123",
        status="running",
        phase="indexing",
        progress=0.5,
        message="Processing files",
        current_operation="Processing src/main.py",
        files_processed=50,
        total_files=100,
        processing_speed=5.2,
        elapsed_time=9.6,
        estimated_remaining=9.4,
        details={
            "branch": "main",
            "commit": "abc123def",
            "files_added": 10,
            "files_modified": 20,
            "files_deleted": 5,
        },
    )


class TestJobPollingEngine:
    """Test suite for JobPollingEngine class."""

    def test_initialization_with_defaults(
        self, mock_api_client, mock_progress_callback
    ):
        """Test JobPollingEngine initialization with default configuration."""
        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
        )

        assert engine.api_client == mock_api_client
        assert engine.progress_callback == mock_progress_callback
        assert engine.config.base_interval == 1.0  # Default
        assert engine.config.max_interval == 10.0  # Default
        assert engine.config.timeout == 300.0  # Default
        assert engine.is_polling is False
        assert engine.current_job_id is None

    def test_initialization_with_custom_config(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test JobPollingEngine initialization with custom configuration."""
        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        assert engine.config == polling_config
        assert engine.config.base_interval == 0.1

    @pytest.mark.asyncio
    async def test_start_polling_success_immediate_completion(
        self, mock_api_client, mock_progress_callback, polling_config, sample_job_status
    ):
        """Test polling for job that completes immediately."""
        # Mock job that is already completed
        completed_status = JobStatus(
            job_id="test-job-123",
            status="completed",
            phase="completed",
            progress=1.0,
            message="Job completed successfully",
        )
        mock_api_client.get_job_status.return_value = completed_status

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        result = await engine.start_polling("test-job-123")

        assert result == completed_status
        assert engine.is_polling is False
        assert engine.current_job_id is None
        mock_api_client.get_job_status.assert_called_once_with("test-job-123")
        mock_progress_callback.assert_called()

    @pytest.mark.asyncio
    async def test_start_polling_success_with_progress_updates(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test polling with multiple progress updates before completion."""
        # Create sequence of job statuses
        statuses = [
            JobStatus(
                job_id="test-job-123",
                status="running",
                phase="git_pull",
                progress=0.1,
                message="Pulling from remote",
            ),
            JobStatus(
                job_id="test-job-123",
                status="running",
                phase="indexing",
                progress=0.5,
                message="Indexing files",
            ),
            JobStatus(
                job_id="test-job-123",
                status="running",
                phase="validation",
                progress=0.9,
                message="Validating index",
            ),
            JobStatus(
                job_id="test-job-123",
                status="completed",
                phase="completed",
                progress=1.0,
                message="Job completed successfully",
            ),
        ]

        mock_api_client.get_job_status.side_effect = statuses

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        result = await engine.start_polling("test-job-123")

        assert result.status == "completed"
        assert result.progress == 1.0
        assert mock_api_client.get_job_status.call_count == 4
        assert mock_progress_callback.call_count == 4

        # Verify progress callback was called with proper format
        progress_calls = mock_progress_callback.call_args_list

        # First call should be git_pull phase
        assert "git_pull" in str(progress_calls[0])

        # Last call should show completion
        assert "completed" in str(progress_calls[-1])

    @pytest.mark.asyncio
    async def test_start_polling_job_failure(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test polling for job that fails with error status."""
        # Mock job that fails
        failed_status = JobStatus(
            job_id="test-job-123",
            status="failed",
            phase="indexing",
            progress=0.3,
            message="Indexing failed: Permission denied",
            error_details="Cannot access /restricted/folder",
        )
        mock_api_client.get_job_status.return_value = failed_status

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(JobPollingError, match="Job failed"):
            await engine.start_polling("test-job-123")

        assert engine.is_polling is False
        assert engine.current_job_id is None

    @pytest.mark.asyncio
    async def test_start_polling_timeout(self, mock_api_client, mock_progress_callback):
        """Test polling timeout when job takes too long."""
        # Mock job that never completes
        running_status = JobStatus(
            job_id="test-job-123",
            status="running",
            phase="indexing",
            progress=0.5,
            message="Still processing...",
        )
        mock_api_client.get_job_status.return_value = running_status

        # Use very short timeout for testing
        config = PollingConfig(
            base_interval=0.05,
            timeout=0.2,  # 200ms timeout
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=config,
        )

        with pytest.raises(JobTimeoutError, match="timed out after .+ seconds"):
            await engine.start_polling("test-job-123")

        assert engine.is_polling is False

    @pytest.mark.asyncio
    async def test_network_error_handling_with_retry(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test network error handling with exponential backoff retry."""
        # First two calls fail, third succeeds
        completed_status = JobStatus(
            job_id="test-job-123",
            status="completed",
            phase="completed",
            progress=1.0,
            message="Job completed successfully",
        )

        mock_api_client.get_job_status.side_effect = [
            NetworkError("Connection failed", 503),
            NetworkError("Temporary error", 502),
            completed_status,
        ]

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        result = await engine.start_polling("test-job-123")

        assert result == completed_status
        assert mock_api_client.get_job_status.call_count == 3

    @pytest.mark.asyncio
    async def test_network_error_exhausted_retries(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test network error handling when retries are exhausted."""
        # All calls fail
        mock_api_client.get_job_status.side_effect = NetworkError(
            "Persistent failure", 503
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(
            NetworkConnectionError, match="Network error after 3 retry attempts"
        ):
            await engine.start_polling("test-job-123")

        # Should have made initial attempt + retries
        expected_calls = 1 + polling_config.network_retry_attempts
        assert mock_api_client.get_job_status.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_authentication_error_no_retry(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test that authentication errors are not retried."""
        mock_api_client.get_job_status.side_effect = AuthenticationError(
            "Token expired", 401
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(AuthenticationError, match="Token expired"):
            await engine.start_polling("test-job-123")

        # Should only make one attempt (no retries for auth errors)
        assert mock_api_client.get_job_status.call_count == 1

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_handling(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test graceful handling of keyboard interrupts (Ctrl+C)."""
        # Mock job that would run forever
        running_status = JobStatus(
            job_id="test-job-123",
            status="running",
            phase="indexing",
            progress=0.5,
            message="Processing files...",
        )

        async def slow_status_check(job_id):
            await asyncio.sleep(0.1)
            return running_status

        mock_api_client.get_job_status.side_effect = slow_status_check

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        # Start polling in background task
        polling_task = asyncio.create_task(engine.start_polling("test-job-123"))

        # Give it time to start
        await asyncio.sleep(0.05)

        # Cancel the task (simulates Ctrl+C)
        polling_task.cancel()

        with pytest.raises(InterruptedPollingError, match="Polling was interrupted"):
            await engine.stop_polling()

        assert engine.is_polling is False
        assert engine.current_job_id is None

    def test_progress_display_formatting(
        self, mock_api_client, mock_progress_callback, sample_job_status
    ):
        """Test progress display formatting follows CIDX patterns."""
        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
        )

        # Test setup message (total=0)
        engine._display_progress(
            JobStatus(
                job_id="test-job-123",
                status="initializing",
                phase="setup",
                progress=0.0,
                message="Preparing sync job",
            )
        )

        setup_call = mock_progress_callback.call_args
        assert setup_call[0][0] == 0  # current
        assert setup_call[0][1] == 0  # total (triggers info display)
        assert "Preparing sync job" in setup_call[1]["info"]

        # Test progress bar (total > 0)
        mock_progress_callback.reset_mock()
        engine._display_progress(sample_job_status)

        progress_call = mock_progress_callback.call_args
        assert progress_call[0][0] == 50  # current files
        assert progress_call[0][1] == 100  # total files
        assert "50/100 files (50%)" in progress_call[1]["info"]
        assert "5.2 emb/s" in progress_call[1]["info"]
        assert "Processing src/main.py" in progress_call[1]["info"]

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test exponential backoff calculation for retry intervals."""
        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        # Test backoff calculation
        initial_interval = 0.1
        backoff_intervals = []

        for attempt in range(1, 5):
            interval = engine._calculate_backoff_interval(attempt, initial_interval)
            backoff_intervals.append(interval)

        # Should follow exponential pattern: base * 2^(attempt-1), capped by max_backoff_multiplier
        assert backoff_intervals[0] == 0.1  # 2^0 = 1
        assert backoff_intervals[1] == 0.2  # 2^1 = 2
        assert backoff_intervals[2] == 0.4  # 2^2 = 4
        assert (
            backoff_intervals[3] == 0.4
        )  # min(2^3, 4.0) = min(8, 4) = 4, so 0.1*4 = 0.4

        # Test max interval cap
        large_attempt = 10
        capped_interval = engine._calculate_backoff_interval(
            large_attempt, initial_interval
        )
        assert capped_interval <= polling_config.max_interval

    def test_concurrent_polling_prevention(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test prevention of concurrent polling operations."""
        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        # Simulate active polling
        engine.is_polling = True
        engine.current_job_id = "active-job"

        with pytest.raises(JobPollingError, match="Already polling job"):
            asyncio.run(engine.start_polling("new-job"))

    @pytest.mark.asyncio
    async def test_cleanup_on_completion(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test proper cleanup when polling completes."""
        completed_status = JobStatus(
            job_id="test-job-123",
            status="completed",
            phase="completed",
            progress=1.0,
            message="Job completed successfully",
        )
        mock_api_client.get_job_status.return_value = completed_status

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        await engine.start_polling("test-job-123")

        # Verify cleanup
        assert engine.is_polling is False
        assert engine.current_job_id is None

    @pytest.mark.asyncio
    async def test_cleanup_on_error(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test proper cleanup when polling encounters error."""
        mock_api_client.get_job_status.side_effect = APIClientError("Server error", 500)

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(JobPollingError):
            await engine.start_polling("test-job-123")

        # Verify cleanup even on error
        assert engine.is_polling is False
        assert engine.current_job_id is None

    def test_job_status_dataclass_validation(self):
        """Test JobStatus dataclass handles various input scenarios."""
        # Test minimal status
        minimal_status = JobStatus(
            job_id="test-job",
            status="running",
            phase="indexing",
            progress=0.5,
            message="Processing",
        )

        assert minimal_status.job_id == "test-job"
        assert minimal_status.files_processed is None
        assert minimal_status.total_files is None
        assert minimal_status.details is None

        # Test full status
        full_status = JobStatus(
            job_id="test-job",
            status="running",
            phase="indexing",
            progress=0.75,
            message="Processing files",
            current_operation="Processing main.py",
            files_processed=75,
            total_files=100,
            processing_speed=10.5,
            elapsed_time=30.0,
            estimated_remaining=10.0,
            error_details="Warning: slow file detected",
            details={"branch": "main"},
        )

        assert full_status.files_processed == 75
        assert full_status.processing_speed == 10.5
        assert full_status.details["branch"] == "main"

    def test_polling_config_validation(self):
        """Test PollingConfig validates configuration values."""
        # Test valid config
        config = PollingConfig(
            base_interval=1.0,
            max_interval=10.0,
            timeout=300.0,
        )

        assert config.base_interval == 1.0
        assert config.max_interval == 10.0
        assert config.network_retry_attempts == 3  # Default

        # Test that max_interval >= base_interval
        with pytest.raises(ValueError, match="max_interval must be >= base_interval"):
            PollingConfig(base_interval=5.0, max_interval=2.0)

        # Test positive timeout
        with pytest.raises(ValueError, match="timeout must be positive"):
            PollingConfig(timeout=-1.0)


class TestJobPollingEngineIntegration:
    """Integration tests for JobPollingEngine with real scenarios."""

    @pytest.mark.asyncio
    async def test_full_sync_job_lifecycle(
        self, mock_api_client, mock_progress_callback
    ):
        """Test complete sync job lifecycle from start to finish."""
        # Create realistic job progression
        job_progression = [
            # Initial submission
            JobStatus(
                job_id="sync-job-456",
                status="queued",
                phase="queued",
                progress=0.0,
                message="Job queued for processing",
            ),
            # Git pull phase
            JobStatus(
                job_id="sync-job-456",
                status="running",
                phase="git_pull",
                progress=0.1,
                message="Pulling from remote repository",
                current_operation="git pull origin main",
            ),
            # Indexing phase start
            JobStatus(
                job_id="sync-job-456",
                status="running",
                phase="indexing",
                progress=0.2,
                message="Starting file indexing",
                files_processed=0,
                total_files=250,
            ),
            # Indexing progress
            JobStatus(
                job_id="sync-job-456",
                status="running",
                phase="indexing",
                progress=0.6,
                message="Indexing files",
                current_operation="Processing src/services/indexer.py",
                files_processed=150,
                total_files=250,
                processing_speed=12.5,
                elapsed_time=45.2,
                estimated_remaining=20.1,
            ),
            # Validation phase
            JobStatus(
                job_id="sync-job-456",
                status="running",
                phase="validation",
                progress=0.9,
                message="Validating index integrity",
                files_processed=250,
                total_files=250,
            ),
            # Completion
            JobStatus(
                job_id="sync-job-456",
                status="completed",
                phase="completed",
                progress=1.0,
                message="Sync completed successfully",
                files_processed=250,
                total_files=250,
                elapsed_time=60.3,
                details={
                    "files_added": 15,
                    "files_modified": 35,
                    "files_deleted": 5,
                    "total_indexed": 250,
                    "index_size_mb": 45.2,
                },
            ),
        ]

        mock_api_client.get_job_status.side_effect = job_progression

        config = PollingConfig(
            base_interval=0.05,  # Fast for testing
            timeout=30.0,
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=config,
        )

        result = await engine.start_polling("sync-job-456")

        # Verify final result
        assert result.status == "completed"
        assert result.progress == 1.0
        assert result.files_processed == 250
        assert result.details["files_added"] == 15

        # Verify all phases were processed
        assert mock_api_client.get_job_status.call_count == len(job_progression)

        # Verify progress callbacks were made with proper formatting
        progress_calls = mock_progress_callback.call_args_list

        # Should have setup messages (total=0) and progress bars (total>0)
        setup_calls = [call for call in progress_calls if call[0][1] == 0]
        progress_calls_filtered = [call for call in progress_calls if call[0][1] > 0]

        assert len(setup_calls) >= 2  # queued, git_pull phases
        assert len(progress_calls_filtered) >= 2  # indexing phases

    @pytest.mark.asyncio
    async def test_network_resilience_realistic_scenario(
        self, mock_api_client, mock_progress_callback
    ):
        """Test network resilience with realistic network issues."""
        # Simulate network flakiness during long-running job
        responses = [
            # First few polls succeed
            JobStatus(
                job_id="test-job",
                status="running",
                phase="indexing",
                progress=0.3,
                message="Processing",
            ),
            JobStatus(
                job_id="test-job",
                status="running",
                phase="indexing",
                progress=0.4,
                message="Processing",
            ),
            # Network issue
            NetworkError("Connection timeout", 504),
            # Recover
            JobStatus(
                job_id="test-job",
                status="running",
                phase="indexing",
                progress=0.6,
                message="Processing",
            ),
            # Another network issue
            NetworkError("Service unavailable", 503),
            # Recover and complete
            JobStatus(
                job_id="test-job",
                status="completed",
                phase="completed",
                progress=1.0,
                message="Done",
            ),
        ]

        mock_api_client.get_job_status.side_effect = responses

        config = PollingConfig(
            base_interval=0.05,
            network_retry_attempts=2,
            timeout=30.0,
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=config,
        )

        result = await engine.start_polling("test-job")

        assert result.status == "completed"
        # Should have made the expected number of calls (6 items in responses list)
        assert mock_api_client.get_job_status.call_count == 6


class TestJobPollingEngineErrorScenarios:
    """Test error scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_malformed_job_status_response(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test handling of malformed job status responses."""
        # Mock malformed response
        mock_api_client.get_job_status.side_effect = APIClientError(
            "Invalid JSON response", 200
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(JobPollingError, match="Failed to get job status"):
            await engine.start_polling("test-job")

    @pytest.mark.asyncio
    async def test_job_not_found_error(
        self, mock_api_client, mock_progress_callback, polling_config
    ):
        """Test handling when job ID is not found on server."""
        mock_api_client.get_job_status.side_effect = APIClientError(
            "Job not found", 404
        )

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=mock_progress_callback,
            config=polling_config,
        )

        with pytest.raises(JobPollingError, match="Job not found"):
            await engine.start_polling("nonexistent-job")

    def test_progress_callback_exception_handling(
        self, mock_api_client, polling_config
    ):
        """Test that progress callback exceptions don't break polling."""

        # Create progress callback that raises exception
        def failing_callback(*args, **kwargs):
            raise RuntimeError("Progress display error")

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=failing_callback,
            config=polling_config,
        )

        # Should not raise exception when displaying progress
        sample_status = JobStatus(
            job_id="test-job",
            status="running",
            phase="indexing",
            progress=0.5,
            message="Processing",
        )

        # This should not raise an exception
        engine._display_progress(sample_status)
