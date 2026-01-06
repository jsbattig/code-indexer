"""End-to-end tests for Rich Live bottom-anchored progress display.

This module tests the complete integration of Rich Live progress display
with actual CLI operations to ensure bottom-anchored display works correctly.
"""

from pathlib import Path
from unittest.mock import patch
from rich.console import Console

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestBottomAnchoredDisplayE2E:
    """E2E tests for bottom-anchored progress display functionality."""

    def test_setup_messages_scroll_above_progress_display(self):
        """Test that setup messages appear above bottom-anchored progress display."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Simulate setup messages before progress starts
        setup_messages = [
            "✅ Collection initialized",
            "✅ Vector provider ready",
            "✅ Starting file processing",
        ]

        # Setup messages should be handled by console directly
        with patch.object(console, "print") as mock_print:
            for message in setup_messages:
                manager.handle_setup_message(message)

            # Verify all setup messages were printed to console
            assert mock_print.call_count == 3
            mock_print.assert_any_call("ℹ️  ✅ Collection initialized", style="cyan")
            mock_print.assert_any_call("ℹ️  ✅ Vector provider ready", style="cyan")
            mock_print.assert_any_call("ℹ️  ✅ Starting file processing", style="cyan")

    def test_progress_display_anchored_at_bottom(self):
        """Test that progress display is anchored at bottom while setup messages scroll."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # First display setup messages
        setup_messages = ["✅ Collection initialized", "✅ Vector provider ready"]

        for message in setup_messages:
            manager.handle_setup_message(message)

        # Start bottom display
        manager.start_bottom_display()
        assert manager.is_active

        # Simulate progress updates that should appear in bottom display
        progress_updates = [
            "Processing 10/100 files (10%)",
            "Processing 25/100 files (25%)",
            "Processing 50/100 files (50%)",
        ]

        with patch.object(manager.live_component, "update") as mock_update:
            for progress in progress_updates:
                manager.handle_progress_update(progress)

            # Verify all progress updates went to Live component
            assert mock_update.call_count == 3
            mock_update.assert_any_call("Processing 10/100 files (10%)")
            mock_update.assert_any_call("Processing 25/100 files (25%)")
            mock_update.assert_any_call("Processing 50/100 files (50%)")

        manager.stop_display()

    def test_error_messages_scroll_above_progress_display(self):
        """Test that error messages scroll above progress display, not interfere with it."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Start progress display
        manager.start_bottom_display()

        # Simulate error messages during progress
        with patch.object(console, "print") as mock_print:
            manager.handle_error_message(Path("file1.py"), "Permission denied")
            manager.handle_error_message(Path("file2.py"), "File not found")

            # Verify error messages printed to console (scrolling area)
            assert mock_print.call_count == 2
            mock_print.assert_any_call(
                "❌ Failed to process file1.py: Permission denied", style="red"
            )
            mock_print.assert_any_call(
                "❌ Failed to process file2.py: File not found", style="red"
            )

        manager.stop_display()

    def test_complete_indexing_workflow_with_bottom_anchored_display(self):
        """Test complete indexing workflow with bottom-anchored display."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Simulate complete indexing workflow
        workflow_steps = [
            # Phase 1: Setup messages (should scroll above)
            ("setup", "✅ Collection initialized"),
            ("setup", "✅ Vector provider ready"),
            ("setup", "✅ Starting file processing"),
            # Phase 2: Progress updates (should appear in bottom display)
            ("progress", "Processing 10/100 files (10%) | 2.5 files/s | 4 threads"),
            ("progress", "Processing 25/100 files (25%) | 3.1 files/s | 4 threads"),
            ("progress", "Processing 50/100 files (50%) | 3.8 files/s | 4 threads"),
            # Phase 3: Error during processing (should scroll above)
            ("error", Path("corrupted.py"), "Invalid encoding"),
            # Phase 4: Continue progress (should appear in bottom display)
            ("progress", "Processing 75/100 files (75%) | 4.2 files/s | 4 threads"),
            ("progress", "Processing 100/100 files (100%) | 4.5 files/s | 4 threads"),
        ]

        with patch.object(console, "print") as mock_console_print:
            # Don't mock start_bottom_display, we want to test the real flow
            manager.start_bottom_display()  # Initialize once
            with patch.object(manager.live_component, "update") as mock_live_update:
                for step_type, *args in workflow_steps:
                    if step_type == "setup":
                        message = args[0]
                        manager.handle_setup_message(message)
                    elif step_type == "progress":
                        info = args[0]
                        manager.handle_progress_update(info)
                    elif step_type == "error":
                        file_path, error_msg = args
                        manager.handle_error_message(file_path, error_msg)

                # Verify setup messages and errors went to console
                setup_and_error_calls = [
                    call
                    for call in mock_console_print.call_args_list
                    if any(
                        msg in str(call)
                        for msg in [
                            "Collection initialized",
                            "Vector provider ready",
                            "Starting file processing",
                            "Failed to process",
                        ]
                    )
                ]
                assert len(setup_and_error_calls) == 4  # 3 setup + 1 error

                # Verify progress updates went to Live display
                # Should have at least 4 updates (one per progress step)
                # May have 1 extra from initialization
                assert mock_live_update.call_count >= 4  # 4+ progress updates

        # Cleanup
        if manager.is_active:
            manager.stop_display()

    def test_display_cleanup_after_completion(self):
        """Test that display is properly cleaned up after indexing completion."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # Start and use display
        manager.start_bottom_display()
        assert manager.is_active

        # Simulate some progress
        manager.handle_progress_update("Processing files...")

        # Stop display (simulating completion)
        manager.stop_display()

        # Verify cleanup
        assert not manager.is_active
        assert manager.live_component is None

    def test_display_handles_multiple_start_stop_cycles(self):
        """Test that display handles multiple start/stop cycles correctly."""
        console = Console()
        manager = RichLiveProgressManager(console=console)

        # First cycle
        manager.start_bottom_display()
        assert manager.is_active
        manager.handle_progress_update("First cycle progress")
        manager.stop_display()
        assert not manager.is_active

        # Second cycle
        manager.start_bottom_display()
        assert manager.is_active
        manager.handle_progress_update("Second cycle progress")
        manager.stop_display()
        assert not manager.is_active

        # Third cycle
        manager.start_bottom_display()
        assert manager.is_active
        manager.handle_progress_update("Third cycle progress")
        manager.stop_display()
        assert not manager.is_active
