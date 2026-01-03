"""Unit tests for temporal metadata store operations (Story #669).

Tests metadata database operations:
- get_point_id(): Retrieve point_id from hash prefix
- get_metadata(): Retrieve full metadata dict from hash prefix
- delete_metadata(): Delete metadata entry
- cleanup_stale_metadata(): Remove orphaned entries

Code Review P0 Violation Fix: These operations had 0% test coverage.
"""

import tempfile
from pathlib import Path
import pytest

from src.code_indexer.storage.temporal_metadata_store import TemporalMetadataStore


class TestTemporalMetadataOperations:
    """Test temporal metadata store CRUD operations."""

    def test_get_point_id_returns_correct_point_id(self):
        """get_point_id() returns correct point_id for hash prefix."""
        # Given: A metadata entry with known point_id
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            point_id = "project:diff:abc123:path/to/file.py:0"
            payload = {
                "commit_hash": "abc123",
                "path": "path/to/file.py",
                "chunk_index": 0
            }

            # Save metadata
            hash_prefix = metadata_store.save_metadata(point_id, payload)

            # When: Retrieving point_id from hash prefix
            retrieved_point_id = metadata_store.get_point_id(hash_prefix)

            # Then: Should return original point_id
            assert retrieved_point_id == point_id, (
                f"Expected point_id '{point_id}', got '{retrieved_point_id}'"
            )

    def test_get_point_id_returns_none_for_missing_hash(self):
        """get_point_id() returns None for non-existent hash prefix."""
        # Given: Empty metadata store
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            # When: Retrieving non-existent hash prefix
            non_existent_hash = "0000000000000000"
            result = metadata_store.get_point_id(non_existent_hash)

            # Then: Should return None
            assert result is None, f"Expected None for missing hash, got '{result}'"

    def test_get_metadata_returns_complete_metadata_dict(self):
        """get_metadata() returns dict with point_id, commit_hash, file_path, chunk_index."""
        # Given: A metadata entry with full metadata
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            point_id = "project:diff:def456:src/main.py:5"
            payload = {
                "commit_hash": "def456",
                "path": "src/main.py",
                "chunk_index": 5
            }

            hash_prefix = metadata_store.save_metadata(point_id, payload)

            # When: Retrieving metadata
            metadata = metadata_store.get_metadata(hash_prefix)

            # Then: Should return complete metadata dict
            assert metadata is not None, "Metadata should not be None"
            assert metadata["point_id"] == point_id
            assert metadata["commit_hash"] == "def456"
            assert metadata["file_path"] == "src/main.py"
            assert metadata["chunk_index"] == 5
            assert "created_at" in metadata  # Timestamp should be included

    def test_get_metadata_returns_none_for_missing_hash(self):
        """get_metadata() returns None for non-existent hash prefix."""
        # Given: Empty metadata store
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            # When: Retrieving non-existent hash prefix
            result = metadata_store.get_metadata("1111111111111111")

            # Then: Should return None
            assert result is None

    def test_delete_metadata_removes_entry(self):
        """delete_metadata() successfully removes metadata entry."""
        # Given: A metadata entry
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            point_id = "project:diff:789abc:file.py:0"
            payload = {"commit_hash": "789abc", "path": "file.py", "chunk_index": 0}
            hash_prefix = metadata_store.save_metadata(point_id, payload)

            # Verify entry exists
            assert metadata_store.get_point_id(hash_prefix) is not None

            # When: Deleting metadata
            metadata_store.delete_metadata(hash_prefix)

            # Then: Entry should be removed
            assert metadata_store.get_point_id(hash_prefix) is None
            assert metadata_store.get_metadata(hash_prefix) is None

    def test_delete_metadata_no_error_for_missing_hash(self):
        """delete_metadata() does not raise error for non-existent hash."""
        # Given: Empty metadata store
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            # When/Then: Deleting non-existent hash should not raise error
            try:
                metadata_store.delete_metadata("2222222222222222")
            except Exception as e:
                pytest.fail(f"delete_metadata raised unexpected exception: {e}")

    def test_cleanup_stale_metadata_removes_orphaned_entries(self):
        """cleanup_stale_metadata() removes entries without vector files."""
        # Given: Metadata entries where some have no vector files
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            # Create 3 metadata entries
            point_id_1 = "project:diff:aaa:file1.py:0"
            point_id_2 = "project:diff:bbb:file2.py:0"
            point_id_3 = "project:diff:ccc:file3.py:0"

            payload_1 = {"commit_hash": "aaa", "path": "file1.py", "chunk_index": 0}
            payload_2 = {"commit_hash": "bbb", "path": "file2.py", "chunk_index": 0}
            payload_3 = {"commit_hash": "ccc", "path": "file3.py", "chunk_index": 0}

            hash_1 = metadata_store.save_metadata(point_id_1, payload_1)
            hash_2 = metadata_store.save_metadata(point_id_2, payload_2)
            hash_3 = metadata_store.save_metadata(point_id_3, payload_3)

            # Verify all 3 entries exist
            assert metadata_store.count_entries() == 3

            # When: Cleanup with only hash_1 and hash_3 as valid (hash_2 is stale)
            valid_hashes = {hash_1, hash_3}
            removed_count = metadata_store.cleanup_stale_metadata(valid_hashes)

            # Then: hash_2 should be removed
            assert removed_count == 1, f"Expected 1 stale entry removed, got {removed_count}"
            assert metadata_store.count_entries() == 2
            assert metadata_store.get_point_id(hash_1) is not None
            assert metadata_store.get_point_id(hash_2) is None  # Removed
            assert metadata_store.get_point_id(hash_3) is not None

    def test_cleanup_stale_metadata_no_stale_entries(self):
        """cleanup_stale_metadata() returns 0 when no stale entries exist."""
        # Given: Metadata entries where all have vector files
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            point_id = "project:diff:xyz:file.py:0"
            payload = {"commit_hash": "xyz", "path": "file.py", "chunk_index": 0}
            hash_prefix = metadata_store.save_metadata(point_id, payload)

            # When: Cleanup with all hashes as valid
            valid_hashes = {hash_prefix}
            removed_count = metadata_store.cleanup_stale_metadata(valid_hashes)

            # Then: No entries removed
            assert removed_count == 0
            assert metadata_store.count_entries() == 1

    def test_cleanup_stale_metadata_empty_valid_set_removes_all(self):
        """cleanup_stale_metadata() with empty valid set removes all entries."""
        # Given: Metadata entries
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            # Create 2 entries
            point_id_1 = "project:diff:111:file1.py:0"
            point_id_2 = "project:diff:222:file2.py:0"
            payload = {"commit_hash": "111", "path": "file1.py", "chunk_index": 0}
            metadata_store.save_metadata(point_id_1, payload)
            metadata_store.save_metadata(point_id_2, payload)

            assert metadata_store.count_entries() == 2

            # When: Cleanup with empty valid set (no vector files exist)
            removed_count = metadata_store.cleanup_stale_metadata(set())

            # Then: All entries removed
            assert removed_count == 2
            assert metadata_store.count_entries() == 0

    def test_save_metadata_upserts_existing_entry(self):
        """save_metadata() updates existing entry with same point_id (upsert behavior)."""
        # Given: An existing metadata entry
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(collection_path)

            point_id = "project:diff:orig:file.py:0"
            original_payload = {
                "commit_hash": "original_hash",
                "path": "original_path.py",
                "chunk_index": 0
            }

            hash_prefix = metadata_store.save_metadata(point_id, original_payload)
            assert metadata_store.count_entries() == 1

            # When: Saving again with same point_id but different metadata
            updated_payload = {
                "commit_hash": "updated_hash",
                "path": "updated_path.py",
                "chunk_index": 1
            }
            hash_prefix_2 = metadata_store.save_metadata(point_id, updated_payload)

            # Then: Should update existing entry (same hash, not create duplicate)
            assert hash_prefix == hash_prefix_2  # Same hash from same point_id
            assert metadata_store.count_entries() == 1  # No duplicate

            # Verify updated metadata
            metadata = metadata_store.get_metadata(hash_prefix)
            assert metadata["commit_hash"] == "updated_hash"
            assert metadata["file_path"] == "updated_path.py"
            assert metadata["chunk_index"] == 1

    def test_metadata_persists_across_store_instances(self):
        """Metadata persists to disk and can be read by new store instance."""
        # Given: Metadata saved by one store instance
        with tempfile.TemporaryDirectory() as tmpdir:
            collection_path = Path(tmpdir) / "code-indexer-temporal"

            # First store instance - save metadata
            store_1 = TemporalMetadataStore(collection_path)
            point_id = "project:diff:persist:file.py:0"
            payload = {"commit_hash": "persist", "path": "file.py", "chunk_index": 0}
            hash_prefix = store_1.save_metadata(point_id, payload)

            # When: Creating new store instance pointing to same path
            store_2 = TemporalMetadataStore(collection_path)

            # Then: Should read persisted metadata
            retrieved_point_id = store_2.get_point_id(hash_prefix)
            assert retrieved_point_id == point_id

            metadata = store_2.get_metadata(hash_prefix)
            assert metadata is not None
            assert metadata["point_id"] == point_id
            assert metadata["commit_hash"] == "persist"
