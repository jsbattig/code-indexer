"""Tests for HNSW index background rebuild integration.

Tests that HNSWIndexManager properly integrates with BackgroundIndexRebuilder
for non-blocking background rebuilds with atomic swaps.
"""

import json
import threading
import time
from pathlib import Path

import numpy as np

from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestHNSWBackgroundRebuild:
    """Test HNSWIndexManager background rebuild functionality."""

    def test_rebuild_from_vectors_uses_background_rebuild(self, tmp_path: Path):
        """Test that rebuild_from_vectors uses background rebuild pattern."""
        # Create test vectors
        num_vectors = 100
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(num_vectors):
            vector = np.random.randn(128).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        # Create metadata
        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 128}, f)

        # Rebuild
        manager = HNSWIndexManager(vector_dim=128)
        count = manager.rebuild_from_vectors(tmp_path)

        assert count == num_vectors

        # Verify index exists
        index_file = tmp_path / "hnsw_index.bin"
        assert index_file.exists()

        # Verify no temp file left behind
        temp_file = tmp_path / "hnsw_index.bin.tmp"
        assert not temp_file.exists()

    def test_concurrent_rebuild_serializes_via_lock(self, tmp_path: Path):
        """Test that concurrent rebuilds are serialized via file lock."""
        # Create test vectors
        num_vectors = 50
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(num_vectors):
            vector = np.random.randn(64).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        # Create metadata
        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 64}, f)

        # Track rebuild timings
        rebuild1_start = threading.Event()
        rebuild1_complete = threading.Event()
        rebuild2_start = threading.Event()
        rebuild2_complete = threading.Event()

        def rebuild1():
            rebuild1_start.set()
            manager = HNSWIndexManager(vector_dim=64)
            manager.rebuild_from_vectors(tmp_path)
            rebuild1_complete.set()

        def rebuild2():
            # Wait for rebuild1 to start
            rebuild1_start.wait(timeout=1.0)
            # Small delay to ensure rebuild1 has lock
            time.sleep(0.05)
            rebuild2_start.set()
            manager = HNSWIndexManager(vector_dim=64)
            manager.rebuild_from_vectors(tmp_path)
            rebuild2_complete.set()

        # Start concurrent rebuilds
        t1 = threading.Thread(target=rebuild1)
        t2 = threading.Thread(target=rebuild2)
        t1.start()
        t2.start()

        # Wait for both to start
        assert rebuild1_start.wait(timeout=1.0)
        assert rebuild2_start.wait(timeout=1.0)

        # Rebuild2 should NOT complete before rebuild1 (serialized by lock)
        time.sleep(0.1)
        if rebuild1_complete.is_set():
            # If rebuild1 completed early, rebuild2 might complete now
            pass
        else:
            # Rebuild1 still running, rebuild2 should be blocked
            assert not rebuild2_complete.is_set()

        # Wait for both to complete
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Both should complete successfully
        assert rebuild1_complete.is_set()
        assert rebuild2_complete.is_set()

        # Final index should exist
        index_file = tmp_path / "hnsw_index.bin"
        assert index_file.exists()

    def test_query_during_rebuild_uses_old_index(self, tmp_path: Path):
        """Test that queries use old index during background rebuild (stale reads)."""
        # Create initial index with 50 vectors
        num_initial = 50
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        initial_vectors = []
        for i in range(num_initial):
            vector = np.random.randn(64).astype(np.float32)
            initial_vectors.append(vector)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        # Create metadata
        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 64}, f)

        # Build initial index
        manager = HNSWIndexManager(vector_dim=64)
        manager.rebuild_from_vectors(tmp_path)

        # Load initial index for querying
        initial_index = manager.load_index(tmp_path, max_elements=1000)
        assert initial_index is not None

        # Add more vectors for rebuild
        for i in range(num_initial, num_initial + 50):
            vector = np.random.randn(64).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        # Start rebuild in background thread
        rebuild_started = threading.Event()
        rebuild_complete = threading.Event()

        def rebuild_worker():
            rebuild_started.set()
            manager2 = HNSWIndexManager(vector_dim=64)
            # Slow rebuild to simulate heavy processing
            time.sleep(0.1)
            manager2.rebuild_from_vectors(tmp_path)
            rebuild_complete.set()

        rebuild_thread = threading.Thread(target=rebuild_worker)
        rebuild_thread.start()

        # Wait for rebuild to start
        assert rebuild_started.wait(timeout=1.0)

        # Query using old index (should work without blocking)
        query_vec = np.random.randn(64).astype(np.float32)
        result_ids, distances = manager.query(initial_index, query_vec, tmp_path, k=10)

        # Query should succeed with old index results
        assert len(result_ids) == 10
        assert all(int(id_val.split("_")[1]) < num_initial for id_val in result_ids)

        # Wait for rebuild to complete
        rebuild_thread.join(timeout=5.0)
        assert rebuild_complete.is_set()

        # Load NEW index after rebuild
        new_index = manager.load_index(tmp_path, max_elements=1000)
        assert new_index is not None

        # New index should have all 100 vectors
        assert new_index.get_current_count() == 100

    def test_rebuild_atomically_swaps_index(self, tmp_path: Path):
        """Test that rebuild atomically swaps index file."""
        # Create initial small index
        num_initial = 10
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(num_initial):
            vector = np.random.randn(64).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 64}, f)

        # Build initial index
        manager = HNSWIndexManager(vector_dim=64)
        manager.rebuild_from_vectors(tmp_path)

        index_file = tmp_path / "hnsw_index.bin"
        initial_size = index_file.stat().st_size

        # Add more vectors
        for i in range(num_initial, num_initial + 40):
            vector = np.random.randn(64).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        # Rebuild
        manager.rebuild_from_vectors(tmp_path)

        # Index file should be larger (more vectors)
        new_size = index_file.stat().st_size
        assert new_size > initial_size

        # Temp file should be cleaned up
        temp_file = tmp_path / "hnsw_index.bin.tmp"
        assert not temp_file.exists()

    def test_rebuild_failure_cleans_up_temp_file(self, tmp_path: Path):
        """Test that failed rebuild cleans up temp file."""
        # Create invalid vector files (will cause rebuild to fail)
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        vector_file = vectors_dir / "vector_0.json"
        with open(vector_file, "w") as f:
            json.dump({"id": "vec_0"}, f)  # Missing 'vector' key

        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 64}, f)

        # Try to rebuild (should fail gracefully)
        manager = HNSWIndexManager(vector_dim=64)
        count = manager.rebuild_from_vectors(tmp_path)

        # Should return 0 (no valid vectors)
        assert count == 0

        # Temp file should NOT exist
        temp_file = tmp_path / "hnsw_index.bin.tmp"
        assert not temp_file.exists()

    def test_rebuild_metadata_updated_after_swap(self, tmp_path: Path):
        """Test that metadata is updated after atomic swap."""
        num_vectors = 50
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        for i in range(num_vectors):
            vector = np.random.randn(128).astype(np.float32)
            vector_file = vectors_dir / f"vector_{i}.json"
            with open(vector_file, "w") as f:
                json.dump({"id": f"vec_{i}", "vector": vector.tolist()}, f)

        meta_file = tmp_path / "collection_meta.json"
        with open(meta_file, "w") as f:
            json.dump({"vector_dim": 128}, f)

        # Rebuild
        manager = HNSWIndexManager(vector_dim=128)
        manager.rebuild_from_vectors(tmp_path)

        # Check metadata was updated
        stats = manager.get_index_stats(tmp_path)
        assert stats is not None
        assert stats["vector_count"] == num_vectors
        assert "last_rebuild" in stats
        assert stats.get("is_stale") is False  # Fresh after rebuild
