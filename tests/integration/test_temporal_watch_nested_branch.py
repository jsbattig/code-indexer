"""Integration test for TemporalWatchHandler with nested branch names.

This test verifies that commit detection works for branches with slashes
like feature/foo or bugfix/bar, where the refs file is at:
  .git/refs/heads/feature/foo

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
Issue: #434 - Verify fix works with nested branch directories
"""

import logging
import subprocess
import time
from unittest.mock import Mock

import pytest
from watchdog.observers import Observer

from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler


@pytest.fixture
def git_nested_branch_repo(tmp_path):
    """Create a git repository with a nested branch name."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo on master
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create initial commit
    test_file = repo_path / "test.py"
    test_file.write_text("# Initial commit\n")
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create nested branch
    subprocess.run(
        ["git", "checkout", "-b", "feature/test-branch"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    return repo_path


def test_temporal_watch_handler_nested_branch_commit(
    git_nested_branch_repo,
):
    """Test that commit detection works for nested branches like feature/foo.

    This verifies that the directory modification detection works when the
    refs file is at .git/refs/heads/feature/test-branch (nested path).
    """
    # Setup: Create handler with mocked dependencies
    indexer = Mock()
    indexer.index_commits_list.return_value = Mock(
        new_blobs_indexed=5, deduplication_ratio=0.8
    )
    metadata = Mock()
    metadata.load_completed.return_value = set()

    handler = TemporalWatchHandler(
        git_nested_branch_repo,
        temporal_indexer=indexer,
        progressive_metadata=metadata,
    )

    # Verify handler initialized with nested branch
    assert handler.current_branch == "feature/test-branch"
    assert handler.git_refs_file == (
        git_nested_branch_repo / ".git/refs/heads/feature/test-branch"
    )
    assert handler.git_refs_file.exists()
    assert handler.git_refs_file.parent == (
        git_nested_branch_repo / ".git/refs/heads/feature"
    )

    # Track commit detection
    commit_detected = False

    def tracking_commit_handler():
        nonlocal commit_detected
        logging.info("✅ COMMIT DETECTED on nested branch!")
        commit_detected = True

    handler._handle_commit_detected = tracking_commit_handler

    # Setup Observer
    observer = Observer()
    observer.schedule(handler, str(git_nested_branch_repo), recursive=True)
    observer.start()

    try:
        # Wait for observer to start
        time.sleep(0.5)

        # Make a commit on nested branch
        test_file = git_nested_branch_repo / "test.py"
        test_file.write_text("# Commit on feature branch\n")
        subprocess.run(
            ["git", "add", "."],
            cwd=git_nested_branch_repo,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Feature commit"],
            cwd=git_nested_branch_repo,
            check=True,
            capture_output=True,
        )

        # Wait for inotify event
        time.sleep(2)

        # ASSERTION: Commit should be detected via nested directory modification
        assert commit_detected, (
            f"Git commit was NOT detected on nested branch!\n"
            f"Branch: {handler.current_branch}\n"
            f"Refs file: {handler.git_refs_file}\n"
            f"Refs dir: {handler.git_refs_file.parent}\n"
            "The handler should detect modifications to .git/refs/heads/feature/"
        )

    finally:
        observer.stop()
        observer.join()
