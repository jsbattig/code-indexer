"""
Test to verify the progress percentage fix works correctly with Rich Progress Display.
"""

# pathlib import removed - no longer needed
from unittest.mock import Mock
import pytest
import time
from io import StringIO

from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager


class TestProgressPercentageFix:
    """Test that progress percentages are calculated correctly with new Rich Progress Display."""

    @pytest.mark.unit
    def test_rich_progress_percentage_calculation(self):
        """Test that Rich Progress Display correctly calculates and displays progress percentages."""

        # Create console mock
        console_mock = Mock()
        console_mock.__enter__ = Mock(return_value=console_mock)
        console_mock.__exit__ = Mock(return_value=None)

        # Create Rich Progress Display manager
        progress_manager = MultiThreadedProgressManager(console=console_mock)

        # Patch the get_time method on the progress object to return consistent values
        progress_manager.progress.get_time = Mock(return_value=time.time())

        # Simulate the pattern that was causing percentage calculation issues
        total_files = 134

        print("\n=== Testing Rich Progress Display Percentage Calculation ===")

        # Test various progress levels to ensure percentages are calculated correctly
        test_scenarios = [
            (1, total_files, 1.0),  # ~0.7%
            (10, total_files, 7.5),  # ~7.5%
            (14, total_files, 10.4),  # ~10.4% (this was the problematic case)
            (50, total_files, 37.3),  # ~37.3%
            (100, total_files, 74.6),  # ~74.6%
            (134, total_files, 100.0),  # 100%
        ]

        for current, total, expected_percentage in test_scenarios:
            # Update the progress manager
            progress_manager.update_complete_state(
                current=current,
                total=total,
                files_per_second=2.5,
                kb_per_second=512.0,
                active_threads=4,
                concurrent_files=[],
            )

            # Get the integrated display and render to string
            display_table = progress_manager.get_integrated_display()

            # Render the table to string using console_mock's mock capabilities
            console_buffer = StringIO()
            from rich.console import Console

            test_console = Console(file=console_buffer, width=120)
            test_console.print(display_table)
            display = console_buffer.getvalue()

            # Verify display is not empty
            assert (
                len(display.strip()) > 0
            ), f"Display should not be empty for {current}/{total}"

            # Verify it contains the correct progress information
            assert (
                f"{current}/{total} files" in display
            ), f"Should show '{current}/{total} files' in display"

            # Calculate actual percentage from display
            calculated_percentage = (current / total * 100) if total > 0 else 0

            # Verify the percentage in the display content
            percentage_text = f"{calculated_percentage:.0f}%"
            assert (
                percentage_text in display
            ), f"Should show correct percentage {percentage_text} in display"

            print(
                f"  ✅ {current}/{total} files -> {calculated_percentage:.1f}% (expected ~{expected_percentage:.1f}%)"
            )

        print("\n✅ Rich Progress Display percentage calculation verified!")
        print(
            "   All progress levels show correct percentages (no longer stuck at low values)"
        )

    @pytest.mark.unit
    def test_info_updates_maintain_progress_state(self):
        """Test that info-only updates maintain the correct progress state."""

        console_mock = Mock()
        console_mock.__enter__ = Mock(return_value=console_mock)
        console_mock.__exit__ = Mock(return_value=None)

        progress_manager = MultiThreadedProgressManager(console=console_mock)

        # Patch the get_time method on the progress object to return consistent values
        progress_manager.progress.get_time = Mock(return_value=time.time())

        total_files = 134

        # Set initial progress state
        progress_manager.update_complete_state(
            current=14,
            total=total_files,
            files_per_second=2.5,
            kb_per_second=512.0,
            active_threads=4,
            concurrent_files=[],
        )

        # Get display before and after (should maintain state)
        display1_table = progress_manager.get_integrated_display()
        display2_table = progress_manager.get_integrated_display()

        # Render both tables to strings for comparison
        console_buffer1 = StringIO()
        console_buffer2 = StringIO()
        from rich.console import Console

        test_console1 = Console(file=console_buffer1, width=120)
        test_console2 = Console(file=console_buffer2, width=120)
        test_console1.print(display1_table)
        test_console2.print(display2_table)
        display1 = console_buffer1.getvalue()
        display2 = console_buffer2.getvalue()

        # Both displays should show the same progress information
        assert "14/134 files" in display1, "First display should show correct progress"
        assert (
            "14/134 files" in display2
        ), "Second display should maintain progress state"

        # Both should show the correct percentage (10.4%)
        assert "10%" in display1, "First display should show ~10%"
        assert "10%" in display2, "Second display should maintain ~10%"

        print("\n✅ Info updates correctly maintain progress state!")
        print("   Progress state is preserved across multiple display calls")


if __name__ == "__main__":
    pytest.main([__file__, "-s"])  # -s to show print statements
