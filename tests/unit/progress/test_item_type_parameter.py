"""Unit tests for item_type parameter in progress display modules.

This test verifies that progress display can show "commits" instead of "files"
when item_type parameter is passed.
"""

from unittest.mock import MagicMock
from rich.console import Console

from src.code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from src.code_indexer.progress.aggregate_progress import AggregateProgressDisplay


class TestItemTypeParameter:
    """Test item_type parameter for dynamic progress display labels."""

    def test_multi_threaded_progress_displays_commits_with_item_type(self):
        """Test MultiThreadedProgressManager shows 'commits' when item_type='commits'."""
        # Setup
        console = Console()
        progress_manager = MultiThreadedProgressManager(console=console, max_slots=4)

        # Call update_complete_state with item_type='commits'
        progress_manager.update_complete_state(
            current=50,
            total=100,
            files_per_second=10.5,
            kb_per_second=250.0,
            active_threads=4,
            concurrent_files=[],
            slot_tracker=None,
            info="Processing commits",
            item_type="commits"  # This is the new parameter
        )

        # Verify progress bar shows "commits" not "files"
        # The files_info field should be "50/100 commits" not "50/100 files"

        # Get the progress task to check fields
        assert progress_manager.main_task_id is not None, "Progress task should be created"

        # Access the task to verify files_info field
        task = progress_manager.progress.tasks[0]
        files_info = task.fields.get('files_info', '')

        # CRITICAL ASSERTION: Should show "commits" not "files"
        assert "commits" in files_info, f"files_info should contain 'commits': {files_info}"
        assert "50/100 commits" == files_info, f"Expected '50/100 commits', got: {files_info}"

        # Ensure "files" is NOT in the count
        assert "files" not in files_info, f"files_info should not contain 'files': {files_info}"

    def test_aggregate_progress_displays_commits_with_item_type(self):
        """Test AggregateProgressDisplay shows 'commits' when item_type='commits'."""
        # Setup
        console = Console()
        aggregate_display = AggregateProgressDisplay(console=console)

        # Call update_progress with item_type='commits'
        aggregate_display.update_progress(
            current=75,
            total=150,
            elapsed_seconds=30.0,
            estimated_remaining=10.0,
            files_per_second=2.5,
            kb_per_second=150.0,
            active_threads=8,
            item_type="commits"  # This is the new parameter
        )

        # Verify progress line shows "commits" not "files"
        progress_line = aggregate_display.get_progress_line()

        # CRITICAL ASSERTION: Should show "commits" not "files"
        assert "75/150 commits" in progress_line, \
            f"Progress line should contain '75/150 commits': {progress_line}"

        # Ensure "files" is NOT in the count
        assert "75/150 files" not in progress_line, \
            f"Progress line should not contain '75/150 files': {progress_line}"

        # Verify metrics line also shows "commits/s" not "files/s"
        metrics_line = aggregate_display.get_metrics_line()
        assert "commits/s" in metrics_line, \
            f"Metrics line should contain 'commits/s': {metrics_line}"
        assert "files/s" not in metrics_line, \
            f"Metrics line should not contain 'files/s': {metrics_line}"
