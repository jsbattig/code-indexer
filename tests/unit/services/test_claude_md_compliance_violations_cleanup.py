"""
FAILING TESTS: CLAUDE.md Violations Cleanup Requirements

These tests validate that ALL CLAUDE.md violations identified by spec-compliance-auditor
have been completely eliminated from the slot-based file tracking implementation.

CRITICAL: These tests should FAIL initially and PASS after complete cleanup.
"""

import unittest
from pathlib import Path


class TestClaudeMdComplianceViolationsCleanup(unittest.TestCase):
    """Test complete elimination of CLAUDE.md violations."""

    def test_consolidated_file_tracker_completely_eliminated(self):
        """FAILING TEST: ConsolidatedFileTracker should not exist anywhere in codebase."""
        # Test that ConsolidatedFileTracker class file doesn't exist
        tracker_file = Path("src/code_indexer/services/consolidated_file_tracker.py")
        self.assertFalse(
            tracker_file.exists(),
            f"ConsolidatedFileTracker class file still exists at {tracker_file}. "
            f"CLAUDE.md violation: Must be completely eliminated.",
        )

    def test_no_consolidated_file_tracker_imports(self):
        """FAILING TEST: No imports of ConsolidatedFileTracker should remain."""
        import subprocess
        import os

        # Change to project root
        project_root = Path(__file__).parent.parent.parent.parent
        os.chdir(project_root)

        # Search for any ConsolidatedFileTracker imports
        result = subprocess.run(
            ["grep", "-r", "from.*consolidated_file_tracker import", "src/"],
            capture_output=True,
            text=True,
        )

        self.assertEqual(
            result.returncode,
            1,  # grep returns 1 when no matches found
            f"ConsolidatedFileTracker imports still exist:\n{result.stdout}\n"
            f"CLAUDE.md violation: All ConsolidatedFileTracker imports must be eliminated.",
        )

    def test_no_backward_compatibility_fallback_code(self):
        """FAILING TEST: No backward compatibility or fallback code should remain."""
        import subprocess
        import os

        project_root = Path(__file__).parent.parent.parent.parent
        os.chdir(project_root)

        # Search for fallback/backward compatibility patterns
        fallback_patterns = [
            "backward compatibility",
            "Legacy tracker",
            "legacy approach",
            "fallback method",
            "just in case",
            "ConsolidatedFileTracker.*Legacy",
        ]

        violations = []
        for pattern in fallback_patterns:
            result = subprocess.run(
                [
                    "grep",
                    "-r",
                    "-i",
                    "--exclude-dir=__pycache__",
                    "--include=*.py",
                    pattern,
                    "src/",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:  # Found matches
                violations.append(f"Pattern '{pattern}':\n{result.stdout}")

        self.assertEqual(
            len(violations),
            0,
            "Fallback/backward compatibility code still exists:\n"
            + "\n".join(violations)
            + "\n"
            "CLAUDE.md violation: All fallback mechanisms must be eliminated.",
        )

    def test_unified_file_status_enum_only(self):
        """FAILING TEST: Only one FileStatus enum should exist."""
        # Check that consolidated_file_tracker.py doesn't exist (so its FileStatus is gone)
        tracker_file = Path("src/code_indexer/services/consolidated_file_tracker.py")
        self.assertFalse(
            tracker_file.exists(),
            "ConsolidatedFileTracker.FileStatus enum still exists (file not deleted)",
        )

        # Verify CleanSlotTracker.FileStatus exists as the single source
        clean_tracker_file = Path("src/code_indexer/services/clean_slot_tracker.py")
        self.assertTrue(
            clean_tracker_file.exists(),
            "CleanSlotTracker.FileStatus enum should remain as single source",
        )

    def test_high_throughput_processor_uses_only_clean_slot_tracker(self):
        """FAILING TEST: HighThroughputProcessor should use only CleanSlotTracker."""
        try:
            # Import should work after cleanup
            from code_indexer.services.high_throughput_processor import (
                HighThroughputProcessor,
            )

            # Check the processor only references CleanSlotTracker in processing methods
            import inspect

            # NEW ARCHITECTURE: Check process_files_high_throughput method instead of __init__
            source = inspect.getsource(
                HighThroughputProcessor.process_files_high_throughput
            )

            # Should NOT reference ConsolidatedFileTracker anywhere
            self.assertNotIn(
                "ConsolidatedFileTracker",
                source,
                "HighThroughputProcessor.process_files_high_throughput still references ConsolidatedFileTracker. "
                "CLAUDE.md violation: Must use only CleanSlotTracker.",
            )

            # Should reference CleanSlotTracker (created locally in method)
            self.assertIn(
                "CleanSlotTracker",
                source,
                "HighThroughputProcessor.process_files_high_throughput should use CleanSlotTracker for local slot tracking.",
            )

            # Verify proper local tracker creation patterns
            self.assertIn(
                "local_slot_tracker = CleanSlotTracker",
                source,
                "Should create local slot tracker in processing method.",
            )

            # Verify hash phase also uses CleanSlotTracker
            self.assertIn(
                "hash_slot_tracker = slot_tracker or CleanSlotTracker",
                source,
                "Hash phase should use CleanSlotTracker for parallel processing.",
            )

        except ImportError as e:
            self.fail(f"Import failed after cleanup: {e}")

    def test_async_display_worker_eliminated(self):
        """PASSING TEST: AsyncDisplayWorker should be completely eliminated."""
        # Check that AsyncDisplayWorker file doesn't exist
        async_worker_file = Path("src/code_indexer/progress/async_display_worker.py")
        self.assertFalse(
            async_worker_file.exists(),
            "AsyncDisplayWorker file still exists. CLAUDE.md violation: Must be completely eliminated.",
        )

        # Check that import fails as expected
        with self.assertRaises(ImportError):
            __import__(
                "code_indexer.progress.async_display_worker",
                fromlist=["AsyncDisplayWorker"],
            )

    def test_no_dual_tracker_system_architecture(self):
        """FAILING TEST: No dual tracker system should exist."""
        import subprocess
        import os

        project_root = Path(__file__).parent.parent.parent.parent
        os.chdir(project_root)

        # Search for dual system patterns
        dual_system_patterns = [
            "self.file_tracker.*legacy",
            "self.consolidated_tracker",
            "dual.*tracker",
            "both.*tracker",
        ]

        violations = []
        for pattern in dual_system_patterns:
            result = subprocess.run(
                ["grep", "-r", "-i", pattern, "src/"], capture_output=True, text=True
            )
            if result.returncode == 0:
                violations.append(f"Dual system pattern '{pattern}':\n{result.stdout}")

        self.assertEqual(
            len(violations),
            0,
            "Dual tracker system still exists:\n" + "\n".join(violations) + "\n"
            "CLAUDE.md violation: Must use single SlotBasedFileTracker only.",
        )

    def test_tests_expect_only_slot_based_architecture(self):
        """FAILING TEST: All tests should expect only slot-based architecture."""
        import subprocess
        import os

        project_root = Path(__file__).parent.parent.parent.parent
        os.chdir(project_root)

        # Find test files that still import ConsolidatedFileTracker
        result = subprocess.run(
            ["grep", "-r", "ConsolidatedFileTracker", "tests/"],
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            # Filter out this test file itself and allow documentation/comments
            violations = []
            for line in result.stdout.split("\n"):
                if (
                    line
                    and "test_claude_md_compliance_violations_cleanup.py" not in line
                ):
                    # Allow references in comments/docstrings but not imports or usage
                    if ("import" in line and "ConsolidatedFileTracker" in line) or (
                        "ConsolidatedFileTracker(" in line
                    ):
                        violations.append(line)

            if violations:
                self.fail(
                    "Tests still use ConsolidatedFileTracker:\n"
                    + "\n".join(violations)
                    + "\n"
                    "CLAUDE.md violation: Tests must expect only slot-based architecture."
                )


if __name__ == "__main__":
    unittest.main()
