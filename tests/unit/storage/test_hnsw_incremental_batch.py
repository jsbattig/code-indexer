"""Unit tests for HNSW incremental batch updates (HNSW-002).

Tests for tracking changed vectors during indexing sessions and
applying incremental HNSW updates at the end of indexing cycles.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any

import numpy as np
import pytest

from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestHNSWIncrementalBatch:
    """Test suite for HNSW incremental batch updates."""

    def create_test_points(self, num_points: int, start_id: int = 0) -> List[Dict[str, Any]]:
        """Create test points with vectors."""
        points = []
        for i in range(num_points):
            point_id = f"test_point_{start_id + i}"
            vector = np.random.rand(1536).tolist()
            points.append({
                "id": point_id,
                "vector": vector,
                "payload": {
                    "path": f"test_file_{start_id + i}.py",
                    "language": "python",
                    "type": "content",
                    "start_line": 1,
                    "end_line": 100,
                }
            })
        return points

    # === AC1: Track Changed Vectors During Indexing Session ===

    def test_track_added_vectors_during_session(self, tmp_path):
        """Test that new vectors are tracked as 'added' during indexing session."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Start indexing session
        store.begin_indexing(collection_name)

        # Verify session tracking was initialized
        assert hasattr(store, "_indexing_session_changes")
        assert collection_name in store._indexing_session_changes
        assert "added" in store._indexing_session_changes[collection_name]
        assert "updated" in store._indexing_session_changes[collection_name]
        assert "deleted" in store._indexing_session_changes[collection_name]

        # Add new points
        points = self.create_test_points(5)
        store.upsert_points(collection_name, points)

        # Verify points were tracked as added
        changes = store._indexing_session_changes[collection_name]
        assert len(changes["added"]) == 5
        assert "test_point_0" in changes["added"]
        assert "test_point_4" in changes["added"]
        assert len(changes["updated"]) == 0
        assert len(changes["deleted"]) == 0

    def test_track_updated_vectors_during_session(self, tmp_path):
        """Test that existing vectors are tracked as 'updated' during indexing session."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index (without session tracking)
        initial_points = self.create_test_points(5)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # Start new indexing session
        store.begin_indexing(collection_name)

        # Update existing points (same IDs, different vectors)
        updated_points = self.create_test_points(3)  # Update first 3 points
        store.upsert_points(collection_name, updated_points)

        # Verify points were tracked as updated
        changes = store._indexing_session_changes[collection_name]
        assert len(changes["updated"]) == 3
        assert "test_point_0" in changes["updated"]
        assert "test_point_2" in changes["updated"]
        assert len(changes["added"]) == 0  # No new points
        assert len(changes["deleted"]) == 0

    def test_track_deleted_vectors_during_session(self, tmp_path):
        """Test that deleted vectors are tracked during indexing session."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index
        initial_points = self.create_test_points(10)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # Start new indexing session
        store.begin_indexing(collection_name)

        # Delete some points
        points_to_delete = ["test_point_2", "test_point_5", "test_point_8"]
        store.delete_points(collection_name, points_to_delete)

        # Verify deletions were tracked
        changes = store._indexing_session_changes[collection_name]
        assert len(changes["deleted"]) == 3
        assert "test_point_2" in changes["deleted"]
        assert "test_point_5" in changes["deleted"]
        assert "test_point_8" in changes["deleted"]
        assert len(changes["added"]) == 0
        assert len(changes["updated"]) == 0

    def test_tracking_cleared_after_end_indexing(self, tmp_path):
        """Test that change tracking is cleared after end_indexing completes."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Start indexing session and add points
        store.begin_indexing(collection_name)
        points = self.create_test_points(5)
        store.upsert_points(collection_name, points)

        # Verify tracking exists
        assert collection_name in store._indexing_session_changes

        # End indexing
        store.end_indexing(collection_name)

        # Verify tracking was cleared
        assert collection_name not in store._indexing_session_changes

    def test_temporal_collection_change_tracking(self, tmp_path):
        """Test that temporal_default collection tracks changes correctly."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "temporal_default"
        store.create_collection(collection_name, vector_size=1536)

        # Start temporal indexing session
        store.begin_indexing(collection_name)

        # Add temporal points
        temporal_points = [{
            "id": f"temporal_vec_{i}",
            "vector": np.random.rand(1536).tolist(),
            "payload": {
                "commit_hash": f"abc123{i}",
                "timestamp": 1234567890 + i,
                "file_path": f"file_{i}.py",
            }
        } for i in range(10)]

        store.upsert_points(collection_name, temporal_points)

        # Verify temporal vectors were tracked
        changes = store._indexing_session_changes[collection_name]
        assert len(changes["added"]) == 10
        assert "temporal_vec_0" in changes["added"]
        assert "temporal_vec_9" in changes["added"]

    # === AC2: Incremental HNSW Update at End of Indexing Cycle ===

    def test_incremental_hnsw_update_vs_full_rebuild(self, tmp_path):
        """Test incremental update is faster than full rebuild."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Create large initial index (1000 vectors)
        initial_points = self.create_test_points(1000)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)

        # Time the initial full rebuild
        start_time = time.time()
        result = store.end_indexing(collection_name)
        full_rebuild_time = time.time() - start_time

        assert result["status"] == "ok"
        assert result["vectors_indexed"] == 1000

        # Now make incremental changes (10 new vectors)
        store.begin_indexing(collection_name)
        incremental_points = self.create_test_points(10, start_id=1000)
        store.upsert_points(collection_name, incremental_points)

        # Time the incremental update
        start_time = time.time()
        result = store.end_indexing(collection_name)
        incremental_time = time.time() - start_time

        assert result["status"] == "ok"
        assert result["vectors_indexed"] == 1010

        # Incremental should be notably faster (at least 2x)
        # Note: In real scenarios with 10K vectors, this would be 5-10x
        assert incremental_time < full_rebuild_time / 2, \
            f"Incremental ({incremental_time:.2f}s) should be faster than full rebuild ({full_rebuild_time:.2f}s)"

        # Verify incremental mode was used
        assert result.get("hnsw_update") == "incremental"

    def test_temporal_collection_incremental_hnsw(self, tmp_path):
        """Test that temporal collection uses incremental HNSW updates."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "temporal_default"
        store.create_collection(collection_name, vector_size=1536)

        # Initial temporal index (1000 vectors simulating historical commits)
        initial_points = [{
            "id": f"temporal_commit_{i}",
            "vector": np.random.rand(1536).tolist(),
            "payload": {
                "commit_hash": f"initial_{i}",
                "timestamp": 1000000000 + i * 100,
                "file_path": f"file_{i % 100}.py",
            }
        } for i in range(1000)]

        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # Incremental temporal index (10 new commits)
        store.begin_indexing(collection_name)
        new_points = [{
            "id": f"temporal_commit_{i}",
            "vector": np.random.rand(1536).tolist(),
            "payload": {
                "commit_hash": f"new_{i}",
                "timestamp": 2000000000 + i * 100,
                "file_path": f"new_file_{i}.py",
            }
        } for i in range(1000, 1010)]

        store.upsert_points(collection_name, new_points)

        # Time the incremental update
        start_time = time.time()
        result = store.end_indexing(collection_name)
        incremental_time = time.time() - start_time

        assert result["status"] == "ok"
        assert result.get("hnsw_update") == "incremental"
        # Should be fast for 10 new vectors out of 1000
        assert incremental_time < 3.0, f"Temporal incremental update took {incremental_time:.2f}s, expected < 3s"

    # === AC4: Auto-Detection of Incremental vs Full Rebuild ===

    def test_auto_detection_full_rebuild_on_first_index(self, tmp_path):
        """Test full rebuild on first index (no session changes)."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # First index without session tracking (simulates first-time index)
        points = self.create_test_points(100)

        # Don't call begin_indexing to simulate legacy behavior
        store.upsert_points(collection_name, points)

        # Should fall back to full rebuild
        result = store.end_indexing(collection_name)

        assert result["status"] == "ok"
        assert result["vectors_indexed"] == 100
        # Should NOT have incremental marker
        assert result.get("hnsw_update") != "incremental"

    def test_auto_detection_incremental_with_changes(self, tmp_path):
        """Test auto-detection chooses incremental when session has changes."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index
        initial_points = self.create_test_points(100)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # Second index with changes
        store.begin_indexing(collection_name)
        new_points = self.create_test_points(5, start_id=100)
        store.upsert_points(collection_name, new_points)

        # Should use incremental update
        result = store.end_indexing(collection_name)

        assert result["status"] == "ok"
        assert result.get("hnsw_update") == "incremental"

    def test_auto_detection_full_rebuild_when_forced(self, tmp_path):
        """Test that full rebuild can be forced when needed."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index with session tracking
        store.begin_indexing(collection_name)
        points = self.create_test_points(100)
        store.upsert_points(collection_name, points)

        # Clear session tracking to force full rebuild
        del store._indexing_session_changes[collection_name]

        # Should use full rebuild
        result = store.end_indexing(collection_name)

        assert result["status"] == "ok"
        assert result.get("hnsw_update") != "incremental"

    # === AC6: Deletion Handling and Soft Delete ===

    def test_deletion_soft_deletes_in_hnsw(self, tmp_path):
        """Test that deleted vectors are soft-deleted in HNSW index."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index with 20 points
        initial_points = self.create_test_points(20)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # Start new session and delete some points
        store.begin_indexing(collection_name)
        points_to_delete = [f"test_point_{i}" for i in [3, 7, 12, 15, 19]]
        store.delete_points(collection_name, points_to_delete)

        # Apply incremental update
        result = store.end_indexing(collection_name)

        assert result["status"] == "ok"
        assert result.get("hnsw_update") == "incremental"

        # Verify deleted points are not returned in searches
        # (Would need to test via search functionality)
        # For now, verify the changes were tracked correctly
        assert collection_name not in store._indexing_session_changes  # Cleared after end

    def test_mixed_operations_tracking(self, tmp_path):
        """Test tracking of mixed add/update/delete operations in single session."""
        # Setup
        store = FilesystemVectorStore(tmp_path, project_root=tmp_path)
        collection_name = "test_collection"
        store.create_collection(collection_name, vector_size=1536)

        # Initial index
        initial_points = self.create_test_points(20)
        store.begin_indexing(collection_name)
        store.upsert_points(collection_name, initial_points)
        store.end_indexing(collection_name)

        # New session with mixed operations
        store.begin_indexing(collection_name)

        # Add new points
        new_points = self.create_test_points(5, start_id=20)
        store.upsert_points(collection_name, new_points)

        # Update existing points
        updated_points = self.create_test_points(3, start_id=5)
        store.upsert_points(collection_name, updated_points)

        # Delete some points
        points_to_delete = [f"test_point_{i}" for i in [0, 10, 15]]
        store.delete_points(collection_name, points_to_delete)

        # Check tracking before end_indexing
        changes = store._indexing_session_changes[collection_name]
        assert len(changes["added"]) == 5
        assert len(changes["updated"]) == 3
        assert len(changes["deleted"]) == 3

        # Apply incremental update
        result = store.end_indexing(collection_name)

        assert result["status"] == "ok"
        assert result.get("hnsw_update") == "incremental"
        assert result["vectors_indexed"] == 22  # 20 + 5 - 3 = 22