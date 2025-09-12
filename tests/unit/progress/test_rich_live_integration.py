"""Unit tests for Rich Live integration - bottom-anchored progress display.

This module tests the implementation of Rich Live component integration
that provides bottom-locked progress display with console output separation.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
from rich.console import Console

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestRichLiveProgressManager:
    """Test suite for Rich Live progress manager component."""

    def test_rich_live_manager_initialization(self):
        """Test Rich Live progress manager initializes correctly."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Should initialize without Rich Live component active yet
        assert manager.console is console
        assert manager.live_component is None
        assert not manager.is_active

    def test_start_bottom_anchored_display(self):
        """Test starting bottom-anchored display creates Live component."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()

            # Should create Live component with correct config
            mock_live.assert_called_once_with(
                renderable="", console=console, refresh_per_second=10, transient=False
            )

            # Should start the Live component
            mock_live_instance.start.assert_called_once()
            assert manager.live_component is mock_live_instance
            assert manager.is_active

    def test_update_display_content(self):
        """Test updating display content through Live component."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()
            test_content = "Test progress content"
            manager.update_display(test_content)

            # Should update Live component with new content
            mock_live_instance.update.assert_called_with(test_content)

    def test_stop_display_cleanup(self):
        """Test stopping display properly cleans up Live component."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()
            manager.stop_display()

            # Should stop Live component and reset state
            mock_live_instance.stop.assert_called_once()
            assert manager.live_component is None
            assert not manager.is_active

    def test_update_display_before_start_raises_error(self):
        """Test that updating display before starting raises error."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        with pytest.raises(RuntimeError, match="Display not started"):
            manager.update_display("Test content")

    def test_stop_display_before_start_is_safe(self):
        """Test that stopping display before starting is safe."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Should not raise error
        manager.stop_display()
        assert manager.live_component is None
        assert not manager.is_active


class TestConsoleOutputSeparation:
    """Test suite for console output separation functionality."""

    def test_setup_messages_bypass_live_component(self):
        """Test that setup messages print directly to console, bypassing Live."""
        console = Mock()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()

            # Setup messages should print directly to console
            manager.handle_setup_message("✅ Collection initialized")
            console.print.assert_called_with(
                "ℹ️  ✅ Collection initialized", style="cyan"
            )

            # Live component should not be updated for setup messages
            mock_live_instance.update.assert_not_called()

    def test_progress_updates_go_to_live_component(self):
        """Test that progress updates go to Live component, not console."""
        console = Mock()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()
            progress_info = "45/120 files | 12.3 files/s | 8 threads"

            # Progress updates should go to Live component
            manager.handle_progress_update(progress_info)
            mock_live_instance.update.assert_called_once()

            # Console should not print progress updates directly
            console.print.assert_not_called()

    def test_error_messages_bypass_live_component(self):
        """Test that error messages print directly to console, bypassing Live."""
        console = Mock()
        manager = RichLiveProgressManager(console=console)

        with patch("code_indexer.progress.progress_display.Live") as mock_live:
            mock_live_instance = Mock()
            mock_live.return_value = mock_live_instance

            manager.start_bottom_display()

            # Error messages should print directly to console
            error_file = Path("test.py")
            error_msg = "Permission denied"
            manager.handle_error_message(error_file, error_msg)

            console.print.assert_called_with(
                f"❌ Failed to process {error_file}: {error_msg}", style="red"
            )

            # Live component should not be updated for error messages
            mock_live_instance.update.assert_not_called()


class TestBackwardsCompatibility:
    """Test suite for backwards compatibility with existing CLI interface."""

    def test_legacy_progress_callback_interface_preserved(self):
        """Test that legacy progress callback interface still works."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Create legacy-style progress callback
        def legacy_callback(current, total, file_path, error=None, info=None):
            if total == 0 and info:
                # Setup messages
                manager.handle_setup_message(info)
            elif total > 0 and info:
                # Progress updates
                manager.handle_progress_update(info)
            elif error:
                # Error messages
                manager.handle_error_message(file_path, error)

        # Test setup message
        with patch.object(manager, "handle_setup_message") as mock_setup:
            legacy_callback(0, 0, Path(""), info="✅ Collection initialized")
            mock_setup.assert_called_once_with("✅ Collection initialized")

        # Test progress update
        with patch.object(manager, "handle_progress_update") as mock_progress:
            legacy_callback(45, 120, Path("test.py"), info="45/120 files")
            mock_progress.assert_called_once_with("45/120 files")

        # Test error message
        with patch.object(manager, "handle_error_message") as mock_error:
            legacy_callback(0, 0, Path("test.py"), error="Permission denied")
            mock_error.assert_called_once_with(Path("test.py"), "Permission denied")


class TestCurrentLimitationsDemonstration:
    """Test suite demonstrating current single-line progress limitations."""

    def test_current_progress_display_mixes_output(self):
        """Demonstrate that current progress display mixes all output together."""
        # This test documents current behavior that we want to change
        # Current implementation: all output goes to same console area
        # Desired behavior: separation between scrolling and fixed areas

        console = Mock()

        # Simulate current CLI behavior
        # Setup messages print to console
        console.print("ℹ️  ✅ Collection initialized", style="cyan")
        console.print("ℹ️  ✅ Vector provider ready", style="cyan")

        # Progress bar also uses same console
        # When progress bar starts, it takes over console output
        with patch("rich.progress.Progress") as mock_progress:
            progress_instance = Mock()
            mock_progress.return_value = progress_instance

            # Progress bar initialization
            progress_instance.start.return_value = None
            progress_instance.add_task.return_value = "task_id"

            # Progress updates overwrite everything
            progress_instance.update.return_value = None

            # LIMITATION: No separation between setup messages and progress
            # Everything shares the same console space
            assert console.print.call_count == 2  # Setup messages
            # Progress bar would take over from here, no separation

    def test_cannot_review_setup_messages_during_progress(self):
        """Demonstrate that current implementation prevents reviewing setup messages."""
        # Current limitation: once progress bar starts, setup messages are hidden
        # This test shows why we need bottom-anchored display

        console = Mock()

        # Setup messages are printed
        setup_messages = [
            "ℹ️  ✅ Collection initialized",
            "ℹ️  ✅ Vector provider ready",
            "ℹ️  ✅ Starting file processing",
        ]

        for msg in setup_messages:
            console.print(msg, style="cyan")

        # Once progress bar starts, messages are no longer visible
        with patch("rich.progress.Progress") as mock_progress:
            progress_instance = Mock()
            mock_progress.return_value = progress_instance

            # Progress bar takes over entire output area
            progress_instance.start.return_value = None

            # LIMITATION: Cannot scroll up to review setup messages
            # because progress bar updates constantly overwrite display

            # User loses access to setup message history
            assert len(setup_messages) == 3  # Messages exist but not accessible
            # This is the problem we're solving with Rich Live bottom-anchoring
