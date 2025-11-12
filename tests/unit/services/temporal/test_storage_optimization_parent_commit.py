"""Tests for temporal storage optimization - parent commit tracking.

This tests the first step: tracking parent commit hash for deleted files
so we can reconstruct content from git on query.
"""

import pytest
import subprocess
from src.code_indexer.services.temporal.temporal_diff_scanner import (
    DiffInfo,
    TemporalDiffScanner,
)


class TestParentCommitTracking:
    """Test that parent commits are tracked for deleted files."""

    def test_diff_info_has_parent_commit_field(self):
        """Test that DiffInfo dataclass has parent_commit_hash field."""
        # This should pass after we update the DiffInfo model
        diff = DiffInfo(
            file_path="test.py",
            diff_type="deleted",
            commit_hash="abc123",
            diff_content="-content",
            parent_commit_hash="parent123",  # NEW FIELD
        )

        assert diff.parent_commit_hash == "parent123"

    @pytest.fixture
    def temp_repo(self, tmp_path):
        """Create a temporary git repository with file additions and deletions."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
        )

        # Commit 1: Add file
        test_file = repo_dir / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "test.py"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test.py"],
            cwd=repo_dir,
            check=True,
        )

        # Get first commit hash
        first_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Commit 2: Delete file
        test_file.unlink()
        subprocess.run(["git", "add", "test.py"], cwd=repo_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Delete test.py"], cwd=repo_dir, check=True
        )

        # Get deletion commit hash
        delete_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        return {
            "repo_dir": repo_dir,
            "first_commit": first_commit,
            "delete_commit": delete_commit,
        }

    def test_deleted_file_tracks_parent_commit(self, temp_repo):
        """Test that deleted files track their parent commit hash."""
        scanner = TemporalDiffScanner(temp_repo["repo_dir"])

        # Get diffs for deletion commit
        diffs = scanner.get_diffs_for_commit(temp_repo["delete_commit"])

        # Find the deleted file diff
        deleted_diff = [d for d in diffs if d.diff_type == "deleted"][0]

        # Verify parent commit is tracked
        assert (
            deleted_diff.parent_commit_hash == temp_repo["first_commit"]
        ), "Deleted file should track parent commit hash"
