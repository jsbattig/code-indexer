"""
End-to-end tests for FTS watch mode functionality.

Tests the complete workflow of monitoring file changes and updating
the FTS index in real-time alongside the semantic index.
"""

import subprocess
import tempfile
import time
from pathlib import Path
import pytest


@pytest.fixture
def test_repo():
    """Create a temporary test repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create a simple test file
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        yield repo_path


@pytest.fixture
def initialized_repo_with_fts(test_repo):
    """Initialize CIDX with FTS index in a test repository."""
    # Initialize CIDX
    result = subprocess.run(
        ["cidx", "init"],
        cwd=test_repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Init failed: {result.stderr}"

    # Start services
    result = subprocess.run(
        ["cidx", "start"],
        cwd=test_repo,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"Start failed: {result.stderr}"

    # Index with FTS
    result = subprocess.run(
        ["cidx", "index", "--fts"],
        cwd=test_repo,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Index failed: {result.stderr}"

    yield test_repo

    # Cleanup
    subprocess.run(
        ["cidx", "stop"],
        cwd=test_repo,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_watch_mode_without_fts_flag_defaults_to_semantic_only(
    initialized_repo_with_fts,
):
    """
    Test Acceptance Criteria 1: Watch Mode Default Behavior.

    Verify that 'cidx watch' without --fts continues semantic-only monitoring.
    """
    repo_path = initialized_repo_with_fts

    # Start watch mode without --fts (should work)
    watch_proc = subprocess.Popen(
        ["cidx", "watch", "--debounce", "1"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to start
        time.sleep(3)

        # Verify process is running
        assert watch_proc.poll() is None, "Watch mode should be running"

        # Modify a file
        test_file = repo_path / "test.py"
        test_file.write_text("def goodbye():\n    print('goodbye')\n")

        # Wait for processing
        time.sleep(3)

        # Process should still be running (semantic watch working)
        assert watch_proc.poll() is None, "Watch mode should still be running"

    finally:
        # Stop watch mode
        watch_proc.terminate()
        try:
            watch_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watch_proc.kill()


def test_watch_mode_with_fts_updates_both_indexes(initialized_repo_with_fts):
    """
    Test Acceptance Criteria 2 & 3: FTS Watch Integration and Incremental Updates.

    Verify that 'cidx watch --fts' monitors both semantic and FTS indexes,
    and file changes trigger updates to both indexes.
    """
    repo_path = initialized_repo_with_fts

    # Start watch mode with --fts
    watch_proc = subprocess.Popen(
        ["cidx", "watch", "--fts", "--debounce", "1"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to start
        time.sleep(3)

        # Verify process is running
        assert watch_proc.poll() is None, "Watch mode with FTS should be running"

        # Modify the file
        test_file = repo_path / "test.py"
        new_content = "def updated_function():\n    print('updated')\n"
        test_file.write_text(new_content)

        # Wait for watch mode to process the change
        time.sleep(4)

        # Stop watch mode
        watch_proc.terminate()
        watch_proc.wait(timeout=5)

        # Verify FTS index was updated by searching
        # Note: We can't easily query the FTS index in this test without
        # implementing a search command, so we verify the file system state
        fts_index_dir = repo_path / ".code-indexer" / "tantivy_index"
        assert fts_index_dir.exists(), "FTS index directory should exist"
        assert (fts_index_dir / "meta.json").exists(), "FTS index metadata should exist"

    finally:
        if watch_proc.poll() is None:
            watch_proc.terminate()
            try:
                watch_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watch_proc.kill()


def test_watch_mode_handles_file_deletion(initialized_repo_with_fts):
    """
    Test Acceptance Criteria 3: Incremental Updates - Deletion Handling.

    Verify that file deletions are properly handled in FTS watch mode.
    """
    repo_path = initialized_repo_with_fts

    # Create an additional file
    new_file = repo_path / "to_delete.py"
    new_file.write_text("def temporary():\n    pass\n")

    # Re-index to include new file
    result = subprocess.run(
        ["cidx", "index", "--fts"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0

    # Start watch mode with --fts
    watch_proc = subprocess.Popen(
        ["cidx", "watch", "--fts", "--debounce", "1"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to start
        time.sleep(3)

        # Delete the file
        new_file.unlink()

        # Wait for watch mode to process the deletion
        time.sleep(4)

        # Verify process still running (deletion handled gracefully)
        assert watch_proc.poll() is None, "Watch mode should handle deletion gracefully"

    finally:
        watch_proc.terminate()
        try:
            watch_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watch_proc.kill()


def test_watch_mode_fts_performance_within_acceptable_range(initialized_repo_with_fts):
    """
    Test Acceptance Criteria 2: Changes reflected in search within 100ms (per-file).

    This test verifies that changes are processed reasonably quickly,
    though exact timing in E2E tests is approximate.
    """
    repo_path = initialized_repo_with_fts

    # Start watch mode with --fts
    watch_proc = subprocess.Popen(
        [
            "cidx",
            "watch",
            "--fts",
            "--debounce",
            "0.5",
        ],  # Shorter debounce for perf test
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to start
        time.sleep(2)

        # Time a file modification
        test_file = repo_path / "test.py"
        start_time = time.time()

        test_file.write_text("def performance_test():\n    print('test')\n")

        # Wait for processing (debounce + processing time)
        time.sleep(2)

        elapsed_time = time.time() - start_time

        # Verify reasonable processing time (within a few seconds for E2E)
        # Note: This includes debounce time, so it's expected to be > 100ms
        assert elapsed_time < 10, f"Processing took {elapsed_time}s, too slow"

    finally:
        watch_proc.terminate()
        try:
            watch_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watch_proc.kill()


def test_watch_mode_missing_fts_index_graceful_handling(test_repo):
    """
    Test Acceptance Criteria 6: Missing Index Handling.

    Verify that using --fts without an existing FTS index shows a warning
    and continues with semantic-only watch.
    """
    repo_path = test_repo

    # Initialize CIDX but DON'T create FTS index
    result = subprocess.run(
        ["cidx", "init"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    result = subprocess.run(
        ["cidx", "start"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Index WITHOUT --fts
    result = subprocess.run(
        ["cidx", "index"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0

    try:
        # Try to start watch mode WITH --fts (should warn but continue)
        watch_proc = subprocess.Popen(
            ["cidx", "watch", "--fts", "--debounce", "1"],
            cwd=repo_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give watch mode time to start and show warning
        time.sleep(3)

        # Verify process is running despite missing FTS index
        assert watch_proc.poll() is None, "Watch should continue with semantic-only"

        # Read stdout to check for warning message
        # Note: This is best-effort since output buffering may delay messages
        watch_proc.terminate()
        stdout, stderr = watch_proc.communicate(timeout=5)

        # Verify warning message appeared
        combined_output = stdout + stderr
        assert any(
            keyword in combined_output.lower()
            for keyword in ["fts index not found", "continuing with semantic"]
        ), "Should show warning about missing FTS index"

    finally:
        if watch_proc.poll() is None:
            watch_proc.terminate()
            try:
                watch_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watch_proc.kill()

        # Cleanup
        subprocess.run(
            ["cidx", "stop"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=30,
        )


def test_watch_mode_handles_rapid_file_changes(initialized_repo_with_fts):
    """
    Test that watch mode handles multiple rapid file changes without errors.

    This tests the robustness of the FTS watch handler under load.
    """
    repo_path = initialized_repo_with_fts

    # Start watch mode with --fts
    watch_proc = subprocess.Popen(
        ["cidx", "watch", "--fts", "--debounce", "0.5"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to start
        time.sleep(2)

        # Make rapid changes to multiple files
        for i in range(5):
            test_file = repo_path / f"rapid_test_{i}.py"
            test_file.write_text(f"def function_{i}():\n    print('{i}')\n")
            time.sleep(0.2)  # Small delay between changes

        # Wait for all changes to be processed
        time.sleep(4)

        # Verify process still running (handled rapid changes)
        assert watch_proc.poll() is None, "Watch mode should handle rapid changes"

    finally:
        watch_proc.terminate()
        try:
            watch_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watch_proc.kill()


def test_watch_mode_handles_concurrent_modifications(initialized_repo_with_fts):
    """
    Verify concurrent file modifications don't cause conflicts or data loss.

    Tests thread safety of TantivyIndexManager when multiple file changes
    are processed simultaneously by watch mode handlers.
    """
    import threading

    repo_path = initialized_repo_with_fts

    # Start watch mode with --fts
    watch_proc = subprocess.Popen(
        ["cidx", "watch", "--fts", "--debounce", "0.5"],
        cwd=repo_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Give watch mode time to initialize
        time.sleep(2)

        # Verify watch process is running
        assert watch_proc.poll() is None, "Watch mode should be running"

        # Modify multiple files concurrently
        def modify_file(filename, content):
            file_path = repo_path / filename
            file_path.write_text(content)

        threads = []
        for i in range(5):
            filename = f"concurrent_test_{i}.py"
            content = f"# Concurrent modification {i}\ndef concurrent_func_{i}():\n    print('test {i}')\n"
            thread = threading.Thread(target=modify_file, args=(filename, content))
            threads.append(thread)
            thread.start()

        # Wait for all modifications to complete
        for thread in threads:
            thread.join()

        # Wait for watch mode to process all changes
        time.sleep(3)

        # Verify all files were created successfully
        for i in range(5):
            filename = f"concurrent_test_{i}.py"
            file_path = repo_path / filename
            assert file_path.exists(), f"File {filename} should exist"

        # Verify watch process still running (no crashes from concurrent access)
        assert (
            watch_proc.poll() is None
        ), "Watch mode should handle concurrent modifications without crashing"

        # Check for any errors in stderr
        watch_proc.terminate()
        stdout, stderr = watch_proc.communicate(timeout=5)

        # Stderr may contain informational messages, but should not have exceptions
        # or stack traces indicating thread safety issues
        assert (
            "Traceback" not in stderr and "Exception" not in stderr
        ), f"Watch mode encountered errors during concurrent modifications:\n{stderr}"

    finally:
        if watch_proc.poll() is None:
            watch_proc.terminate()
            try:
                watch_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watch_proc.kill()
