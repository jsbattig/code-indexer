"""Concurrency and lock safety tests for FilesystemVectorStore.

Tests for HIGH PRIORITY BUG #2: Nested locks with I/O operations.
Story #540 Code Review Fix.
"""

import pytest
import tempfile
import numpy as np
import threading
import time
from pathlib import Path
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestConcurrentUpserts:
    """Test concurrent upsert operations don't cause deadlock or corruption."""

    def test_concurrent_upserts_different_files_no_deadlock(self):
        """Concurrent upserts of different files should not deadlock.

        This tests that the lock refactoring properly releases locks
        before performing I/O operations, allowing concurrent upserts
        of different files to proceed without blocking each other excessively.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Initial state: Index two files
            initial_points = [
                {
                    "id": "auth_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                },
                {
                    "id": "utils_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/utils.py", "chunk_index": 0},
                },
            ]
            store.upsert_points("test_collection", initial_points)

            # Now try concurrent updates of different files
            errors = []
            completed = []

            def update_auth():
                try:
                    auth_points = [
                        {
                            "id": "auth_new_0",
                            "vector": np.random.rand(1024).tolist(),
                            "payload": {"path": "src/auth.py", "chunk_index": 0},
                        }
                    ]
                    store.upsert_points("test_collection", auth_points)
                    completed.append("auth")
                except Exception as e:
                    errors.append(("auth", e))

            def update_utils():
                try:
                    utils_points = [
                        {
                            "id": "utils_new_0",
                            "vector": np.random.rand(1024).tolist(),
                            "payload": {"path": "src/utils.py", "chunk_index": 0},
                        }
                    ]
                    store.upsert_points("test_collection", utils_points)
                    completed.append("utils")
                except Exception as e:
                    errors.append(("utils", e))

            # Start both threads
            t1 = threading.Thread(target=update_auth)
            t2 = threading.Thread(target=update_utils)

            start_time = time.time()
            t1.start()
            t2.start()

            # Wait with timeout to detect deadlock
            timeout = 10  # 10 seconds should be plenty
            t1.join(timeout=timeout)
            t2.join(timeout=timeout)
            elapsed = time.time() - start_time

            # Verify no deadlock occurred
            assert not t1.is_alive(), "Thread 1 (auth) deadlocked or timed out"
            assert not t2.is_alive(), "Thread 2 (utils) deadlocked or timed out"
            assert elapsed < timeout, f"Operations took {elapsed}s, potential deadlock"

            # Verify no errors
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(completed) == 2, f"Both operations should complete: {completed}"

            # Verify both files updated correctly
            collection_path = base_path / "test_collection"
            auth_new = list(collection_path.rglob("vector_auth_new_*.json"))
            utils_new = list(collection_path.rglob("vector_utils_new_*.json"))
            auth_old = list(collection_path.rglob("vector_auth_0.json"))
            utils_old = list(collection_path.rglob("vector_utils_0.json"))

            assert len(auth_new) == 1, "Auth should have new vector"
            assert len(utils_new) == 1, "Utils should have new vector"
            assert len(auth_old) == 0, "Auth old vector should be deleted"
            assert len(utils_old) == 0, "Utils old vector should be deleted"

    def test_concurrent_upserts_same_file_sequential_consistency(self):
        """Concurrent upserts of the SAME file should maintain consistency.

        While concurrent upserts of the same file will serialize due to locks,
        they should not deadlock and the final state should be consistent.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Initial state
            initial_points = [
                {
                    "id": "auth_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/auth.py", "chunk_index": 0},
                }
            ]
            store.upsert_points("test_collection", initial_points)

            # Concurrent updates of same file (will serialize)
            errors = []
            completed = []

            def update_1():
                try:
                    points = [
                        {
                            "id": "auth_v1",
                            "vector": np.random.rand(1024).tolist(),
                            "payload": {"path": "src/auth.py", "chunk_index": 0},
                        }
                    ]
                    store.upsert_points("test_collection", points)
                    completed.append("v1")
                except Exception as e:
                    errors.append(("v1", e))

            def update_2():
                try:
                    points = [
                        {
                            "id": "auth_v2",
                            "vector": np.random.rand(1024).tolist(),
                            "payload": {"path": "src/auth.py", "chunk_index": 0},
                        }
                    ]
                    store.upsert_points("test_collection", points)
                    completed.append("v2")
                except Exception as e:
                    errors.append(("v2", e))

            t1 = threading.Thread(target=update_1)
            t2 = threading.Thread(target=update_2)

            start_time = time.time()
            t1.start()
            t2.start()

            timeout = 10
            t1.join(timeout=timeout)
            t2.join(timeout=timeout)
            elapsed = time.time() - start_time

            # Verify no deadlock
            assert not t1.is_alive(), "Thread 1 deadlocked"
            assert not t2.is_alive(), "Thread 2 deadlocked"
            assert elapsed < timeout, f"Operations took {elapsed}s, potential deadlock"

            # Verify no errors
            assert len(errors) == 0, f"Errors occurred: {errors}"
            assert len(completed) == 2, "Both updates should complete"

            # Verify final state is consistent (one of the two versions won)
            collection_path = base_path / "test_collection"
            all_vectors = list(collection_path.rglob("vector_*.json"))

            # Should have exactly one vector (either v1 or v2, not both)
            assert len(all_vectors) == 1, f"Should have exactly 1 vector, found {len(all_vectors)}"

            # Verify path index is consistent
            path_index = store._path_indexes["test_collection"]
            point_ids = path_index.get_point_ids("src/auth.py")
            assert len(point_ids) == 1, "Path index should have exactly 1 point"
            assert point_ids in [{"auth_v1"}, {"auth_v2"}], "Should be one of the versions"

    def test_lock_hold_time_reasonable(self):
        """Lock hold time should be minimal (gather data, release, do I/O).

        This test verifies that the lock refactoring reduces lock hold time
        by releasing locks before I/O operations.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Create a large number of old vectors to delete (simulates I/O load)
            old_points = [
                {
                    "id": f"old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/file.py", "chunk_index": i},
                }
                for i in range(50)  # 50 old vectors to delete
            ]
            store.upsert_points("test_collection", old_points)

            # New upsert with just 1 vector (should delete 49 old ones)
            new_points = [
                {
                    "id": "new_0",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/file.py", "chunk_index": 0},
                }
            ]

            # Measure time for upsert (includes cleanup of 49 vectors)
            start_time = time.time()
            store.upsert_points("test_collection", new_points)
            elapsed = time.time() - start_time

            # Verify operation completed in reasonable time
            # Even with 49 deletions, should be fast (< 5 seconds)
            assert elapsed < 5.0, f"Upsert took {elapsed}s, lock contention suspected"

            # Verify cleanup worked
            collection_path = base_path / "test_collection"
            old_vectors = list(collection_path.rglob("vector_old_*.json"))
            new_vectors = list(collection_path.rglob("vector_new_*.json"))

            assert len(old_vectors) == 0, "All old vectors should be deleted"
            assert len(new_vectors) == 1, "New vector should exist"

    def test_no_nested_lock_exception_during_cleanup(self):
        """Verify cleanup doesn't cause nested lock exceptions.

        This test ensures that the refactored cleanup logic doesn't
        cause lock ordering issues or exceptions during nested lock acquisition.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            store = FilesystemVectorStore(base_path=base_path)

            store.create_collection("test_collection", vector_size=1024)
            store.begin_indexing("test_collection")

            # Initial vectors
            old_points = [
                {
                    "id": f"old_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/file.py", "chunk_index": i},
                }
                for i in range(10)
            ]
            store.upsert_points("test_collection", old_points)

            # Upsert new vectors (should trigger cleanup with nested locks)
            new_points = [
                {
                    "id": f"new_{i}",
                    "vector": np.random.rand(1024).tolist(),
                    "payload": {"path": "src/file.py", "chunk_index": i},
                }
                for i in range(10)
            ]

            # This should complete without raising any lock-related exceptions
            try:
                store.upsert_points("test_collection", new_points)
            except Exception as e:
                pytest.fail(f"Upsert raised exception (possible lock issue): {e}")

            # Verify cleanup worked
            collection_path = base_path / "test_collection"
            old_vectors = list(collection_path.rglob("vector_old_*.json"))
            new_vectors = list(collection_path.rglob("vector_new_*.json"))

            assert len(old_vectors) == 0
            assert len(new_vectors) == 10
