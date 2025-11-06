"""Tests for Story 0: Test Repository Creation for Diff-Based Temporal Validation.

This test suite validates that the test repository has the correct structure,
commit history, and file changes for diff-based temporal indexing validation.
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Tuple



TEST_REPO_PATH = Path("/tmp/cidx-test-repo")


class TestRepositoryStructure:
    """Test suite for repository structure validation (AC 1-4)."""

    def test_repository_exists(self) -> None:
        """AC 1: Repository created at /tmp/cidx-test-repo/."""
        assert TEST_REPO_PATH.exists(), "Repository directory does not exist"
        assert TEST_REPO_PATH.is_dir(), "Repository path is not a directory"

    def test_git_initialized(self) -> None:
        """AC 4: .git directory initialized."""
        git_dir = TEST_REPO_PATH / ".git"
        assert git_dir.exists(), ".git directory does not exist"
        assert git_dir.is_dir(), ".git directory is not a directory"

    def test_file_count(self) -> None:
        """AC 2: Contains exactly 12 files in specified structure."""
        # Get all files excluding .git directory
        files = list(TEST_REPO_PATH.rglob("*"))
        files = [f for f in files if f.is_file() and ".git" not in str(f)]

        assert len(files) == 12, f"Expected 12 files, found {len(files)}: {files}"

    def test_file_structure(self) -> None:
        """AC 2: Files exist in correct directory structure."""
        expected_files = [
            "src/auth.py",
            "src/database.py",
            "src/api.py",
            "src/utils.py",
            "src/config.py",
            "tests/test_auth.py",
            "tests/test_database.py",
            "tests/test_api.py",
            "README.md",  # Root level
            "docs/CHANGELOG.md",
            "docs/API.md",
            ".gitignore",
        ]

        for file_path in expected_files:
            full_path = TEST_REPO_PATH / file_path
            assert full_path.exists(), f"Expected file does not exist: {file_path}"
            assert full_path.is_file(), f"Path is not a file: {file_path}"

    def test_files_have_content(self) -> None:
        """AC 3: All files have realistic code content."""
        # Check that each Python file has actual code (not empty)
        python_files = list(TEST_REPO_PATH.rglob("*.py"))
        python_files = [f for f in python_files if ".git" not in str(f)]

        assert len(python_files) > 0, "No Python files found"

        for py_file in python_files:
            content = py_file.read_text()
            assert len(content) > 0, f"File is empty: {py_file}"
            # Basic check for Python syntax (has def or class or import)
            has_code = any(
                keyword in content
                for keyword in ["def ", "class ", "import ", "from "]
            )
            assert has_code, f"File lacks realistic Python content: {py_file}"


class TestCommitHistory:
    """Test suite for commit history validation (AC 5-8)."""

    @staticmethod
    def get_commits() -> List[Dict[str, str]]:
        """Get list of all commits with metadata."""
        result = subprocess.run(
            ["git", "log", "--format=%H|%ad|%s", "--date=iso"],
            cwd=TEST_REPO_PATH,
            capture_output=True,
            text=True,
            check=True,
        )

        commits = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            hash_val, date_str, message = line.split("|", 2)
            commits.append({
                "hash": hash_val,
                "date": date_str,
                "message": message,
            })

        return list(reversed(commits))  # Return in chronological order

    def test_commit_count(self) -> None:
        """AC 5: Exactly 12 commits in chronological order."""
        commits = self.get_commits()
        assert len(commits) == 12, f"Expected 12 commits, found {len(commits)}"

    def test_commit_dates(self) -> None:
        """AC 6: Commit dates match specification (Nov 1-4, 2025)."""
        commits = self.get_commits()
        expected_dates = [
            "2025-11-01 10:00:00", "2025-11-01 14:00:00", "2025-11-01 18:00:00",
            "2025-11-02 10:00:00", "2025-11-02 14:00:00", "2025-11-02 18:00:00",
            "2025-11-03 10:00:00", "2025-11-03 14:00:00", "2025-11-03 16:00:00",
            "2025-11-03 18:00:00", "2025-11-04 10:00:00", "2025-11-04 14:00:00",
        ]
        for i, (commit, expected_date) in enumerate(zip(commits, expected_dates)):
            commit_date = commit["date"][:19]
            assert commit_date == expected_date, f"Commit {i+1} date mismatch"

    def test_commit_messages(self) -> None:
        """AC 7: Commit messages are descriptive."""
        commits = self.get_commits()
        expected_messages = [
            "Initial project setup", "Add API endpoints", "Add configuration system",
            "Add utility functions", "Add test suite", "Refactor authentication",
            "Add API tests", "Delete old database code", "Rename db_new to database",
            "Add documentation", "Binary file addition", "Large refactoring",
        ]
        for i, (commit, expected_msg) in enumerate(zip(commits, expected_messages)):
            assert commit["message"] == expected_msg, f"Commit {i+1} message mismatch"


class TestFileChanges:
    """Test suite for file changes validation (AC 9-14)."""

    @staticmethod
    def get_commit_changes(commit_index: int) -> Tuple[List[str], List[str], List[str], List[Tuple[str, str]]]:
        """Get file changes for a specific commit (1-indexed)."""
        commits = TestCommitHistory.get_commits()
        commit_hash = commits[commit_index - 1]["hash"]
        result = subprocess.run(
            ["git", "show", "--name-status", "--format=", commit_hash],
            cwd=TEST_REPO_PATH, capture_output=True, text=True, check=True,
        )
        added, modified, deleted, renamed = [], [], [], []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            status = parts[0]
            if status == "A":
                added.append(parts[1])
            elif status == "M":
                modified.append(parts[1])
            elif status == "D":
                deleted.append(parts[1])
            elif status.startswith("R"):
                renamed.append((parts[1], parts[2]))
        return added, modified, deleted, renamed

    def test_commit_8_deletion(self) -> None:
        """AC 11: Commit 8 deletes database.py."""
        added, modified, deleted, renamed = self.get_commit_changes(8)
        assert "src/database.py" in deleted, "Commit 8 should delete src/database.py"

    def test_commit_9_rename(self) -> None:
        """AC 12: Commit 9 renames db_new.py to database.py."""
        added, modified, deleted, renamed = self.get_commit_changes(9)
        assert len(renamed) == 1, "Commit 9 should have exactly 1 rename"
        old_name, new_name = renamed[0]
        assert old_name == "src/db_new.py" and new_name == "src/database.py"

    def test_commit_11_binary_file(self) -> None:
        """AC 13: Commit 11 adds binary file."""
        added, modified, deleted, renamed = self.get_commit_changes(11)
        assert "docs/architecture.png" in added, "Commit 11 should add architecture.png"

    def test_commit_12_large_diff(self) -> None:
        """AC 14: Commit 12 has large diff."""
        commits = TestCommitHistory.get_commits()
        result = subprocess.run(
            ["git", "show", "--format=", "--numstat", commits[11]["hash"]],
            cwd=TEST_REPO_PATH, capture_output=True, text=True, check=True,
        )
        changes = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 3 and parts[0] != "-":
                changes[parts[2]] = int(parts[0]) + int(parts[1])
        assert changes.get("src/api.py", 0) >= 200, "api.py should have 200+ line changes"
        assert changes.get("src/auth.py", 0) >= 150, "auth.py should have 150+ line changes"
