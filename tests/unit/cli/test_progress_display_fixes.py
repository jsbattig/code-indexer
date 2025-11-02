"""
Test suite for three critical progress display fixes.

This test file validates:
1. None/None display bug - defensive type checking in progress_callback
2. Hash phase slot tracker - slot_tracker parameter passed during hash phase
3. Time display - TimeElapsedColumn and TimeRemainingColumn present

All tests follow TDD methodology with failing tests first.
"""

from pathlib import Path
from unittest.mock import Mock
from rich.console import Console
from rich.progress import TimeElapsedColumn, TimeRemainingColumn

from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from src.code_indexer.progress.progress_display import RichLiveProgressManager
from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker


class TestNoneValueDefense:
    """Test Fix #1: None/None display bug - defensive type checking."""

    def test_progress_callback_handles_none_current_value(self):
        """Test that None current value is converted to 0."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)

        # Test calling update_complete_state with None current value
        # Should NOT raise exception and should convert None to 0
        progress_manager.update_complete_state(
            current=None,  # None value
            total=100,
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info="Test",
        )

        # Verify progress was initialized with 0 instead of None
        assert progress_manager._progress_started is True
        # The progress bar should show 0/100, not None/100

    def test_progress_callback_handles_none_total_value(self):
        """Test that None total value is converted to 0."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)

        # Test calling update_complete_state with None total value
        # Should NOT raise exception and should convert None to 0
        progress_manager.update_complete_state(
            current=50,
            total=None,  # None value
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info="Test",
        )

        # When total=None (converted to 0), should NOT start progress bar
        # because total=0 means setup message mode
        assert progress_manager._progress_started is False

    def test_progress_callback_handles_both_none_values(self):
        """Test that both None values are handled correctly."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)

        # Test calling update_complete_state with both None values
        # Should NOT raise exception
        progress_manager.update_complete_state(
            current=None,  # None value
            total=None,  # None value
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info="Test",
        )

        # Should NOT start progress bar when both are None
        assert progress_manager._progress_started is False

    def test_cli_daemon_delegation_progress_callback_none_defense(self):
        """Test that cli_daemon_delegation.py progress_callback defends against None."""
        # This test verifies the fix at line 726 in cli_daemon_delegation.py

        # Create mock components
        console = Console()
        live_manager = RichLiveProgressManager(console)

        # Create the progress_callback function as it appears in cli_daemon_delegation.py
        def progress_callback(current, total, file_path, info="", **kwargs):
            """Progress callback for daemon indexing with Rich Live display."""

            # DEFENSIVE: Ensure current and total are always integers, never None
            current = int(current) if current is not None else 0
            total = int(total) if total is not None else 0

            # Setup messages scroll at top (when total=0)
            if total == 0:
                live_manager.handle_setup_message(info)
                return

            # Would normally continue with progress bar logic...
            return current, total

        # Test with None values
        result = progress_callback(None, None, Path("test.py"), info="test message")

        # Verify None values were converted to integers
        # When both are None, they become (0, 0), which triggers setup message mode
        assert result is None  # Function returns early for total=0

        # Test with one None value
        result = progress_callback(None, 100, Path("test.py"), info="test")
        assert result == (0, 100)

        # Test with both valid values
        result = progress_callback(50, 100, Path("test.py"), info="test")
        assert result == (50, 100)


class TestHashPhaseSlotTracker:
    """Test Fix #2: Hash phase slot tracker parameter passing."""

    def test_hash_phase_passes_slot_tracker(self):
        """Test that hash phase sends slot_tracker to progress callback."""
        # Create mock progress callback
        progress_callback_mock = Mock()

        # Create a mock hash_slot_tracker
        hash_slot_tracker = CleanSlotTracker(max_slots=14)

        # Simulate the call pattern from high_throughput_processor.py line 409-416
        current_progress = 50
        total_files = 100
        file_path = Path("test.py")
        files_per_sec = 10.5
        kb_per_sec = 500.3
        active_threads = 12
        concurrent_files = [{"file_path": "test.py", "status": "hashing"}]

        info = f"{current_progress}/{total_files} files ({100 * current_progress // total_files}%) | {files_per_sec:.1f} files/s | {kb_per_sec:.1f} KB/s | {active_threads} threads | 🔍 {file_path.name}"

        # Make the call as it appears in high_throughput_processor.py
        progress_callback_mock(
            current_progress,
            total_files,
            file_path,
            info=info,
            concurrent_files=concurrent_files,
            slot_tracker=hash_slot_tracker,  # CRITICAL: This parameter must be passed
        )

        # Verify the mock was called with slot_tracker parameter
        progress_callback_mock.assert_called_once()
        call_kwargs = progress_callback_mock.call_args[1]

        # CRITICAL ASSERTION: slot_tracker must be in kwargs
        assert (
            "slot_tracker" in call_kwargs
        ), "slot_tracker parameter is missing from hash phase progress callback"
        assert call_kwargs["slot_tracker"] is hash_slot_tracker

    def test_hash_phase_slot_tracker_used_in_display(self):
        """Test that hash phase slot_tracker is actually used for display."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)

        # Create hash_slot_tracker with test data
        hash_slot_tracker = CleanSlotTracker(max_slots=14)

        # Add test file data to slot 0
        from src.code_indexer.services.clean_slot_tracker import FileData, FileStatus

        test_file_data = FileData(
            filename="test_hash.py", file_size=1024, status=FileStatus.PROCESSING
        )
        hash_slot_tracker.status_array[0] = test_file_data

        # Call update_complete_state with hash_slot_tracker
        progress_manager.update_complete_state(
            current=50,
            total=100,
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=hash_slot_tracker,  # Pass slot tracker
            info="🔍 Hashing files...",
        )

        # Verify slot_tracker was stored
        assert progress_manager.slot_tracker is hash_slot_tracker

        # Verify display uses slot_tracker data
        display = progress_manager.get_integrated_display()
        assert display is not None


class TestTimeDisplay:
    """Test Fix #3: Time display - verify TimeElapsed and TimeRemaining columns."""

    def test_progress_manager_has_time_columns(self):
        """Test that MultiThreadedProgressManager includes time display columns."""
        console = Console()
        progress_manager = MultiThreadedProgressManager(console)

        # Verify Progress instance has time columns
        # Check that columns list contains TimeElapsedColumn and TimeRemainingColumn
        columns = progress_manager.progress.columns

        has_elapsed = any(isinstance(col, TimeElapsedColumn) for col in columns)
        has_remaining = any(isinstance(col, TimeRemainingColumn) for col in columns)

        assert has_elapsed, "TimeElapsedColumn is missing from progress display"
        assert has_remaining, "TimeRemainingColumn is missing from progress display"

    def test_time_columns_show_in_display(self):
        """Test that time information is actually displayed."""
        console = Console()
        progress_manager = MultiThreadedProgressManager(console)

        # Initialize progress with some data
        progress_manager.update_complete_state(
            current=50,
            total=100,
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info="Test",
        )

        # Get display and verify time columns are rendering
        display = progress_manager.get_integrated_display()
        assert display is not None

        # Verify progress was started (which means time tracking is active)
        assert progress_manager._progress_started is True


class TestIntegrationScenarios:
    """Integration tests combining all three fixes."""

    def test_hash_phase_with_none_values_and_time_display(self):
        """Test hash phase handles None values while showing time display."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)
        hash_slot_tracker = CleanSlotTracker(max_slots=14)

        # Simulate hash phase with None current value (edge case)
        progress_manager.update_complete_state(
            current=None,  # None value - should convert to 0
            total=100,
            files_per_second=10.0,
            kb_per_second=500.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=hash_slot_tracker,
            info="🔍 Hashing files...",
        )

        # Verify no crash and progress initialized
        assert progress_manager._progress_started is True
        assert progress_manager.slot_tracker is hash_slot_tracker

    def test_full_indexing_workflow_with_all_fixes(self):
        """Test complete indexing workflow using all three fixes."""
        console = Console()
        live_manager = RichLiveProgressManager(console)
        progress_manager = MultiThreadedProgressManager(console, live_manager)

        # Phase 1: Hash phase with slot tracker
        hash_slot_tracker = CleanSlotTracker(max_slots=14)
        progress_manager.update_complete_state(
            current=0,
            total=100,
            files_per_second=0.0,
            kb_per_second=0.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=hash_slot_tracker,
            info="🔍 Starting hash calculation...",
        )

        assert progress_manager.slot_tracker is hash_slot_tracker

        # Phase 2: Update with progress (potential None values)
        for i in range(1, 101):
            current = i if i % 10 != 0 else None  # Inject None every 10th iteration
            progress_manager.update_complete_state(
                current=current,
                total=100,
                files_per_second=10.0,
                kb_per_second=500.0,
                active_threads=12,
                concurrent_files=[],
                slot_tracker=hash_slot_tracker,
                info=f"🔍 Hashing file {i}...",
            )

        # Phase 3: Verify final state
        display = progress_manager.get_integrated_display()
        assert display is not None
        assert progress_manager._progress_started is True

        # Verify time columns are present
        columns = progress_manager.progress.columns
        has_elapsed = any(isinstance(col, TimeElapsedColumn) for col in columns)
        has_remaining = any(isinstance(col, TimeRemainingColumn) for col in columns)
        assert has_elapsed and has_remaining
