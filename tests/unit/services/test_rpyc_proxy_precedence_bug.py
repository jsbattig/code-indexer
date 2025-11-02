"""Test that verifies NO fallback to slot_tracker.get_concurrent_files_data() in daemon mode.

ARCHITECTURE:
- Daemon mode: ALWAYS uses concurrent_files_json (JSON-serialized data), NO RPyC proxy calls
- Standalone mode: Uses set_slot_tracker() to populate self._concurrent_files
- NO FALLBACK: get_integrated_display() never calls slot_tracker.get_concurrent_files_data()

This eliminates 50-100ms RPyC proxy overhead per callback and prevents stale data issues.
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


def test_no_fallback_when_concurrent_files_empty():
    """Test that display does NOT fallback to RPyC proxy when concurrent_files is empty.

    CRITICAL: Empty concurrent_files means completion state, not missing data.
    The display should show NO files, NOT fallback to slot_tracker.get_concurrent_files_data().
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

    # Update with slot_tracker AND empty concurrent_files (completion state)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=8,
        concurrent_files=[],  # Empty = completion state, NOT missing data
        slot_tracker=mock_slot_tracker,
    )

    # Get display - should NOT fallback to RPyC proxy
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole
    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # CRITICAL: Display should NOT show proxy data (no fallback)
    assert "proxy_file1.py" not in display_text, \
        f"Display must NOT fallback to RPyC proxy. Got: {display_text}"

    # CRITICAL: RPyC proxy method should NOT be called (no fallback)
    mock_slot_tracker.get_concurrent_files_data.assert_not_called()


def test_real_slot_tracker_still_works_for_direct_mode():
    """Test that real CleanSlotTracker still works in standalone (non-daemon) mode.

    In standalone mode, set_slot_tracker() populates self._concurrent_files.
    NO direct calls to slot_tracker.get_concurrent_files_data() from get_integrated_display().
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

    # Set slot tracker (standalone mode) - provides concurrent files via slot_tracker
    progress_manager.set_slot_tracker(slot_tracker)

    # In standalone mode, concurrent_files should come from slot_tracker
    concurrent_files_data = slot_tracker.get_concurrent_files_data()

    # Update progress (standalone mode passes concurrent_files from slot_tracker)
    progress_manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=128.0,
        active_threads=4,
        concurrent_files=concurrent_files_data,  # Get data from slot_tracker
        slot_tracker=slot_tracker,  # Real CleanSlotTracker
    )

    # Get display - should work via set_slot_tracker (not get_concurrent_files_data)
    display = progress_manager.get_integrated_display()

    # Render to string
    from rich.console import Console as RenderConsole
    render_buffer = StringIO()
    render_console = RenderConsole(file=render_buffer, force_terminal=True, width=120)
    render_console.print(display)
    display_text = render_buffer.getvalue()

    # Verify slot tracker data appears (via set_slot_tracker mechanism)
    assert "direct_file0.py" in display_text or "direct_file1.py" in display_text, \
        f"Display should work with CleanSlotTracker in standalone mode. Got: {display_text}"
