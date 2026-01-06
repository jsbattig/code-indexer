"""
Unit tests for GoldenRepoManager operation locking.

Tests verify that concurrent operations (add, remove, refresh) on golden repositories
are properly synchronized and that metadata file operations maintain consistency.

Story #620 Priority 2A Acceptance Criteria:
- Concurrent add operations should be serialized
- Concurrent remove operations should be serialized
- Concurrent add/remove operations should be serialized
- Metadata file access should be protected
- Lock should be released on exception
"""

import pytest
import threading
import time
import json
from unittest.mock import Mock, patch
from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


@pytest.fixture
def mock_data_dir(tmp_path):
    """Create temporary data directory."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    golden_repos_dir = data_dir / "golden-repos"
    golden_repos_dir.mkdir()
    return str(data_dir)


@pytest.fixture
def manager(mock_data_dir):
    """Create GoldenRepoManager instance for testing."""
    mgr = GoldenRepoManager(data_dir=mock_data_dir)
    # Mock background_job_manager dependency
    mgr.background_job_manager = Mock()
    mgr.background_job_manager.submit_job.return_value = "test-job-id-123"
    return mgr


def test_concurrent_add_operations_serialized(manager):
    """
    Test that concurrent add_golden_repo operations are serialized.

    Acceptance Criteria:
    - Multiple concurrent add operations should not corrupt metadata
    - Operations should complete in serial order
    - All operations should succeed without race conditions
    """
    # Track execution order
    execution_log = []
    lock = threading.Lock()

    # Mock the internal methods that do actual work
    original_save = manager._save_metadata

    def tracked_save_metadata():
        """Track when metadata is saved."""
        with lock:
            execution_log.append(("save_start", threading.current_thread().name))
        time.sleep(0.05)  # Simulate slow I/O
        original_save()
        with lock:
            execution_log.append(("save_end", threading.current_thread().name))

    with (
        patch.object(manager, "_save_metadata", side_effect=tracked_save_metadata),
        patch.object(manager, "_validate_git_repository", return_value=True),
        patch.object(manager, "_clone_repository", return_value="/path/to/clone"),
        patch.object(manager, "_execute_post_clone_workflow"),
    ):
        # Run three concurrent add operations
        threads = []
        for i in range(3):

            def add_repo(index=i):
                manager.add_golden_repo(
                    alias=f"test-repo-{index}",
                    repo_url=f"https://github.com/user/repo{index}.git",
                    default_branch="main",
                    submitter_username="test-user",
                )

            thread = threading.Thread(target=add_repo, name=f"add_{i}")
            threads.append(thread)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5.0)

        # Verify all threads completed
        assert all(not t.is_alive() for t in threads), "All threads should complete"

        # Verify metadata saves were serialized (no overlapping saves)
        save_starts = [
            i for i, (event, _) in enumerate(execution_log) if event == "save_start"
        ]
        save_ends = [
            i for i, (event, _) in enumerate(execution_log) if event == "save_end"
        ]

        # Each save_end should come before the next save_start
        for i in range(len(save_starts) - 1):
            assert (
                save_ends[i] < save_starts[i + 1]
            ), f"Metadata saves should be serialized (log: {execution_log})"


def test_concurrent_remove_operations_serialized(manager):
    """
    Test that concurrent remove_golden_repo operations are serialized.

    Acceptance Criteria:
    - Multiple concurrent remove operations should not corrupt metadata
    - Operations should complete in serial order
    - No race conditions during cleanup
    """
    # Pre-populate metadata with test repos
    from code_indexer.server.repositories.golden_repo_manager import GoldenRepo

    manager.golden_repos = {
        "repo1": GoldenRepo(
            alias="repo1",
            repo_url="https://github.com/user/repo1.git",
            default_branch="main",
            clone_path="/path/to/repo1",
            created_at="2025-01-01T00:00:00Z",
        ),
        "repo2": GoldenRepo(
            alias="repo2",
            repo_url="https://github.com/user/repo2.git",
            default_branch="main",
            clone_path="/path/to/repo2",
            created_at="2025-01-01T00:00:00Z",
        ),
        "repo3": GoldenRepo(
            alias="repo3",
            repo_url="https://github.com/user/repo3.git",
            default_branch="main",
            clone_path="/path/to/repo3",
            created_at="2025-01-01T00:00:00Z",
        ),
    }
    manager._save_metadata()

    # Track execution order
    execution_log = []
    lock = threading.Lock()

    def tracked_cleanup(clone_path):
        """Track when cleanup is called."""
        with lock:
            execution_log.append(
                ("cleanup_start", threading.current_thread().name, clone_path)
            )
        time.sleep(0.05)  # Simulate slow cleanup
        result = True  # Mock successful cleanup
        with lock:
            execution_log.append(
                ("cleanup_end", threading.current_thread().name, clone_path)
            )
        return result

    with patch.object(
        manager, "_cleanup_repository_files", side_effect=tracked_cleanup
    ):
        # Run three concurrent remove operations
        threads = []
        for i in range(1, 4):

            def remove_repo(index=i):
                manager.remove_golden_repo(
                    alias=f"repo{index}", submitter_username="test-user"
                )

            thread = threading.Thread(target=remove_repo, name=f"remove_{i}")
            threads.append(thread)

        # Start all threads
        for t in threads:
            t.start()

        # Wait for completion
        for t in threads:
            t.join(timeout=5.0)

        # Verify all threads completed
        assert all(not t.is_alive() for t in threads), "All threads should complete"

        # Verify cleanup operations were serialized
        cleanup_starts = [
            i
            for i, (event, _, _) in enumerate(execution_log)
            if event == "cleanup_start"
        ]
        cleanup_ends = [
            i for i, (event, _, _) in enumerate(execution_log) if event == "cleanup_end"
        ]

        # Each cleanup_end should come before the next cleanup_start
        for i in range(len(cleanup_starts) - 1):
            assert (
                cleanup_ends[i] < cleanup_starts[i + 1]
            ), f"Cleanup operations should be serialized (log: {execution_log})"


def test_concurrent_add_remove_serialized(manager):
    """
    Test that concurrent add and remove operations don't interfere.

    Acceptance Criteria:
    - Add and remove operations should be serialized
    - No metadata corruption from mixed operations
    - Both operation types should complete successfully
    """
    # Pre-populate with one repo
    from code_indexer.server.repositories.golden_repo_manager import GoldenRepo

    manager.golden_repos = {
        "existing-repo": GoldenRepo(
            alias="existing-repo",
            repo_url="https://github.com/user/existing.git",
            default_branch="main",
            clone_path="/path/to/existing",
            created_at="2025-01-01T00:00:00Z",
        ),
    }
    manager._save_metadata()

    # Track operations
    operation_log = []
    lock = threading.Lock()

    def track_operation(op_type, op_name):
        with lock:
            operation_log.append((op_type, op_name, time.time()))

    with (
        patch.object(manager, "_validate_git_repository", return_value=True),
        patch.object(manager, "_clone_repository", return_value="/path/to/new"),
        patch.object(manager, "_execute_post_clone_workflow"),
        patch.object(manager, "_cleanup_repository_files", return_value=True),
    ):
        # Create threads for add and remove operations
        def add_operation():
            track_operation("start", "add")
            manager.add_golden_repo(
                alias="new-repo",
                repo_url="https://github.com/user/new.git",
                default_branch="main",
                submitter_username="test-user",
            )
            track_operation("end", "add")

        def remove_operation():
            time.sleep(0.01)  # Small delay to ensure add starts first
            track_operation("start", "remove")
            manager.remove_golden_repo(
                alias="existing-repo", submitter_username="test-user"
            )
            track_operation("end", "remove")

        add_thread = threading.Thread(target=add_operation)
        remove_thread = threading.Thread(target=remove_operation)

        add_thread.start()
        remove_thread.start()

        add_thread.join(timeout=5.0)
        remove_thread.join(timeout=5.0)

        # Verify both completed
        assert not add_thread.is_alive(), "Add thread should complete"
        assert not remove_thread.is_alive(), "Remove thread should complete"

        # Verify operations were serialized (no overlap)
        add_start = next(
            t for op, name, t in operation_log if name == "add" and op == "start"
        )
        add_end = next(
            t for op, name, t in operation_log if name == "add" and op == "end"
        )
        remove_start = next(
            t for op, name, t in operation_log if name == "remove" and op == "start"
        )
        remove_end = next(
            t for op, name, t in operation_log if name == "remove" and op == "end"
        )

        # Either add completes before remove starts, or remove completes before add starts
        operations_serialized = (add_end < remove_start) or (remove_end < add_start)
        assert (
            operations_serialized
        ), f"Operations should be serialized (log: {operation_log})"


def test_metadata_lock_prevents_corruption(manager):
    """
    Test that metadata file lock prevents corruption from concurrent access.

    Acceptance Criteria:
    - Concurrent metadata reads/writes should not corrupt file
    - File should remain valid JSON after concurrent operations
    - All writes should be atomic
    """
    # Pre-populate metadata
    from code_indexer.server.repositories.golden_repo_manager import GoldenRepo

    manager.golden_repos = {
        f"repo{i}": GoldenRepo(
            alias=f"repo{i}",
            repo_url=f"https://github.com/user/repo{i}.git",
            default_branch="main",
            clone_path=f"/path/to/repo{i}",
            created_at="2025-01-01T00:00:00Z",
        )
        for i in range(5)
    }
    manager._save_metadata()

    # Track metadata file state
    metadata_snapshots = []
    lock = threading.Lock()

    def concurrent_metadata_update(repo_index):
        """Simulate concurrent metadata updates."""
        from code_indexer.server.repositories.golden_repo_manager import GoldenRepo

        for j in range(3):
            # Read metadata
            manager._load_metadata()

            # Modify metadata
            new_alias = f"repo{repo_index}-updated-{j}"
            manager.golden_repos[new_alias] = GoldenRepo(
                alias=new_alias,
                repo_url=f"https://github.com/user/{new_alias}.git",
                default_branch="main",
                clone_path=f"/path/to/{new_alias}",
                created_at="2025-01-01T00:00:00Z",
            )

            # Save metadata
            manager._save_metadata()

            # Capture snapshot
            with lock:
                with open(manager.metadata_file, "r") as f:
                    content = f.read()
                    metadata_snapshots.append(content)

            time.sleep(0.01)  # Small delay

    # Run concurrent metadata updates
    threads = [
        threading.Thread(target=concurrent_metadata_update, args=(i,)) for i in range(3)
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    # Verify all threads completed
    assert all(not t.is_alive() for t in threads), "All threads should complete"

    # Verify all snapshots are valid JSON (no corruption)
    for snapshot in metadata_snapshots:
        try:
            json.loads(snapshot)
        except json.JSONDecodeError:
            pytest.fail(f"Metadata corruption detected: {snapshot}")

    # Verify final metadata is valid and consistent
    manager._load_metadata()
    assert isinstance(manager.golden_repos, dict), "Final metadata should be valid dict"


def test_operation_lock_released_on_exception(manager):
    """
    Test that operation lock is released when metadata operations raise exceptions.

    Acceptance Criteria:
    - Lock should be released even if _save_metadata fails
    - Lock should be released even if _load_metadata fails
    - Subsequent metadata operations should succeed after exceptions
    - Lock state should be unlocked after exception (verified directly)
    """
    from code_indexer.server.repositories.golden_repo_manager import GoldenRepo

    # Pre-populate manager with test data
    manager.golden_repos["test-repo"] = GoldenRepo(
        alias="test-repo",
        repo_url="https://github.com/user/test.git",
        default_branch="main",
        clone_path="/path/to/test",
        created_at="2025-01-01T00:00:00Z",
    )

    # Capture real open() before patching to avoid recursion
    real_open = open

    # Test 1: _save_metadata releases lock on exception
    save_call_count = [0]

    def failing_open_write(*args, **kwargs):
        """Mock open() that fails on first write attempt."""
        save_call_count[0] += 1
        if save_call_count[0] == 1:
            raise IOError("Disk full - write failed")
        # Use captured real open (not the mocked one)
        return real_open(*args, **kwargs)

    with patch("builtins.open", side_effect=failing_open_write):
        # Verify lock is not held before operation
        assert not manager._operation_lock.locked(), "Lock should be free initially"

        # First _save_metadata should fail and release lock
        with pytest.raises(IOError, match="Disk full"):
            manager._save_metadata()

        # Verify lock was released after exception
        assert (
            not manager._operation_lock.locked()
        ), "Lock should be released after exception"
        assert save_call_count[0] == 1, "First save attempt should have been made"

        # Second _save_metadata should succeed (lock was released)
        manager._save_metadata()
        assert save_call_count[0] == 2, "Second save should succeed (lock was released)"
        assert (
            not manager._operation_lock.locked()
        ), "Lock should be released after successful operation"

    # Test 2: _load_metadata releases lock on exception
    load_call_count = [0]

    def failing_open_read(*args, **kwargs):
        """Mock open() that fails on first read attempt."""
        load_call_count[0] += 1
        if load_call_count[0] == 1:
            raise IOError("File corrupted - read failed")
        # Use captured real open (not the mocked one)
        return real_open(*args, **kwargs)

    with patch("builtins.open", side_effect=failing_open_read):
        # Verify lock is not held before operation
        assert not manager._operation_lock.locked(), "Lock should be free initially"

        # First _load_metadata should fail and release lock
        with pytest.raises(IOError, match="File corrupted"):
            manager._load_metadata()

        # Verify lock was released after exception
        assert (
            not manager._operation_lock.locked()
        ), "Lock should be released after exception"
        assert load_call_count[0] == 1, "First load attempt should have been made"

        # Second _load_metadata should succeed (lock was released)
        manager._load_metadata()
        assert load_call_count[0] == 2, "Second load should succeed (lock was released)"
        assert (
            not manager._operation_lock.locked()
        ), "Lock should be released after successful operation"
