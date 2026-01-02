"""
Unit tests for GlobalRegistry file locking.

Tests verify that concurrent operations on global registry are properly synchronized
and that registry file operations maintain consistency.

Story #620 Priority 2B Acceptance Criteria:
- Concurrent register operations should be serialized
- Concurrent unregister operations should be serialized
- Concurrent register/unregister operations should be serialized
- Registry file access should be protected
- Lock should be released on exception
"""

import pytest
import threading
import time
import json
from unittest.mock import patch
from code_indexer.global_repos.global_registry import GlobalRegistry


@pytest.fixture
def temp_registry_dir(tmp_path):
    """Create temporary directory for registry testing."""
    registry_dir = tmp_path / "golden-repos"
    registry_dir.mkdir()
    return str(registry_dir)


@pytest.fixture
def registry(temp_registry_dir):
    """Create GlobalRegistry instance for testing."""
    return GlobalRegistry(golden_repos_dir=temp_registry_dir)


def test_concurrent_register_operations_serialized(registry):
    """
    Test that concurrent register_global_repo operations are serialized.

    Acceptance Criteria:
    - Multiple concurrent register operations should not corrupt registry
    - Operations should complete in serial order
    - All operations should succeed without race conditions

    NOTE: This test validates locking by verifying all repos are successfully registered
    and that the registry file remains valid JSON throughout concurrent operations.
    The file corruption test provides additional validation of serialization.
    """
    # Run three concurrent register operations
    threads = []
    for i in range(3):

        def register_repo(index=i):
            registry.register_global_repo(
                repo_name=f"test-repo-{index}",
                alias_name=f"test-repo-{index}-global",
                repo_url=f"https://github.com/user/repo{index}.git",
                index_path=f"/path/to/index{index}",
            )

        thread = threading.Thread(target=register_repo, name=f"register_{i}")
        threads.append(thread)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join(timeout=5.0)

    # Verify all threads completed
    assert all(not t.is_alive() for t in threads), "All threads should complete"

    # Verify all three repos were successfully registered
    registry._load_registry()
    assert (
        len([k for k in registry._registry_data.keys() if "test-repo-" in k]) == 3
    ), "All three register operations should succeed"

    # Verify registry file is valid JSON
    with open(registry.registry_file, "r") as f:
        data = json.load(f)
    assert (
        len([k for k in data.keys() if "test-repo-" in k]) == 3
    ), "Registry file should contain all three repos"


def test_concurrent_unregister_operations_serialized(registry):
    """
    Test that concurrent unregister_global_repo operations are serialized.

    Acceptance Criteria:
    - Multiple concurrent unregister operations should not corrupt registry
    - Operations should complete in serial order
    - No race conditions during cleanup

    NOTE: This test validates locking by verifying all repos are successfully unregistered
    and that the registry file remains valid JSON throughout concurrent operations.
    """
    # Pre-populate registry
    for i in range(1, 4):
        registry.register_global_repo(
            repo_name=f"repo{i}",
            alias_name=f"repo{i}-global",
            repo_url=f"https://github.com/user/repo{i}.git",
            index_path=f"/path/to/repo{i}",
        )

    # Run three concurrent unregister operations
    threads = []
    for i in range(1, 4):

        def unregister_repo(index=i):
            registry.unregister_global_repo(alias_name=f"repo{index}-global")

        thread = threading.Thread(target=unregister_repo, name=f"unregister_{i}")
        threads.append(thread)

    # Start all threads
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join(timeout=5.0)

    # Verify all threads completed
    assert all(not t.is_alive() for t in threads), "All threads should complete"

    # Verify all three repos were successfully unregistered
    registry._load_registry()
    assert (
        len(
            [
                k
                for k in registry._registry_data.keys()
                if "repo" in k and "-global" in k
            ]
        )
        == 0
    ), "All three unregister operations should succeed"

    # Verify registry file is valid JSON and empty
    with open(registry.registry_file, "r") as f:
        data = json.load(f)
    assert (
        len([k for k in data.keys() if "repo" in k and "-global" in k]) == 0
    ), "Registry file should have no repos after unregister"


def test_concurrent_register_unregister_serialized(registry):
    """
    Test that concurrent register and unregister operations don't interfere.

    Acceptance Criteria:
    - Register and unregister operations should be serialized
    - No registry corruption from mixed operations
    - Both operation types should complete successfully

    NOTE: This test validates locking by verifying both operations complete successfully
    and the final registry state is consistent (new repo registered, existing repo unregistered).
    """
    # Pre-populate with one repo
    registry.register_global_repo(
        repo_name="existing-repo",
        alias_name="existing-repo-global",
        repo_url="https://github.com/user/existing.git",
        index_path="/path/to/existing",
    )

    # Create threads for register and unregister operations
    def register_operation():
        registry.register_global_repo(
            repo_name="new-repo",
            alias_name="new-repo-global",
            repo_url="https://github.com/user/new.git",
            index_path="/path/to/new",
        )

    def unregister_operation():
        time.sleep(0.01)  # Small delay to ensure register starts first
        registry.unregister_global_repo(alias_name="existing-repo-global")

    register_thread = threading.Thread(target=register_operation)
    unregister_thread = threading.Thread(target=unregister_operation)

    register_thread.start()
    unregister_thread.start()

    register_thread.join(timeout=5.0)
    unregister_thread.join(timeout=5.0)

    # Verify both completed
    assert not register_thread.is_alive(), "Register thread should complete"
    assert not unregister_thread.is_alive(), "Unregister thread should complete"

    # Verify final state is consistent
    registry._load_registry()
    assert "new-repo-global" in registry._registry_data, "New repo should be registered"
    assert (
        "existing-repo-global" not in registry._registry_data
    ), "Existing repo should be unregistered"

    # Verify registry file is valid JSON
    with open(registry.registry_file, "r") as f:
        data = json.load(f)
    assert "new-repo-global" in data, "Registry file should contain new repo"
    assert (
        "existing-repo-global" not in data
    ), "Registry file should not contain removed repo"


def test_registry_file_lock_prevents_corruption(registry):
    """
    Test that registry file lock prevents corruption from concurrent access.

    Acceptance Criteria:
    - Concurrent registry reads/writes should not corrupt file
    - File should remain valid JSON after concurrent operations
    - All writes should be atomic
    """
    # Pre-populate registry
    for i in range(5):
        registry.register_global_repo(
            repo_name=f"repo{i}",
            alias_name=f"repo{i}-global",
            repo_url=f"https://github.com/user/repo{i}.git",
            index_path=f"/path/to/repo{i}",
        )

    # Track registry file state
    registry_snapshots = []
    lock = threading.Lock()

    def concurrent_registry_update(repo_index):
        """Simulate concurrent registry updates."""
        for j in range(3):
            # Read registry
            registry._load_registry()

            # Modify registry
            new_alias = f"repo{repo_index}-updated-{j}-global"
            registry._registry_data[new_alias] = {
                "repo_name": f"repo{repo_index}-updated-{j}",
                "alias_name": new_alias,
                "repo_url": f"https://github.com/user/repo{repo_index}-updated-{j}.git",
                "index_path": f"/path/to/repo{repo_index}-updated-{j}",
                "created_at": "2025-01-01T00:00:00Z",
                "last_refresh": "2025-01-01T00:00:00Z",
                "enable_temporal": False,
                "temporal_options": None,
            }

            # Save registry
            registry._save_registry()

            # Capture snapshot
            with lock:
                with open(registry.registry_file, "r") as f:
                    content = f.read()
                    registry_snapshots.append(content)

            time.sleep(0.01)  # Small delay

    # Run concurrent registry updates
    threads = [
        threading.Thread(target=concurrent_registry_update, args=(i,)) for i in range(3)
    ]

    for t in threads:
        t.start()

    for t in threads:
        t.join(timeout=5.0)

    # Verify all threads completed
    assert all(not t.is_alive() for t in threads), "All threads should complete"

    # Verify all snapshots are valid JSON (no corruption)
    for snapshot in registry_snapshots:
        try:
            json.loads(snapshot)
        except json.JSONDecodeError:
            pytest.fail(f"Registry corruption detected: {snapshot}")

    # Verify final registry is valid and consistent
    registry._load_registry()
    assert isinstance(
        registry._registry_data, dict
    ), "Final registry should be valid dict"


def test_file_lock_released_on_exception(registry):
    """
    Test that file lock is released when registry operations raise exceptions.

    Acceptance Criteria:
    - Lock should be released even if _save_registry fails
    - Lock should be released even if _load_registry fails
    - Subsequent registry operations should succeed after exceptions
    - Python's 'with' context manager guarantees lock release
    """
    # Capture real open() before patching to avoid recursion
    real_open = open

    # Test 1: _save_registry releases lock on exception
    import tempfile as temp_module

    save_call_count = [0]
    real_mkstemp = temp_module.mkstemp

    def failing_mkstemp(*args, **kwargs):
        """Mock mkstemp() that fails on first write attempt."""
        save_call_count[0] += 1
        if save_call_count[0] == 1:
            raise IOError("Disk full - mkstemp failed")
        # Use real mkstemp for subsequent calls
        return real_mkstemp(*args, **kwargs)

    with patch("tempfile.mkstemp", side_effect=failing_mkstemp):
        # First _save_registry should fail and release lock
        # Note: mkstemp() failure raises IOError directly (not wrapped in RuntimeError)
        with pytest.raises(IOError, match="Disk full"):
            registry._save_registry()

        assert save_call_count[0] == 1, "First save attempt should have been made"

        # Second _save_registry should succeed (lock was released by context manager)
        registry._save_registry()
        assert save_call_count[0] == 2, "Second save should succeed (lock was released)"

    # Test 2: _load_registry releases lock on exception
    load_call_count = [0]

    def failing_open_read(*args, **kwargs):
        """Mock open() that fails on first read attempt."""
        load_call_count[0] += 1
        if load_call_count[0] == 1:
            raise IOError("File corrupted - read failed")
        # Use captured real open (not the mocked one)
        return real_open(*args, **kwargs)

    with patch("builtins.open", side_effect=failing_open_read):
        # First _load_registry should fail and release lock
        # Note: _load_registry catches exceptions and starts fresh, so no exception propagates
        registry._load_registry()

        assert load_call_count[0] == 1, "First load attempt should have been made"

        # Second _load_registry should succeed (lock was released by context manager)
        registry._load_registry()
        assert load_call_count[0] == 2, "Second load should succeed (lock was released)"
