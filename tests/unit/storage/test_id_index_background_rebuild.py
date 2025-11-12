"""Tests for ID index background rebuild integration.

Tests that IDIndexManager properly integrates with BackgroundIndexRebuilder
for non-blocking background rebuilds with atomic swaps.
"""

import json
import struct
import threading
import time
from pathlib import Path


from code_indexer.storage.id_index_manager import IDIndexManager


class TestIDIndexBackgroundRebuild:
    """Test IDIndexManager background rebuild functionality."""

    def test_rebuild_from_vectors_uses_background_rebuild(self, tmp_path: Path):
        """Test that rebuild_from_vectors uses background rebuild pattern."""
        # Create test vector files
        num_vectors = 50
        for i in range(num_vectors):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2, 0.3]}, f)

        # Rebuild
        manager = IDIndexManager()
        id_index = manager.rebuild_from_vectors(tmp_path)

        assert len(id_index) == num_vectors

        # Verify index file exists
        index_file = tmp_path / "id_index.bin"
        assert index_file.exists()

        # Verify no temp file left behind
        temp_file = tmp_path / "id_index.bin.tmp"
        assert not temp_file.exists()

    def test_concurrent_rebuild_serializes_via_lock(self, tmp_path: Path):
        """Test that concurrent rebuilds are serialized via file lock."""
        # Create test vector files
        num_vectors = 30
        for i in range(num_vectors):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Track rebuild timings
        rebuild1_complete = threading.Event()
        rebuild2_complete = threading.Event()
        rebuild1_started = threading.Event()

        def rebuild1():
            rebuild1_started.set()
            manager = IDIndexManager()
            manager.rebuild_from_vectors(tmp_path)
            rebuild1_complete.set()

        def rebuild2():
            # Wait for rebuild1 to start
            rebuild1_started.wait(timeout=1.0)
            time.sleep(0.05)  # Ensure rebuild1 has lock
            manager = IDIndexManager()
            manager.rebuild_from_vectors(tmp_path)
            rebuild2_complete.set()

        # Start concurrent rebuilds
        t1 = threading.Thread(target=rebuild1)
        t2 = threading.Thread(target=rebuild2)
        t1.start()
        t2.start()

        # Wait for completion
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Both should complete successfully
        assert rebuild1_complete.is_set()
        assert rebuild2_complete.is_set()

        # Final index should exist
        index_file = tmp_path / "id_index.bin"
        assert index_file.exists()

    def test_rebuild_atomically_swaps_index(self, tmp_path: Path):
        """Test that rebuild atomically swaps index file."""
        # Create initial small index
        num_initial = 10
        for i in range(num_initial):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Build initial index
        manager = IDIndexManager()
        manager.rebuild_from_vectors(tmp_path)

        index_file = tmp_path / "id_index.bin"
        initial_size = index_file.stat().st_size

        # Add more vectors
        for i in range(num_initial, num_initial + 40):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Rebuild
        manager.rebuild_from_vectors(tmp_path)

        # Index file should be larger (more entries)
        new_size = index_file.stat().st_size
        assert new_size > initial_size

        # Temp file should be cleaned up
        temp_file = tmp_path / "id_index.bin.tmp"
        assert not temp_file.exists()

    def test_load_index_during_rebuild_uses_old_index(self, tmp_path: Path):
        """Test that loads use old index during background rebuild."""
        # Create initial index with 20 vectors
        num_initial = 20
        for i in range(num_initial):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Build initial index
        manager = IDIndexManager()
        manager.rebuild_from_vectors(tmp_path)

        # Load initial index
        initial_index = manager.load_index(tmp_path)
        assert len(initial_index) == num_initial

        # Add more vectors for rebuild
        for i in range(num_initial, num_initial + 30):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Start rebuild in background
        rebuild_complete = threading.Event()

        def rebuild_worker():
            manager2 = IDIndexManager()
            time.sleep(0.1)  # Simulate slow rebuild
            manager2.rebuild_from_vectors(tmp_path)
            rebuild_complete.set()

        rebuild_thread = threading.Thread(target=rebuild_worker)
        rebuild_thread.start()

        # Load during rebuild (should get old index without blocking)
        time.sleep(0.05)
        during_rebuild_index = manager.load_index(tmp_path)

        # Should still see old index (20 entries)
        assert len(during_rebuild_index) == num_initial

        # Wait for rebuild to complete
        rebuild_thread.join(timeout=5.0)
        assert rebuild_complete.is_set()

        # Load NEW index after rebuild
        new_index = manager.load_index(tmp_path)
        assert len(new_index) == 50  # All vectors

    def test_rebuild_binary_format_correctness(self, tmp_path: Path):
        """Test that rebuild produces correct binary format."""
        # Create vector files
        num_vectors = 25
        for i in range(num_vectors):
            vector_file = tmp_path / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": [0.1, 0.2]}, f)

        # Rebuild
        manager = IDIndexManager()
        manager.rebuild_from_vectors(tmp_path)

        # Verify binary format
        index_file = tmp_path / "id_index.bin"
        with open(index_file, "rb") as f:
            # Read header
            num_entries = struct.unpack("<I", f.read(4))[0]
            assert num_entries == num_vectors

            # Read first entry to verify format
            id_len = struct.unpack("<H", f.read(2))[0]
            id_str = f.read(id_len).decode("utf-8")
            path_len = struct.unpack("<H", f.read(2))[0]
            path_str = f.read(path_len).decode("utf-8")

            # Verify structure
            assert id_str.startswith("vec_")
            assert path_str.endswith(".json")
