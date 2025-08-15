"""
Unit tests for working directory awareness in reconcile functionality.

These tests validate the core components needed for detecting and handling
working directory changes during reconcile operations.
"""

import subprocess
import tempfile
import time
from pathlib import Path
import pytest

from src.code_indexer.services.branch_aware_indexer import BranchAwareIndexer


class TestWorkingDirectoryDetection:
    """Test detection of working directory modifications."""

    @pytest.fixture
    def git_repo_with_file(self):
        """Create a git repository with a committed file."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir)

            # Initialize git repo
            subprocess.run(
                ["git", "init"], cwd=repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
            )

            # Create and commit initial file
            test_file = repo_dir / "test_file.py"
            test_file.write_text(
                "def original_function():\n    return 'original content'\n"
            )

            subprocess.run(["git", "add", "test_file.py"], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True
            )

            yield repo_dir, test_file

    def test_file_differs_from_committed_version_when_modified(
        self, git_repo_with_file
    ):
        """Test detection of working directory modifications."""
        repo_dir, test_file = git_repo_with_file

        # Create mock config and indexer
        config = type("MockConfig", (), {"codebase_dir": str(repo_dir)})()
        indexer = BranchAwareIndexer(None, None, None, config)

        # Initially, file should match committed version
        assert not indexer._file_differs_from_committed_version("test_file.py")

        # Modify file without committing
        test_file.write_text(
            "def modified_function():\n    return 'modified content'\n"
        )

        # Now file should differ from committed version
        assert indexer._file_differs_from_committed_version("test_file.py")

    def test_file_matches_committed_version_when_unchanged(self, git_repo_with_file):
        """Test detection when file matches committed state."""
        repo_dir, test_file = git_repo_with_file

        config = type("MockConfig", (), {"codebase_dir": str(repo_dir)})()
        indexer = BranchAwareIndexer(None, None, None, config)

        # File matches committed version
        assert not indexer._file_differs_from_committed_version("test_file.py")

        # Even after reading/touching file (same content)
        content = test_file.read_text()
        test_file.write_text(content)  # Write same content

        assert not indexer._file_differs_from_committed_version("test_file.py")

    def test_file_differs_after_git_restore(self, git_repo_with_file):
        """Test detection after git restore."""
        repo_dir, test_file = git_repo_with_file

        config = type("MockConfig", (), {"codebase_dir": str(repo_dir)})()
        indexer = BranchAwareIndexer(None, None, None, config)

        # Modify file
        test_file.write_text(
            "def modified_function():\n    return 'modified content'\n"
        )
        assert indexer._file_differs_from_committed_version("test_file.py")

        # Restore file to committed state
        subprocess.run(
            ["git", "checkout", "--", "test_file.py"], cwd=repo_dir, check=True
        )

        # File should now match committed version
        assert not indexer._file_differs_from_committed_version("test_file.py")


class TestContentIDGeneration:
    """Test content ID generation for different file states."""

    @pytest.fixture
    def indexer_with_repo(self):
        """Create indexer with git repository."""
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_dir = Path(temp_dir)

            # Setup git repo
            subprocess.run(
                ["git", "init"], cwd=repo_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
            )

            # Create and commit file
            test_file = repo_dir / "test_file.py"
            test_file.write_text("original content")
            subprocess.run(["git", "add", "test_file.py"], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-m", "Initial"], cwd=repo_dir, check=True)

            config = type("MockConfig", (), {"codebase_dir": str(repo_dir)})()
            indexer = BranchAwareIndexer(None, None, None, config)

            yield indexer, repo_dir, test_file

    def test_content_id_for_committed_file(self, indexer_with_repo):
        """Test content ID generation for unchanged files."""
        indexer, repo_dir, test_file = indexer_with_repo

        content_id = indexer._get_effective_content_id_for_reconcile("test_file.py")

        # Should be commit-based format (not working_dir format)
        assert "working_dir_" not in content_id
        assert "test_file.py:" in content_id
        assert len(content_id.split(":")) >= 2  # At least file_path:commit_hash

    def test_content_id_for_working_dir_changes(self, indexer_with_repo):
        """Test content ID generation for modified files."""
        indexer, repo_dir, test_file = indexer_with_repo

        # Modify file
        test_file.write_text("modified content")
        time.sleep(0.1)  # Ensure different mtime

        content_id = indexer._get_effective_content_id_for_reconcile("test_file.py")

        # Should be working_dir-based format with consistent underscore formatting
        assert "working_dir_" in content_id
        assert "test_file.py:working_dir_" in content_id
        assert len(content_id.split(":")) == 2  # file_path:working_dir_timestamp_size

    def test_content_id_stability(self, indexer_with_repo):
        """Test that content IDs are stable for same state."""
        indexer, repo_dir, test_file = indexer_with_repo

        # Generate ID twice for same committed state
        id1 = indexer._get_effective_content_id_for_reconcile("test_file.py")
        id2 = indexer._get_effective_content_id_for_reconcile("test_file.py")
        assert id1 == id2

        # Generate ID twice for same working dir state
        test_file.write_text("modified content")
        id3 = indexer._get_effective_content_id_for_reconcile("test_file.py")
        id4 = indexer._get_effective_content_id_for_reconcile("test_file.py")
        assert id3 == id4

        # But committed state should differ from working dir state
        assert id1 != id3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
