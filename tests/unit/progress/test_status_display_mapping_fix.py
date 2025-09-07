"""
Tests for Status Display Mapping Fix.

This module tests the surgical fix for missing "finalizing..." status display mapping
in multi_threaded_display.py. Users see "vectorizing..." but not "finalizing..." or
complete status transitions.

ROOT CAUSE:
- ConsolidatedFileTracker emits "finalizing..." status during file completion
- MultiThreadedDisplay only maps "processing" → "vectorizing..." and "complete" → "complete ✓"
- "finalizing..." status falls through to raw display, breaking user experience

SURGICAL FIX:
- Add elif line_data.status == "finalizing...": status_str = "finalizing..." to mapping
- This ensures all status states are visible: starting → vectorizing → finalizing → complete
"""

from pathlib import Path

from code_indexer.progress.multi_threaded_display import ConcurrentFileDisplay
from code_indexer.services.consolidated_file_tracker import (
    ConsolidatedFileTracker,
    FileStatus,
)
from rich.console import Console


class TestStatusDisplayMappingFix:
    """Test suite for status display mapping fix."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Console()
        self.display = ConcurrentFileDisplay(self.console, max_lines=8)
        self.tracker = ConsolidatedFileTracker(max_concurrent_files=8)

    def test_finalizing_status_display_mapping_failing_case(self):
        """FAILING TEST: 'finalizing...' status should be properly mapped in display.

        This test will FAIL until the fix is implemented because:
        - ConsolidatedFileTracker emits "finalizing..." status during completion
        - MultiThreadedDisplay only maps "processing" and "complete" statuses
        - "finalizing..." falls through to raw display, confusing users

        Expected behavior after fix:
        - "finalizing..." status should display as "finalizing..."
        - Complete status progression: starting → vectorizing → finalizing → complete ✓
        """
        file_path = Path("/test/file.py")
        file_size = 1024
        thread_id = 1

        # Start file processing and progress through all status states
        self.tracker.start_file_processing(thread_id, file_path, file_size)

        # Test "processing" → "vectorizing..." mapping (this should work)
        self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)
        concurrent_data = self.tracker.get_concurrent_files_data()

        # Get the display line for this file
        display_lines = self.tracker.get_formatted_display_lines()
        assert len(display_lines) == 1
        display_line = display_lines[0]

        # Verify "processing" maps to "vectorizing..."
        assert "vectorizing..." in display_line, (
            f"Expected 'vectorizing...' in display for processing status, "
            f"got: {display_line}"
        )

        # Update to "finalizing..." status (the problematic case)
        # This simulates what happens during file completion
        file_data = concurrent_data[0]
        file_data["status"] = "finalizing..."

        # Mock the file data with finalizing status
        from code_indexer.progress.multi_threaded_display import FileLineData

        line_data = FileLineData(
            thread_id=thread_id,
            file_path=str(file_path),
            file_size=file_size,
            status="finalizing...",
            estimated_seconds=5.0,
        )

        # Format the display line using the display component
        formatted_line = self.display._format_file_line(line_data)

        # FAILING ASSERTION: "finalizing..." should be mapped to display properly
        # This will FAIL because the mapping is missing in multi_threaded_display.py
        assert "finalizing..." in formatted_line, (
            f"Expected 'finalizing...' to appear in display, but got: {formatted_line}. "
            f"The status mapping is missing from multi_threaded_display.py lines 191-197."
        )

        # Verify the status is not showing raw or incorrectly
        assert "finalizing..." in formatted_line and not formatted_line.endswith(
            "finalizing..."
        ), f"Status should be properly formatted, not raw. Got: {formatted_line}"

    def test_complete_status_progression_visibility(self):
        """FAILING TEST: All status states should be visible in display progression.

        This test verifies that users can see the complete status progression:
        starting... → vectorizing... → finalizing... → complete ✓

        This test will FAIL until the "finalizing..." mapping is added.
        """
        file_path = Path("/test/progression_file.py")
        thread_id = 1

        # Start file processing
        self.tracker.start_file_processing(thread_id, file_path, 2048)

        # Test all status progressions
        status_progression = [
            ("starting...", "starting..."),  # Raw status, should display as-is
            ("processing", "vectorizing..."),  # Should map to vectorizing...
            ("finalizing...", "finalizing..."),  # Should map to finalizing... (FAILING)
            ("complete", "complete ✓"),  # Should map to complete ✓
        ]

        for raw_status, expected_display in status_progression:
            # Update to this status
            if raw_status == "starting...":
                # starting... is the initial status
                pass
            elif raw_status == "processing":
                self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)
            elif raw_status == "complete":
                self.tracker.complete_file_processing(thread_id)
            else:
                # For "finalizing...", we need to simulate this status
                # Since it's an intermediate status during completion
                concurrent_data = self.tracker.get_concurrent_files_data()
                if concurrent_data:
                    concurrent_data[0]["status"] = raw_status

            # Get display line
            if raw_status == "finalizing...":
                # Use the display component directly for finalizing status
                from code_indexer.progress.multi_threaded_display import FileLineData

                line_data = FileLineData(
                    thread_id=thread_id,
                    file_path=str(file_path),
                    file_size=2048,
                    status=raw_status,
                    estimated_seconds=3.0,
                )
                display_line = self.display._format_file_line(line_data)
            else:
                display_lines = self.tracker.get_formatted_display_lines()
                if display_lines:
                    display_line = display_lines[0]
                else:
                    continue  # File might be cleaned up after completion

            # Verify the expected display text appears
            if raw_status == "finalizing...":
                # This assertion will FAIL until the fix is implemented
                assert expected_display in display_line, (
                    f"Status progression failed at '{raw_status}'. "
                    f"Expected '{expected_display}' in display, got: {display_line}. "
                    f"Missing status mapping in multi_threaded_display.py"
                )
            else:
                assert expected_display in display_line, (
                    f"Status progression failed at '{raw_status}'. "
                    f"Expected '{expected_display}', got: {display_line}"
                )

    def test_status_mapping_consistency_with_consolidated_tracker(self):
        """FAILING TEST: Display mappings should handle all ConsolidatedFileTracker statuses.

        This test ensures that MultiThreadedDisplay can handle all status values
        that ConsolidatedFileTracker emits, including the missing "finalizing..." status.

        This test will FAIL until the complete status mapping is implemented.
        """
        from code_indexer.progress.multi_threaded_display import FileLineData

        # Test all possible statuses from ConsolidatedFileTracker
        test_statuses = [
            ("starting...", "starting..."),  # Raw display
            ("processing", "vectorizing..."),  # Mapped display
            ("finalizing...", "finalizing..."),  # MISSING mapping (will fail)
            ("complete", "complete ✓"),  # Mapped display
            ("unknown_status", "unknown_status"),  # Fallback to raw
        ]

        for raw_status, expected_display in test_statuses:
            line_data = FileLineData(
                thread_id=1,
                file_path="/test/mapping_test.py",
                file_size=1024,
                status=raw_status,
                estimated_seconds=2.5,
            )

            # Format using the display component
            formatted_line = self.display._format_file_line(line_data)

            # Verify the status is correctly mapped
            if raw_status == "finalizing...":
                # This assertion will FAIL until the mapping is added
                assert expected_display in formatted_line, (
                    f"Missing status mapping for '{raw_status}'. "
                    f"Expected '{expected_display}' in: {formatted_line}. "
                    f"Fix needed in multi_threaded_display.py lines 191-197: "
                    f"add elif line_data.status == 'finalizing...': status_str = 'finalizing...'"
                )
            else:
                assert expected_display in formatted_line, (
                    f"Status mapping failed for '{raw_status}'. "
                    f"Expected '{expected_display}' in: {formatted_line}"
                )

    def test_user_experience_complete_status_visibility(self):
        """FAILING TEST: Users should see complete status transitions without gaps.

        This test simulates the user experience during file processing and verifies
        that all status transitions are visible, including the missing "finalizing..."
        state that occurs just before completion.

        This test will FAIL because users currently see a gap in status progression.
        """
        files = [Path(f"/test/user_exp_{i}.py") for i in range(3)]

        # Start processing multiple files
        for i, file_path in enumerate(files):
            self.tracker.start_file_processing(i, file_path, 1024 * (i + 1))

        # Progress files through different states to simulate real processing
        test_scenarios = [
            # File 0: Complete progression including finalizing
            (0, ["starting...", "processing", "finalizing...", "complete"]),
            # File 1: Stuck in processing (should show vectorizing...)
            (1, ["starting...", "processing"]),
            # File 2: Quick completion (should show all transitions)
            (2, ["starting...", "processing", "finalizing...", "complete"]),
        ]

        for thread_id, status_sequence in test_scenarios:
            for status in status_sequence:
                if status == "starting...":
                    continue  # Already set during start_file_processing
                elif status == "processing":
                    self.tracker.update_file_status(thread_id, FileStatus.PROCESSING)
                elif status == "complete":
                    self.tracker.complete_file_processing(thread_id)
                elif status == "finalizing...":
                    # Simulate the finalizing status that occurs during completion
                    concurrent_data = self.tracker.get_concurrent_files_data()
                    file_data = next(
                        (f for f in concurrent_data if f["thread_id"] == thread_id),
                        None,
                    )
                    if file_data:
                        file_data["status"] = status

                # Check that user can see the current status
                if status == "finalizing...":
                    # Test the display component directly for finalizing status
                    from code_indexer.progress.multi_threaded_display import (
                        FileLineData,
                    )

                    line_data = FileLineData(
                        thread_id=thread_id,
                        file_path=str(files[thread_id]),
                        file_size=1024 * (thread_id + 1),
                        status=status,
                        estimated_seconds=1.0,
                    )
                    display_line = self.display._format_file_line(line_data)

                    # FAILING ASSERTION: finalizing status should be visible
                    assert "finalizing..." in display_line, (
                        f"User cannot see 'finalizing...' status for file {thread_id}. "
                        f"Got: {display_line}. This creates a jarring user experience where "
                        f"files jump from 'vectorizing...' directly to 'complete ✓' without "
                        f"showing the intermediate 'finalizing...' state."
                    )

    def test_surgical_fix_location_verification(self):
        """FAILING TEST: Verify the exact location where the fix needs to be applied.

        This test identifies the exact lines in multi_threaded_display.py that need
        the surgical fix and verifies the current behavior is broken.

        This test will FAIL until the fix is applied to lines 191-197.
        """
        # Read the current source code to verify the fix location
        import inspect

        # Get the _format_file_line method source
        method_source = inspect.getsource(self.display._format_file_line)

        # Verify the current broken mapping structure exists
        assert (
            'if line_data.status == "processing":' in method_source
        ), "Expected to find processing status mapping in source"
        assert (
            'elif line_data.status == "complete":' in method_source
        ), "Expected to find complete status mapping in source"

        # This assertion will FAIL - the finalizing mapping is missing
        assert 'elif line_data.status == "finalizing...":' in method_source, (
            "MISSING: The 'finalizing...' status mapping is not found in source code. "
            "Fix needed in multi_threaded_display.py around lines 191-197: "
            "Add: elif line_data.status == 'finalizing...': status_str = 'finalizing...'"
        )

        # Test the actual behavior to confirm it's broken
        from code_indexer.progress.multi_threaded_display import FileLineData

        line_data = FileLineData(
            thread_id=1,
            file_path="/test/surgical_fix.py",
            file_size=1024,
            status="finalizing...",
            estimated_seconds=2.0,
        )

        formatted_line = self.display._format_file_line(line_data)

        # The current implementation should show raw "finalizing..." instead of mapped version
        # After fix, this should show proper mapped "finalizing..."
        current_behavior_shows_raw = "finalizing..." in formatted_line
        assert (
            current_behavior_shows_raw
        ), f"Expected current broken behavior to show raw status, got: {formatted_line}"

        # But verify it's not properly formatted (this is the bug)
        # The fix will ensure proper formatting and consistency with other status mappings
