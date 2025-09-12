"""Unit tests for Aggregate Progress Line functionality.

Tests for Feature 2: Aggregate Progress Line from Rich Progress Display epic.
This module tests the two-line aggregate progress format that provides clean
overall metrics without individual file details.

Target format:
Line 1: Indexing ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 37% • 0:01:23 • 0:02:12 • 45/120 files
Line 2: 12.3 files/s | 456.7 KB/s | 8 threads
"""

from rich.console import Console
from rich.progress import Progress

from code_indexer.progress.progress_display import RichLiveProgressManager


class TestAggregateProgressLine:
    """Tests for the aggregate progress line functionality."""

    def test_current_single_line_format_shows_individual_files(self):
        """FAILING TEST: Current single-line format shows individual file names instead of aggregate.

        This test demonstrates the current limitation where progress shows individual
        file names in the description, which is too detailed for aggregate view.

        Story 1 Acceptance Criteria:
        - GIVEN indexing is in progress with 45/120 files processed
        - WHEN progress is displayed
        - THEN show overall progress bar with percentage, timing, and file count
        - AND do not show individual file names in aggregate view
        """
        console = Console()
        manager = RichLiveProgressManager(console)

        # Start display and create current format Progress bar
        manager.start_bottom_display()

        # Current CLI format from cli.py lines 1564-1578
        current_progress = Progress(
            "Indexing",
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            "[progress.elapsed]{task.elapsed}",
            "•",
            "[progress.remaining]{task.remaining}",
            "•",
            "{task.description}",  # This shows individual file names
        )

        # Simulate current behavior - shows individual file info
        task_id = current_progress.add_task("Starting...", total=120)
        current_progress.update(
            task_id,
            completed=45,
            description="15.2 files/s | 789.1 KB/s | 8 threads | /path/to/current/file.py",
        )

        # Get rendered output
        with console.capture() as capture:
            console.print(current_progress)
        current_output = capture.get()

        # ASSERTION: Current format includes individual file path (this should fail for aggregate view)
        # Check for file path indicators (may be truncated in display)
        assert any(
            indicator in current_output
            for indicator in ["/path/to", ".py", "/current/"]
        ), "Current format should show individual files - this is what we want to change"

        # ASSERTION: File count is not clearly separated (should fail)
        assert (
            "45/120 files" not in current_output
        ), "Current format doesn't show clear file count - this is what we need to add"

        # Clean up
        manager.stop_display()

    def test_clean_progress_bar_format_requirements(self):
        """FAILING TEST: Clean progress bar should show aggregate metrics without individual files.

        Story 1 Acceptance Criteria:
        - Progress bar shows overall percentage (37%)
        - Shows elapsed time (0:01:23)
        - Shows remaining time (0:02:12)
        - Shows file count as "45/120 files"
        - Does NOT show individual file names
        """
        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        # This is the DESIRED format that doesn't exist yet
        # The test will fail because AggregateProgressDisplay doesn't exist
        try:
            from code_indexer.progress.aggregate_progress import (
                AggregateProgressDisplay,
            )

            aggregate_progress = AggregateProgressDisplay(console)

            # Configure aggregate progress with clean format
            aggregate_progress.update_progress(
                current=45,
                total=120,
                elapsed_seconds=83,  # 1:23
                estimated_remaining=132,  # 2:12
                files_per_second=12.3,
                kb_per_second=456.7,
                active_threads=8,
            )

            # Get the rendered first line (progress bar)
            progress_line = aggregate_progress.get_progress_line()

            # Should contain percentage
            assert "37%" in progress_line, "Progress bar should show percentage"

            # Should contain timing
            assert "0:01:23" in progress_line, "Progress bar should show elapsed time"
            assert "0:02:12" in progress_line, "Progress bar should show remaining time"

            # Should contain file count
            assert (
                "45/120 files" in progress_line
            ), "Progress bar should show file count"

            # Should NOT contain individual file paths (but should contain file count with /)
            assert (
                ".py" not in progress_line
            ), "Progress bar should not show individual file names"
            # Check that there are no file paths (slashes not in the file count context)
            # We know file count has format "N/M files", so exclude that pattern
            line_without_file_count = progress_line.replace(f"{45}/{120} files", "")
            assert (
                "/" not in line_without_file_count
            ), "Progress bar should not show file paths"

        except ImportError:
            # This should fail because AggregateProgressDisplay doesn't exist yet
            assert (
                False
            ), "AggregateProgressDisplay class doesn't exist - need to implement"

        manager.stop_display()

    def test_aggregate_metrics_line_format_requirements(self):
        """FAILING TEST: Second line should show aggregate performance metrics.

        Story 2 Acceptance Criteria:
        - Second line shows files/s rate (12.3 files/s)
        - Shows KB/s throughput (456.7 KB/s)
        - Shows active thread count (8 threads)
        - Uses clean pipe-separated format
        """
        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            from code_indexer.progress.aggregate_progress import (
                AggregateProgressDisplay,
            )

            aggregate_progress = AggregateProgressDisplay(console)

            # Configure metrics
            aggregate_progress.update_metrics(
                files_per_second=12.3, kb_per_second=456.7, active_threads=8
            )

            # Get the rendered metrics line
            metrics_line = aggregate_progress.get_metrics_line()

            # Should show files per second
            assert "12.3 files/s" in metrics_line, "Metrics should show files/s rate"

            # Should show KB per second
            assert "456.7 KB/s" in metrics_line, "Metrics should show KB/s throughput"

            # Should show thread count
            assert "8 threads" in metrics_line, "Metrics should show thread count"

            # Should use pipe separators
            assert "|" in metrics_line, "Metrics should use pipe separators"

            # Expected format: "12.3 files/s | 456.7 KB/s | 8 threads"
            expected = "12.3 files/s | 456.7 KB/s | 8 threads"
            assert (
                expected in metrics_line
            ), f"Metrics line should match format: {expected}"

        except ImportError:
            # This should fail because AggregateProgressDisplay doesn't exist yet
            assert (
                False
            ), "AggregateProgressDisplay class doesn't exist - need to implement"

        manager.stop_display()

    def test_two_line_format_integration(self):
        """FAILING TEST: Two-line format should integrate with RichLiveProgressManager.

        Integration Requirements:
        - First line: Clean progress bar with timing and file count
        - Second line: Aggregate performance metrics
        - Both lines display together in bottom-anchored Live display
        - No individual file names in either line
        """
        console = Console()
        manager = RichLiveProgressManager(console)
        manager.start_bottom_display()

        try:
            from code_indexer.progress.aggregate_progress import (
                AggregateProgressDisplay,
            )

            aggregate_progress = AggregateProgressDisplay(console)

            # Update with complete progress state
            aggregate_progress.update_complete_state(
                current=45,
                total=120,
                elapsed_seconds=83,
                estimated_remaining=132,
                files_per_second=12.3,
                kb_per_second=456.7,
                active_threads=8,
            )

            # Get full two-line display
            full_display = aggregate_progress.get_full_display()

            # Should be two lines
            lines = full_display.split("\n")
            assert len(lines) == 2, "Display should have exactly two lines"

            progress_line, metrics_line = lines

            # First line assertions
            assert "37%" in progress_line, "First line should show percentage"
            assert "45/120 files" in progress_line, "First line should show file count"
            assert "0:01:23" in progress_line, "First line should show elapsed time"

            # Second line assertions
            assert "12.3 files/s" in metrics_line, "Second line should show files/s"
            assert "456.7 KB/s" in metrics_line, "Second line should show KB/s"
            assert "8 threads" in metrics_line, "Second line should show thread count"

            # Integration with RichLiveProgressManager
            manager.update_display(full_display)

            # Verify display is active and content is set
            is_active, has_live_component = manager.get_state()
            assert is_active, "Manager should be active after update"
            assert has_live_component, "Manager should have live component"

        except ImportError:
            assert (
                False
            ), "AggregateProgressDisplay integration doesn't exist - need to implement"

        manager.stop_display()

    def test_performance_metrics_calculation(self):
        """FAILING TEST: Performance metrics should be calculated from progress data.

        Requirements:
        - Files/s rate calculated from processed files and elapsed time
        - KB/s throughput calculated from data size and elapsed time
        - Thread count from active processing threads
        - Metrics update in real-time as progress advances
        """
        try:
            from code_indexer.progress.aggregate_progress import (
                ProgressMetricsCalculator,
            )

            calculator = ProgressMetricsCalculator()

            # Simulate progress over time
            calculator.record_progress_point(
                timestamp=1000.0, files_processed=0, bytes_processed=0, active_threads=4
            )

            calculator.record_progress_point(
                timestamp=1010.0,  # 10 seconds later
                files_processed=50,
                bytes_processed=512000,  # 500KB
                active_threads=8,
            )

            metrics = calculator.get_current_metrics()

            # Should calculate files/s: 50 files / 10 seconds = 5.0 files/s
            assert (
                metrics.files_per_second == 5.0
            ), f"Expected 5.0 files/s, got {metrics.files_per_second}"

            # Should calculate KB/s: 500KB / 10 seconds = 50.0 KB/s
            assert (
                metrics.kb_per_second == 50.0
            ), f"Expected 50.0 KB/s, got {metrics.kb_per_second}"

            # Should track current thread count
            assert (
                metrics.active_threads == 8
            ), f"Expected 8 threads, got {metrics.active_threads}"

        except ImportError:
            assert False, "ProgressMetricsCalculator doesn't exist - need to implement"

    def test_rich_progress_bar_customization(self):
        """FAILING TEST: Progress bar should use Rich components for clean formatting.

        Requirements:
        - Use Rich Progress with custom columns
        - Clean visual separators (•)
        - Proper time formatting (MM:SS)
        - File count formatting (N/Total files)
        """
        try:
            from code_indexer.progress.aggregate_progress import (
                create_aggregate_progress_bar,
            )

            progress_bar = create_aggregate_progress_bar()

            # Should have specific column layout
            columns = progress_bar.columns
            assert (
                len(columns) >= 6
            ), "Progress bar should have multiple columns for clean layout"

            # Should create task and update with metrics
            task_id = progress_bar.add_task("Indexing", total=120)
            progress_bar.update(
                task_id,
                completed=45,
                # Custom field for file count display
                file_count="45/120 files",
            )

            # Test rendering - capture with the same console instance
            console = Console()
            with console.capture() as capture:
                console.print(progress_bar)
            output = capture.get()

            # Should show clean format without individual files
            # Progress should be around 37-38% (45/120 = 37.5%)
            assert "%" in output, "Should show percentage"
            assert any(
                pct in output for pct in ["37%", "38%"]
            ), f"Should show correct percentage, got: {output}"
            assert "45/120 files" in output, "Should show file count"
            # Check for file paths (excluding the file count)
            output_without_count = output.replace("45/120 files", "")
            assert (
                ".py" not in output_without_count
            ), "Should not show individual file names"
            assert not any(
                path in output_without_count for path in ["/src/", "/home/", ".py"]
            ), "Should not show file paths"

        except ImportError:
            assert (
                False
            ), "create_aggregate_progress_bar doesn't exist - need to implement"
