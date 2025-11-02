"""Test that proves the RPyC proxy precedence bug causing frozen slots.

THE BUG:
In daemon mode, MultiThreadedProgressManager.get_integrated_display() calls:
  1. slot_tracker.get_concurrent_files_data() - RPyC proxy call (SLOW, may be stale)
  2. self._concurrent_files - Fresh serialized data already passed in kwargs

This is BACKWARD! We should prefer fresh serialized data over RPyC proxy calls.

CORRECT BEHAVIOR:
  1. PREFER self._concurrent_files (fresh serialized data from daemon)
  2. Fallback to slot_tracker.get_concurrent_files_data() only if concurrent_files unavailable

This test uses a mock to simulate RPyC proxy behavior and verify correct precedence.
"""

from src.code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileStatus,
    FileData,
)
from src.code_indexer.progress.multi_threaded_display import (
    MultiThreadedProgressManager,
)
from rich.console import Console
from io import StringIO
from unittest.mock import Mock


def test_prefers_serialized_concurrent_files_over_rpyc_proxy():
    """Test that display PREFERS serialized concurrent_files over RPyC proxy calls.

    This test simulates daemon mode where:
    - slot_tracker is an RPyC proxy object (slow, may have stale data)
    - concurrent_files is fresh serialized data passed in kwargs

    CORRECT BEHAVIOR: Should use concurrent_files, NOT call proxy.get_concurrent_files_data()
    """
    # Setup: Create progress manager
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Create mock RPyC proxy slot_tracker
    # This simulates the RPyC proxy object passed from daemon
    mock_slot_tracker = Mock(spec=CleanSlotTracker)

    # Mock returns STALE data (simulating RPyC latency/caching)
    stale_data = [
        {"slot_id": 0, "file_path": "stale_file1.py", "file_size": 1024, "status": "processing"},
        {"slot_id": 1, "file_path": "stale_file2.py", "file_size": 1024, "status": "processing"},
    ]
    mock_slot_tracker.get_concurrent_files_data = Mock(return_value=stale_data)

    # Fresh serialized data passed in kwargs (this is what daemon sends)
    fresh_concurrent_files = [
        {"slot_id": 0, "file_path": "fresh_file1.py", "file_size": 2048, "status": "processing"},
        {"slot_id": 1, "file_path": "fresh_file2.py", "file_size": 2048, "status": "processing"},
    ]

    # Update progress manager with BOTH slot_tracker (RPyC proxy) AND concurrent_files (fresh data)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=fresh_concurrent_files,  # Fresh serialized data
        slot_tracker=mock_slot_tracker,  # RPyC proxy (stale)
    )

    # Get display - should use FRESH concurrent_files, NOT call RPyC proxy
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole
    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # ASSERTION 1: Display should show FRESH files (from serialized concurrent_files)
    assert "fresh_file1.py" in display_text or "fresh_file2.py" in display_text, \
        f"Display should show FRESH serialized files, not stale RPyC data. Got: {display_text}"

    # ASSERTION 2: Display should NOT show stale files (from RPyC proxy)
    assert "stale_file1.py" not in display_text and "stale_file2.py" not in display_text, \
        f"Display should NOT show stale RPyC proxy files. Got: {display_text}"

    # ASSERTION 3: RPyC proxy method should NOT be called (we prefer serialized data)
    # This is the key fix - we should use concurrent_files, not call the proxy
    mock_slot_tracker.get_concurrent_files_data.assert_not_called()


def test_falls_back_to_proxy_when_no_concurrent_files():
    """Test that display falls back to RPyC proxy only when concurrent_files unavailable.

    This handles the case where daemon doesn't send concurrent_files for some reason.
    """
    # Setup
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Create mock RPyC proxy slot_tracker
    mock_slot_tracker = Mock(spec=CleanSlotTracker)
    proxy_data = [
        {"slot_id": 0, "file_path": "proxy_file1.py", "file_size": 1024, "status": "processing"},
    ]
    mock_slot_tracker.get_concurrent_files_data = Mock(return_value=proxy_data)

    # Update with slot_tracker but NO concurrent_files (empty list)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=[],  # No concurrent files provided
        slot_tracker=mock_slot_tracker,
    )

    # Get display - should fallback to RPyC proxy
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole
    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # ASSERTION 1: Display should show proxy data (fallback)
    assert "proxy_file1.py" in display_text, \
        f"Display should fallback to RPyC proxy when no concurrent_files. Got: {display_text}"

    # ASSERTION 2: RPyC proxy method SHOULD be called (fallback scenario)
    mock_slot_tracker.get_concurrent_files_data.assert_called_once()


def test_real_slot_tracker_still_works_for_direct_mode():
    """Test that real CleanSlotTracker still works in direct (non-daemon) mode.

    This ensures we don't break the direct connection use case.
    """
    # Setup: Real slot tracker (not RPyC proxy)
    slot_tracker = CleanSlotTracker(max_slots=8)
    console = Console(file=StringIO(), force_terminal=True, width=120)
    progress_manager = MultiThreadedProgressManager(
        console=console,
        max_slots=8,
    )

    # Acquire slots with real slot tracker
    for i in range(4):
        file_data = FileData(
            filename=f"direct_file{i}.py",
            file_size=1024,
            status=FileStatus.PROCESSING,
        )
        slot_tracker.acquire_slot(file_data)

    # Update with real slot_tracker and empty concurrent_files (direct mode)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=4,
        concurrent_files=[],  # Empty in direct mode
        slot_tracker=slot_tracker,  # Real CleanSlotTracker
    )

    # Get display - should work with real slot tracker
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole
    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # Verify real slot tracker data appears
    assert "direct_file0.py" in display_text or "direct_file1.py" in display_text, \
        f"Display should work with real CleanSlotTracker in direct mode. Got: {display_text}"
