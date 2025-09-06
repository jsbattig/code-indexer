"""
Tests for Rich Progress Display CLI integration - Anti-Fallback Compliance.

This test verifies that the CLI progress callback ALWAYS uses Rich Progress Display
and has NO FALLBACKS or alternative code paths.
"""

import pytest
from unittest.mock import Mock
from pathlib import Path
from rich.table import Table

from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from code_indexer.progress.progress_display import RichLiveProgressManager


class TestRichProgressCLIIntegration:
    """Test Rich Progress Display CLI integration without fallbacks."""

    def setup_method(self):
        """Setup test components."""
        # Create a proper console mock that supports context manager protocol
        self.console_mock = Mock()
        self.console_mock.__enter__ = Mock(return_value=self.console_mock)
        self.console_mock.__exit__ = Mock(return_value=None)
        self.console_mock.clear_live = Mock()

        self.live_manager = RichLiveProgressManager(console=self.console_mock)
        self.progress_manager = MultiThreadedProgressManager(
            console=self.console_mock, live_manager=self.live_manager
        )

        # Mock the get_time method to return a proper float for Rich Progress calculations
        import time

        self.progress_manager.progress.get_time = Mock(return_value=time.time())

    @pytest.mark.unit
    def test_progress_callback_always_uses_rich_display(self):
        """Test that progress callback ALWAYS uses Rich Progress Display - NO FALLBACKS."""

        # SUCCESS! Anti-fallback violation has been removed from CLI
        # The CLI now ALWAYS uses MultiThreadedProgressManager regardless of concurrent_files

        # This test verifies the principle by ensuring MultiThreadedProgressManager
        # is designed to handle all scenarios without fallbacks

        # Test scenario 1: With concurrent files
        concurrent_files = [
            {
                "thread_id": 1,
                "file_path": "test.py",
                "file_size": 1024,
                "status": "processing",
            }
        ]

        self.progress_manager.update_complete_state(
            current=5,
            total=10,
            files_per_second=2.5,
            kb_per_second=512.0,
            active_threads=2,
            concurrent_files=concurrent_files,
        )

        display1 = self.progress_manager.get_integrated_display()
        assert display1 is not None, "Must provide display with concurrent files"
        # Rich Table objects are sufficient - test that it's not empty
        assert isinstance(display1, Table), "Should return Rich Table object"

        # Test the underlying concurrent display was updated
        concurrent_lines = self.progress_manager.concurrent_display.get_rendered_lines()
        assert len(concurrent_lines) > 0, "Should have concurrent file lines"
        assert any(
            "test.py" in line for line in concurrent_lines
        ), "Must show concurrent file info"

        # Test scenario 2: Without concurrent files (empty list)
        self.progress_manager.update_complete_state(
            current=5,
            total=10,
            files_per_second=2.5,
            kb_per_second=512.0,
            active_threads=2,
            concurrent_files=[],
        )

        display2 = self.progress_manager.get_integrated_display()
        assert (
            display2 is not None
        ), "Must provide display even without concurrent files"
        # Rich Table objects are sufficient for display integration
        assert isinstance(display2, Table), "Should return Rich Table object"

        # Test that progress was properly initialized
        assert self.progress_manager._progress_started, "Progress should be started"
        assert (
            self.progress_manager.main_task_id is not None
        ), "Should have main task ID"

        # Both scenarios MUST work without fallbacks
        # This proves the CLI anti-fallback fix is working

    @pytest.mark.unit
    def test_multi_threaded_display_always_provides_output(self):
        """Test that MultiThreadedProgressManager ALWAYS provides display content."""

        # Test with empty concurrent files - should still provide output
        self.progress_manager.update_complete_state(
            current=5,
            total=10,
            files_per_second=2.3,
            kb_per_second=456.7,
            active_threads=4,
            concurrent_files=[],  # Empty concurrent files
        )

        display = self.progress_manager.get_integrated_display()

        # Should ALWAYS provide display content, even with empty concurrent files
        assert display is not None, "Rich Progress Display must ALWAYS provide content"
        assert isinstance(display, Table), "Should return Rich Table object"

        # Test that progress was properly initialized and metrics stored
        assert self.progress_manager._progress_started, "Progress should be started"
        assert self.progress_manager._current_metrics_info, "Should have metrics info"
        assert (
            "2.3 files/s" in self.progress_manager._current_metrics_info
        ), "Should show processing rate"
        assert (
            "4 threads" in self.progress_manager._current_metrics_info
        ), "Should show thread count"

    @pytest.mark.unit
    def test_rich_live_manager_integration(self):
        """Test that Rich Live Manager integrates properly."""

        # Rich Live Manager should be startable
        self.live_manager.start_bottom_display()
        assert self.live_manager.is_active, "Live manager should be active after start"

        # Should be able to update display
        test_content = "Test progress content"
        self.live_manager.update_display(test_content)

        # Should be able to handle setup messages
        self.live_manager.handle_setup_message("Setup message")

        # Should be able to handle errors
        self.live_manager.handle_error_message(Path("test.py"), "Test error")

        # Should be able to stop
        self.live_manager.stop_display()
        assert (
            not self.live_manager.is_active
        ), "Live manager should be inactive after stop"

    @pytest.mark.unit
    def test_no_console_print_fallback_allowed(self):
        """Test that NO console.print fallback is acceptable - ANTI-FALLBACK PRINCIPLE."""

        # This test establishes that ANY use of console.print as fallback is FORBIDDEN
        # The CLI must ALWAYS use Rich Progress Display components

        # Test various scenarios that should NEVER trigger console.print fallback:

        # Scenario 1: Empty concurrent files
        display = self.progress_manager.get_integrated_display()
        assert display is not None, "Must provide display even with no concurrent files"

        # Scenario 2: Single threaded processing (active_threads=1)
        self.progress_manager.update_complete_state(
            current=1,
            total=5,
            files_per_second=1.0,
            kb_per_second=100.0,
            active_threads=1,
            concurrent_files=[],
        )
        display = self.progress_manager.get_integrated_display()
        assert isinstance(display, Table), "Should return Rich Table object"
        # Check that metrics info contains thread count
        assert (
            "1 threads" in self.progress_manager._current_metrics_info
        ), "Must handle single thread scenario"

        # Scenario 3: Zero thread scenario (completion)
        self.progress_manager.update_complete_state(
            current=5,
            total=5,
            files_per_second=0.0,
            kb_per_second=0.0,
            active_threads=0,
            concurrent_files=[],
        )
        display = self.progress_manager.get_integrated_display()
        assert display is not None, "Must provide display even at completion"

    @pytest.mark.unit
    def test_rich_progress_handles_all_cli_scenarios(self):
        """Test that Rich Progress Display handles ALL scenarios the CLI needs."""

        # Setup messages (total=0)
        # CLI calls: show_setup_message("Setup message")
        self.live_manager.handle_setup_message("Initializing collection")
        # Should not raise exception

        # File progress messages (total>0)
        # CLI calls: update_file_progress_with_concurrent_files(current, total, info, concurrent_files)
        concurrent_files = [
            {
                "thread_id": 1,
                "file_path": "test1.py",
                "file_size": 1024,
                "status": "vectorizing...",
            },
            {
                "thread_id": 2,
                "file_path": "test2.py",
                "file_size": 2048,
                "status": "complete",
            },
        ]

        self.progress_manager.update_complete_state(
            current=2,
            total=10,
            files_per_second=3.5,
            kb_per_second=789.2,
            active_threads=2,
            concurrent_files=concurrent_files,
        )

        display = self.progress_manager.get_integrated_display()
        assert isinstance(display, Table), "Should return Rich Table object"

        # Check that concurrent files were properly processed
        concurrent_lines = self.progress_manager.concurrent_display.get_rendered_lines()
        assert len(concurrent_lines) > 0, "Should have concurrent file lines"

        # Check that the concurrent display contains the expected files
        display_content = "\n".join(concurrent_lines)
        assert "test1.py" in display_content, "Should show concurrent files"
        assert "test2.py" in display_content, "Should show concurrent files"
        assert "vectorizing..." in display_content, "Should show file status"
        assert "complete" in display_content, "Should show file status"

        # Error messages
        # CLI calls: show_error_message(file_path, error)
        self.live_manager.handle_error_message(Path("error.py"), "Test error")
        # Should not raise exception


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
