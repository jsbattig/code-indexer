"""Unit tests for FilesystemVectorStore incremental update functionality.

Tests change tracking for HNSW-001 (Watch Mode) and HNSW-002 (Batch Mode).
"""

import numpy as np
import pytest
from pathlib import Path
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_base_path(tmp_path):
    """Create temporary base path for vector store."""
    base_path = tmp_path / "vector_store"
    base_path.mkdir(parents=True, exist_ok=True)
    return base_path


@pytest.fixture
def vector_store(temp_base_path):
    """Create FilesystemVectorStore instance."""
    return FilesystemVectorStore(base_path=temp_base_path, project_root=temp_base_path.parent)


@pytest.fixture
def test_collection(vector_store):
    """Create test collection."""
    collection_name = "test_collection"
    vector_size = 128
    vector_store.create_collection(collection_name, vector_size)
    return collection_name


@pytest.fixture
def sample_points():
    """Generate sample points for testing."""
    np.random.seed(42)
    points = []
    for i in range(10):
        vector = np.random.randn(128).astype(np.float32).tolist()
        points.append({
            "id": f"point_{i}",
            "vector": vector,
            "payload": {
                "path": f"file_{i}.py",
                "content": f"content_{i}",
                "line_start": 1,
                "line_end": 10,
                "language": "python"
            }
        })
    return points


class TestChangeTrackingInitialization:
    """Test initialization of change tracking in indexing sessions."""

    def test_begin_indexing_initializes_change_tracking(self, vector_store, test_collection):
        """Test that begin_indexing() initializes _indexing_session_changes."""
        # Attribute should exist (initialized in __init__)
        assert hasattr(vector_store, '_indexing_session_changes')

        # But collection-specific tracking should not exist yet
        assert test_collection not in vector_store._indexing_session_changes

        # Call begin_indexing
        vector_store.begin_indexing(test_collection)

        # Now collection-specific tracking should be initialized
        assert hasattr(vector_store, '_indexing_session_changes')
        assert test_collection in vector_store._indexing_session_changes
        assert 'added' in vector_store._indexing_session_changes[test_collection]
        assert 'updated' in vector_store._indexing_session_changes[test_collection]
        assert 'deleted' in vector_store._indexing_session_changes[test_collection]

    def test_change_tracking_structure(self, vector_store, test_collection):
        """Test that change tracking has correct structure."""
        vector_store.begin_indexing(test_collection)

        # RED: Will fail - change tracking not implemented
        changes = vector_store._indexing_session_changes[test_collection]
        assert isinstance(changes['added'], set)
        assert isinstance(changes['updated'], set)
        assert isinstance(changes['deleted'], set)


class TestUpsertPointsChangeTracking:
    """Test change tracking during upsert_points operations."""

    def test_upsert_new_points_tracks_as_added(self, vector_store, test_collection, sample_points):
        """Test that upserting new points tracks them as 'added'."""
        vector_store.begin_indexing(test_collection)

        # Upsert new points
        vector_store.upsert_points(test_collection, sample_points[:5])

        # RED: Will fail - change tracking not implemented
        changes = vector_store._indexing_session_changes[test_collection]
        assert len(changes['added']) == 5
        assert 'point_0' in changes['added']
        assert 'point_4' in changes['added']
        assert len(changes['updated']) == 0
        assert len(changes['deleted']) == 0

    def test_upsert_existing_points_tracks_as_updated(self, vector_store, test_collection, sample_points):
        """Test that upserting existing points tracks them as 'updated'."""
        # First indexing session
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[:5])
        vector_store.end_indexing(test_collection)

        # Second indexing session - update existing points
        vector_store.begin_indexing(test_collection)
        modified_points = sample_points[:3]
        for point in modified_points:
            point['payload']['content'] = f"modified_{point['id']}"

        vector_store.upsert_points(test_collection, modified_points)

        # RED: Will fail - change tracking not implemented
        changes = vector_store._indexing_session_changes[test_collection]
        assert len(changes['updated']) == 3
        assert 'point_0' in changes['updated']
        assert 'point_2' in changes['updated']
        assert len(changes['added']) == 0

    def test_upsert_without_begin_indexing_no_tracking(self, vector_store, test_collection, sample_points):
        """Test that upsert_points without begin_indexing doesn't track changes."""
        # Upsert without begin_indexing
        vector_store.upsert_points(test_collection, sample_points[:5])

        # Should not have change tracking
        assert not hasattr(vector_store, '_indexing_session_changes') or \
               test_collection not in vector_store._indexing_session_changes


class TestDeletePointsChangeTracking:
    """Test change tracking during delete_points operations."""

    def test_delete_points_tracks_as_deleted(self, vector_store, test_collection, sample_points):
        """Test that deleting points tracks them as 'deleted'."""
        # Index some points first
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[:5])
        vector_store.end_indexing(test_collection)

        # Start new session and delete
        vector_store.begin_indexing(test_collection)
        vector_store.delete_points(test_collection, ['point_0', 'point_1'])

        # RED: Will fail - delete tracking not implemented
        changes = vector_store._indexing_session_changes[test_collection]
        assert len(changes['deleted']) == 2
        assert 'point_0' in changes['deleted']
        assert 'point_1' in changes['deleted']


class TestWatchModeParameter:
    """Test watch_mode parameter in upsert_points."""

    def test_upsert_points_accepts_watch_mode_parameter(self, vector_store, test_collection, sample_points):
        """Test that upsert_points accepts watch_mode parameter."""
        vector_store.begin_indexing(test_collection)

        # RED: Will fail - watch_mode parameter not implemented
        try:
            vector_store.upsert_points(
                test_collection,
                sample_points[:5],
                watch_mode=True
            )
            # If we get here, parameter is accepted
            assert True
        except TypeError as e:
            # Expected failure - parameter doesn't exist yet
            assert "watch_mode" in str(e)
            pytest.fail("watch_mode parameter not implemented in upsert_points")

    def test_watch_mode_triggers_immediate_hnsw_update(self, vector_store, test_collection, sample_points):
        """Test that watch_mode=True triggers immediate HNSW update."""
        vector_store.begin_indexing(test_collection)

        # RED: Will fail - watch mode HNSW update not implemented
        # We'll verify this by checking if HNSW index is updated after upsert
        vector_store.upsert_points(
            test_collection,
            sample_points[:5],
            watch_mode=True
        )

        # In watch mode, HNSW should be updated immediately
        # We'll test this in integration tests with actual HNSW manager


class TestEndIndexingAutoDetection:
    """Test auto-detection logic in end_indexing for incremental vs full rebuild."""

    def test_end_indexing_with_changes_triggers_incremental(self, vector_store, test_collection, sample_points):
        """Test that end_indexing detects changes and uses incremental update."""
        # First, create initial index
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[:5])
        vector_store.end_indexing(test_collection)

        # Now make changes and verify incremental update is used
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[5:10])  # Add 5 more points
        result = vector_store.end_indexing(test_collection)

        # Should indicate incremental update was used (not full rebuild)
        assert 'hnsw_update' in result
        assert result['hnsw_update'] == 'incremental'

    def test_end_indexing_first_index_triggers_full_rebuild(self, vector_store, test_collection, sample_points):
        """Test that end_indexing on first index does full rebuild."""
        # First index without begin_indexing (no change tracking)
        vector_store.upsert_points(test_collection, sample_points[:5])

        result = vector_store.end_indexing(test_collection)

        # Should do full rebuild (no change tracking)
        # Default behavior - should not have 'hnsw_update' key or should be 'full'
        assert result.get('hnsw_update') != 'incremental'

    def test_end_indexing_clears_session_changes(self, vector_store, test_collection, sample_points):
        """Test that end_indexing clears session changes after applying."""
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[:5])

        # RED: Will fail - cleanup not implemented
        result = vector_store.end_indexing(test_collection)

        # Session changes should be cleared
        if hasattr(vector_store, '_indexing_session_changes'):
            assert test_collection not in vector_store._indexing_session_changes


class TestChangeTrackingMultipleSessions:
    """Test change tracking across multiple indexing sessions."""

    def test_multiple_sessions_independent_tracking(self, vector_store, test_collection, sample_points):
        """Test that each session has independent change tracking."""
        # Session 1
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[:3])
        vector_store.end_indexing(test_collection)

        # Session 2
        vector_store.begin_indexing(test_collection)
        vector_store.upsert_points(test_collection, sample_points[3:6])

        # RED: Will fail - should only track session 2 changes
        changes = vector_store._indexing_session_changes[test_collection]
        # Session 2 should only see points 3-5 as added
        # Points 0-2 are already indexed, so they shouldn't be in changes
        assert len(changes['added']) == 3
        assert 'point_3' in changes['added']
        assert 'point_0' not in changes['added']  # From previous session


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
