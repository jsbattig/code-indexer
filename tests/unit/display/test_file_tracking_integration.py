"""
Integration tests for Feature 3: Individual File Tracking
Testing integration with existing Rich Progress Display system
"""

from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.utils.status_display import (
    StatusDisplayManager,
    StatusDisplayMode,
    create_free_scroll_stream_status,
)
from rich.console import Console


class TestFileTrackingIntegration:
    """Test Feature 3 integration with Rich Progress Display system"""

    def test_status_display_manager_with_file_tracking_enabled(self):
        """Test StatusDisplayManager with file tracking enabled."""
        console = Mock(spec=Console)

        # Create status display manager with file tracking enabled
        manager = StatusDisplayManager(
            mode=StatusDisplayMode.FREE_SCROLL_STREAM,
            console=console,
            enable_file_tracking=True,
        )

        # Start the display
        manager.start("Test Indexing Operation")

        # Test file tracking methods are available
        assert hasattr(manager, "start_file_processing")
        assert hasattr(manager, "update_file_status")
        assert hasattr(manager, "complete_file_processing")

        # Test file tracking workflow
        file_path = Path("test_integration.py")
        file_size = 2048

        with patch("time.time", return_value=1000.0):
            manager.start_file_processing(file_path, file_size)

        with patch("time.time", return_value=1003.0):
            manager.update_file_status(file_path, "vectorizing")

        with patch("time.time", return_value=1007.0):
            manager.complete_file_processing(file_path)

        # Verify the display has file tracker enabled
        assert manager.display.enable_file_tracking
        assert manager.display.file_tracker is not None

        # Verify file lines are created properly
        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1007.0
        )
        assert len(file_lines) == 1
        assert "├─ test_integration.py (2.0 KB, 7s) complete" == file_lines[0]

        manager.stop()

    def test_convenience_function_with_file_tracking(self):
        """Test create_free_scroll_stream_status convenience function with file tracking."""
        console = Mock(spec=Console)

        # Test file tracking disabled (default)
        manager_disabled = create_free_scroll_stream_status(console)
        manager_disabled.start("Test Operation")

        assert not manager_disabled.enable_file_tracking
        assert (
            not hasattr(manager_disabled.display, "file_tracker")
            or manager_disabled.display.file_tracker is None
        )

        manager_disabled.stop()

        # Test file tracking enabled
        manager_enabled = create_free_scroll_stream_status(
            console, enable_file_tracking=True
        )
        manager_enabled.start("Test Operation")

        assert manager_enabled.enable_file_tracking
        assert manager_enabled.display.enable_file_tracking
        assert manager_enabled.display.file_tracker is not None

        manager_enabled.stop()

    def test_multi_file_processing_workflow(self):
        """Test complete multi-file processing workflow with visual formatting."""
        console = Mock(spec=Console)

        manager = create_free_scroll_stream_status(console, enable_file_tracking=True)
        manager.start("Multi-file Indexing")

        # Start processing multiple files
        files_info = [
            (Path("utils.py"), 2150),  # 2.1 KB
            (Path("config.py"), 1843),  # 1.8 KB
            (Path("main.py"), 3481),  # 3.4 KB
        ]

        # Start all files at t=1000
        with patch("time.time", return_value=1000.0):
            for file_path, file_size in files_info:
                manager.start_file_processing(file_path, file_size)

        # Update statuses at different times (simulating multi-threaded processing)
        with patch("time.time", return_value=1005.0):
            manager.update_file_status(Path("utils.py"), "vectorizing")
            manager.update_file_status(Path("config.py"), "vectorizing")
            manager.update_file_status(Path("main.py"), "vectorizing")

        # Get current display lines
        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1005.0
        )
        assert len(file_lines) == 3

        expected_lines = [
            "├─ utils.py (2.1 KB, 5s) vectorizing...",
            "├─ config.py (1.8 KB, 5s) vectorizing...",
            "├─ main.py (3.4 KB, 5s) vectorizing...",
        ]

        for expected_line in expected_lines:
            assert expected_line in file_lines

        # Complete one file and verify completion behavior
        with patch("time.time", return_value=1008.0):
            manager.complete_file_processing(Path("config.py"))

        # Verify the completed file shows "complete" status
        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1008.0
        )
        assert len(file_lines) == 3  # All files still visible

        config_line = next((line for line in file_lines if "config.py" in line), None)
        assert config_line is not None and "complete" in config_line

        # Verify other files still show vectorizing
        utils_line = next((line for line in file_lines if "utils.py" in line), None)
        main_line = next((line for line in file_lines if "main.py" in line), None)
        assert utils_line is not None and "vectorizing..." in utils_line
        assert main_line is not None and "vectorizing..." in main_line

        manager.stop()

    def test_file_tracking_disabled_graceful_handling(self):
        """Test that file tracking methods work gracefully when disabled."""
        console = Mock(spec=Console)

        # Create manager with file tracking disabled
        manager = create_free_scroll_stream_status(console, enable_file_tracking=False)
        manager.start("Test Operation")

        # These methods should not crash when file tracking is disabled
        file_path = Path("test.py")
        manager.start_file_processing(file_path, 1024)
        manager.update_file_status(file_path, "vectorizing")
        manager.complete_file_processing(file_path)

        # No errors should be raised
        manager.stop()

    def test_visual_panel_title_updates_with_file_count(self):
        """Test that the panel title updates to show active file count."""
        console = Mock(spec=Console)

        manager = create_free_scroll_stream_status(console, enable_file_tracking=True)
        manager.start("Visual Test")

        # Start with no files - should show basic title
        display = manager.display
        file_lines = display.file_tracker.get_active_file_lines()
        assert len(file_lines) == 0

        # Add one file
        with patch("time.time", return_value=1000.0):
            manager.start_file_processing(Path("single.py"), 1024)

        # Check that panel would show file count
        file_lines = display.file_tracker.get_active_file_lines(current_time=1000.0)
        assert len(file_lines) == 1

        # Add more files
        with patch("time.time", return_value=1001.0):
            manager.start_file_processing(Path("file2.py"), 2048)
            manager.start_file_processing(Path("file3.py"), 3072)

        file_lines = display.file_tracker.get_active_file_lines(current_time=1001.0)
        assert len(file_lines) == 3

        # The panel title logic should reflect active file count in _show_bottom_tool_panel
        # Verify this indirectly by checking file tracker has the expected files
        active_files = display.file_tracker.active_files
        assert len(active_files) == 3
        assert "single.py" in str(active_files.keys())
        assert "file2.py" in str(active_files.keys())
        assert "file3.py" in str(active_files.keys())

        manager.stop()


class TestFileTrackingErrorHandling:
    """Test error handling and edge cases in file tracking integration"""

    def test_file_tracking_with_zero_byte_files(self):
        """Test file tracking handles zero-byte files correctly."""
        console = Mock(spec=Console)
        manager = create_free_scroll_stream_status(console, enable_file_tracking=True)
        manager.start("Zero Byte File Test")

        empty_file = Path("empty.py")

        with patch("time.time", return_value=1000.0):
            manager.start_file_processing(empty_file, 0)

        with patch("time.time", return_value=1002.0):
            manager.update_file_status(empty_file, "vectorizing")

        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1002.0
        )
        assert len(file_lines) == 1
        assert "├─ empty.py (0.0 KB, 2s) vectorizing..." == file_lines[0]

        manager.stop()

    def test_file_tracking_with_very_long_filenames(self):
        """Test file tracking with very long filenames."""
        console = Mock(spec=Console)
        manager = create_free_scroll_stream_status(console, enable_file_tracking=True)
        manager.start("Long Filename Test")

        long_filename = (
            "very_long_filename_that_might_cause_display_issues_in_terminal_output.py"
        )
        long_file_path = Path(long_filename)

        with patch("time.time", return_value=1000.0):
            manager.start_file_processing(long_file_path, 1024)

        with patch("time.time", return_value=1003.0):
            manager.update_file_status(long_file_path, "vectorizing")

        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1003.0
        )
        assert len(file_lines) == 1

        # Should contain the full filename and proper formatting
        line = file_lines[0]
        assert line.startswith("├─ ")
        assert long_filename in line
        assert "(1.0 KB, 3s) vectorizing..." in line

        manager.stop()

    def test_file_tracking_with_duplicate_starts(self):
        """Test file tracking handles duplicate start calls gracefully."""
        console = Mock(spec=Console)
        manager = create_free_scroll_stream_status(console, enable_file_tracking=True)
        manager.start("Duplicate Start Test")

        file_path = Path("duplicate_test.py")

        with patch("time.time", return_value=1000.0):
            manager.start_file_processing(file_path, 1024)
            # Start same file again with different size
            manager.start_file_processing(file_path, 2048)

        with patch("time.time", return_value=1003.0):
            manager.update_file_status(file_path, "vectorizing")

        file_lines = manager.display.file_tracker.get_active_file_lines(
            current_time=1003.0
        )
        assert len(file_lines) == 1

        # Should use the most recent start (2048 bytes = 2.0 KB)
        line = file_lines[0]
        assert "2.0 KB" in line

        manager.stop()
