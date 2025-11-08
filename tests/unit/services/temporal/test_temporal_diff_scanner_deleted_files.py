"""Unit tests for TemporalDiffScanner deleted files git call optimization.

Issue #1: Multiple Git Calls for Deleted Files - CRITICAL

Current behavior (BROKEN):
- Commit with 2 deleted files: 3 git calls (1 git show + 2 git rev-parse)
- Commit with 10 deleted files: 11 git calls (1 git show + 10 git rev-parse)

Required behavior:
- Calculate parent commit ONCE before parsing diffs
- Pass parent_commit_hash to _finalize_diff() as parameter
- Result: Truly 1-2 git calls per commit (1 show + 1 rev-parse if any deletes)

This test suite validates the fix for N+1 git calls when processing deleted files.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.code_indexer.services.temporal.temporal_diff_scanner import (
    TemporalDiffScanner,
)


class TestTemporalDiffScannerDeletedFiles:
    """Test suite for deleted files git call optimization."""

    @patch("subprocess.run")
    def test_two_deleted_files_should_use_2_git_calls_not_3(self, mock_run):
        """FAILING TEST: 2 deleted files should use 2 git calls, NOT 3 (N+1 problem).

        Current behavior (BROKEN): 3 git calls
        - 1 call: git show --full-index commit
        - 1 call: git rev-parse commit^ (for first deleted file)
        - 1 call: git rev-parse commit^ (for second deleted file) <-- REDUNDANT!

        Expected behavior (AFTER FIX): 2 git calls
        - 1 call: git show --full-index commit
        - 1 call: git rev-parse commit^ (once before parsing, reused for both files)
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock unified diff output with 2 deleted files
        unified_diff_output = """diff --git a/src/deleted1.py b/src/deleted1.py
deleted file mode 100644
index blob_hash_1..0000000000000000000000000000000000000000
--- a/src/deleted1.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def deleted_function_1():
-    pass
diff --git a/src/deleted2.py b/src/deleted2.py
deleted file mode 100644
index blob_hash_2..0000000000000000000000000000000000000000
--- a/src/deleted2.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def deleted_function_2():
-    pass
"""

        # Mock responses for git calls
        # Current implementation will make 3 calls (1 show + 2 rev-parse)
        mock_responses = [
            # Call 1: git show
            MagicMock(stdout=unified_diff_output, stderr="", returncode=0),
            # Call 2: git rev-parse commit^ (for first deleted file)
            MagicMock(stdout="parent_commit_xyz\n", stderr="", returncode=0),
            # Call 3: git rev-parse commit^ (for second deleted file - REDUNDANT!)
            MagicMock(stdout="parent_commit_xyz\n", stderr="", returncode=0),
        ]
        mock_run.side_effect = mock_responses

        diffs = scanner.get_diffs_for_commit("def456")

        # Verify results
        assert len(diffs) == 2
        assert diffs[0].file_path == "src/deleted1.py"
        assert diffs[0].diff_type == "deleted"
        assert diffs[0].blob_hash == "blob_hash_1"
        assert diffs[0].parent_commit_hash == "parent_commit_xyz"

        assert diffs[1].file_path == "src/deleted2.py"
        assert diffs[1].diff_type == "deleted"
        assert diffs[1].blob_hash == "blob_hash_2"
        assert diffs[1].parent_commit_hash == "parent_commit_xyz"

        # CRITICAL: Should be 2 calls, NOT 3 (this will FAIL with current implementation)
        assert mock_run.call_count == 2, (
            f"Expected 2 git calls (1 show + 1 rev-parse), "
            f"but got {mock_run.call_count} calls. "
            f"This is the N+1 problem - each deleted file triggers a separate git rev-parse."
        )

        # Verify call 1: git show
        assert mock_run.call_args_list[0] == call(
            ["git", "show", "--full-index", "--format=", "def456"],
            cwd=Path("/tmp/test-repo"),
            capture_output=True,
            text=True,
            errors="replace",
        )

        # Verify call 2: git rev-parse commit^ (ONLY ONCE)
        assert mock_run.call_args_list[1] == call(
            ["git", "rev-parse", "def456^"],
            cwd=Path("/tmp/test-repo"),
            capture_output=True,
            text=True,
            errors="replace",
        )
