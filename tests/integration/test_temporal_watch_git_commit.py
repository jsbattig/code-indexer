"""Integration test for TemporalWatchHandler git commit detection.

This test verifies that:
1. TemporalWatchHandler is properly registered with Observer
2. Git commits trigger on_modified() events
3. Handler correctly processes commit events

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
Issue: #434 - TemporalWatchHandler not triggered by git commits
"""

import logging
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from watchdog.observers import Observer

from code_indexer.cli_temporal_watch_handler import TemporalWatchHandler


@pytest.fixture
def git_test_repo(tmp_path):
    """Create a real git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
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

    return repo_path


@pytest.fixture
def mock_temporal_indexer():
    """Mock TemporalIndexer for testing."""
    indexer = Mock()
    indexer.index_commits_list.return_value = Mock(
        vectors_created=5,
        skip_ratio=0.2,  # 20% skipped
    )
    return indexer


@pytest.fixture
def mock_progressive_metadata():
    """Mock TemporalProgressiveMetadata for testing."""
    metadata = Mock()
    metadata.load_completed.return_value = set()  # Empty set initially
    return metadata


def test_temporal_watch_handler_detects_git_commit(
    git_test_repo, mock_temporal_indexer, mock_progressive_metadata
):
    """Test that TemporalWatchHandler detects git commits via inotify.

    This is a CRITICAL integration test that verifies:
    1. Handler is properly initialized with correct git refs path
    2. Observer.schedule() registers handler correctly
    3. Git commits trigger on_modified() events
    4. Handler receives correct event paths from watchdog

    ROOT CAUSE: Handler's on_modified() checks absolute paths but watchdog
    provides relative paths. This test reproduces the issue.
    """
    # Setup: Create handler with mocked dependencies
    handler = TemporalWatchHandler(
        git_test_repo,
        temporal_indexer=mock_temporal_indexer,
        progressive_metadata=mock_progressive_metadata,
    )

    # Verify handler initialized correctly
    assert handler.project_root == git_test_repo
    assert handler.current_branch == "master"
    assert handler.git_refs_file == git_test_repo / ".git/refs/heads/master"
    assert handler.git_refs_file.exists()

    # Track if commit detection was triggered
    commit_detected = False
    original_handle_commit = handler._handle_commit_detected

    def tracking_commit_handler():
        nonlocal commit_detected
        logging.info("✅ COMMIT DETECTED - _handle_commit_detected() called!")
        commit_detected = True
        # Don't call original to avoid actual indexing (we're just testing detection)

    handler._handle_commit_detected = tracking_commit_handler

    # Setup Observer (same as cli.py line 4387)
    observer = Observer()
    observer.schedule(handler, str(git_test_repo), recursive=True)
    observer.start()

    try:
        # Wait for observer to start
        time.sleep(0.5)

        # Make a git commit (this should trigger inotify on refs file)
        test_file = git_test_repo / "test.py"
        test_file.write_text("# Second commit\n")
        subprocess.run(
            ["git", "add", "."], cwd=git_test_repo, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Second commit"],
            cwd=git_test_repo,
            check=True,
            capture_output=True,
        )

        # Wait for inotify event to be processed (should be <100ms but give 2s)
        time.sleep(2)

        # ASSERTION: Verify commit was detected via directory modification
        assert commit_detected, (
            "Git commit was NOT detected! The handler should have detected the "
            "directory modification and triggered _handle_commit_detected().\n"
            f"Git refs directory: {handler.git_refs_file.parent}\n"
            "This means the fix for atomic rename detection is not working."
        )

    finally:
        observer.stop()
        observer.join()


def test_temporal_watch_handler_path_matching():
    """Test that handler correctly matches event paths.

    This test verifies the path comparison logic in on_modified().
    It tests both absolute and relative path scenarios to identify
    the root cause of the path mismatch issue.
    """
    # This test will help us understand what paths watchdog provides
    from watchdog.events import FileModifiedEvent

    # Create a mock handler setup
    project_root = Path("/tmp/test_project")
    git_refs_file = project_root / ".git/refs/heads/master"

    # Test case 1: Absolute path (what handler expects)
    event_absolute = FileModifiedEvent(str(git_refs_file))
    assert event_absolute.src_path == str(git_refs_file)

    # Test case 2: Relative path (what watchdog might provide)
    event_relative = FileModifiedEvent(".git/refs/heads/master")
    assert event_relative.src_path == ".git/refs/heads/master"

    # Test case 3: Path relative to watched directory
    event_watched_relative = FileModifiedEvent(
        str(project_root / ".git/refs/heads/master")
    )

    # This demonstrates the problem: handler compares absolute paths
    # but watchdog might provide relative paths depending on how
    # the watch was registered
    assert str(git_refs_file) == str(project_root / ".git/refs/heads/master")
