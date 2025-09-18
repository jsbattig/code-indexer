"""
Tests for Real-Time Progress Display - Story 14: Enhanced JobPollingEngine

Tests the real-time progress display system that provides single-line progress bar
updates with speed metrics, current operation display, and estimated time remaining.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from code_indexer.remote.polling import JobPollingEngine, JobStatus, PollingConfig
from code_indexer.api_clients.base_client import CIDXRemoteAPIClient


class TestRealtimeProgressDisplay:
    """Test suite for real-time progress display enhancements."""

    def test_progress_display_follows_cidx_format_setup_messages(self):
        """Test progress display follows CIDX format for setup messages (total=0)."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Create status with no file progress (setup message)
        status = JobStatus(
            job_id="test-123",
            status="running",
            phase="git_pull",
            progress=0.0,
            message="Pulling latest changes from remote",
            files_processed=None,
            total_files=None,
        )

        engine._display_progress(status, elapsed_time=30.5, remaining_time=120.3)

        # Should call progress_callback with total=0 (triggers info display)
        progress_callback.assert_called_once_with(
            0,
            0,
            Path(""),
            info="git_pull: Pulling latest changes from remote (timeout: 2m)",
        )

    def test_progress_display_follows_cidx_format_file_progress(self):
        """Test progress display follows CIDX format for file progress (total>0)."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Create status with file progress
        status = JobStatus(
            job_id="test-123",
            status="running",
            phase="indexing",
            progress=0.6,
            message="Processing files",
            files_processed=180,
            total_files=300,
            processing_speed=2.5,
            current_operation="/repo/src/services/indexer.py",
        )

        engine._display_progress(status, elapsed_time=45.2, remaining_time=75.8)

        # Should call progress_callback with correct CIDX format
        # Format: "X/Y files (Z%) | A emb/s | phase | filename"
        expected_info = "180/300 files (60%) | 2.5 emb/s | indexing | /repo/src/services/indexer.py | timeout: 1m"
        progress_callback.assert_called_once_with(
            180, 300, Path("/repo/src/services/indexer.py"), info=expected_info
        )

    def test_speed_metrics_display_formatting(self):
        """Test speed metrics are properly formatted in progress display."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Test different speed values
        test_cases = [
            (1.234, "1.2 emb/s"),
            (10.789, "10.8 emb/s"),
            (0.1, "0.1 emb/s"),
            (100.567, "100.6 emb/s"),
        ]

        for speed, expected_format in test_cases:
            progress_callback.reset_mock()

            status = JobStatus(
                job_id="test-123",
                status="running",
                phase="indexing",
                progress=0.5,
                message="Processing",
                files_processed=50,
                total_files=100,
                processing_speed=speed,
                current_operation="test.py",
            )

            engine._display_progress(status)

            # Extract info argument (keyword argument) and check speed formatting
            call_args = progress_callback.call_args
            info = call_args[1]["info"]  # info is a keyword argument
            assert expected_format in info

    def test_current_operation_display_with_filename_extraction(self):
        """Test current operation displays proper filename from full path."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Test with full file path
        status = JobStatus(
            job_id="test-123",
            status="running",
            phase="indexing",
            progress=0.3,
            message="Processing",
            files_processed=30,
            total_files=100,
            processing_speed=1.5,
            current_operation="/home/user/project/src/components/auth/login.py",
        )

        engine._display_progress(status)

        # Should use full path for info but extract filename for display
        call_args = progress_callback.call_args
        file_path_arg = call_args[0][2]  # Third positional argument
        info_arg = call_args[1]["info"]

        assert file_path_arg == Path("/home/user/project/src/components/auth/login.py")
        assert "/home/user/project/src/components/auth/login.py" in info_arg

    def test_estimated_time_remaining_display(self):
        """Test estimated time remaining is properly calculated and displayed."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Test timeout display in seconds (< 60s)
        status = JobStatus(
            job_id="test-123",
            status="running",
            phase="indexing",
            progress=0.75,
            message="Almost done",
            files_processed=75,
            total_files=100,
            processing_speed=2.0,
            current_operation="final.py",
        )

        engine._display_progress(status, elapsed_time=90, remaining_time=45)

        call_args = progress_callback.call_args
        info = call_args[1]["info"]  # info is a keyword argument
        assert "timeout: 45s" in info

        # Test timeout display in minutes (>= 60s)
        progress_callback.reset_mock()

        engine._display_progress(status, elapsed_time=60, remaining_time=150)

        call_args = progress_callback.call_args
        info = call_args[1]["info"]  # info is a keyword argument
        assert "timeout: 2m" in info

    def test_single_line_progress_bar_no_scrolling(self):
        """Test that progress updates use single line format (no scrolling output)."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Simulate rapid progress updates
        for i in range(0, 101, 10):  # 0%, 10%, 20%, ..., 100%
            status = JobStatus(
                job_id="test-123",
                status="running",
                phase="indexing",
                progress=i / 100.0,
                message="Processing",
                files_processed=i,
                total_files=100,
                processing_speed=3.5,
                current_operation=f"file_{i}.py",
            )

            engine._display_progress(status)

        # Should have called progress_callback 11 times (one per update)
        assert progress_callback.call_count == 11

        # Each call should use same structure (fixed bottom line)
        for call in progress_callback.call_args_list:
            args = call[0]  # positional arguments
            kwargs = call[1]  # keyword arguments
            _, total, file_path = args[0], args[1], args[2]
            info = kwargs["info"]

            # All calls should have total > 0 (progress bar mode)
            assert total > 0
            assert isinstance(file_path, Path)
            assert isinstance(info, str)

    def test_phase_transition_progress_display_consistency(self):
        """Test progress display consistency during phase transitions."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Test transition from git_pull to indexing
        git_status = JobStatus(
            job_id="test-123",
            status="running",
            phase="git_pull",
            progress=1.0,  # 100% complete
            message="Git pull completed",
            files_processed=None,  # No file progress for git phase
            total_files=None,
        )

        engine._display_progress(git_status)

        indexing_status = JobStatus(
            job_id="test-123",
            status="running",
            phase="indexing",
            progress=0.0,  # Just started
            message="Starting indexing",
            files_processed=0,
            total_files=250,
            processing_speed=0.0,
            current_operation="Initializing...",
        )

        engine._display_progress(indexing_status)

        # Both calls should work without errors
        assert progress_callback.call_count == 2

        # First call should be setup message (total=0)
        first_call = progress_callback.call_args_list[0]
        assert first_call[0][1] == 0  # total=0

        # Second call should be progress bar (total>0)
        second_call = progress_callback.call_args_list[1]
        assert second_call[0][1] > 0  # total>0

    def test_error_resilience_in_progress_display(self):
        """Test progress display handles errors gracefully without breaking polling."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock(side_effect=Exception("Display error"))

        engine = JobPollingEngine(api_client, progress_callback)

        status = JobStatus(
            job_id="test-123",
            status="running",
            phase="indexing",
            progress=0.5,
            message="Processing",
            files_processed=50,
            total_files=100,
        )

        # Should not raise exception even if progress_callback fails
        engine._display_progress(status)

        # Callback should have been called (and failed)
        progress_callback.assert_called_once()

    def test_multi_threaded_display_updates(self):
        """Test progress display handles concurrent updates safely."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        engine = JobPollingEngine(api_client, progress_callback)

        # Simulate multiple threads updating progress concurrently
        import threading

        def update_progress(file_num):
            status = JobStatus(
                job_id="test-123",
                status="running",
                phase="indexing",
                progress=file_num / 100.0,
                message="Processing",
                files_processed=file_num,
                total_files=100,
                current_operation=f"file_{file_num}.py",
            )
            engine._display_progress(status)

        # Create multiple threads updating progress
        threads = []
        for i in range(1, 11):  # 10 threads
            thread = threading.Thread(target=update_progress, args=(i,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All threads should have completed without errors
        assert progress_callback.call_count == 10

    @pytest.mark.asyncio
    async def test_real_time_updates_during_polling_loop(self):
        """Test real-time progress updates during actual polling loop."""
        api_client = Mock(spec=CIDXRemoteAPIClient)
        progress_callback = Mock()

        # Mock API responses with progressive status updates
        status_responses = [
            {
                "job_id": "test-123",
                "status": "running",
                "phase": "git_pull",
                "progress": 0.5,
                "message": "Pulling changes",
            },
            {
                "job_id": "test-123",
                "status": "running",
                "phase": "indexing",
                "progress": 0.3,
                "message": "Processing files",
                "files_processed": 30,
                "total_files": 100,
                "processing_speed": 2.1,
                "current_operation": "src/main.py",
            },
            {
                "job_id": "test-123",
                "status": "completed",
                "phase": "completed",
                "progress": 1.0,
                "message": "Sync completed",
                "files_processed": 100,
                "total_files": 100,
            },
        ]

        api_client.get_job_status = AsyncMock(side_effect=status_responses)

        engine = JobPollingEngine(
            api_client,
            progress_callback,
            config=PollingConfig(base_interval=0.1, timeout=2.0),
        )

        # Start polling and let it run through all status updates
        final_status = await engine.start_polling("test-123")

        # Should have made progress updates for each status response
        assert progress_callback.call_count >= 3
        assert final_status.status == "completed"

        # Check that final status had correct progress display
        last_call = progress_callback.call_args_list[-1]
        args = last_call[0]  # positional arguments
        kwargs = last_call[1]  # keyword arguments
        current, total, _ = args[0], args[1], args[2]
        info = kwargs["info"]

        assert current == 100
        assert total == 100
        assert "100/100 files (100%)" in info
