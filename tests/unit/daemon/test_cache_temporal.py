"""Unit tests for CacheEntry temporal cache functionality.

Tests verify that CacheEntry correctly handles temporal HNSW index caching
using the IDENTICAL pattern as HEAD collection caching.
"""

import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from src.code_indexer.daemon.cache import CacheEntry


class TestCacheEntryTemporalFields(TestCase):
    """Test CacheEntry temporal cache field extensions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_has_temporal_hnsw_index_field(self):
        """CacheEntry should have temporal_hnsw_index field initialized to None."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 1: CacheEntry extended with temporal cache fields
        assert hasattr(cache_entry, "temporal_hnsw_index")
        assert cache_entry.temporal_hnsw_index is None

    def test_cache_entry_has_temporal_id_mapping_field(self):
        """CacheEntry should have temporal_id_mapping field initialized to None."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 1: CacheEntry extended with temporal cache fields
        assert hasattr(cache_entry, "temporal_id_mapping")
        assert cache_entry.temporal_id_mapping is None

    def test_cache_entry_has_temporal_index_version_field(self):
        """CacheEntry should have temporal_index_version field initialized to None."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 1: CacheEntry extended with temporal cache fields
        assert hasattr(cache_entry, "temporal_index_version")
        assert cache_entry.temporal_index_version is None


class TestLoadTemporalIndexes(TestCase):
    """Test load_temporal_indexes() method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Create temporal collection structure
        self.temporal_collection_path = (
            self.project_path / ".code-indexer" / "index" / "code-indexer-temporal"
        )
        self.temporal_collection_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_has_load_temporal_indexes_method(self):
        """CacheEntry should have load_temporal_indexes() method."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 2: load_temporal_indexes() method exists
        assert hasattr(cache_entry, "load_temporal_indexes")
        assert callable(cache_entry.load_temporal_indexes)

    @patch("code_indexer.storage.id_index_manager.IDIndexManager")
    @patch("code_indexer.storage.hnsw_index_manager.HNSWIndexManager")
    def test_load_temporal_indexes_calls_hnsw_manager(
        self, mock_hnsw_manager_class, mock_id_manager_class
    ):
        """load_temporal_indexes() should use HNSWIndexManager.load_index()."""
        # Acceptance Criterion 2: load_temporal_indexes() method using mmap

        # Create mock HNSW manager and index
        mock_hnsw_manager = MagicMock()
        mock_hnsw_index = MagicMock()
        mock_hnsw_manager.load_index.return_value = mock_hnsw_index
        mock_hnsw_manager_class.return_value = mock_hnsw_manager

        # Create mock ID manager and mapping
        mock_id_manager = MagicMock()
        mock_id_mapping = {"0": {"file_path": "test.py", "chunk_index": 0}}
        mock_id_manager.load_index.return_value = mock_id_mapping
        mock_id_manager_class.return_value = mock_id_manager

        # Create collection metadata
        metadata = {
            "vector_size": 1536,
            "hnsw_index": {"index_rebuild_uuid": "test-uuid-123"},
        }
        metadata_file = self.temporal_collection_path / "collection_meta.json"
        metadata_file.write_text(json.dumps(metadata))

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Load temporal indexes
        cache_entry.load_temporal_indexes(self.temporal_collection_path)

        # Verify HNSWIndexManager was created with correct constructor signature
        # HNSWIndexManager(vector_dim, space) NOT HNSWIndexManager(collection_path)
        mock_hnsw_manager_class.assert_called_once_with(vector_dim=1536, space="cosine")

        # Verify load_index() was called with collection path
        mock_hnsw_manager.load_index.assert_called_once_with(
            self.temporal_collection_path, max_elements=100000
        )

        # Verify IDIndexManager was created and load_index() called
        mock_id_manager_class.assert_called_once()
        mock_id_manager.load_index.assert_called_once_with(
            self.temporal_collection_path
        )

        # Verify temporal cache fields are populated
        assert cache_entry.temporal_hnsw_index is mock_hnsw_index
        assert cache_entry.temporal_id_mapping is mock_id_mapping
        assert cache_entry.temporal_index_version == "test-uuid-123"

    @patch("code_indexer.storage.id_index_manager.IDIndexManager")
    @patch("code_indexer.storage.hnsw_index_manager.HNSWIndexManager")
    def test_load_temporal_indexes_skips_if_already_loaded(
        self, mock_hnsw_manager_class, mock_id_manager_class
    ):
        """load_temporal_indexes() should skip loading if already loaded."""
        # Acceptance Criterion 2: Idempotent loading

        mock_hnsw_manager = MagicMock()
        mock_hnsw_index = MagicMock()
        mock_hnsw_manager.load_index.return_value = mock_hnsw_index
        mock_hnsw_manager_class.return_value = mock_hnsw_manager

        mock_id_manager = MagicMock()
        mock_id_mapping = {"0": {"file_path": "test.py"}}
        mock_id_manager.load_index.return_value = mock_id_mapping
        mock_id_manager_class.return_value = mock_id_manager

        # Create metadata
        metadata = {"vector_size": 1536, "hnsw_index": {"index_rebuild_uuid": "uuid1"}}
        metadata_file = self.temporal_collection_path / "collection_meta.json"
        metadata_file.write_text(json.dumps(metadata))

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Load once
        cache_entry.load_temporal_indexes(self.temporal_collection_path)
        assert mock_hnsw_manager.load_index.call_count == 1
        assert mock_id_manager.load_index.call_count == 1

        # Load again - should skip
        cache_entry.load_temporal_indexes(self.temporal_collection_path)

        # Should still be called only once (skipped second call)
        assert mock_hnsw_manager.load_index.call_count == 1
        assert mock_id_manager.load_index.call_count == 1

    def test_load_temporal_indexes_raises_on_missing_collection(self):
        """load_temporal_indexes() should raise error if collection doesn't exist."""
        # Acceptance Criterion 2: Error handling for missing collection

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        non_existent_path = self.project_path / "non_existent_collection"

        # Should raise FileNotFoundError or similar
        with self.assertRaises((FileNotFoundError, OSError)):
            cache_entry.load_temporal_indexes(non_existent_path)

        # Temporal cache should remain None
        assert cache_entry.temporal_hnsw_index is None
        assert cache_entry.temporal_id_mapping is None


class TestInvalidateTemporal(TestCase):
    """Test invalidate_temporal() method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_has_invalidate_temporal_method(self):
        """CacheEntry should have invalidate_temporal() method."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 3: invalidate_temporal() method exists
        assert hasattr(cache_entry, "invalidate_temporal")
        assert callable(cache_entry.invalidate_temporal)

    def test_invalidate_temporal_clears_all_temporal_fields(self):
        """invalidate_temporal() should clear all temporal cache fields."""
        # Acceptance Criterion 3: invalidate_temporal() with cleanup

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Set temporal fields (simulating loaded cache)
        cache_entry.temporal_hnsw_index = MagicMock()
        cache_entry.temporal_id_mapping = {"0": {"file_path": "test.py"}}
        cache_entry.temporal_index_version = "uuid-123"

        # Invalidate
        cache_entry.invalidate_temporal()

        # All temporal fields should be None
        assert cache_entry.temporal_hnsw_index is None
        assert cache_entry.temporal_id_mapping is None
        assert cache_entry.temporal_index_version is None

    def test_invalidate_temporal_does_not_affect_head_cache(self):
        """invalidate_temporal() should not affect HEAD collection cache."""
        # Acceptance Criterion 3: Temporal and HEAD cache isolation

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Set both HEAD and temporal fields
        cache_entry.hnsw_index = MagicMock()  # HEAD cache
        cache_entry.id_mapping = {"0": {"file_path": "head.py"}}
        cache_entry.temporal_hnsw_index = MagicMock()  # Temporal cache
        cache_entry.temporal_id_mapping = {"0": {"file_path": "temporal.py"}}

        # Invalidate temporal only
        cache_entry.invalidate_temporal()

        # Temporal should be None
        assert cache_entry.temporal_hnsw_index is None
        assert cache_entry.temporal_id_mapping is None

        # HEAD should be unchanged
        assert cache_entry.hnsw_index is not None
        assert cache_entry.id_mapping is not None


class TestIsTemporalStaleAfterRebuild(TestCase):
    """Test is_temporal_stale_after_rebuild() method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

        self.temporal_collection_path = (
            self.project_path / ".code-indexer" / "index" / "code-indexer-temporal"
        )
        self.temporal_collection_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_has_is_temporal_stale_after_rebuild_method(self):
        """CacheEntry should have is_temporal_stale_after_rebuild() method."""
        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Acceptance Criterion 4: temporal_index_version tracking
        assert hasattr(cache_entry, "is_temporal_stale_after_rebuild")
        assert callable(cache_entry.is_temporal_stale_after_rebuild)

    def test_is_temporal_stale_returns_false_if_not_loaded(self):
        """is_temporal_stale_after_rebuild() should return False if cache not loaded."""
        # Acceptance Criterion 4: Not stale if not loaded

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Temporal cache not loaded (version is None)
        assert cache_entry.temporal_index_version is None

        # Should return False (not stale, just not loaded)
        result = cache_entry.is_temporal_stale_after_rebuild(
            self.temporal_collection_path
        )
        assert result is False

    def test_is_temporal_stale_returns_false_if_version_matches(self):
        """is_temporal_stale_after_rebuild() should return False if versions match."""
        # Acceptance Criterion 4: Not stale if version matches

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Create metadata with version
        metadata = {"hnsw_index": {"index_rebuild_uuid": "uuid-v1"}}
        metadata_file = self.temporal_collection_path / "collection_meta.json"
        metadata_file.write_text(json.dumps(metadata))

        # Set cached version to match
        cache_entry.temporal_index_version = "uuid-v1"

        # Should return False (versions match, not stale)
        result = cache_entry.is_temporal_stale_after_rebuild(
            self.temporal_collection_path
        )
        assert result is False

    def test_is_temporal_stale_returns_true_if_version_differs(self):
        """is_temporal_stale_after_rebuild() should return True if versions differ."""
        # Acceptance Criterion 4: Stale if version differs (rebuild detected)

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Create metadata with NEW version
        metadata = {"hnsw_index": {"index_rebuild_uuid": "uuid-v2"}}
        metadata_file = self.temporal_collection_path / "collection_meta.json"
        metadata_file.write_text(json.dumps(metadata))

        # Set cached version to OLD version
        cache_entry.temporal_index_version = "uuid-v1"

        # Should return True (rebuild detected, cache is stale)
        result = cache_entry.is_temporal_stale_after_rebuild(
            self.temporal_collection_path
        )
        assert result is True


class TestGetStatsWithTemporal(TestCase):
    """Test get_stats() includes temporal cache information."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_get_stats_includes_temporal_loaded_field(self):
        """get_stats() should include temporal_loaded field."""
        # Acceptance Criterion 1: Extended stats

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        stats = cache_entry.get_stats()

        assert "temporal_loaded" in stats
        assert stats["temporal_loaded"] is False  # Not loaded yet

    def test_get_stats_includes_temporal_version_field(self):
        """get_stats() should include temporal_version field."""
        # Acceptance Criterion 1: Extended stats

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        stats = cache_entry.get_stats()

        assert "temporal_version" in stats
        assert stats["temporal_version"] is None  # Not loaded yet

    def test_get_stats_shows_temporal_loaded_when_cache_active(self):
        """get_stats() should show temporal_loaded=True when cache is active."""
        # Acceptance Criterion 1: Extended stats reflect cache state

        cache_entry = CacheEntry(self.project_path, ttl_minutes=10)

        # Simulate loaded temporal cache
        cache_entry.temporal_hnsw_index = MagicMock()
        cache_entry.temporal_id_mapping = {"0": {"file_path": "test.py"}}
        cache_entry.temporal_index_version = "uuid-abc"

        stats = cache_entry.get_stats()

        assert stats["temporal_loaded"] is True
        assert stats["temporal_version"] == "uuid-abc"
