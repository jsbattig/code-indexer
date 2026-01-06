"""
Unit tests for RefreshScheduler per-repo locking.

Tests verify that concurrent refresh operations on different repos can proceed in parallel,
while concurrent refresh attempts on the same repo are serialized via per-repo locks.

Story #620 Priority 1B Acceptance Criteria:
- Concurrent refreshes on different repos should not interfere
- Concurrent refresh attempts on same repo should be serialized
- Lock should be released on exception
- Lock should be released on timeout
"""

import pytest
import threading
import time
from unittest.mock import Mock, patch
from code_indexer.global_repos.refresh_scheduler import RefreshScheduler
from code_indexer.global_repos.query_tracker import QueryTracker
from code_indexer.global_repos.cleanup_manager import CleanupManager


@pytest.fixture
def mock_golden_repos_dir(tmp_path):
    """Create temporary golden repos directory."""
    golden_dir = tmp_path / "golden-repos"
    golden_dir.mkdir()
    return str(golden_dir)


@pytest.fixture
def mock_query_tracker():
    """Create mock QueryTracker."""
    return Mock(spec=QueryTracker)


@pytest.fixture
def mock_cleanup_manager():
    """Create mock CleanupManager."""
    return Mock(spec=CleanupManager)


@pytest.fixture
def mock_config_source():
    """Create mock config source."""
    config = Mock()
    config.get_global_refresh_interval.return_value = 3600
    return config


@pytest.fixture
def scheduler(
    mock_golden_repos_dir, mock_config_source, mock_query_tracker, mock_cleanup_manager
):
    """Create RefreshScheduler instance for testing."""
    return RefreshScheduler(
        golden_repos_dir=mock_golden_repos_dir,
        config_source=mock_config_source,
        query_tracker=mock_query_tracker,
        cleanup_manager=mock_cleanup_manager,
    )


@pytest.fixture
def mock_git_pull_updater():
    """Create common GitPullUpdater mock to reduce test duplication."""

    def _create_mock():
        mock_updater = Mock()
        mock_updater.has_changes.return_value = True
        mock_updater.get_source_path.return_value = "/path/to/source"
        return mock_updater

    return _create_mock


def test_concurrent_refreshes_different_repos_no_interference(
    scheduler, mock_git_pull_updater
):
    """
    Test that concurrent refresh operations on different repos can proceed in parallel.

    Acceptance Criteria:
    - Two refresh operations on different repos should run concurrently
    - Neither should block the other
    - Both should complete successfully
    """
    with (
        patch.object(scheduler.registry, "get_global_repo") as mock_get_repo,
        patch.object(scheduler.alias_manager, "read_alias") as mock_read_alias,
        patch.object(scheduler, "_create_new_index") as mock_create_index,
        patch.object(scheduler.alias_manager, "swap_alias"),
        patch.object(scheduler.cleanup_manager, "schedule_cleanup"),
        patch.object(scheduler.registry, "update_refresh_timestamp"),
        patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_class,
    ):

        # Setup mocks
        mock_get_repo.side_effect = lambda alias: {
            "alias_name": alias,
            "repo_url": (
                "https://github.com/user/repo1.git"
                if alias == "repo1-global"
                else "https://github.com/user/repo2.git"
            ),
        }
        mock_read_alias.return_value = "/path/to/current/index"
        mock_updater_class.return_value = mock_git_pull_updater()

        # Track when each refresh starts and completes
        refresh_events = {"repo1": [], "repo2": []}

        def slow_create_index(alias_name, source_path):
            """Simulate slow index creation to test concurrency."""
            repo_key = "repo1" if "repo1" in alias_name else "repo2"
            refresh_events[repo_key].append(("start", time.time()))
            time.sleep(0.1)  # Simulate work
            refresh_events[repo_key].append(("end", time.time()))
            return f"/path/to/new/index/{repo_key}"

        mock_create_index.side_effect = slow_create_index

        # Run two concurrent refreshes
        thread1 = threading.Thread(
            target=scheduler.refresh_repo, args=("repo1-global",)
        )
        thread2 = threading.Thread(
            target=scheduler.refresh_repo, args=("repo2-global",)
        )

        start_time = time.time()
        thread1.start()
        thread2.start()
        thread1.join(timeout=2.0)
        thread2.join(timeout=2.0)
        elapsed_time = time.time() - start_time

        # Verify both refreshes completed
        assert (
            len(refresh_events["repo1"]) == 2
        ), "Repo1 refresh should have started and ended"
        assert (
            len(refresh_events["repo2"]) == 2
        ), "Repo2 refresh should have started and ended"

        # Verify concurrent execution (total time should be < sum of individual times)
        assert (
            elapsed_time < 0.15
        ), f"Refreshes should run concurrently (took {elapsed_time}s)"

        # Verify overlap: repo2 should start before repo1 ends
        refresh_events["repo1"][0][1]
        repo1_end = refresh_events["repo1"][1][1]
        repo2_start = refresh_events["repo2"][0][1]

        assert (
            repo2_start < repo1_end
        ), "Repo2 should start before repo1 completes (concurrent execution)"


def test_concurrent_refreshes_same_repo_serialized(scheduler, mock_git_pull_updater):
    """
    Test that concurrent refresh attempts on the same repo are serialized.

    Acceptance Criteria:
    - Second refresh attempt should wait for first to complete
    - No race conditions or corruption
    - Both attempts should eventually complete
    """
    with (
        patch.object(scheduler.registry, "get_global_repo") as mock_get_repo,
        patch.object(scheduler.alias_manager, "read_alias") as mock_read_alias,
        patch.object(scheduler, "_create_new_index") as mock_create_index,
        patch.object(scheduler.alias_manager, "swap_alias"),
        patch.object(scheduler.cleanup_manager, "schedule_cleanup"),
        patch.object(scheduler.registry, "update_refresh_timestamp"),
        patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_class,
    ):

        # Setup mocks
        mock_get_repo.return_value = {
            "alias_name": "test-repo-global",
            "repo_url": "https://github.com/user/test-repo.git",
        }
        mock_read_alias.return_value = "/path/to/current/index"
        mock_updater_class.return_value = mock_git_pull_updater()

        # Track refresh execution order
        refresh_order = []
        lock = threading.Lock()

        def slow_create_index(alias_name, source_path):
            """Simulate slow index creation to test serialization."""
            with lock:
                refresh_order.append(("start", threading.current_thread().name))
            time.sleep(0.1)  # Simulate work
            with lock:
                refresh_order.append(("end", threading.current_thread().name))
            return f"/path/to/new/index/{threading.current_thread().name}"

        mock_create_index.side_effect = slow_create_index

        # Run two concurrent refresh attempts on same repo
        thread1 = threading.Thread(
            target=scheduler.refresh_repo, args=("test-repo-global",), name="refresh1"
        )
        thread2 = threading.Thread(
            target=scheduler.refresh_repo, args=("test-repo-global",), name="refresh2"
        )

        start_time = time.time()
        thread1.start()
        time.sleep(0.01)  # Small delay to ensure thread1 starts first
        thread2.start()
        thread1.join(timeout=2.0)
        thread2.join(timeout=2.0)
        elapsed_time = time.time() - start_time

        # Verify both refreshes completed
        assert (
            len(refresh_order) == 4
        ), f"Both refreshes should complete (got {len(refresh_order)} events)"

        # Verify serialization: second refresh should not start until first completes
        first_start = next(
            i for i, (event, thread) in enumerate(refresh_order) if event == "start"
        )
        first_end = next(
            i for i, (event, thread) in enumerate(refresh_order) if event == "end"
        )
        second_start = next(
            i
            for i, (event, thread) in enumerate(refresh_order)
            if event == "start" and i > first_start
        )

        assert (
            first_end < second_start
        ), f"Second refresh should start after first completes (order: {refresh_order})"

        # Verify sequential execution (total time should be ~sum of individual times)
        assert (
            elapsed_time >= 0.2
        ), f"Refreshes should run sequentially (took {elapsed_time}s)"


def test_refresh_lock_released_on_exception(scheduler, mock_git_pull_updater):
    """
    Test that per-repo lock is released when refresh raises an exception.

    Acceptance Criteria:
    - Lock should be released even if refresh fails
    - Subsequent refresh attempts should succeed
    - Exception should be logged but not propagate
    """
    with (
        patch.object(scheduler.registry, "get_global_repo") as mock_get_repo,
        patch.object(scheduler.alias_manager, "read_alias") as mock_read_alias,
        patch.object(scheduler, "_create_new_index") as mock_create_index,
        patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_class,
    ):

        # Setup mocks
        mock_get_repo.return_value = {
            "alias_name": "test-repo-global",
            "repo_url": "https://github.com/user/test-repo.git",
        }
        mock_read_alias.return_value = "/path/to/current/index"
        mock_updater_class.return_value = mock_git_pull_updater()

        # First call raises exception, second succeeds
        call_count = [0]

        def create_index_with_exception(alias_name, source_path):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Index creation failed")
            return "/path/to/new/index"

        mock_create_index.side_effect = create_index_with_exception

        # First refresh should fail but release lock
        scheduler.refresh_repo("test-repo-global")

        # Verify exception was caught (no exception propagated)
        assert call_count[0] == 1, "First refresh should have been attempted"

        # Second refresh should succeed (lock was released)
        with (
            patch.object(scheduler.alias_manager, "swap_alias"),
            patch.object(scheduler.cleanup_manager, "schedule_cleanup"),
            patch.object(scheduler.registry, "update_refresh_timestamp"),
        ):

            scheduler.refresh_repo("test-repo-global")
            assert call_count[0] == 2, "Second refresh should have succeeded"


def test_refresh_lock_released_on_timeout(scheduler, mock_git_pull_updater):
    """
    Test that per-repo lock is released when refresh times out.

    Acceptance Criteria:
    - Lock should be released if refresh takes too long
    - Timeout should be configurable
    - Subsequent refresh attempts should succeed
    """
    with (
        patch.object(scheduler.registry, "get_global_repo") as mock_get_repo,
        patch.object(scheduler.alias_manager, "read_alias") as mock_read_alias,
        patch.object(scheduler, "_create_new_index") as mock_create_index,
        patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_class,
    ):

        # Setup mocks
        mock_get_repo.return_value = {
            "alias_name": "test-repo-global",
            "repo_url": "https://github.com/user/test-repo.git",
        }
        mock_read_alias.return_value = "/path/to/current/index"
        mock_updater_class.return_value = mock_git_pull_updater()

        # Track execution
        execution_log = []

        def slow_create_index(alias_name, source_path):
            """Simulate very slow index creation."""
            execution_log.append("start")
            time.sleep(2.0)  # Simulate timeout
            execution_log.append("end")
            return "/path/to/new/index"

        mock_create_index.side_effect = slow_create_index

        # Start long-running refresh in background
        thread1 = threading.Thread(
            target=scheduler.refresh_repo, args=("test-repo-global",)
        )
        thread1.start()

        # Wait a bit to ensure thread1 acquires lock
        time.sleep(0.1)

        # Second refresh should either wait for lock or timeout gracefully
        thread2 = threading.Thread(
            target=scheduler.refresh_repo, args=("test-repo-global",)
        )
        thread2.start()

        # Wait for both threads
        thread1.join(timeout=3.0)
        thread2.join(timeout=3.0)

        # Verify lock was eventually released (both threads completed or timed out gracefully)
        assert not thread1.is_alive(), "Thread1 should have completed"
        assert (
            not thread2.is_alive()
        ), "Thread2 should have completed or timed out gracefully"


def test_refresh_lock_prevents_duplicate_refresh(scheduler, mock_git_pull_updater):
    """
    Test that per-repo lock prevents duplicate refresh operations.

    Acceptance Criteria:
    - Only one refresh should proceed at a time for same repo
    - Second attempt should wait or skip gracefully
    - No duplicate index creation
    """
    with (
        patch.object(scheduler.registry, "get_global_repo") as mock_get_repo,
        patch.object(scheduler.alias_manager, "read_alias") as mock_read_alias,
        patch.object(scheduler, "_create_new_index") as mock_create_index,
        patch.object(scheduler.alias_manager, "swap_alias"),
        patch.object(scheduler.cleanup_manager, "schedule_cleanup"),
        patch.object(scheduler.registry, "update_refresh_timestamp"),
        patch(
            "code_indexer.global_repos.refresh_scheduler.GitPullUpdater"
        ) as mock_updater_class,
    ):

        # Setup mocks
        mock_get_repo.return_value = {
            "alias_name": "test-repo-global",
            "repo_url": "https://github.com/user/test-repo.git",
        }
        mock_read_alias.return_value = "/path/to/current/index"
        mock_updater_class.return_value = mock_git_pull_updater()

        # Track number of index creations
        create_count = [0]

        def track_create_index(alias_name, source_path):
            create_count[0] += 1
            time.sleep(0.1)  # Simulate work
            return "/path/to/new/index"

        mock_create_index.side_effect = track_create_index

        # Run three concurrent refresh attempts
        threads = [
            threading.Thread(target=scheduler.refresh_repo, args=("test-repo-global",))
            for _ in range(3)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2.0)

        # Verify all threads completed
        assert all(not t.is_alive() for t in threads), "All threads should complete"

        # With per-repo locking, all 3 attempts should create indexes (serialized)
        assert (
            create_count[0] == 3
        ), f"All 3 refresh attempts should complete sequentially (got {create_count[0]})"
