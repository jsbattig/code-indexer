"""Unit tests for dynamic HNSW sizing and resize functionality.

Tests the fix for the critical bug where HNSW index crashes with "exceeds the specified limit"
when repositories exceed 100K chunks due to hardcoded max_elements=100000.

Test Coverage:
- Dynamic max_elements calculation
- Proactive resize triggering (80% threshold)
- Metadata storage of max_elements
- Crash recovery with automatic resize
- Growth simulation without large repos
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from code_indexer.storage.hnsw_index_manager import HNSWIndexManager


class TestDynamicMaxElementsCalculation:
    """Test dynamic calculation of max_elements based on current count."""

    def test_calculate_max_elements_empty_index(self):
        """Test calculation for empty index returns minimum threshold."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # Empty index should use minimum threshold (100k)
        max_elements = manager.calculate_dynamic_max_elements(current_count=0)

        assert max_elements == 100000, "Empty index should use 100K minimum"

    def test_calculate_max_elements_with_growth_factor(self):
        """Test calculation applies 1.5x growth factor when above minimum."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 80K vectors * 1.5 = 120K max_elements (above 100K minimum)
        max_elements = manager.calculate_dynamic_max_elements(current_count=80000)

        assert max_elements == 120000, "Should apply 1.5x growth factor when above minimum"

    def test_calculate_max_elements_respects_minimum(self):
        """Test calculation respects minimum threshold of 100K."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 60K vectors * 1.5 = 90K, but minimum is 100K
        max_elements = manager.calculate_dynamic_max_elements(current_count=60000)

        assert max_elements == 100000, "Should respect 100K minimum"

    def test_calculate_max_elements_large_repo(self):
        """Test calculation for large repositories (>100K vectors)."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 200K vectors should suggest 300K max_elements (200K * 1.5)
        max_elements = manager.calculate_dynamic_max_elements(current_count=200000)

        assert max_elements == 300000, "Should handle large repos with growth factor"


class TestProactiveResizeTrigger:
    """Test proactive resize triggering when index reaches 80% capacity."""

    def test_should_resize_when_below_threshold(self):
        """Test should_resize returns False when well below threshold."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 50K out of 100K = 50% utilization
        should_resize = manager.should_resize(
            current_count=50000, max_elements=100000
        )

        assert not should_resize, "Should not resize at 50% utilization"

    def test_should_resize_at_threshold(self):
        """Test should_resize returns True at 80% threshold."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 80K out of 100K = 80% utilization (threshold)
        should_resize = manager.should_resize(
            current_count=80000, max_elements=100000
        )

        assert should_resize, "Should resize at 80% threshold"

    def test_should_resize_above_threshold(self):
        """Test should_resize returns True when above threshold."""
        manager = HNSWIndexManager(vector_dim=128, space="cosine")

        # 90K out of 100K = 90% utilization
        should_resize = manager.should_resize(
            current_count=90000, max_elements=100000
        )

        assert should_resize, "Should resize above 80% threshold"


class TestMetadataStorageMaxElements:
    """Test metadata storage and retrieval of max_elements."""

    def test_metadata_includes_max_elements_on_build(self):
        """Test build_index stores max_elements in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build index with 1000 vectors
            vectors = np.random.rand(1000, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(1000)]

            manager.build_index(
                collection_path=collection_path,
                vectors=vectors,
                ids=ids,
            )

            # Read metadata
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            assert "hnsw_index" in metadata
            assert "max_elements" in metadata["hnsw_index"]
            assert metadata["hnsw_index"]["max_elements"] >= 1000

    def test_metadata_includes_max_elements_on_incremental_save(self):
        """Test save_incremental_update stores max_elements in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build initial index
            vectors = np.random.rand(100, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(100)]
            manager.build_index(collection_path, vectors, ids)

            # Load for incremental update
            index, id_to_label, label_to_id, next_label = (
                manager.load_for_incremental_update(collection_path)
            )

            # Add one more vector
            new_vector = np.random.rand(128).astype(np.float32)
            label, id_to_label, label_to_id, next_label = manager.add_or_update_vector(
                index, "vec_100", new_vector, id_to_label, label_to_id, next_label
            )

            # Save with updated max_elements
            manager.save_incremental_update(
                index, collection_path, id_to_label, label_to_id, vector_count=101
            )

            # Read metadata
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            assert "max_elements" in metadata["hnsw_index"]


class TestLoadIndexWithDynamicMaxElements:
    """Test load_index reads max_elements from metadata and applies it."""

    def test_load_index_uses_metadata_max_elements(self):
        """Test load_index uses max_elements from metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build index with specific max_elements in metadata
            vectors = np.random.rand(100, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(100)]
            manager.build_index(collection_path, vectors, ids)

            # Manually update metadata to simulate larger max_elements
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            metadata["hnsw_index"]["max_elements"] = 150000

            with open(meta_file, "w") as f:
                json.dump(metadata, f)

            # Load index without specifying max_elements
            index = manager.load_index(collection_path)

            # Verify index was loaded (should not crash)
            assert index is not None
            assert index.get_current_count() == 100

    def test_load_index_without_metadata_uses_default(self):
        """Test load_index uses default when metadata missing max_elements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build index
            vectors = np.random.rand(100, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(100)]
            manager.build_index(collection_path, vectors, ids)

            # Remove max_elements from metadata (simulate old metadata)
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            if "max_elements" in metadata.get("hnsw_index", {}):
                del metadata["hnsw_index"]["max_elements"]

            with open(meta_file, "w") as f:
                json.dump(metadata, f)

            # Load index should use calculated default
            index = manager.load_index(collection_path)

            assert index is not None


class TestCrashRecovery:
    """Test crash recovery with automatic resize."""

    def test_load_index_resizes_when_count_exceeds_metadata(self):
        """Test load_index automatically resizes when actual count exceeds stored max_elements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build index with 1000 vectors
            vectors = np.random.rand(1000, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(1000)]
            manager.build_index(collection_path, vectors, ids)

            # Manually corrupt metadata to simulate crash scenario
            # (stored max_elements < actual count)
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            metadata["hnsw_index"]["max_elements"] = 500  # Corrupt value

            with open(meta_file, "w") as f:
                json.dump(metadata, f)

            # Load index should detect corruption and resize
            index = manager.load_index(collection_path)

            # Should load successfully with automatic resize
            assert index is not None
            assert index.get_current_count() == 1000


class TestIncrementalResizeIntegration:
    """Integration tests for resize during incremental updates."""

    def test_multiple_incremental_adds_with_resize(self):
        """Test multiple incremental additions with automatic resize."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir)
            manager = HNSWIndexManager(vector_dim=128, space="cosine")

            # Build initial index with 10 vectors
            initial_count = 10
            vectors = np.random.rand(initial_count, 128).astype(np.float32)
            ids = [f"vec_{i}" for i in range(initial_count)]
            manager.build_index(collection_path, vectors, ids)

            # Load for incremental updates
            index, id_to_label, label_to_id, next_label = (
                manager.load_for_incremental_update(collection_path)
            )

            # Add 100 more vectors incrementally
            for i in range(100):
                new_vector = np.random.rand(128).astype(np.float32)
                label, id_to_label, label_to_id, next_label = manager.add_or_update_vector(
                    index, f"vec_{initial_count + i}", new_vector, id_to_label, label_to_id, next_label
                )

            # Save final state
            manager.save_incremental_update(
                index, collection_path, id_to_label, label_to_id, vector_count=110
            )

            # Verify index is functional
            assert index.get_current_count() == 110

            # Verify metadata has updated max_elements
            meta_file = collection_path / "collection_meta.json"
            with open(meta_file) as f:
                metadata = json.load(f)

            stored_max = metadata["hnsw_index"]["max_elements"]
            assert stored_max >= 110, f"max_elements {stored_max} should accommodate 110 vectors"
