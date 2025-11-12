"""Unit tests for TemporalDiffScanner - Diff-based temporal indexing.

Following strict TDD methodology - one test at a time.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the classes we're testing (will fail initially - TDD)
from src.code_indexer.services.temporal.temporal_diff_scanner import (
    DiffInfo,
    TemporalDiffScanner,
)


class TestDiffInfo:
    """Test suite for DiffInfo dataclass."""

    def test_diff_info_dataclass_structure(self):
        """Test DiffInfo dataclass has required fields."""
        diff_info = DiffInfo(
            file_path="src/test.py",
            diff_type="modified",
            commit_hash="abc123",
            diff_content="@@ -1,3 +1,3 @@\n-old line\n+new line",
            old_path="",
        )

        assert diff_info.file_path == "src/test.py"
        assert diff_info.diff_type == "modified"
        assert diff_info.commit_hash == "abc123"
        assert diff_info.diff_content == "@@ -1,3 +1,3 @@\n-old line\n+new line"
        assert diff_info.old_path == ""


class TestTemporalDiffScanner:
    """Test suite for TemporalDiffScanner."""

    def test_temporal_diff_scanner_init(self):
        """Test TemporalDiffScanner initialization."""
        test_repo_path = Path("/tmp/cidx-test-repo")
        scanner = TemporalDiffScanner(test_repo_path)
        assert scanner.codebase_dir == test_repo_path
        assert isinstance(scanner.codebase_dir, Path)

    @patch("subprocess.run")
    def test_get_diffs_for_added_file(self, mock_run):
        """Test getting diffs for a commit with an added file."""
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git show --name-status to return an added file
        mock_run.side_effect = [
            # First call: get changed files
            MagicMock(
                stdout="A\tsrc/new_file.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get full content of added file
            MagicMock(
                stdout="def new_function():\n    return 42\n",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash for the file
            MagicMock(
                stdout="1234567890abcdef",
                stderr="",
                returncode=0,
            ),
        ]

        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 1
        assert diffs[0].file_path == "src/new_file.py"
        assert diffs[0].diff_type == "added"
        assert diffs[0].commit_hash == "abc123"
        assert "def new_function" in diffs[0].diff_content
        assert diffs[0].old_path == ""

        # Verify git was called correctly (including blob hash call)
        assert mock_run.call_count == 3
        mock_run.assert_any_call(
            ["git", "show", "--name-status", "--format=", "abc123"],
            cwd=Path("/tmp/test-repo"),
            capture_output=True,
            text=True,
            errors="replace",
        )

    @patch("subprocess.run")
    def test_get_diffs_for_deleted_file(self, mock_run):
        """Test getting diffs for a commit with a deleted file."""
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands for deleted file
        mock_run.side_effect = [
            # First call: get changed files
            MagicMock(
                stdout="D\tsrc/old_file.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get content from parent commit
            MagicMock(
                stdout="def old_function():\n    return 'deleted'\n",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash from parent commit
            MagicMock(
                stdout="abcdef1234567890",
                stderr="",
                returncode=0,
            ),
            # Fourth call: get parent commit hash
            MagicMock(
                stdout="parent123abc",
                stderr="",
                returncode=0,
            ),
        ]

        diffs = scanner.get_diffs_for_commit("def456")

        assert len(diffs) == 1
        assert diffs[0].file_path == "src/old_file.py"
        assert diffs[0].diff_type == "deleted"
        assert diffs[0].commit_hash == "def456"
        assert "old_function" in diffs[0].diff_content
        assert diffs[0].old_path == ""
        assert diffs[0].parent_commit_hash == "parent123abc"

    @patch("subprocess.run")
    def test_get_diffs_for_modified_file(self, mock_run):
        """Test getting diffs for a commit with a modified file."""
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands
        mock_run.side_effect = [
            # First call: get changed files
            MagicMock(
                stdout="M\tsrc/modified.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get unified diff
            MagicMock(
                stdout="""@@ -10,5 +10,8 @@ def login(username, password):
-    if username == "admin" and password == "admin":
-        return True
+    token = create_token(username)
+    if token:
+        return token
     return False""",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash for the file
            MagicMock(
                stdout="fedcba0987654321",
                stderr="",
                returncode=0,
            ),
        ]

        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 1
        assert diffs[0].file_path == "src/modified.py"
        assert diffs[0].diff_type == "modified"
        assert diffs[0].commit_hash == "abc123"
        assert "@@ -10,5 +10,8 @@" in diffs[0].diff_content
        assert "-    if username" in diffs[0].diff_content
        assert "+    token = create_token" in diffs[0].diff_content
        assert diffs[0].old_path == ""

    @patch("subprocess.run")
    def test_get_diffs_for_renamed_file(self, mock_run):
        """Test getting diffs for a commit with a renamed file."""
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands with rename
        mock_run.side_effect = [
            # First call: get changed files with rename
            MagicMock(
                stdout="R100\tsrc/old_name.py\tsrc/new_name.py\n",
                stderr="",
                returncode=0,
            ),
        ]

        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 1
        assert diffs[0].file_path == "src/new_name.py"
        assert diffs[0].diff_type == "renamed"
        assert diffs[0].commit_hash == "abc123"
        assert "renamed from src/old_name.py to src/new_name.py" in diffs[0].diff_content
        assert diffs[0].old_path == "src/old_name.py"

    @patch("subprocess.run")
    def test_get_diffs_with_whitespace_only_lines(self, mock_run):
        """Test getting diffs with whitespace-only lines in git output.

        Git may produce output with empty lines or whitespace-only lines.
        These should be skipped without crashing.
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands with whitespace-only lines
        mock_run.side_effect = [
            # First call: get changed files with whitespace lines
            MagicMock(
                stdout="A\tsrc/new_file.py\n\n   \t\n\nM\tsrc/modified.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get content for added file
            MagicMock(
                stdout="def new_function():\n    return 42\n",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash for added file
            MagicMock(
                stdout="1234567890abcdef",
                stderr="",
                returncode=0,
            ),
            # Fourth call: get diff for modified file
            MagicMock(
                stdout="@@ -1,3 +1,3 @@\n-old line\n+new line",
                stderr="",
                returncode=0,
            ),
            # Fifth call: get blob hash for modified file
            MagicMock(
                stdout="fedcba0987654321",
                stderr="",
                returncode=0,
            ),
        ]

        # Should not crash with IndexError
        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 2
        assert diffs[0].file_path == "src/new_file.py"
        assert diffs[1].file_path == "src/modified.py"

    @patch("subprocess.run")
    def test_get_diffs_with_malformed_status_line(self, mock_run):
        """Test getting diffs with malformed git status line.

        Git output may contain corrupted lines with only status and no path.
        These should be skipped without crashing.
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands with malformed line (status only, no tab/path)
        mock_run.side_effect = [
            # First call: get changed files with malformed line
            MagicMock(
                stdout="A\tsrc/new_file.py\nM\nA\tsrc/another_file.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get content for first added file
            MagicMock(
                stdout="def new_function():\n    return 42\n",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash for first added file
            MagicMock(
                stdout="1234567890abcdef",
                stderr="",
                returncode=0,
            ),
            # Fourth call: get content for second added file
            MagicMock(
                stdout="def another_function():\n    return 24\n",
                stderr="",
                returncode=0,
            ),
            # Fifth call: get blob hash for second added file
            MagicMock(
                stdout="fedcba0987654321",
                stderr="",
                returncode=0,
            ),
        ]

        # Should not crash with IndexError
        diffs = scanner.get_diffs_for_commit("abc123")

        # Should get 2 valid diffs (malformed line skipped)
        assert len(diffs) == 2
        assert diffs[0].file_path == "src/new_file.py"
        assert diffs[1].file_path == "src/another_file.py"

    @patch("subprocess.run")
    def test_get_diffs_with_malformed_rename_line(self, mock_run):
        """Test getting diffs with malformed rename line.

        Git rename output should always have 3 parts (status, old_path, new_path).
        If it has only 2 parts, it should be skipped.
        """
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands with malformed rename line (only 2 parts)
        mock_run.side_effect = [
            # First call: get changed files with malformed rename
            MagicMock(
                stdout="R100\tsrc/new_name.py\nA\tsrc/valid_file.py\n",
                stderr="",
                returncode=0,
            ),
            # Second call: get content for added file
            MagicMock(
                stdout="def new_function():\n    return 42\n",
                stderr="",
                returncode=0,
            ),
            # Third call: get blob hash for added file
            MagicMock(
                stdout="1234567890abcdef",
                stderr="",
                returncode=0,
            ),
        ]

        # Should not crash with IndexError
        diffs = scanner.get_diffs_for_commit("abc123")

        # Should get 1 valid diff (malformed rename skipped)
        assert len(diffs) == 1
        assert diffs[0].file_path == "src/valid_file.py"

    @patch("subprocess.run")
    def test_get_diffs_for_binary_file_added(self, mock_run):
        """Test getting diffs for a commit with a binary file addition."""
        scanner = TemporalDiffScanner(Path("/tmp/test-repo"))

        # Mock git commands with binary file
        mock_run.side_effect = [
            # First call: get changed files
            MagicMock(
                stdout="A\tarchitecture.png\n",
                stderr="",
                returncode=0,
            ),
            # Second call: attempt to read content - binary returns error
            MagicMock(
                stdout="",
                stderr="binary file",
                returncode=0,
            ),
        ]

        diffs = scanner.get_diffs_for_commit("abc123")

        assert len(diffs) == 1
        assert diffs[0].file_path == "architecture.png"
        assert diffs[0].diff_type == "binary"
        assert diffs[0].commit_hash == "abc123"
        assert "Binary file added" in diffs[0].diff_content
        assert diffs[0].old_path == ""