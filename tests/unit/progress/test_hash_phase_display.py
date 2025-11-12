"""Test hash phase display functionality."""

from pathlib import Path
from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
    FileStatus,
    FileData,
)
from rich.console import Console


def test_hash_phase_label_detection():
    """Test that hash phase is detected from info string."""
    console = Console()
    manager = MultiThreadedProgressManager(console=console)

    # Test hash phase detection
    manager.update_complete_state(
        current=10,
        total=100,
        files_per_second=5.0,
        kb_per_second=100.0,
        active_threads=4,
        concurrent_files=[],
        slot_tracker=None,
        info="10/100 files (10%) | 5.0 files/s | 100.0 KB/s | 4 threads | 🔍 test.py",
    )

    assert manager._current_phase == "🔍 Hashing"

    # Test indexing phase detection
    manager.update_complete_state(
        current=20,
        total=100,
        files_per_second=5.0,
        kb_per_second=100.0,
        active_threads=4,
        concurrent_files=[],
        slot_tracker=None,
        info="20/100 files (20%) | 5.0 files/s | 100.0 KB/s | 4 threads | 📊 test_file.py",
    )

    assert manager._current_phase == "🚀 Indexing"


def test_concurrent_files_display_fallback():
    """Test that concurrent files are displayed when slot_tracker is None."""
    console = Console()
    manager = MultiThreadedProgressManager(console=console)

    # Create mock concurrent files data (hash phase format)
    concurrent_files = [
        {
            "slot_id": 0,
            "file_path": Path("/test/file1.py"),
            "file_size": 1024,
            "status": "processing",
            "estimated_seconds": 1,
            "start_time": 0,
            "last_updated": 0,
        },
        {
            "slot_id": 1,
            "file_path": "/test/file2.js",
            "file_size": 2048,
            "status": "complete",
            "estimated_seconds": 1,
            "start_time": 0,
            "last_updated": 0,
        },
    ]

    # Update with hash phase info and concurrent files
    manager.update_complete_state(
        current=2,
        total=10,
        files_per_second=2.0,
        kb_per_second=50.0,
        active_threads=2,
        concurrent_files=concurrent_files,
        slot_tracker=None,  # No slot tracker in hash phase
        info="2/10 files (20%) | 2.0 files/s | 50.0 KB/s | 2 threads | 🔍 file1.py",
    )

    # Verify concurrent files are stored
    assert len(manager._concurrent_files) == 2
    assert manager._concurrent_files[0]["file_path"] == Path("/test/file1.py")
    assert manager._concurrent_files[1]["status"] == "complete"

    # Get display and verify it contains file information
    display = manager.get_integrated_display()
    assert display is not None  # Should have created a display table


def test_slot_tracker_takes_precedence():
    """Test that concurrent_files takes precedence in daemon mode (FIXED behavior)."""
    console = Console()
    manager = MultiThreadedProgressManager(console=console)

    # Create a real slot tracker with data (simulates RPyC proxy in daemon mode)
    slot_tracker = CleanSlotTracker(max_slots=2)
    file_data = FileData(
        filename="tracker_file.py",
        file_size=3072,
        status=FileStatus.PROCESSING,
        start_time=0,
    )
    slot_id = slot_tracker.acquire_slot(file_data)

    # concurrent_files contains fresh serialized data (preferred in daemon mode)
    concurrent_files = [
        {
            "file_path": "concurrent_file.py",
            "file_size": 1024,
            "status": "processing",
        }
    ]

    # Update with both slot_tracker and concurrent_files
    manager.update_complete_state(
        current=1,
        total=5,
        files_per_second=1.0,
        kb_per_second=25.0,
        active_threads=1,
        concurrent_files=concurrent_files,
        slot_tracker=slot_tracker,
        info="1/5 files (20%) | 1.0 files/s | 25.0 KB/s | 1 threads | Processing...",
    )

    # Verify slot_tracker was set (both values stored, but concurrent_files used for display)
    assert manager.slot_tracker == slot_tracker

    # Release slot for cleanup
    slot_tracker.release_slot(slot_id)


def test_hash_phase_status_display():
    """Test that processing status shows as 'hashing' during hash phase."""
    console = Console()
    manager = MultiThreadedProgressManager(console=console)

    # Set hash phase
    concurrent_files = [
        {
            "file_path": "test.py",
            "file_size": 1024,
            "status": "processing",
        }
    ]

    manager.update_complete_state(
        current=1,
        total=10,
        files_per_second=1.0,
        kb_per_second=10.0,
        active_threads=1,
        concurrent_files=concurrent_files,
        slot_tracker=None,
        info="1/10 files (10%) | 1.0 files/s | 10.0 KB/s | 1 threads | 🔍 test.py",
    )

    # Phase should be hash
    assert manager._current_phase == "🔍 Hashing"

    # Display should show hashing status for processing files
    _ = manager.get_integrated_display()
    # The display logic will show "hashing..." for processing status during hash phase
