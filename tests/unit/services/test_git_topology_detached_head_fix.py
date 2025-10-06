"""
Unit tests for GitTopologyService detached HEAD handling.

Tests the fix for the branch change visibility bug where synthetic branch names
like "detached-6a649690" were causing _get_all_tracked_files() to fail.
"""

import pytest
import tempfile
import shutil
import subprocess
from pathlib import Path
from code_indexer.services.git_topology_service import GitTopologyService


class TestGitTopologyDetachedHeadFix:
    """Test suite for detached HEAD branch name handling."""

    @pytest.fixture
    def git_repo(self):
        """Create a temporary git repository for testing."""
        repo_dir = Path(tempfile.mkdtemp(prefix="test_git_topology_"))

        try:
            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                cwd=repo_dir,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_dir, check=True
            )

            # Create and commit test files
            (repo_dir / "file1.txt").write_text("content1")
            (repo_dir / "file2.txt").write_text("content2")
            (repo_dir / "file3.txt").write_text("content3")

            subprocess.run(["git", "add", "."], cwd=repo_dir, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=repo_dir, check=True
            )

            yield repo_dir

        finally:
            shutil.rmtree(repo_dir, ignore_errors=True)

    def test_get_all_tracked_files_with_detached_branch_name(self, git_repo):
        """
        Test that _get_all_tracked_files() works with synthetic detached-* branch names.

        CRITICAL BUG FIX TEST:
        - Synthetic branch names like "detached-6a649690" are not valid git references
        - _get_all_tracked_files() must use "HEAD" instead when branch starts with "detached-"
        - Otherwise git ls-tree fails and returns empty list
        - This causes branch isolation to hide ALL files
        """
        service = GitTopologyService(git_repo)

        # Test with synthetic detached branch name (should use HEAD internally)
        files = service._get_all_tracked_files("detached-abc1234")

        # Should return all tracked files, not empty list
        assert len(files) == 3, f"Expected 3 files, got {len(files)}: {files}"
        assert "file1.txt" in files
        assert "file2.txt" in files
        assert "file3.txt" in files

    def test_get_all_tracked_files_with_normal_branch_name(self, git_repo):
        """
        Test that _get_all_tracked_files() still works with normal branch names.

        Ensures the fix doesn't break normal branch name handling.
        """
        service = GitTopologyService(git_repo)

        # Test with normal branch name (HEAD or master)
        files_head = service._get_all_tracked_files("HEAD")
        files_master = service._get_all_tracked_files("master")

        # Both should return all tracked files
        assert len(files_head) == 3
        assert len(files_master) == 3
        assert set(files_head) == set(files_master)

    def test_analyze_branch_change_with_detached_head(self, git_repo):
        """
        Test that analyze_branch_change() correctly handles detached HEAD state.

        This is the integration test that verifies:
        1. analyze_branch_change() receives synthetic "detached-*" branch name
        2. Calls _get_all_tracked_files() with that synthetic name
        3. _get_all_tracked_files() uses HEAD internally
        4. Returns correct list of files for unchanged_files
        5. Branch isolation receives complete file list
        """
        service = GitTopologyService(git_repo)

        # Create a feature branch
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=git_repo, check=True)
        (git_repo / "file4.txt").write_text("feature content")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Feature"], cwd=git_repo, check=True)

        # Analyze branch change from master to detached HEAD
        analysis = service.analyze_branch_change("master", "detached-abc1234")

        # Should return files that need metadata updates (all files in new branch)
        # Since only file4.txt is different, the others should be in unchanged_files
        assert len(analysis.files_to_update_metadata) > 0, (
            f"Expected unchanged files, got {len(analysis.files_to_update_metadata)}. "
            f"This indicates _get_all_tracked_files() failed with detached branch name!"
        )

        # Total files should be 4 (file1, file2, file3, file4)
        total_files = len(analysis.files_to_reindex) + len(
            analysis.files_to_update_metadata
        )
        assert total_files == 4, (
            f"Expected 4 total files, got {total_files}. "
            f"Changed: {analysis.files_to_reindex}, "
            f"Unchanged: {analysis.files_to_update_metadata}"
        )
