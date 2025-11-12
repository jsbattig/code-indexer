"""Unit tests for TemporalDiffScanner optimization - Single git call per commit.

Story #471: Optimized Commit Retrieval - Single Git Call Per Commit

This test suite validates the performance optimization that reduces git overhead
from 330ms (10-12 git calls) to 33ms (1 git call) per commit using unified diff format.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

from src.code_indexer.services.temporal.temporal_diff_scanner import (
    TemporalDiffScanner,
)


class TestTemporalDiffScannerSingleGitCall:
    """Test suite for single git call optimization."""

    @patch("subprocess.run")
    def test_single_git_call_for_10_files(self, mock_run):
        """Optimized implementation makes only 1 git call for 10 files.

        Optimized behavior:
        - 1 call: git show --full-index commit (unified diff format with all file changes)
        Total: 1 call (vs 21 calls in old implementation)

        The unified diff output from 'git show' contains:
        - All file paths
        - File types (added/deleted/modified/binary/renamed)
        - Blob hashes (from index lines with --full-index flag)
        - Full diff content
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock single git show call with unified diff output
        unified_diff_output = """diff --git a/src/file_0.py b/src/file_0.py
new file mode 100644
index 0000000000000000000000000000000000000000..blob0000000000000000000000000000000000000000
--- /dev/null
+++ b/src/file_0.py
@@ -0,0 +1,2 @@
+def function_0():
+    return 0
diff --git a/src/file_1.py b/src/file_1.py
new file mode 100644
index 0000000000000000000000000000000000000001..blob0000000000000000000000000000000000000001
--- /dev/null
+++ b/src/file_1.py
@@ -0,0 +1,2 @@
+def function_1():
+    return 1
diff --git a/src/file_2.py b/src/file_2.py
new file mode 100644
index 0000000000000000000000000000000000000002..blob0000000000000000000000000000000000000002
--- /dev/null
+++ b/src/file_2.py
@@ -0,0 +1,2 @@
+def function_2():
+    return 2
diff --git a/src/file_3.py b/src/file_3.py
new file mode 100644
index 0000000000000000000000000000000000000003..blob0000000000000000000000000000000000000003
--- /dev/null
+++ b/src/file_3.py
@@ -0,0 +1,2 @@
+def function_3():
+    return 3
diff --git a/src/file_4.py b/src/file_4.py
new file mode 100644
index 0000000000000000000000000000000000000004..blob0000000000000000000000000000000000000004
--- /dev/null
+++ b/src/file_4.py
@@ -0,0 +1,2 @@
+def function_4():
+    return 4
diff --git a/src/file_5.py b/src/file_5.py
new file mode 100644
index 0000000000000000000000000000000000000005..blob0000000000000000000000000000000000000005
--- /dev/null
+++ b/src/file_5.py
@@ -0,0 +1,2 @@
+def function_5():
+    return 5
diff --git a/src/file_6.py b/src/file_6.py
new file mode 100644
index 0000000000000000000000000000000000000006..blob0000000000000000000000000000000000000006
--- /dev/null
+++ b/src/file_6.py
@@ -0,0 +1,2 @@
+def function_6():
+    return 6
diff --git a/src/file_7.py b/src/file_7.py
new file mode 100644
index 0000000000000000000000000000000000000007..blob0000000000000000000000000000000000000007
--- /dev/null
+++ b/src/file_7.py
@@ -0,0 +1,2 @@
+def function_7():
+    return 7
diff --git a/src/file_8.py b/src/file_8.py
new file mode 100644
index 0000000000000000000000000000000000000008..blob0000000000000000000000000000000000000008
--- /dev/null
+++ b/src/file_8.py
@@ -0,0 +1,2 @@
+def function_8():
+    return 8
diff --git a/src/file_9.py b/src/file_9.py
new file mode 100644
index 0000000000000000000000000000000000000009..blob0000000000000000000000000000000000000009
--- /dev/null
+++ b/src/file_9.py
@@ -0,0 +1,2 @@
+def function_9():
+    return 9
"""

        mock_run.return_value = MagicMock(
            stdout=unified_diff_output,
            stderr="",
            returncode=0,
        )

        diffs = scanner.get_diffs_for_commit("abc123")

        # Verify results
        assert len(diffs) == 10
        for i in range(10):
            assert diffs[i].file_path == f"src/file_{i}.py"
            assert diffs[i].diff_type == "added"
            assert diffs[i].blob_hash == f"blob{i:040d}"
            assert f"def function_{i}()" in diffs[i].diff_content

        # OPTIMIZED BEHAVIOR: Only 1 git call
        assert mock_run.call_count == 1

        # Verify it's git show with unified diff format and full-index (with -U5 for 5 lines of context)
        assert mock_run.call_args_list[0] == call(
            ["git", "show", "-U5", "--full-index", "--format=", "abc123"],
            cwd=Path("/tmp/test-repo"),
            capture_output=True,
            text=True,
            errors="replace",
        )
