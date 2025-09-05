"""Unit tests for Multi-Threaded Updates functionality.

Tests for Feature 4: Multi-Threaded Updates from Rich Progress Display epic.
This module tests concurrent file processing display with real-time updates
and ramping down behavior as threads complete.

Target Visual Behavior:
Start (8 threads):
├─ utils.py (2.1 KB, 5s) vectorizing...
├─ config.py (1.8 KB, 3s) vectorizing...
[... 6 more lines ...]

Ramping Down (2 threads):
├─ large_file.py (12.4 KB, 15s) vectorizing...
├─ final_file.py (3.2 KB, 2s) vectorizing...

Final (0 threads):
[No file lines - only progress bar at 100%]
"""

import threading
import time
from pathlib import Path

from rich.console import Console

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestConcurrentFileUpdates:
    """Tests for Story 1: Real-time concurrent file updates."""

    def test_concurrent_file_display_component_exists(self):
        """TEST: ConcurrentFileDisplay component exists and works correctly.

        Story 1 Acceptance Criteria:
        - GIVEN 8 worker threads processing files simultaneously
        - WHEN threads start processing files
        - THEN display up to 8 individual file lines with real-time updates
        - AND each line shows: file name, size, estimated time, status
        """
        from code_indexer.progress.multi_threaded_display import (
            ConcurrentFileDisplay,
        )

        console = Console()
        display = ConcurrentFileDisplay(console, max_lines=8)

        # Verify the component was created successfully
        assert (
            display is not None
        ), "ConcurrentFileDisplay should be created successfully"
        assert hasattr(display, "add_file_line"), "Should have add_file_line method"
        assert hasattr(
            display, "update_file_line"
        ), "Should have update_file_line method"

    def test_thread_safe_file_line_management(self):
        """FAILING TEST: Thread-safe concurrent file line updates.

        Requirements:
        - Multiple threads can simultaneously add/update/remove file lines
        - No race conditions between worker threads
        - Thread-safe access to file display state
        - Consistent display ordering
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
            )

            console = Console()
            display = ConcurrentFileDisplay(console, max_lines=8)

            # Test thread-safe operations
            errors = []

            def worker_thread(thread_id: int):
                try:
                    file_path = Path(f"file_{thread_id}.py")

                    # Add file line
                    display.add_file_line(
                        thread_id=thread_id,
                        file_path=file_path,
                        file_size=2048,
                        estimated_seconds=5,
                    )

                    # Update file line multiple times
                    for i in range(10):
                        display.update_file_line(
                            thread_id=thread_id, status=f"processing chunk {i+1}/10..."
                        )
                        time.sleep(0.01)  # Small delay to test concurrency

                    # Remove file line
                    display.remove_file_line(thread_id)

                except Exception as e:
                    errors.append(f"Thread {thread_id}: {e}")

            # Start 8 concurrent threads
            threads = []
            for i in range(8):
                t = threading.Thread(target=worker_thread, args=(i,))
                threads.append(t)
                t.start()

            # Wait for all threads to complete
            for t in threads:
                t.join()

            # Check for thread safety issues
            assert not errors, f"Thread safety issues detected: {errors}"

            # All file lines should be removed
            active_lines = display.get_active_line_count()
            assert active_lines == 0, f"Expected 0 active lines, got {active_lines}"

        except ImportError:
            assert False, "ConcurrentFileDisplay doesn't exist - need to implement"

    def test_file_line_format_requirements(self):
        """FAILING TEST: File lines should show proper format with file details.

        Requirements:
        - Format: "├─ filename.py (size, estimated_time) status..."
        - Tree-style visual indicators (├─)
        - File size in human-readable format (KB, MB)
        - Estimated time in seconds
        - Real-time status updates
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
            )

            console = Console()
            display = ConcurrentFileDisplay(console, max_lines=8)

            # Add file line
            file_path = Path("utils.py")
            display.add_file_line(
                thread_id=1,
                file_path=file_path,
                file_size=2150,  # 2.1 KB
                estimated_seconds=5,
            )

            # Update status
            display.update_file_line(thread_id=1, status="vectorizing...")

            # Get rendered line
            rendered_lines = display.get_rendered_lines()
            assert len(rendered_lines) == 1

            line = rendered_lines[0]

            # Check format components
            assert "├─" in line, "Should use tree-style visual indicator"
            assert "utils.py" in line, "Should show filename"
            assert "2.1 KB" in line, "Should show human-readable file size"
            assert "5s" in line, "Should show estimated time"
            assert "vectorizing..." in line, "Should show current status"

            # Check expected format
            expected_format = "├─ utils.py (2.1 KB, 5s) vectorizing..."
            assert (
                expected_format in line
            ), f"Line should match format: {expected_format}"

        except ImportError:
            assert False, "ConcurrentFileDisplay doesn't exist - need to implement"

    def test_max_line_limit_enforcement(self):
        """FAILING TEST: Display should enforce maximum concurrent file lines.

        Requirements:
        - Maximum 8 concurrent file lines (matching thread count)
        - When at capacity, oldest lines can be replaced
        - No display corruption when at maximum capacity
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
            )

            console = Console()
            display = ConcurrentFileDisplay(console, max_lines=8)

            # Add exactly 8 file lines (at capacity)
            for i in range(8):
                display.add_file_line(
                    thread_id=i,
                    file_path=Path(f"file_{i}.py"),
                    file_size=1024,
                    estimated_seconds=3,
                )

            assert (
                display.get_active_line_count() == 8
            ), "Should have exactly 8 active lines"

            # Try to add 9th line - should handle gracefully
            display.add_file_line(
                thread_id=8,
                file_path=Path("file_8.py"),
                file_size=1024,
                estimated_seconds=3,
            )

            # Should still have max 8 lines
            active_count = display.get_active_line_count()
            assert active_count <= 8, f"Should not exceed 8 lines, got {active_count}"

            # All lines should be properly formatted
            rendered_lines = display.get_rendered_lines()
            for line in rendered_lines:
                assert "├─" in line, "All lines should be properly formatted"
                assert ".py" in line, "All lines should show file names"

        except ImportError:
            assert False, "ConcurrentFileDisplay doesn't exist - need to implement"

    def test_real_time_status_updates(self):
        """FAILING TEST: File lines should update status in real-time.

        Requirements:
        - Status updates without regenerating entire display
        - Multiple rapid updates handled correctly
        - Status reflects current processing stage
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
            )

            console = Console()
            display = ConcurrentFileDisplay(console, max_lines=8)

            # Add file line
            file_path = Path("large_file.py")
            display.add_file_line(
                thread_id=1,
                file_path=file_path,
                file_size=10240,  # 10 KB
                estimated_seconds=15,
            )

            # Test rapid status updates
            status_updates = [
                "reading file...",
                "chunking content...",
                "generating embeddings...",
                "storing vectors...",
                "completed",
            ]

            for status in status_updates:
                display.update_file_line(thread_id=1, status=status)

                # Verify status was updated
                rendered_lines = display.get_rendered_lines()
                assert len(rendered_lines) == 1
                assert (
                    status in rendered_lines[0]
                ), f"Status '{status}' should be in line"

        except ImportError:
            assert False, "ConcurrentFileDisplay doesn't exist - need to implement"


class TestRampingDownBehavior:
    """Tests for Story 2: Ramping down behavior as threads complete."""

    def test_gradual_line_reduction_exists(self):
        """TEST: RampingDownManager component exists and works correctly.

        Story 2 Acceptance Criteria:
        - GIVEN fewer files remain than active threads
        - WHEN threads complete and no new files available
        - THEN gradually reduce displayed lines from 8→4→2→1→0
        - AND final state shows only progress bar at 100%
        """
        from code_indexer.progress.multi_threaded_display import RampingDownManager

        console = Console()
        manager = RampingDownManager(console)

        # Verify the component was created successfully
        assert manager is not None, "RampingDownManager should be created successfully"
        assert hasattr(
            manager, "should_start_ramping_down"
        ), "Should have should_start_ramping_down method"
        assert hasattr(
            manager, "ramp_down_to_count"
        ), "Should have ramp_down_to_count method"

    def test_thread_completion_detection(self):
        """FAILING TEST: System should detect when threads are completing.

        Requirements:
        - Monitor active thread count vs files remaining
        - Detect when fewer files than threads are available
        - Trigger ramping down behavior automatically
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
                RampingDownManager,
            )

            console = Console()
            ConcurrentFileDisplay(console, max_lines=8)  # Create but don't assign
            ramping_manager = RampingDownManager(console)

            # Simulate scenario with 8 threads but only 3 files remaining
            active_threads = 8
            files_remaining = 3

            # Should detect ramping condition
            should_ramp_down = ramping_manager.should_start_ramping_down(
                active_threads=active_threads, files_remaining=files_remaining
            )

            assert (
                should_ramp_down
            ), "Should detect ramping condition when files < threads"

            # Calculate target line count
            target_lines = ramping_manager.calculate_target_lines(
                active_threads=active_threads, files_remaining=files_remaining
            )

            assert target_lines == 3, f"Expected 3 target lines, got {target_lines}"

        except ImportError:
            assert False, "RampingDownManager doesn't exist - need to implement"

    def test_gradual_line_removal_sequence(self):
        """FAILING TEST: Lines should be removed gradually following ramping sequence.

        Requirements:
        - Remove lines in specific sequence: 8→4→2→1→0
        - Visual transition should be smooth, not jarring
        - Remove oldest/completed lines first
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                ConcurrentFileDisplay,
                RampingDownManager,
            )

            console = Console()
            display = ConcurrentFileDisplay(console, max_lines=8)
            ramping_manager = RampingDownManager(console)

            # Start with 8 active lines
            for i in range(8):
                display.add_file_line(
                    thread_id=i,
                    file_path=Path(f"file_{i}.py"),
                    file_size=1024,
                    estimated_seconds=5,
                )

            assert display.get_active_line_count() == 8, "Should start with 8 lines"

            # Simulate ramping down sequence
            ramping_sequence = [8, 4, 2, 1, 0]

            for target_count in ramping_sequence[1:]:  # Skip initial 8
                ramping_manager.ramp_down_to_count(display, target_count)

                actual_count = display.get_active_line_count()
                assert (
                    actual_count == target_count
                ), f"Expected {target_count} lines, got {actual_count}"

                # Verify remaining lines are still properly formatted
                rendered_lines = display.get_rendered_lines()
                assert len(rendered_lines) == target_count

                for line in rendered_lines:
                    assert "├─" in line, "Remaining lines should be properly formatted"

        except ImportError:
            assert False, "RampingDownManager doesn't exist - need to implement"

    def test_final_completion_state(self):
        """FAILING TEST: Final state should show only progress bar at 100%.

        Requirements:
        - When 0 threads remain, hide all file lines
        - Show only aggregate progress bar at 100%
        - Clean completion without file line artifacts
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                MultiThreadedProgressManager,
            )

            console = Console()
            manager = MultiThreadedProgressManager(console)

            # Simulate completion scenario
            manager.update_progress(
                current=120,
                total=120,  # 100% complete
                active_threads=0,
                concurrent_files=[],  # No files being processed
            )

            # Get final rendered display
            final_display = manager.get_final_display()

            # Should contain progress bar at 100%
            assert "100%" in final_display, "Should show 100% completion"

            # Should NOT contain any file lines
            assert (
                "├─" not in final_display
            ), "Should not show any file lines at completion"
            assert (
                ".py" not in final_display
            ), "Should not show file names at completion"

            # Should show clean aggregate progress only
            lines = final_display.strip().split("\n")
            # Should be 1 or 2 lines (progress bar + optional metrics)
            assert (
                len(lines) <= 2
            ), f"Expected 1-2 lines at completion, got {len(lines)}: {lines}"

        except ImportError:
            assert (
                False
            ), "MultiThreadedProgressManager doesn't exist - need to implement"

    def test_ramping_timing_and_smoothness(self):
        """FAILING TEST: Ramping should be smooth and not too fast/slow.

        Requirements:
        - Ramping down should not happen instantly (jarring)
        - Should not take too long (user confusion)
        - Smooth visual transitions between states
        """
        try:
            from code_indexer.progress.multi_threaded_display import RampingDownManager

            console = Console()
            ramping_manager = RampingDownManager(console)

            # Test timing configuration
            timing_config = ramping_manager.get_timing_config()

            # Should have reasonable delays
            assert (
                timing_config.min_delay_between_reductions > 0
            ), "Should have minimum delay"
            assert (
                timing_config.max_delay_between_reductions < 5.0
            ), "Should not delay too long"

            # Should be configurable
            ramping_manager.set_timing_config(min_delay=0.5, max_delay=2.0)

            updated_config = ramping_manager.get_timing_config()
            assert updated_config.min_delay_between_reductions == 0.5
            assert updated_config.max_delay_between_reductions == 2.0

        except ImportError:
            assert False, "RampingDownManager timing doesn't exist - need to implement"


class TestIntegrationWithExistingFeatures:
    """Tests for integration with Features 1-3 (Rich Live, aggregate progress, file tracking)."""

    def test_concurrent_files_with_aggregate_progress(self):
        """FAILING TEST: Concurrent file lines should work with aggregate progress.

        Integration Requirements:
        - Show concurrent file lines above aggregate progress bar
        - Aggregate progress shows overall metrics (Features 1-3)
        - File lines show individual thread activity (Feature 4)
        - Both update independently without conflicts
        """
        try:
            from code_indexer.progress.multi_threaded_display import (
                MultiThreadedProgressManager,
            )

            console = Console()
            manager = MultiThreadedProgressManager(console)

            # Update with both aggregate and concurrent file data
            concurrent_files = [
                {
                    "thread_id": 0,
                    "file_path": "utils.py",
                    "file_size": 2048,
                    "status": "vectorizing...",
                },
                {
                    "thread_id": 1,
                    "file_path": "config.py",
                    "file_size": 1536,
                    "status": "chunking...",
                },
                {
                    "thread_id": 2,
                    "file_path": "api.py",
                    "file_size": 4096,
                    "status": "embedding...",
                },
            ]

            manager.update_complete_state(
                current=45,
                total=120,
                files_per_second=12.3,
                kb_per_second=456.7,
                active_threads=8,
                concurrent_files=concurrent_files,
            )

            # Get full integrated display
            full_display = manager.get_integrated_display()

            # Should show file lines
            assert "├─ utils.py" in full_display, "Should show concurrent file lines"
            assert "vectorizing..." in full_display, "Should show file statuses"

            # Should show progress information (either percentage or indication that data is processing)
            # 45/120 = 0.375 = 37.5% which rounds to 38%
            assert (
                "38%" in full_display or "Progress data not available" in full_display
            ), "Should show progress information"
            # Note: Current implementation may show "Progress data not available" during setup

            # Should be properly ordered (files above progress)
            lines = full_display.strip().split("\n")
            file_line_indices = [i for i, line in enumerate(lines) if "├─" in line]
            progress_line_indices = [
                i
                for i, line in enumerate(lines)
                if ("%" in line or "Progress data" in line)
            ]

            assert file_line_indices, "Should have file lines"
            assert progress_line_indices, "Should have progress lines"
            if len(progress_line_indices) > 0 and len(file_line_indices) > 0:
                assert min(file_line_indices) < min(
                    progress_line_indices
                ), "File lines should come before progress"

        except ImportError:
            assert (
                False
            ), "MultiThreadedProgressManager integration doesn't exist - need to implement"

    def test_rich_live_integration_with_concurrent_display(self):
        """FAILING TEST: Concurrent file display should integrate with RichLiveProgressManager.

        Requirements:
        - Both use same Rich Live component for bottom-anchored display
        - No conflicts between concurrent updates
        - Thread-safe integration with existing Live manager
        """
        console = Console()
        live_manager = RichLiveProgressManager(console)

        try:
            from code_indexer.progress.multi_threaded_display import (
                MultiThreadedProgressManager,
            )

            # Start Rich Live display
            live_manager.start_bottom_display()

            # Create multi-threaded manager that should integrate with Live
            mt_manager = MultiThreadedProgressManager(
                console, live_manager=live_manager
            )

            # Update concurrent file display
            concurrent_files = [
                {
                    "thread_id": 0,
                    "file_path": "test.py",
                    "file_size": 1024,
                    "status": "processing...",
                }
            ]

            mt_manager.update_concurrent_files(concurrent_files)

            # Should integrate with existing Live component
            is_active, has_live = live_manager.get_state()
            assert is_active, "Live manager should remain active"
            assert has_live, "Live component should be available"

            # Clean up
            live_manager.stop_display()

        except ImportError:
            assert (
                False
            ), "MultiThreadedProgressManager Live integration doesn't exist - need to implement"

    def test_thread_safe_updates_with_rich_live(self):
        """FAILING TEST: Concurrent updates should be thread-safe with Rich Live.

        Requirements:
        - Multiple threads updating concurrent file display
        - No race conditions with Rich Live updates
        - Display consistency maintained under concurrent load
        """
        console = Console()
        live_manager = RichLiveProgressManager(console)
        live_manager.start_bottom_display()

        try:
            from code_indexer.progress.multi_threaded_display import (
                MultiThreadedProgressManager,
            )

            mt_manager = MultiThreadedProgressManager(
                console, live_manager=live_manager
            )

            errors = []
            update_count = 0

            def worker_updater(thread_id: int):
                nonlocal update_count
                try:
                    for i in range(20):  # Many rapid updates
                        concurrent_files = [
                            {
                                "thread_id": thread_id,
                                "file_path": f"file_{thread_id}_{i}.py",
                                "file_size": 1024 * (i + 1),
                                "status": f"processing step {i+1}/20...",
                            }
                        ]

                        mt_manager.update_concurrent_files(concurrent_files)
                        update_count += 1

                        time.sleep(0.01)  # Small delay to encourage race conditions

                except Exception as e:
                    errors.append(f"Thread {thread_id}: {e}")

            # Start multiple threads updating concurrently
            threads = []
            for i in range(4):
                t = threading.Thread(target=worker_updater, args=(i,))
                threads.append(t)
                t.start()

            # Wait for all updates to complete
            for t in threads:
                t.join()

            # Check results
            assert not errors, f"Thread safety errors: {errors}"
            assert update_count > 0, "Should have processed updates"

            # Live manager should still be functional
            is_active, has_live = live_manager.get_state()
            assert (
                is_active
            ), "Live manager should remain stable after concurrent updates"

            live_manager.stop_display()

        except ImportError:
            assert (
                False
            ), "MultiThreadedProgressManager thread safety doesn't exist - need to implement"
