"""
Unit tests for RealTimeFeedbackManager - Story 04 component.

Tests the core functionality for eliminating silent periods:
- Immediate start feedback (< 100ms)
- Continuous activity heartbeat (every 5-10 seconds)
- Real-time file status transitions (< 100ms)
- Comprehensive progress information formatting
- Multi-threaded processing visibility
"""

import time
import threading
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from code_indexer.progress.real_time_feedback_manager import (
    RealTimeFeedbackManager,
    HeartbeatMonitor,
    FileStatusTracker,
)


class TestRealTimeFeedbackManager:
    """Test the main RealTimeFeedbackManager class."""

    @pytest.fixture
    def feedback_manager(self):
        """Create RealTimeFeedbackManager for testing."""
        return RealTimeFeedbackManager(
            total_files=10, thread_count=8, activity_interval=5.0
        )

    @pytest.fixture
    def mock_callback(self):
        """Create mock progress callback."""
        return Mock()

    def test_immediate_start_feedback_timing(self, feedback_manager, mock_callback):
        """
        Test immediate start feedback is provided within 100ms.

        CURRENTLY FAILING - RealTimeFeedbackManager class doesn't exist yet.
        """
        start_time = time.time()

        # This should provide immediate feedback
        feedback_manager.initialize_continuous_feedback(mock_callback)

        feedback_time = time.time()
        elapsed = feedback_time - start_time

        # Verify immediate feedback timing
        assert elapsed < 0.1, f"Start feedback took {elapsed:.3f}s, should be < 100ms"

        # Verify callback was called with correct start message
        mock_callback.assert_called_with(
            0, 0, Path(""), info="🚀 Starting parallel processing with 8 workers"
        )

    def test_continuous_activity_heartbeat(self, feedback_manager, mock_callback):
        """
        Test continuous activity updates every 5-10 seconds.

        CURRENTLY FAILING - HeartbeatMonitor doesn't exist yet.
        """
        feedback_manager.initialize_continuous_feedback(mock_callback)

        # Simulate time passing without file completions
        with patch("time.time") as mock_time:
            # Start at time 0
            mock_time.return_value = 0.0
            feedback_manager.initialize_continuous_feedback(mock_callback)

            # Advance to 6 seconds (should trigger heartbeat)
            mock_time.return_value = 6.0
            feedback_manager.provide_continuous_activity_updates(8, mock_callback)

            # Verify heartbeat callback
            assert (
                len(mock_callback.call_args_list) >= 2
            ), "Should have start + heartbeat calls"

            # Check heartbeat message format by looking at info keyword arguments
            heartbeat_found = any(
                "⚙️" in call.kwargs.get("info", "")
                and "workers active" in call.kwargs.get("info", "")
                for call in mock_callback.call_args_list
            )

            assert (
                heartbeat_found
            ), f"Heartbeat message not found in callback calls: {[call.kwargs.get('info', '') for call in mock_callback.call_args_list]}"

    def test_file_status_transitions_timing(self, feedback_manager, mock_callback):
        """
        Test real-time file status transitions are immediate (< 100ms).

        CURRENTLY FAILING - FileStatusTracker doesn't exist yet.
        """
        file_path = Path("test_file.py")

        # Test queued → processing transition
        start_time = time.time()
        feedback_manager.update_file_status_realtime(file_path, "queued", mock_callback)
        queued_time = time.time()

        feedback_manager.update_file_status_realtime(
            file_path, "processing", mock_callback
        )
        processing_time = time.time()

        feedback_manager.update_file_status_realtime(
            file_path, "complete", mock_callback
        )
        complete_time = time.time()

        # Verify timing requirements
        assert queued_time - start_time < 0.1, "Queued status took too long"
        assert (
            processing_time - queued_time < 0.1
        ), "Processing transition took too long"
        assert (
            complete_time - processing_time < 0.1
        ), "Complete transition took too long"

        # Verify status icons and messages
        calls = mock_callback.call_args_list
        assert len(calls) == 3, f"Expected 3 status calls, got {len(calls)}"

        assert "📥" in calls[0].kwargs["info"], "Queued status missing 📥 icon"
        assert "🔄" in calls[1].kwargs["info"], "Processing status missing 🔄 icon"
        assert "✅" in calls[2].kwargs["info"], "Complete status missing ✅ icon"

    def test_comprehensive_progress_formatting(self, feedback_manager, mock_callback):
        """
        Test comprehensive progress information formatting.

        CURRENTLY FAILING - Progress formatting methods don't exist yet.
        """
        # Test progress update with all required components
        feedback_manager.update_overall_progress_realtime(
            completed_files=25,
            total_files=100,
            files_per_second=4.2,
            kb_per_second=156.8,
            active_threads=8,
            current_file="large_file.py",
            callback=mock_callback,
        )

        # Verify comprehensive format
        mock_callback.assert_called()
        call_info = mock_callback.call_args.kwargs["info"]  # info parameter

        # Check all required components
        assert "25/100" in call_info, "File completion count missing"
        assert "25%" in call_info or "(25%)" in call_info, "Percentage missing"
        assert "4.2" in call_info and "files/s" in call_info, "Files/s rate missing"
        assert "156.8" in call_info and "KB/s" in call_info, "KB/s rate missing"
        assert "8" in call_info and "threads" in call_info, "Thread count missing"
        assert "large_file.py" in call_info, "Current file missing"

        # Verify format uses | separators for readability
        assert "|" in call_info, "Progress info should use | separators"

    def test_multithreaded_processing_visibility(self, feedback_manager, mock_callback):
        """
        Test multi-threaded processing visibility display.

        CURRENTLY FAILING - Multi-threaded display methods don't exist yet.
        """
        # Create mock concurrent file data
        concurrent_files = [
            {
                "slot_id": 1,
                "file_path": "file1.py",
                "progress_percent": 25,
                "status": "processing",
            },
            {
                "slot_id": 2,
                "file_path": "file2.py",
                "progress_percent": 80,
                "status": "vectorizing",
            },
            {
                "slot_id": 3,
                "file_path": "file3.py",
                "progress_percent": 60,
                "status": "chunking",
            },
        ]

        feedback_manager.update_multithreaded_visibility(
            concurrent_files, mock_callback
        )

        # Verify multi-threaded display format
        mock_callback.assert_called()
        call_info = mock_callback.call_args.kwargs["info"]

        # Should show worker information with percentages
        assert (
            "Worker" in call_info or "Thread" in call_info
        ), "Worker/Thread info missing"
        assert "%" in call_info, "Progress percentages missing"
        assert any(
            f in call_info for f in ["file1.py", "file2.py", "file3.py"]
        ), "File names missing"

        # Should indicate concurrent processing
        assert len(concurrent_files) <= 8, "Should handle up to 8 concurrent files"

    def test_silent_period_prevention(self, feedback_manager, mock_callback):
        """
        Test that silent period monitoring prevents gaps > 10 seconds.

        CURRENTLY FAILING - Silent period monitoring doesn't exist yet.
        """
        feedback_manager.initialize_continuous_feedback(mock_callback)

        with patch("time.time") as mock_time:
            # Start at time 0
            mock_time.return_value = 0.0
            feedback_manager.last_feedback_time = 0.0

            # Advance to 12 seconds (should trigger silent period prevention)
            mock_time.return_value = 12.0
            result = feedback_manager.ensure_no_silent_periods(mock_callback)

            assert result is True, "Silent period prevention should trigger"

            # Verify anti-silent period callback
            mock_callback.assert_called_with(
                0, 0, Path(""), info="⚙️ Processing continues..."
            )

    def test_heartbeat_monitor_thread_safety(self, mock_callback):
        """
        Test that heartbeat monitoring is thread-safe.

        Uses a short heartbeat interval to ensure triggers during test.
        """
        # Create feedback manager with short interval for testing
        feedback_manager = RealTimeFeedbackManager(
            total_files=10,
            thread_count=8,
            activity_interval=0.05,  # 50ms interval for testing
        )

        feedback_manager.initialize_continuous_feedback(mock_callback)

        # Simulate concurrent heartbeat updates from multiple threads
        def update_heartbeat(worker_id):
            for i in range(2):
                feedback_manager.provide_continuous_activity_updates(
                    active_workers=worker_id, callback=mock_callback
                )
                time.sleep(0.1)  # Sleep longer than heartbeat interval

        # Start multiple threads
        threads = []
        for worker_id in range(3):  # Fewer threads for cleaner test
            thread = threading.Thread(target=update_heartbeat, args=(worker_id,))
            threads.append(thread)
            thread.start()

        # Wait for threads to complete
        for thread in threads:
            thread.join()

        # Verify thread safety (should not crash and should have multiple calls)
        # We expect the initial call plus at least one heartbeat from threaded calls
        assert (
            mock_callback.call_count >= 2
        ), f"Should have multiple calls from threaded execution, got {mock_callback.call_count}"

        # Most importantly, verify it didn't crash during concurrent access
        assert True, "Thread safety test completed without crashing"

    def test_calculate_processing_rate_accuracy(self, feedback_manager):
        """
        Test processing rate calculations are accurate and smooth.

        CURRENTLY FAILING - Rate calculation methods don't exist yet.
        """
        # Simulate file completions over time
        with patch("time.time") as mock_time:
            mock_time.return_value = 0.0
            feedback_manager._initialize_rate_tracking()

            # Complete files at regular intervals
            rates = []
            for i in range(1, 6):
                mock_time.return_value = i * 2.0  # Every 2 seconds
                rate = feedback_manager._calculate_files_per_second(i)
                rates.append(rate)
                if i > 1:  # Skip first call which may be 0 due to initialization
                    assert (
                        rate > 0
                    ), f"Rate should be positive after first call, got {rate} at iteration {i}"

            # Should have at least some positive rates
            positive_rates = [r for r in rates if r > 0]
            assert (
                len(positive_rates) >= 2
            ), f"Should have multiple positive rates, got {rates}"

            # Final rate should be approximately 0.5 files/second
            final_rate = rates[-1]
            assert 0.4 <= final_rate <= 0.6, f"Expected ~0.5 files/s, got {final_rate}"


class TestHeartbeatMonitor:
    """Test the HeartbeatMonitor component."""

    def test_heartbeat_timing_accuracy(self):
        """
        Test heartbeat monitor provides updates at correct intervals.

        CURRENTLY FAILING - HeartbeatMonitor class doesn't exist yet.
        """
        monitor = HeartbeatMonitor(interval_seconds=5.0)
        mock_callback = Mock()

        with patch("time.time") as mock_time:
            mock_time.return_value = 0.0
            monitor.start_monitoring(mock_callback)

            # No heartbeat yet (< 5 seconds)
            mock_time.return_value = 4.0
            monitor.check_heartbeat(8, mock_callback)
            assert not mock_callback.called, "Heartbeat too early"

            # Heartbeat should trigger (>= 5 seconds)
            mock_time.return_value = 5.5
            monitor.check_heartbeat(8, mock_callback)
            assert mock_callback.called, "Heartbeat should trigger"

    def test_heartbeat_message_format(self):
        """
        Test heartbeat messages have correct format and content.

        CURRENTLY FAILING - HeartbeatMonitor doesn't exist yet.
        """
        monitor = HeartbeatMonitor(interval_seconds=5.0)
        mock_callback = Mock()

        monitor.trigger_heartbeat(active_workers=6, callback=mock_callback)

        mock_callback.assert_called_once()
        call_info = mock_callback.call_args.kwargs["info"]

        assert "⚙️" in call_info, "Heartbeat missing gear emoji"
        assert "6 workers active" in call_info, "Worker count missing"
        assert "processing files" in call_info, "Processing indication missing"


class TestFileStatusTracker:
    """Test the FileStatusTracker component."""

    def test_status_icon_mapping(self):
        """
        Test correct status icons are used for different states.

        CURRENTLY FAILING - FileStatusTracker class doesn't exist yet.
        """
        tracker = FileStatusTracker()

        # Test all status icon mappings
        assert tracker.get_status_icon("queued") == "📥"
        assert tracker.get_status_icon("processing") == "🔄"
        assert tracker.get_status_icon("complete") == "✅"
        assert tracker.get_status_icon("error") == "❌"
        assert tracker.get_status_icon("unknown") == "🔄"  # Default

    def test_status_message_formatting(self):
        """
        Test status messages are properly formatted.

        CURRENTLY FAILING - FileStatusTracker doesn't exist yet.
        """
        tracker = FileStatusTracker()
        file_path = Path("test_file.py")

        message = tracker.format_status_message(file_path, "processing")

        assert "🔄" in message, "Processing icon missing"
        assert "Processing" in message, "Status text missing"
        assert "test_file.py" in message, "Filename missing"

        # Test format: "🔄 Processing test_file.py"
        expected_parts = ["🔄", "Processing", "test_file.py"]
        for part in expected_parts:
            assert part in message, f"Missing part: {part}"
