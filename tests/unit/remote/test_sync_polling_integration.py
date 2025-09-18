"""Integration tests for sync command with polling engine.

Tests the integration between the sync command and job polling engine,
ensuring proper progress display and job completion tracking.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from code_indexer.remote.sync_execution import (
    execute_repository_sync,
    _poll_sync_jobs,
    SyncJobResult,
)
from code_indexer.remote.polling import JobStatus, JobPollingEngine


@pytest.fixture
def mock_sync_client():
    """Create mock sync client."""
    client = AsyncMock()
    client.sync_repository = AsyncMock()
    client.sync_all_repositories = AsyncMock()
    client.get_job_status = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_progress_callback():
    """Create mock progress callback."""
    return Mock()


@pytest.fixture
def sample_job_results():
    """Create sample job results for testing."""
    return [
        SyncJobResult(
            job_id="job-1",
            status="queued",
            message="Job queued",
            repository="repo1",
        ),
        SyncJobResult(
            job_id="job-2",
            status="running",
            message="Job running",
            repository="repo2",
        ),
    ]


@pytest.fixture
def project_root(tmp_path):
    """Create mock project root with configuration files."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()

    config_dir = project_dir / ".code-indexer"
    config_dir.mkdir()

    # Create remote config
    remote_config = config_dir / ".remote-config"
    remote_config.write_text('{"server_url": "https://test-server.com"}')

    # Create credentials file
    credentials_file = config_dir / ".credentials"
    credentials_file.write_text('{"username": "test", "password": "test"}')

    return project_dir


class TestSyncPollingIntegration:
    """Test integration between sync execution and polling."""

    @pytest.mark.asyncio
    async def test_poll_sync_jobs_single_job_completion(
        self, mock_sync_client, mock_progress_callback, sample_job_results
    ):
        """Test polling a single job to completion."""
        # Setup job progression
        job_statuses = [
            JobStatus(
                job_id="job-1",
                status="running",
                phase="indexing",
                progress=0.5,
                message="Processing files",
                files_processed=50,
                total_files=100,
            ),
            JobStatus(
                job_id="job-1",
                status="completed",
                phase="completed",
                progress=1.0,
                message="Job completed successfully",
                files_processed=100,
                total_files=100,
            ),
        ]

        mock_sync_client.get_job_status.side_effect = job_statuses

        # Test only the first job (which needs polling)
        jobs_to_poll = [sample_job_results[0]]

        await _poll_sync_jobs(
            mock_sync_client, jobs_to_poll, 60, mock_progress_callback
        )

        # Verify job was polled and updated
        assert mock_sync_client.get_job_status.call_count == 2
        assert jobs_to_poll[0].status == "completed"
        assert jobs_to_poll[0].message == "Job completed successfully"

        # Verify progress callbacks were made
        assert mock_progress_callback.call_count >= 2

    @pytest.mark.asyncio
    async def test_poll_sync_jobs_multiple_jobs(
        self, mock_sync_client, mock_progress_callback, sample_job_results
    ):
        """Test polling multiple jobs simultaneously."""

        # Setup different progressions for each job
        def job_status_side_effect(job_id):
            if job_id == "job-1":
                return [
                    JobStatus(
                        job_id="job-1",
                        status="running",
                        phase="indexing",
                        progress=0.8,
                        message="Almost done",
                    ),
                    JobStatus(
                        job_id="job-1",
                        status="completed",
                        phase="completed",
                        progress=1.0,
                        message="Done",
                    ),
                ][mock_sync_client.get_job_status.call_count % 2]
            else:  # job-2
                return JobStatus(
                    job_id="job-2",
                    status="completed",
                    phase="completed",
                    progress=1.0,
                    message="Done",
                )

        mock_sync_client.get_job_status.side_effect = job_status_side_effect

        await _poll_sync_jobs(
            mock_sync_client, sample_job_results, 60, mock_progress_callback
        )

        # Both jobs should be completed
        assert all(job.status == "completed" for job in sample_job_results)

        # Should have polled both jobs
        assert mock_sync_client.get_job_status.call_count >= 2

    @pytest.mark.asyncio
    async def test_poll_sync_jobs_with_job_failure(
        self, mock_sync_client, mock_progress_callback, sample_job_results
    ):
        """Test polling when a job fails."""
        failed_status = JobStatus(
            job_id="job-1",
            status="failed",
            phase="indexing",
            progress=0.3,
            message="Indexing failed: Permission denied",
            error_details="Cannot access restricted folder",
        )

        mock_sync_client.get_job_status.return_value = failed_status

        jobs_to_poll = [sample_job_results[0]]

        # Should handle job failure gracefully
        await _poll_sync_jobs(
            mock_sync_client, jobs_to_poll, 60, mock_progress_callback
        )

        # Job result should be updated with error status
        assert jobs_to_poll[0].status == "error"
        assert "Polling failed" in jobs_to_poll[0].message

    @pytest.mark.asyncio
    async def test_poll_sync_jobs_skip_completed_jobs(
        self, mock_sync_client, mock_progress_callback
    ):
        """Test that completed jobs are skipped during polling."""
        completed_jobs = [
            SyncJobResult(
                job_id="job-1",
                status="completed",
                message="Already completed",
                repository="repo1",
            )
        ]

        await _poll_sync_jobs(
            mock_sync_client, completed_jobs, 60, mock_progress_callback
        )

        # Should not poll already completed jobs
        mock_sync_client.get_job_status.assert_not_called()
        mock_progress_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_sync_jobs_network_resilience(
        self, mock_sync_client, mock_progress_callback, sample_job_results
    ):
        """Test polling network error handling."""
        from code_indexer.api_clients.base_client import NetworkError

        # First call fails, second succeeds
        responses = [
            NetworkError("Connection timeout", 504),
            JobStatus(
                job_id="job-1",
                status="completed",
                phase="completed",
                progress=1.0,
                message="Done",
            ),
        ]

        mock_sync_client.get_job_status.side_effect = responses

        jobs_to_poll = [sample_job_results[0]]

        await _poll_sync_jobs(
            mock_sync_client, jobs_to_poll, 60, mock_progress_callback
        )

        # Should have retried and succeeded
        assert mock_sync_client.get_job_status.call_count == 2
        assert jobs_to_poll[0].status == "completed"

    @pytest.mark.asyncio
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    async def test_execute_repository_sync_with_polling(
        self,
        mock_load_creds,
        mock_load_config,
        mock_progress_callback,
        project_root,
    ):
        """Test full sync execution with polling enabled."""
        # Mock configuration loading
        mock_load_config.return_value = {"server_url": "https://test-server.com"}
        mock_load_creds.return_value = {"username": "test", "password": "test"}

        # Mock sync client
        with patch(
            "code_indexer.remote.sync_execution.SyncClient"
        ) as mock_sync_client_class:
            mock_sync_client = AsyncMock()
            mock_sync_client_class.return_value = mock_sync_client

            # Mock job submission
            job_result = SyncJobResult(
                job_id="test-job-123",
                status="queued",
                message="Job submitted",
                repository="test-repo",
            )
            mock_sync_client.sync_repository.return_value = job_result

            # Mock job polling progression
            job_progression = [
                JobStatus(
                    job_id="test-job-123",
                    status="running",
                    phase="git_pull",
                    progress=0.2,
                    message="Pulling from remote",
                ),
                JobStatus(
                    job_id="test-job-123",
                    status="completed",
                    phase="completed",
                    progress=1.0,
                    message="Sync completed successfully",
                ),
            ]
            mock_sync_client.get_job_status.side_effect = job_progression

            # Execute sync with polling
            results = await execute_repository_sync(
                repository_alias="test-repo",
                project_root=project_root,
                sync_all=False,
                full_reindex=False,
                no_pull=False,
                dry_run=False,
                timeout=300,
                enable_polling=True,
                progress_callback=mock_progress_callback,
            )

            # Verify results
            assert len(results) == 1
            assert results[0].job_id == "test-job-123"
            assert results[0].status == "completed"

            # Verify polling was performed
            assert mock_sync_client.get_job_status.call_count == 2
            assert mock_progress_callback.call_count >= 2

    @pytest.mark.asyncio
    @patch("code_indexer.remote.sync_execution._load_remote_configuration")
    @patch("code_indexer.remote.sync_execution._load_and_decrypt_credentials")
    async def test_execute_repository_sync_dry_run_no_polling(
        self,
        mock_load_creds,
        mock_load_config,
        mock_progress_callback,
        project_root,
    ):
        """Test that dry run mode doesn't start polling."""
        # Mock configuration loading
        mock_load_config.return_value = {"server_url": "https://test-server.com"}
        mock_load_creds.return_value = {"username": "test", "password": "test"}

        # Execute dry run sync
        results = await execute_repository_sync(
            repository_alias="test-repo",
            project_root=project_root,
            sync_all=False,
            full_reindex=False,
            no_pull=False,
            dry_run=True,
            timeout=300,
            enable_polling=True,
            progress_callback=mock_progress_callback,
        )

        # Verify dry run results
        assert len(results) == 1
        assert results[0].status == "would_sync"
        assert "Would sync repository" in results[0].message

        # Verify no polling was performed (no progress callback calls)
        mock_progress_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_polling_config_from_timeout(
        self, mock_sync_client, mock_progress_callback
    ):
        """Test that polling config is properly created from timeout parameter."""
        jobs = [
            SyncJobResult(
                job_id="test-job",
                status="queued",
                message="Test",
                repository="test-repo",
            )
        ]

        # Mock successful completion
        mock_sync_client.get_job_status.return_value = JobStatus(
            job_id="test-job",
            status="completed",
            phase="completed",
            progress=1.0,
            message="Done",
        )

        # Test with custom timeout
        timeout = 600  # 10 minutes

        await _poll_sync_jobs(mock_sync_client, jobs, timeout, mock_progress_callback)

        # Verify job was polled
        mock_sync_client.get_job_status.assert_called_once()

        # The timeout should have been used in PollingConfig creation
        # (We can't directly verify this without mocking PollingConfig,
        # but the job should complete successfully with the longer timeout)
        assert jobs[0].status == "completed"


class TestJobPollingEngineProgressDisplay:
    """Test progress display integration with JobPollingEngine."""

    def test_progress_callback_format_cidx_compatible(self):
        """Test that progress callback follows CIDX format."""

        mock_api_client = AsyncMock()
        progress_calls = []

        def capture_progress(current, total, path, info=None, **kwargs):
            progress_calls.append((current, total, str(path), info))

        engine = JobPollingEngine(
            api_client=mock_api_client,
            progress_callback=capture_progress,
        )

        # Test setup message (total=0)
        setup_status = JobStatus(
            job_id="test-job",
            status="initializing",
            phase="setup",
            progress=0.0,
            message="Preparing sync job",
        )
        engine._display_progress(setup_status)

        # Test progress bar (total > 0)
        progress_status = JobStatus(
            job_id="test-job",
            status="running",
            phase="indexing",
            progress=0.75,
            message="Processing files",
            current_operation="Processing src/main.py",
            files_processed=75,
            total_files=100,
            processing_speed=10.5,
        )
        engine._display_progress(progress_status)

        # Verify calls
        assert len(progress_calls) == 2

        # Setup call
        setup_call = progress_calls[0]
        assert setup_call[0] == 0  # current
        assert setup_call[1] == 0  # total (triggers info display)
        assert "setup: Preparing sync job" in setup_call[3]  # info

        # Progress call
        progress_call = progress_calls[1]
        assert progress_call[0] == 75  # current files
        assert progress_call[1] == 100  # total files
        assert "75/100 files (75%)" in progress_call[3]  # info
        assert "10.5 emb/s" in progress_call[3]  # processing speed
        assert "indexing" in progress_call[3]  # phase
        assert "Processing src/main.py" in progress_call[3]  # current operation
