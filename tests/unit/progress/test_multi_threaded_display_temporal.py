"""Unit tests for temporal status string handling in multi-threaded display.

This module tests the fix for the slot display truncation bug where Path.name
treats forward slashes in temporal status strings as path separators.

Bug: "abc12345 - Vectorizing 50% (4/8 chunks)" gets truncated to "8 chunks)"
Fix: Detect temporal status strings and preserve them, only extract basename for real paths.
"""

from pathlib import Path
from rich.console import Console

from code_indexer.progress.multi_threaded_display import MultiThreadedProgressManager
from code_indexer.services.clean_slot_tracker import FileData


class TestTemporalStatusStringHandling:
    """Test that temporal status strings with slashes are not truncated."""

    def setup_method(self):
        """Set up test fixtures."""
        self.console = Console()
        self.manager = MultiThreadedProgressManager(console=self.console)

    def test_temporal_status_string_not_truncated(self):
        """Test that temporal status string is preserved, not truncated by Path.name.

        BUG: Path("abc12345 - Vectorizing 50% (4/8 chunks)").name returns "8 chunks)"
        because Path treats the forward slash as a path separator.

        EXPECTED: Full string "abc12345 - Vectorizing 50% (4/8 chunks)" preserved.
        """
        # Create FileData with temporal status string
        temporal_status = "abc12345 - Vectorizing 50% (4/8 chunks)"
        file_data = FileData(
            filename=temporal_status, file_size=1024 * 50, status="vectorizing"  # 50 KB
        )

        # Format the line
        result = self.manager._format_file_line_from_data(file_data)

        # MUST contain full temporal status string, NOT truncated "8 chunks)"
        assert temporal_status in result, (
            f"Temporal status string truncated! Expected '{temporal_status}' in result, "
            f"but got: {result}"
        )

        # MUST NOT be truncated to just "8 chunks)"
        assert result != "├─ 8 chunks) (50.0 KB, 1s) vectorizing...", (
            f"Path.name truncated temporal status string to '8 chunks)'. "
            f"Got: {result}"
        )

    def test_regular_file_path_still_extracts_basename(self):
        """Test that regular file paths still extract basename correctly.

        Ensures backward compatibility: real file paths should still use Path.name
        to extract just the filename, not the full path.
        """
        test_cases = [
            ("src/foo/bar.py", "bar.py"),
            ("/absolute/path/to/file.txt", "file.txt"),
            ("nested/directories/deep/module.py", "module.py"),
        ]

        for file_path, expected_basename in test_cases:
            file_data = FileData(
                filename=file_path, file_size=1024, status="processing"
            )

            result = self.manager._format_file_line_from_data(file_data)

            # Must contain ONLY the basename, not full path
            assert (
                expected_basename in result
            ), f"Expected basename '{expected_basename}' in result. Got: {result}"

            # Must NOT contain the full path (except for the basename part)
            # Check that parent directories are not in the result
            parent_dir = str(Path(file_path).parent)
            if parent_dir and parent_dir != ".":
                # Extract just the directory part before the basename
                dir_part = file_path.split(expected_basename)[0]
                assert dir_part not in result, (
                    f"Full path '{file_path}' should be truncated to basename. "
                    f"Found parent directory '{dir_part}' in result: {result}"
                )

    def test_concurrent_files_temporal_status_not_truncated(self):
        """Test that temporal status strings are preserved in concurrent file display.

        This tests the specific bug in get_integrated_display() at lines 336-340
        where concurrent_files processing truncates temporal status strings at '/' character.

        BUG: Line 340: filename = str(filename).split("/")[-1]
        Input: "abc12345 - Vectorizing 50% (4/8 chunks)"
        Current output: "8 chunks)" (truncated after '/')
        Expected: Full string preserved
        """
        # Temporal status string with '/' in progress (4/8)
        temporal_status = "abc12345 - Vectorizing 50% (4/8 chunks)"

        # Create concurrent files data as it comes from daemon serialization
        concurrent_files = [
            {
                "file_path": temporal_status,
                "file_size": 51200,  # 50 KB
                "status": "processing",
            }
        ]

        # Update state with concurrent files
        self.manager.update_complete_state(
            current=5,
            total=10,
            files_per_second=2.5,
            kb_per_second=100.0,
            active_threads=4,
            concurrent_files=concurrent_files,
            slot_tracker=None,
            info="🚀 Indexing",
        )

        # Get integrated display
        display_table = self.manager.get_integrated_display()

        # Extract rendered text from Rich Table
        from rich.console import Console
        from io import StringIO

        buffer = StringIO()
        test_console = Console(file=buffer, width=200)
        test_console.print(display_table)
        rendered_output = buffer.getvalue()

        # MUST contain full temporal status string, NOT truncated "8 chunks)"
        assert temporal_status in rendered_output, (
            f"Temporal status string truncated in concurrent file display! "
            f"Expected '{temporal_status}' in output, but got:\n{rendered_output}"
        )

        # MUST NOT show only the truncated "8 chunks)"
        assert "├─ 8 chunks)" not in rendered_output, (
            f"Temporal status string was truncated to '8 chunks)'. "
            f"Full output:\n{rendered_output}"
        )

    def test_concurrent_files_regular_paths_extract_basename(self):
        """Test that regular file paths in concurrent_files still extract basename.

        Ensures backward compatibility: real file paths with '/' should still extract
        basename, not show full paths.
        """
        # Regular file path with '/' separators
        file_path = "src/services/indexer.py"
        expected_basename = "indexer.py"

        concurrent_files = [
            {"file_path": file_path, "file_size": 2048, "status": "processing"}
        ]

        self.manager.update_complete_state(
            current=3,
            total=10,
            files_per_second=1.5,
            kb_per_second=50.0,
            active_threads=2,
            concurrent_files=concurrent_files,
            slot_tracker=None,
            info="🚀 Indexing",
        )

        display_table = self.manager.get_integrated_display()

        from rich.console import Console
        from io import StringIO

        buffer = StringIO()
        test_console = Console(file=buffer, width=200)
        test_console.print(display_table)
        rendered_output = buffer.getvalue()

        # MUST contain only basename
        assert (
            expected_basename in rendered_output
        ), f"Expected basename '{expected_basename}' in output. Got:\n{rendered_output}"

        # MUST NOT contain parent directories
        assert "src/services/" not in rendered_output, (
            f"Full path should be truncated to basename. "
            f"Found 'src/services/' in output:\n{rendered_output}"
        )

    def test_concurrent_files_path_object_extracts_basename(self):
        """Test that Path objects in concurrent_files extract basename correctly."""
        # Path object (from slot_tracker fallback code)
        file_path = Path("src/utils/helpers.py")
        expected_basename = "helpers.py"

        concurrent_files = [
            {"file_path": file_path, "file_size": 1024, "status": "complete"}
        ]

        self.manager.update_complete_state(
            current=1,
            total=1,
            files_per_second=1.0,
            kb_per_second=10.0,
            active_threads=1,
            concurrent_files=concurrent_files,
            slot_tracker=None,
            info="🚀 Indexing",
        )

        display_table = self.manager.get_integrated_display()

        from rich.console import Console
        from io import StringIO

        buffer = StringIO()
        test_console = Console(file=buffer, width=200)
        test_console.print(display_table)
        rendered_output = buffer.getvalue()

        # MUST contain only basename
        assert (
            expected_basename in rendered_output
        ), f"Expected basename '{expected_basename}' for Path object. Got:\n{rendered_output}"

        # MUST NOT contain parent directory
        assert "src/utils/" not in rendered_output, (
            f"Path object should extract basename only. "
            f"Found 'src/utils/' in output:\n{rendered_output}"
        )
