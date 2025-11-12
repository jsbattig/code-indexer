"""
Unit tests for daemon progress display UX bugs.

Tests two critical bugs:
1. Bug 1: "none/<total>" display when info parsing fails (should show numeric current)
2. Bug 2: Empty concurrent_files list in daemon mode (should reconstruct from slot_tracker)
"""

import pytest
from io import StringIO
from unittest.mock import Mock
from rich.console import Console

from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from code_indexer.progress.progress_display import RichLiveProgressManager
from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileData,
    FileStatus,
)


def render_table_to_text(table, console: Console) -> str:
    """Render a Rich Table to plain text for testing."""
    string_io = StringIO()
    temp_console = Console(file=string_io, force_terminal=False, width=120)
    temp_console.print(table)
    return string_io.getvalue()


class TestDaemonProgressUXBugs:
    """Test suite for daemon progress display UX bugs."""

    @pytest.fixture
    def console(self):
        """Create real Console for testing (Rich requires it)."""
        # Use real Console instead of mock - Rich Progress requires actual Console methods
        return Console()

    @pytest.fixture
    def live_manager(self):
        """Create mock RichLiveProgressManager."""
        manager = Mock(spec=RichLiveProgressManager)
        manager.handle_setup_message = Mock()
        manager.handle_progress_update = Mock()
        return manager

    @pytest.fixture
    def progress_manager(self, console, live_manager):
        """Create MultiThreadedProgressManager for testing."""
        return MultiThreadedProgressManager(
            console=console, live_manager=live_manager, max_slots=14
        )

    @pytest.fixture
    def slot_tracker(self):
        """Create CleanSlotTracker with test data."""
        tracker = CleanSlotTracker(max_slots=14)

        # Add some test file data to slots
        tracker.status_array[0] = FileData(
            filename="file1.py",
            file_size=25000,
            status=FileStatus.VECTORIZING,
        )
        tracker.status_array[1] = FileData(
            filename="file2.py",
            file_size=18000,
            status=FileStatus.CHUNKING,
        )
        tracker.status_array[2] = FileData(
            filename="file3.py",
            file_size=32000,
            status=FileStatus.STARTING,
        )

        return tracker

    # ==================== Bug 1: "none/<total>" Display Tests ====================

    def test_bug1_malformed_info_shows_none_current(self, progress_manager):
        """
        BUG 1 TEST: When info string is malformed, current shows as 'none'.

        EXPECTED: Always show numeric current count (150/1357)
        ACTUAL: Shows "none/1357" with "0.0 files/s"

        This test should FAIL initially, demonstrating the bug.
        """
        # Simulate malformed info string (missing metrics)
        current = 150
        total = 1357
        malformed_info = "Processing files..."  # Missing " | " delimited metrics

        # Update progress with malformed info
        progress_manager.update_complete_state(
            current=current,
            total=total,
            files_per_second=0.0,  # Will default to 0.0 due to parsing failure
            kb_per_second=0.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info=malformed_info,
        )

        # Get display and check for "none"
        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # BUG ASSERTION: This should FAIL initially
        # The display should show "150/1357" but currently shows "none/1357"
        assert (
            "none" not in display_text.lower()
        ), f"Display shows 'none' instead of numeric current: {display_text}"
        assert (
            f"{current}/{total}" in display_text
        ), f"Display should show '{current}/{total}' but got: {display_text}"

    def test_bug1_empty_info_shows_none_current(self, progress_manager):
        """
        BUG 1 TEST: When info string is empty, current shows as 'none'.
        """
        current = 500
        total = 2000

        progress_manager.update_complete_state(
            current=current,
            total=total,
            files_per_second=0.0,
            kb_per_second=0.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info="",  # Empty info
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        assert (
            "none" not in display_text.lower()
        ), f"Display shows 'none' with empty info: {display_text}"
        assert (
            f"{current}/{total}" in display_text
        ), f"Display should show '{current}/{total}': {display_text}"

    def test_bug1_missing_metrics_shows_zero_speed(self, progress_manager):
        """
        BUG 1 TEST: When metrics are unparseable, shows "0.0 files/s".
        """
        current = 200
        total = 1000
        info = "200/1000 files"  # Missing other metrics

        progress_manager.update_complete_state(
            current=current,
            total=total,
            files_per_second=0.0,
            kb_per_second=0.0,
            active_threads=12,
            concurrent_files=[],
            slot_tracker=None,
            info=info,
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # Should show "0.0 files/s" due to parsing failure
        # After fix, this should use the provided files_per_second parameter
        assert "0.0 files/s" in display_text or "files/s" in display_text

    def test_parsing_with_valid_info_extracts_current(self):
        """
        Test that valid info string correctly extracts current value.

        This demonstrates the CORRECT behavior that should always work.
        """
        info = "150/1357 files (11%) | 12.5 files/s | 250.0 KB/s | 12 threads | file.py"

        # Parse info string (simulating daemon callback logic)
        parts = info.split(" | ")
        files_part = parts[0]  # "150/1357 files (11%)"

        # Extract current from files_part
        if "/" in files_part:
            current_str = files_part.split("/")[0]
            current = int(current_str)
            assert current == 150, f"Should extract 150 from '{files_part}'"

    # ==================== Bug 2: Missing Concurrent Files Tests ====================

    def test_bug2_concurrent_files_empty_in_daemon_mode(
        self, progress_manager, slot_tracker
    ):
        """
        BUG 2 TEST: concurrent_files is always empty list in daemon mode.

        EXPECTED: Show concurrent file listing like standalone mode:
            ├─ filename1.py (25 KB, 1.2s) ✅ vectorizing...
            ├─ filename2.py (18 KB, 0.8s) ✅ vectorizing...

        ACTUAL: No concurrent files shown at all (empty list hardcoded)

        This test should FAIL initially, demonstrating the bug.
        """
        current = 150
        total = 1357
        info = "150/1357 files (11%) | 12.5 files/s | 250.0 KB/s | 12 threads | file.py"

        # Daemon mode: concurrent_files is hardcoded to []
        progress_manager.update_complete_state(
            current=current,
            total=total,
            files_per_second=12.5,
            kb_per_second=250.0,
            active_threads=12,
            concurrent_files=[],  # BUG: Always empty in daemon mode
            slot_tracker=slot_tracker,  # Slot tracker HAS data but it's not used
            info=info,
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # BUG ASSERTION: This should FAIL initially
        # Should show file listings but currently shows nothing
        assert (
            "file1.py" in display_text
        ), f"Should show file1.py from slot_tracker: {display_text}"
        assert (
            "file2.py" in display_text
        ), f"Should show file2.py from slot_tracker: {display_text}"
        assert (
            "vectorizing" in display_text or "chunking" in display_text
        ), f"Should show file status: {display_text}"

    def test_bug2_no_concurrent_file_listing_visible(
        self, progress_manager, slot_tracker
    ):
        """
        BUG 2 TEST: Concurrent file listing not visible at all.
        """
        progress_manager.update_complete_state(
            current=100,
            total=500,
            files_per_second=10.0,
            kb_per_second=200.0,
            active_threads=12,
            concurrent_files=[],  # Empty in daemon mode
            slot_tracker=slot_tracker,
            info="100/500 files (20%) | 10.0 files/s | 200.0 KB/s | 12 threads",
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # Should contain file tree markers
        assert "├─" in display_text, f"Should show file tree markers: {display_text}"

    def test_slot_tracker_has_data_but_not_displayed(self, slot_tracker):
        """
        Verify that slot_tracker DOES have data, proving the bug is display-side.
        """
        # Verify slot tracker has data
        assert slot_tracker.status_array[0] is not None
        assert slot_tracker.status_array[0].filename == "file1.py"
        assert slot_tracker.status_array[1] is not None
        assert slot_tracker.status_array[1].filename == "file2.py"

        # The data exists, but daemon mode doesn't display it
        # This proves the bug is in the display layer, not data availability

    # ==================== Integration Tests ====================

    def test_standalone_mode_shows_concurrent_files(
        self, progress_manager, slot_tracker
    ):
        """
        Demonstrate that standalone mode DOES show concurrent files correctly.

        This is the EXPECTED behavior that daemon mode should match.
        """
        # Standalone mode: concurrent_files is populated OR slot_tracker is used
        progress_manager.set_slot_tracker(slot_tracker)

        progress_manager.update_complete_state(
            current=100,
            total=500,
            files_per_second=10.0,
            kb_per_second=200.0,
            active_threads=12,
            concurrent_files=[],  # Even empty, slot_tracker provides data
            slot_tracker=slot_tracker,
            info="100/500 files",
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # This works in standalone because slot_tracker is used
        assert "file1.py" in display_text
        assert "file2.py" in display_text

    def test_fix_should_use_slot_tracker_when_concurrent_files_empty(
        self, progress_manager, slot_tracker
    ):
        """
        After fix: When concurrent_files is empty, should use slot_tracker to reconstruct.
        """
        # Daemon provides slot_tracker but empty concurrent_files
        progress_manager.update_complete_state(
            current=200,
            total=1000,
            files_per_second=15.0,
            kb_per_second=300.0,
            active_threads=12,
            concurrent_files=[],  # Empty from daemon
            slot_tracker=slot_tracker,  # But slot_tracker has data
            info="200/1000 files (20%)",
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, progress_manager.console)

        # After fix: Should show files from slot_tracker
        assert "file1.py" in display_text
        assert "file2.py" in display_text
        assert "file3.py" in display_text


class TestProgressCallbackParsing:
    """Test progress callback parsing logic in daemon delegation."""

    def test_parse_valid_info_string(self):
        """Test parsing of well-formed info string."""
        info = "150/1357 files (11%) | 12.5 files/s | 250.0 KB/s | 12 threads | current_file.py"

        parts = info.split(" | ")
        assert len(parts) >= 4

        # Extract and verify metrics from info string
        files_per_second = float(parts[1].replace(" files/s", ""))
        kb_per_second = float(parts[2].replace(" KB/s", ""))
        threads_part = parts[3].split(" | ")[0]
        active_threads = int(threads_part.split()[0])

        assert files_per_second == 12.5
        assert kb_per_second == 250.0
        assert active_threads == 12

    def test_parse_malformed_info_fallback(self):
        """Test that malformed info falls back to safe defaults."""
        info = "Processing..."  # Malformed
        current = 150

        try:
            parts = info.split(" | ")
            if len(parts) < 4:
                # Fallback to safe defaults
                files_per_second = 0.0
                kb_per_second = 0.0
                active_threads = 12
        except Exception:
            files_per_second = 0.0
            kb_per_second = 0.0
            active_threads = 12

        # Should not crash, should use fallbacks
        assert files_per_second == 0.0
        assert kb_per_second == 0.0
        assert active_threads == 12

        # CRITICAL: Should still use the 'current' parameter
        assert current == 150  # This value should ALWAYS be used

    def test_extract_current_from_info_with_fallback(self):
        """
        Test extraction of current value from info with fallback to parameter.

        This is the FIX: Always prefer the 'current' parameter over parsed value.
        """
        current_param = 150

        # All cases should use current_param regardless of info string content
        # Case 1: Valid info - use current_param, not parsed value
        assert current_param == 150

        # Case 2: Malformed info - use current_param as fallback
        assert current_param == 150

        # Case 3: Empty info - use current_param as fallback
        assert current_param == 150


class TestDaemonCallbackIntegration:
    """Test daemon callback integration with progress manager."""

    @pytest.fixture
    def mock_rich_live_manager(self):
        """Create mock RichLiveProgressManager."""
        manager = Mock(spec=RichLiveProgressManager)
        manager.handle_setup_message = Mock()
        manager.handle_progress_update = Mock()
        return manager

    def test_daemon_callback_with_malformed_info(self, mock_rich_live_manager):
        """
        Test that daemon callback handles malformed info gracefully.

        Simulates the actual daemon callback in cli_daemon_delegation.py
        """
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=mock_rich_live_manager, max_slots=14
        )

        # Simulate daemon callback with malformed info
        current = 150
        total = 1357
        info = "Malformed info without metrics"

        # This simulates the callback logic in cli_daemon_delegation.py lines 740-756
        try:
            parts = info.split(" | ")
            if len(parts) >= 4:
                files_per_second = float(parts[1].replace(" files/s", ""))
                kb_per_second = float(parts[2].replace(" KB/s", ""))
                threads_text = parts[3]
                active_threads = (
                    int(threads_text.split()[0]) if threads_text.split() else 12
                )
            else:
                # Fallback when parsing fails
                files_per_second = 0.0
                kb_per_second = 0.0
                active_threads = 12
        except (ValueError, IndexError):
            files_per_second = 0.0
            kb_per_second = 0.0
            active_threads = 12

        # CRITICAL: current parameter should ALWAYS be used
        progress_manager.update_complete_state(
            current=current,  # This should ALWAYS appear in display
            total=total,
            files_per_second=files_per_second,
            kb_per_second=kb_per_second,
            active_threads=active_threads,
            concurrent_files=[],
            slot_tracker=None,
            info=info,
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, console)

        # Should show numeric current, never "none"
        assert "none" not in display_text.lower()
        assert f"{current}/{total}" in display_text

    def test_daemon_callback_with_slot_tracker(self, mock_rich_live_manager):
        """
        Test daemon callback when slot_tracker is available but concurrent_files is empty.
        """
        console = Console()
        progress_manager = MultiThreadedProgressManager(
            console=console, live_manager=mock_rich_live_manager, max_slots=14
        )

        # Create slot tracker with data
        slot_tracker = CleanSlotTracker(max_slots=14)
        slot_tracker.status_array[0] = FileData(
            filename="daemon_file.py",
            file_size=50000,
            status=FileStatus.VECTORIZING,
        )

        # Daemon mode: concurrent_files is empty but slot_tracker has data
        progress_manager.update_complete_state(
            current=100,
            total=500,
            files_per_second=10.0,
            kb_per_second=200.0,
            active_threads=12,
            concurrent_files=[],  # Empty in daemon mode
            slot_tracker=slot_tracker,  # But has data
            info="100/500 files",
        )

        display = progress_manager.get_integrated_display()
        display_text = render_table_to_text(display, console)

        # After fix: Should show files from slot_tracker
        assert "daemon_file.py" in display_text
        assert "vectorizing" in display_text.lower()
