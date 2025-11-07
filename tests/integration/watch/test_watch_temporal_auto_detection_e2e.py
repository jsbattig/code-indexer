"""End-to-end integration tests for watch mode temporal auto-detection.

Tests the complete workflow of:
1. Auto-detecting existing indexes (semantic + temporal)
2. Starting watch mode with auto-detected handlers
3. Git commit detection triggering incremental temporal indexing
4. Progress reporting during watch-triggered indexing

Story: 02_Feat_WatchModeAutoDetection/01_Story_WatchModeAutoUpdatesAllIndexes.md
"""

import subprocess
import tempfile
import time
from pathlib import Path
import pytest
import json


@pytest.fixture
def git_test_repo():
    """Create a temporary git repository with initial commit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git
        subprocess.run(
            ["git", "init"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        # Create initial file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        subprocess.run(
            ["git", "add", "."],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            capture_output=True,
            check=True,
        )

        yield repo_path


@pytest.fixture
def initialized_repo_with_temporal(git_test_repo):
    """Initialize CIDX with semantic + temporal indexes."""
    # Initialize CIDX
    result = subprocess.run(
        ["cidx", "init"],
        cwd=git_test_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Init failed: {result.stderr}"

    # Index semantic (HEAD collection)
    result = subprocess.run(
        ["cidx", "index", "--quiet"],
        cwd=git_test_repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Semantic index failed: {result.stderr}"

    # Index temporal (git history)
    result = subprocess.run(
        ["cidx", "temporal-index", "--quiet"],
        cwd=git_test_repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Temporal index failed: {result.stderr}"

    # Verify both indexes exist
    index_base = git_test_repo / ".code-indexer/index"
    assert (index_base / "code-indexer-HEAD").exists(), "Semantic index not found"
    assert (
        index_base / "code-indexer-temporal"
    ).exists(), "Temporal index not found"

    yield git_test_repo


@pytest.fixture
def initialized_repo_semantic_only(git_test_repo):
    """Initialize CIDX with only semantic index (no temporal)."""
    # Initialize CIDX
    result = subprocess.run(
        ["cidx", "init"],
        cwd=git_test_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Init failed: {result.stderr}"

    # Index semantic only
    result = subprocess.run(
        ["cidx", "index", "--quiet"],
        cwd=git_test_repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Semantic index failed: {result.stderr}"

    # Verify only semantic index exists
    index_base = git_test_repo / ".code-indexer/index"
    assert (index_base / "code-indexer-HEAD").exists(), "Semantic index not found"
    assert not (
        index_base / "code-indexer-temporal"
    ).exists(), "Temporal index should not exist"

    yield git_test_repo


class TestWatchModeAutoDetection:
    """Test suite for watch mode auto-detection of indexes."""

    def test_watch_auto_detects_semantic_and_temporal_indexes(
        self, initialized_repo_with_temporal
    ):
        """
        Test Acceptance Criteria: Auto-detection with semantic + temporal.

        Given semantic and temporal indexes both exist
        When user runs "cidx watch"
        Then both handlers are started
        And console displays: "Detected 2 index(es) to watch"
        And console displays: "✅ Semantic index"
        And console displays: "✅ Temporal index"
        """
        repo_path = initialized_repo_with_temporal

        # Start watch mode
        watch_proc = subprocess.Popen(
            ["cidx", "watch"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Give watch mode time to start and print detection messages
            time.sleep(2)

            # Check process is running
            assert watch_proc.poll() is None, "Watch mode should be running"

            # Terminate and capture output
            watch_proc.terminate()
            stdout, stderr = watch_proc.communicate(timeout=5)
            output = stdout + stderr

            # Verify detection messages
            assert (
                "Detected 2 index(es) to watch" in output
            ), f"Should detect 2 indexes. Output: {output}"
            assert (
                "Semantic index" in output
            ), f"Should mention semantic index. Output: {output}"
            assert (
                "Temporal index" in output
            ), f"Should mention temporal index. Output: {output}"

        finally:
            if watch_proc.poll() is None:
                watch_proc.kill()
                watch_proc.wait()

    def test_watch_with_semantic_only_no_temporal(self, initialized_repo_semantic_only):
        """
        Test Acceptance Criteria: Watch mode with only semantic index.

        Given only semantic index exists
        When user runs "cidx watch"
        Then only semantic handler is started
        And console displays: "Detected 1 index(es) to watch"
        And console displays: "✅ Semantic index"
        And temporal handler is NOT started
        """
        repo_path = initialized_repo_semantic_only

        # Start watch mode
        watch_proc = subprocess.Popen(
            ["cidx", "watch"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Give watch mode time to start
            time.sleep(2)

            # Check process is running
            assert watch_proc.poll() is None, "Watch mode should be running"

            # Terminate and capture output
            watch_proc.terminate()
            stdout, stderr = watch_proc.communicate(timeout=5)
            output = stdout + stderr

            # Verify detection messages
            assert (
                "Detected 1 index(es) to watch" in output
            ), f"Should detect 1 index. Output: {output}"
            assert (
                "Semantic index" in output
            ), f"Should mention semantic index. Output: {output}"
            assert (
                "Temporal index" not in output
            ), f"Should NOT mention temporal index. Output: {output}"

        finally:
            if watch_proc.poll() is None:
                watch_proc.kill()
                watch_proc.wait()


class TestWatchModeGitCommitDetection:
    """Test suite for git commit detection triggering temporal indexing."""

    def test_watch_mode_detects_and_indexes_new_commit(
        self, initialized_repo_with_temporal
    ):
        """
        Test Acceptance Criteria: Incremental indexing on commit.

        Given watch mode is running with temporal index
        And temporal_progress.json shows 1 commit indexed
        When user makes a new commit (commit #2)
        Then _handle_commit_detected() is called within 5 seconds
        And only commit #2 is indexed (not commit #1)
        And temporal_progress.json is updated with commit #2
        And new commit is searchable via temporal query
        """
        repo_path = initialized_repo_with_temporal

        # Verify initial state - 1 commit indexed
        progress_file = (
            repo_path / ".code-indexer/index/code-indexer-temporal/temporal_progress.json"
        )
        assert progress_file.exists(), "temporal_progress.json should exist"

        initial_progress = json.loads(progress_file.read_text())
        initial_commits = set(initial_progress.get("completed_commits", []))
        assert len(initial_commits) == 1, "Should have 1 initial commit indexed"

        # Start watch mode
        watch_proc = subprocess.Popen(
            ["cidx", "watch"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Give watch mode time to start
            time.sleep(2)
            assert watch_proc.poll() is None, "Watch mode should be running"

            # Make a new commit
            new_file = repo_path / "new_feature.py"
            new_file.write_text("def new_feature():\n    return 'new'\n")

            subprocess.run(
                ["git", "add", "."],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Add new feature"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # Wait for watch mode to detect and index the commit
            # Polling fallback = 5s, inotify = ~100ms, give it 10s buffer
            time.sleep(10)

            # Verify temporal_progress.json was updated
            updated_progress = json.loads(progress_file.read_text())
            updated_commits = set(updated_progress.get("completed_commits", []))

            assert (
                len(updated_commits) == 2
            ), f"Should have 2 commits indexed. Got: {len(updated_commits)}"
            new_commits = updated_commits - initial_commits
            assert (
                len(new_commits) == 1
            ), f"Should have 1 new commit. Got: {new_commits}"

            # Get the new commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            latest_commit = result.stdout.strip()
            assert (
                latest_commit in updated_commits
            ), f"Latest commit {latest_commit} should be in progress file"

            # Verify new commit is searchable (query temporal index)
            query_result = subprocess.run(
                ["cidx", "temporal-query", "new_feature", "--quiet", "--limit", "5"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert (
                query_result.returncode == 0
            ), f"Temporal query failed: {query_result.stderr}"
            assert (
                "new_feature" in query_result.stdout.lower()
            ), "New commit should be searchable"

        finally:
            if watch_proc.poll() is None:
                watch_proc.terminate()
                watch_proc.wait(timeout=5)

    def test_watch_mode_progress_reporting_on_commit(
        self, initialized_repo_with_temporal
    ):
        """
        Test Acceptance Criteria: Progress reporting matches standalone mode.

        Given watch mode is running
        When new commit indexing is in progress
        Then progress reporting shows commit processing
        And RichLiveProgressManager is used
        And UX matches standalone temporal-index command
        """
        repo_path = initialized_repo_with_temporal

        # Start watch mode
        watch_proc = subprocess.Popen(
            ["cidx", "watch"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            # Give watch mode time to start
            time.sleep(2)
            assert watch_proc.poll() is None, "Watch mode should be running"

            # Make a commit with multiple files to trigger visible progress
            for i in range(5):
                test_file = repo_path / f"feature_{i}.py"
                test_file.write_text(f"def feature_{i}():\n    return {i}\n")

            subprocess.run(
                ["git", "add", "."],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "Add multiple features"],
                cwd=repo_path,
                capture_output=True,
                check=True,
            )

            # Wait for indexing to start
            time.sleep(10)

            # Terminate and capture output
            watch_proc.terminate()
            stdout, stderr = watch_proc.communicate(timeout=5)
            output = stdout + stderr

            # Verify progress indicators present
            # Look for commit hash patterns (8 hex chars)
            import re

            commit_patterns = re.findall(r"[0-9a-f]{8}", output)
            assert (
                len(commit_patterns) > 0
            ), f"Should show commit hashes in progress. Output: {output}"

            # Should mention indexing activity
            assert (
                "commit" in output.lower() or "indexing" in output.lower()
            ), f"Should mention indexing activity. Output: {output}"

        finally:
            if watch_proc.poll() is None:
                watch_proc.kill()
                watch_proc.wait()


class TestWatchModeNoIndexes:
    """Test suite for watch mode with no indexes."""

    def test_watch_with_no_indexes_shows_warning(self, git_test_repo):
        """
        Test Acceptance Criteria: Warning when no indexes exist.

        Given no indexes exist
        When user runs "cidx watch"
        Then warning is displayed: "No indexes found. Run 'cidx index' first."
        And watch mode exits immediately
        And no handlers are started
        """
        repo_path = git_test_repo

        # Initialize CIDX but don't create any indexes
        result = subprocess.run(
            ["cidx", "init"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Try to start watch mode
        result = subprocess.run(
            ["cidx", "watch"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Watch mode should exit immediately
        output = result.stdout + result.stderr
        assert (
            "No indexes found" in output or "no indexes" in output.lower()
        ), f"Should show no indexes warning. Output: {output}"
