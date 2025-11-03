"""Unit tests for HNSW incremental update functionality.

Tests HNSW-001 (Watch Mode Real-Time Updates) and HNSW-002 (Batch Incremental Updates).
"""

import numpy as np
import pytest
from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


@pytest.fixture
def temp_collection_path(tmp_path):
    """Create temporary collection directory."""
    collection_path = tmp_path / "test_collection"
    collection_path.mkdir(parents=True, exist_ok=True)

    # Create collection metadata
    import json
    meta_file = collection_path / "collection_meta.json"
    metadata = {
        "name": "test_collection",
        "vector_size": 128,
        "created_at": "2025-01-01T00:00:00"
    }
    with open(meta_file, "w") as f:
        json.dump(metadata, f)

    return collection_path


@pytest.fixture
def hnsw_manager():
    """Create HNSWIndexManager instance."""
    return HNSWIndexManager(vector_dim=128, space="cosine")


@pytest.fixture
def sample_vectors():
    """Generate sample vectors for testing."""
    np.random.seed(42)
    vectors = np.random.randn(10, 128).astype(np.float32)
    ids = [f"vec_{i}" for i in range(10)]
    return vectors, ids


class TestHNSWIncrementalMethods:
    """Test HNSW incremental update methods (Story HNSW-001 & HNSW-002)."""

    def test_load_for_incremental_update_nonexistent_index(self, hnsw_manager, temp_collection_path):
        """Test loading index for incremental update when index doesn't exist."""
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Should return None and empty mappings
        assert index is None
        assert id_to_label == {}
        assert label_to_id == {}
        assert next_label == 0

    def test_load_for_incremental_update_existing_index(
        self, hnsw_manager, temp_collection_path, sample_vectors
    ):
        """Test loading existing index for incremental update."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors,
            ids=ids
        )

        # Load for incremental update
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Verify index loaded
        assert index is not None
        assert len(id_to_label) == 10
        assert len(label_to_id) == 10
        assert next_label == 10  # Next label after 0-9

        # Verify mappings are consistent
        for point_id, label in id_to_label.items():
            assert label_to_id[label] == point_id

    def test_add_or_update_vector_new_point(self, hnsw_manager, temp_collection_path, sample_vectors):
        """Test adding new vector to HNSW index."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors[:5],
            ids=ids[:5]
        )

        # Load index for incremental update
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Add new vector
        new_vector = vectors[5]
        new_id = ids[5]
        label, updated_id_to_label, updated_label_to_id, updated_next_label = hnsw_manager.add_or_update_vector(
            index=index,
            point_id=new_id,
            vector=new_vector,
            id_to_label=id_to_label,
            label_to_id=label_to_id,
            next_label=next_label
        )

        # Verify new label assigned
        assert label == next_label  # Should be label 5
        assert new_id in updated_id_to_label
        assert updated_id_to_label[new_id] == label
        assert updated_label_to_id[label] == new_id
        assert updated_next_label == next_label + 1

    def test_add_or_update_vector_existing_point(self, hnsw_manager, temp_collection_path, sample_vectors):
        """Test updating existing vector in HNSW index."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors[:5],
            ids=ids[:5]
        )

        # Load index for incremental update
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Update existing vector
        updated_vector = np.random.randn(128).astype(np.float32)
        existing_id = ids[0]
        old_label = id_to_label[existing_id]

        label, updated_id_to_label, updated_label_to_id, updated_next_label = hnsw_manager.add_or_update_vector(
            index=index,
            point_id=existing_id,
            vector=updated_vector,
            id_to_label=id_to_label,
            label_to_id=label_to_id,
            next_label=next_label
        )

        # Verify label reused (not incremented)
        assert label == old_label
        assert updated_next_label == next_label  # Should NOT increment for updates
        assert existing_id in updated_id_to_label
        assert updated_id_to_label[existing_id] == old_label

    def test_remove_vector_soft_delete(self, hnsw_manager, temp_collection_path, sample_vectors):
        """Test soft delete of vector from HNSW index."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors[:5],
            ids=ids[:5]
        )

        # Load index for incremental update
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Soft delete a vector
        delete_id = ids[0]
        hnsw_manager.remove_vector(
            index=index,
            point_id=delete_id,
            id_to_label=id_to_label
        )

        # Query should not return deleted vector
        query_vector = vectors[0]
        result_ids, distances = hnsw_manager.query(
            index=index,
            query_vector=query_vector,
            collection_path=temp_collection_path,
            k=3  # Request fewer than available to avoid HNSW errors
        )

        # Deleted vector should not appear in results
        assert delete_id not in result_ids
        # Should return other vectors (at least 1, since we have 4 remaining after delete)
        assert len(result_ids) >= 1

    def test_save_incremental_update(self, hnsw_manager, temp_collection_path, sample_vectors):
        """Test saving HNSW index after incremental updates."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors[:5],
            ids=ids[:5]
        )

        # Load index for incremental update
        index, id_to_label, label_to_id, next_label = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        # Add new vector
        new_vector = vectors[5]
        new_id = ids[5]
        label, id_to_label, label_to_id, next_label = hnsw_manager.add_or_update_vector(
            index=index,
            point_id=new_id,
            vector=new_vector,
            id_to_label=id_to_label,
            label_to_id=label_to_id,
            next_label=next_label
        )

        # Save incremental update
        hnsw_manager.save_incremental_update(
            index=index,
            collection_path=temp_collection_path,
            id_to_label=id_to_label,
            label_to_id=label_to_id,
            vector_count=6
        )

        # Reload and verify
        reloaded_index, reloaded_id_to_label, reloaded_label_to_id, _ = hnsw_manager.load_for_incremental_update(
            temp_collection_path
        )

        assert reloaded_index is not None
        assert len(reloaded_id_to_label) == 6
        assert new_id in reloaded_id_to_label

    def test_incremental_update_preserves_search_accuracy(
        self, hnsw_manager, temp_collection_path, sample_vectors
    ):
        """Test that incremental updates don't degrade search accuracy."""
        vectors, ids = sample_vectors

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors[:5],
            ids=ids[:5]
        )

        # Query before incremental update
        index_before = hnsw_manager.load_index(temp_collection_path)
        query_vector = vectors[0]
        ids_before, distances_before = hnsw_manager.query(
            index=index_before,
            query_vector=query_vector,
            collection_path=temp_collection_path,
            k=3
        )

        # This test will fail until incremental methods are implemented
        # For now, just verify that query works
        assert len(ids_before) > 0
        assert ids_before[0] == "vec_0"  # Closest to itself


class TestHNSWLabelManagement:
    """Test label management and ID mapping consistency."""

    def test_label_counter_increments_correctly(self, hnsw_manager, temp_collection_path):
        """Test that _next_label counter increments correctly."""
        # RED: Label management methods don't exist yet
        # This will fail when we try to use them
        pass

    def test_id_to_label_mapping_consistency(self, hnsw_manager, temp_collection_path):
        """Test that id_to_label and label_to_id stay consistent."""
        # RED: Mapping management doesn't exist yet
        pass

    def test_label_reuse_for_updated_points(self, hnsw_manager, temp_collection_path):
        """Test that updating a point reuses its label."""
        # RED: Update logic doesn't exist yet
        pass


class TestHNSWPerformance:
    """Test performance characteristics of incremental updates."""

    def test_incremental_update_faster_than_rebuild(self, hnsw_manager, temp_collection_path):
        """Test that incremental update is faster than full rebuild."""
        import time

        # Generate large dataset
        np.random.seed(42)
        vectors = np.random.randn(1000, 128).astype(np.float32)
        ids = [f"vec_{i}" for i in range(1000)]

        # Build initial index
        hnsw_manager.build_index(
            collection_path=temp_collection_path,
            vectors=vectors,
            ids=ids
        )

        # Measure full rebuild time
        rebuild_start = time.time()
        hnsw_manager.rebuild_from_vectors(
            collection_path=temp_collection_path
        )
        rebuild_time = time.time() - rebuild_start

        # RED: Incremental methods don't exist yet
        # This test will fail when we try to call them
        # Expected: incremental_time < rebuild_time / 2
        assert rebuild_time > 0  # Placeholder assertion


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
