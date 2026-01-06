"""Unit tests for temporal reconciliation functionality.

Tests crash-resilient temporal indexing with disk-based reconciliation.
"""

import json
from unittest.mock import Mock, patch
from src.code_indexer.services.temporal.temporal_reconciliation import (
    discover_indexed_commits_from_disk,
    reconcile_temporal_index,
)
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.storage.temporal_metadata_store import TemporalMetadataStore


def _create_v2_metadata_store(collection_path, vector_files_data):
    """Helper to create temporal_metadata.db for v2 format tests.

    Args:
        collection_path: Path to collection directory
        vector_files_data: List of tuples (point_id, payload_dict)
    """
    metadata_store = TemporalMetadataStore(collection_path)
    for point_id, payload in vector_files_data:
        metadata_store.save_metadata(point_id, payload)


class TestDiscoverIndexedCommitsFromDisk:
    """Test AC1: Discover indexed commits from disk by scanning vector files."""

    def test_discovers_commits_from_single_vector_file(self, tmp_path):
        """Test extracting commit hash from a single vector file."""
        # Arrange: Create collection directory with one vector file
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_file = collection_path / "vector_001.json"
        vector_data = {
            "id": "test-project:diff:abc123def456:src/main.py:0",
            "vector": [0.1, 0.2, 0.3],
            "payload": {},
        }
        vector_file.write_text(json.dumps(vector_data))

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert "abc123def456" in indexed_commits
        assert len(indexed_commits) == 1
        assert skipped_count == 0

    def test_discovers_multiple_commits_from_multiple_files(self, tmp_path):
        """Test discovering unique commits across multiple vector files."""
        # Arrange: Create multiple vector files with different commits
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        commits_data = [
            ("vector_001.json", "commit_hash_1"),
            ("vector_002.json", "commit_hash_2"),
            ("vector_003.json", "commit_hash_1"),  # Duplicate
            ("vector_004.json", "commit_hash_3"),
        ]

        for filename, commit_hash in commits_data:
            vector_file = collection_path / filename
            vector_data = {
                "id": f"project:diff:{commit_hash}:file.py:0",
                "vector": [0.1],
                "payload": {},
            }
            vector_file.write_text(json.dumps(vector_data))

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert len(indexed_commits) == 3  # Unique commits
        assert "commit_hash_1" in indexed_commits
        assert "commit_hash_2" in indexed_commits
        assert "commit_hash_3" in indexed_commits
        assert skipped_count == 0

    def test_handles_corrupted_json_files_gracefully(self, tmp_path):
        """Test that corrupted files are skipped with warning."""
        # Arrange: Create valid and corrupted files
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        # Valid file
        valid_file = collection_path / "vector_001.json"
        valid_file.write_text(
            json.dumps(
                {
                    "id": "project:diff:valid_commit:file.py:0",
                    "vector": [0.1],
                    "payload": {},
                }
            )
        )

        # Corrupted files
        (collection_path / "vector_002.json").write_text("CORRUPTED JSON{{{")
        (collection_path / "vector_003.json").write_text("")  # Empty
        (collection_path / "vector_004.json").write_text("null")  # Invalid structure

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert len(indexed_commits) == 1
        assert "valid_commit" in indexed_commits
        assert skipped_count == 3  # Three corrupted files

    def test_handles_malformed_point_id_format(self, tmp_path):
        """Test handling of point_ids that don't match expected format."""
        # Arrange: Create files with various malformed point_ids
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        test_cases = [
            ("vector_001.json", "not:enough:parts"),  # Too few parts
            ("vector_002.json", "project:wrong_type:hash:file:0"),  # Not 'diff'
            ("vector_003.json", "project:diff:valid_hash:file.py:0"),  # Valid
            ("vector_004.json", "no_colons_at_all"),  # No separators
        ]

        for filename, point_id in test_cases:
            vector_file = collection_path / filename
            vector_data = {"id": point_id, "vector": [0.1], "payload": {}}
            vector_file.write_text(json.dumps(vector_data))

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert len(indexed_commits) == 1
        assert "valid_hash" in indexed_commits
        assert skipped_count == 0  # Malformed IDs don't cause file skip

    def test_returns_empty_set_for_empty_collection(self, tmp_path):
        """Test handling of collection with no vector files."""
        # Arrange: Empty collection directory
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert len(indexed_commits) == 0
        assert skipped_count == 0

    def test_returns_empty_set_for_nonexistent_collection(self, tmp_path):
        """Test handling of collection directory that doesn't exist."""
        # Arrange: Non-existent path
        collection_path = tmp_path / "nonexistent"

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        assert len(indexed_commits) == 0
        assert skipped_count == 0

    def test_handles_commit_message_vectors_differently(self, tmp_path):
        """Test that commit message vectors (type='commit') are not included."""
        # Arrange: Mix of diff and commit message vectors
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        test_cases = [
            ("vector_001.json", "project:diff:diff_commit:file.py:0"),  # Diff vector
            ("vector_002.json", "project:commit:msg_commit:0"),  # Commit msg vector
        ]

        for filename, point_id in test_cases:
            vector_file = collection_path / filename
            vector_data = {"id": point_id, "vector": [0.1], "payload": {}}
            vector_file.write_text(json.dumps(vector_data))

        # Act
        indexed_commits, skipped_count = discover_indexed_commits_from_disk(
            collection_path
        )

        # Assert
        # Only diff vectors should be counted
        assert len(indexed_commits) == 1
        assert "diff_commit" in indexed_commits
        assert "msg_commit" not in indexed_commits


class TestReconcileTemporalIndex:
    """Test AC2: Find missing commits via git history reconciliation."""

    def test_identifies_missing_commits(self, tmp_path):
        """Test finding commits in git history that are not indexed."""
        # Arrange: Mock vector store and commits
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        # Create 2 indexed commits
        metadata_entries = []
        for i, commit_hash in enumerate(["commit1", "commit2"]):
            vector_file = collection_path / f"vector_{i:03d}.json"
            point_id = f"project:diff:{commit_hash}:file.py:0"
            vector_data = {
                "id": point_id,
                "vector": [0.1],
                "payload": {
                    "commit_hash": commit_hash,
                    "path": "file.py",
                    "chunk_index": 0,
                },
            }
            vector_file.write_text(json.dumps(vector_data))
            metadata_entries.append((point_id, vector_data["payload"]))

        # Create metadata db to mark as v2 format (prevents v1 cleanup)
        _create_v2_metadata_store(collection_path, metadata_entries)

        # Mock vector store base_path
        vector_store.base_path = index_dir

        # All commits from git (5 commits)
        all_commits = [
            CommitInfo("commit1", 1000, "Author", "author@test.com", "Msg 1", ""),
            CommitInfo("commit2", 2000, "Author", "author@test.com", "Msg 2", ""),
            CommitInfo("commit3", 3000, "Author", "author@test.com", "Msg 3", ""),
            CommitInfo("commit4", 4000, "Author", "author@test.com", "Msg 4", ""),
            CommitInfo("commit5", 5000, "Author", "author@test.com", "Msg 5", ""),
        ]

        # Act
        missing_commits = reconcile_temporal_index(
            vector_store, all_commits, "code-indexer-temporal"
        )

        # Assert
        assert len(missing_commits) == 3
        assert missing_commits[0].hash == "commit3"
        assert missing_commits[1].hash == "commit4"
        assert missing_commits[2].hash == "commit5"

    def test_preserves_chronological_order(self, tmp_path):
        """Test that missing commits maintain git history order."""
        # Arrange
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        # Index only middle commit
        vector_file = collection_path / "vector_001.json"
        point_id = "project:diff:commit3:file.py:0"
        vector_data = {
            "id": point_id,
            "vector": [0.1],
            "payload": {"commit_hash": "commit3", "path": "file.py", "chunk_index": 0},
        }
        vector_file.write_text(json.dumps(vector_data))

        # Create metadata db to mark as v2 format (prevents v1 cleanup)
        _create_v2_metadata_store(collection_path, [(point_id, vector_data["payload"])])

        vector_store.base_path = index_dir

        # Commits in chronological order
        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "First", ""),
            CommitInfo("commit2", 2000, "A", "a@test.com", "Second", ""),
            CommitInfo("commit3", 3000, "A", "a@test.com", "Third", ""),
            CommitInfo("commit4", 4000, "A", "a@test.com", "Fourth", ""),
            CommitInfo("commit5", 5000, "A", "a@test.com", "Fifth", ""),
        ]

        # Act
        missing_commits = reconcile_temporal_index(
            vector_store, all_commits, "code-indexer-temporal"
        )

        # Assert: Order preserved
        assert len(missing_commits) == 4
        assert [c.hash for c in missing_commits] == [
            "commit1",
            "commit2",
            "commit4",
            "commit5",
        ]

    def test_handles_all_commits_indexed(self, tmp_path):
        """Test edge case where all commits are already indexed."""
        # Arrange
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        # Index all commits
        metadata_entries = []
        for i, commit_hash in enumerate(["commit1", "commit2", "commit3"]):
            vector_file = collection_path / f"vector_{i:03d}.json"
            point_id = f"project:diff:{commit_hash}:file.py:0"
            vector_data = {
                "id": point_id,
                "vector": [0.1],
                "payload": {
                    "commit_hash": commit_hash,
                    "path": "file.py",
                    "chunk_index": 0,
                },
            }
            vector_file.write_text(json.dumps(vector_data))
            metadata_entries.append((point_id, vector_data["payload"]))

        # Create metadata db to mark as v2 format (prevents v1 cleanup)
        _create_v2_metadata_store(collection_path, metadata_entries)

        vector_store.base_path = index_dir

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
            CommitInfo("commit2", 2000, "A", "a@test.com", "M2", ""),
            CommitInfo("commit3", 3000, "A", "a@test.com", "M3", ""),
        ]

        # Act
        missing_commits = reconcile_temporal_index(
            vector_store, all_commits, "code-indexer-temporal"
        )

        # Assert
        assert len(missing_commits) == 0

    def test_handles_no_commits_indexed(self, tmp_path):
        """Test edge case where no commits are indexed yet."""
        # Arrange
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_store.base_path = index_dir

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
            CommitInfo("commit2", 2000, "A", "a@test.com", "M2", ""),
        ]

        # Act
        missing_commits = reconcile_temporal_index(
            vector_store, all_commits, "code-indexer-temporal"
        )

        # Assert
        assert len(missing_commits) == 2
        assert missing_commits[0].hash == "commit1"
        assert missing_commits[1].hash == "commit2"

    def test_deletes_all_stale_metadata_files_when_they_exist(self, tmp_path):
        """Test that reconciliation deletes 3 metadata files when they exist (preserves collection_meta.json and projection_matrix.npy)."""
        # Arrange: Create vector store with all metadata files present
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_store.base_path = index_dir

        # Create 4 metadata files that should be deleted (all in collection directory now)
        metadata_files_to_delete = [
            collection_path / "hnsw_index.bin",
            collection_path / "id_index.bin",
            collection_path / "temporal_meta.json",
            collection_path / "temporal_progress.json",
        ]

        # Create 2 metadata files that should be preserved
        preserved_files = [
            collection_path / "collection_meta.json",
            collection_path / "projection_matrix.npy",
        ]

        for meta_file in metadata_files_to_delete + preserved_files:
            meta_file.write_text("stale metadata content")

        # Verify all files exist before reconciliation
        for meta_file in metadata_files_to_delete + preserved_files:
            assert meta_file.exists()

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
        ]

        # Act: Reconcile (should delete only metadata_files_to_delete)
        with patch(
            "src.code_indexer.services.temporal.temporal_reconciliation.logger"
        ) as mock_logger:
            reconcile_temporal_index(vector_store, all_commits, "code-indexer-temporal")

        # Assert: Only deletable metadata files deleted
        for meta_file in metadata_files_to_delete:
            assert not meta_file.exists(), f"{meta_file.name} should have been deleted"

        # Assert: Preserved files still exist
        for meta_file in preserved_files:
            assert meta_file.exists(), f"{meta_file.name} should have been preserved"

        # Assert: Logger called with deletion count (4 files deleted)
        mock_logger.info.assert_any_call(
            "Reconciliation: Deleted 4 stale metadata files"
        )

    def test_handles_missing_metadata_files_gracefully(self, tmp_path):
        """Test that reconciliation handles missing metadata files without crashing."""
        # Arrange: Vector store with NO metadata files
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_store.base_path = index_dir

        # Verify metadata files do NOT exist (collection_meta.json and projection_matrix.npy not deleted)
        # All metadata files now in collection directory
        metadata_files = [
            collection_path / "hnsw_index.bin",
            collection_path / "id_index.bin",
            collection_path / "temporal_meta.json",
            collection_path / "temporal_progress.json",
        ]

        for meta_file in metadata_files:
            assert not meta_file.exists()

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
        ]

        # Act: Should not crash despite missing files
        with patch(
            "src.code_indexer.services.temporal.temporal_reconciliation.logger"
        ) as mock_logger:
            missing_commits = reconcile_temporal_index(
                vector_store, all_commits, "code-indexer-temporal"
            )

        # Assert: Completed successfully
        assert len(missing_commits) == 1
        assert missing_commits[0].hash == "commit1"

        # Assert: No deletion log message (0 files deleted)
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        deletion_logs = [
            msg for msg in info_calls if "Deleted" in msg and "metadata" in msg
        ]
        assert len(deletion_logs) == 0, "Should not log deletion when no files deleted"

    def test_continues_reconciliation_after_metadata_deletion(self, tmp_path):
        """Test that reconciliation continues correctly after deleting metadata files."""
        # Arrange: Create metadata files + vector files with commits
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_store.base_path = index_dir

        # Create metadata files (collection_meta.json and projection_matrix.npy are preserved, so only 4 files deleted)
        # All metadata files now in collection directory
        metadata_files_to_delete = [
            collection_path / "hnsw_index.bin",
            collection_path / "id_index.bin",
            collection_path / "temporal_meta.json",
            collection_path / "temporal_progress.json",
        ]

        preserved_files = [
            collection_path / "collection_meta.json",
            collection_path / "projection_matrix.npy",
        ]

        for meta_file in metadata_files_to_delete + preserved_files:
            meta_file.write_text("stale metadata")

        # Create vector files for indexed commits
        metadata_entries = []
        for i, commit_hash in enumerate(["commit1", "commit2"]):
            vector_file = collection_path / f"vector_{i:03d}.json"
            point_id = f"project:diff:{commit_hash}:file.py:0"
            vector_data = {
                "id": point_id,
                "vector": [0.1, 0.2, 0.3],
                "payload": {
                    "commit_hash": commit_hash,
                    "path": "file.py",
                    "chunk_index": 0,
                },
            }
            vector_file.write_text(json.dumps(vector_data))
            metadata_entries.append((point_id, vector_data["payload"]))

        # Create metadata db to mark as v2 format (prevents v1 cleanup)
        _create_v2_metadata_store(collection_path, metadata_entries)

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
            CommitInfo("commit2", 2000, "A", "a@test.com", "M2", ""),
            CommitInfo("commit3", 3000, "A", "a@test.com", "M3", ""),
            CommitInfo("commit4", 4000, "A", "a@test.com", "M4", ""),
        ]

        # Act
        with patch(
            "src.code_indexer.services.temporal.temporal_reconciliation.logger"
        ) as mock_logger:
            missing_commits = reconcile_temporal_index(
                vector_store, all_commits, "code-indexer-temporal"
            )

        # Assert: Deletable metadata deleted
        for meta_file in metadata_files_to_delete:
            assert not meta_file.exists()

        # Assert: Preserved files still exist
        for meta_file in preserved_files:
            assert meta_file.exists()

        # Assert: Commits discovered correctly despite metadata deletion
        assert len(missing_commits) == 2
        assert missing_commits[0].hash == "commit3"
        assert missing_commits[1].hash == "commit4"

        # Assert: Both deletion and reconciliation logged
        info_calls = [call[0][0] for call in mock_logger.info.call_args_list]

        deletion_log = [msg for msg in info_calls if "Deleted 4 stale metadata" in msg]
        assert len(deletion_log) == 1

        reconciliation_log = [
            msg for msg in info_calls if "Reconciliation: 2 indexed" in msg
        ]
        assert len(reconciliation_log) == 1

    def test_logs_deletion_count_correctly(self, tmp_path):
        """Test that logger reports correct deletion count when subset of files exist."""
        # Arrange: Create only 2 out of 4 metadata files (collection_meta.json and projection_matrix.npy never deleted)
        vector_store = Mock()
        index_dir = tmp_path / "index"
        index_dir.mkdir(parents=True)
        collection_path = index_dir / "code-indexer-temporal"
        collection_path.mkdir(parents=True)

        vector_store.base_path = index_dir

        # Create only 2 deletable metadata files (not collection_meta.json or projection_matrix.npy as they're preserved)
        # All metadata files now in collection directory
        existing_files = [
            collection_path / "hnsw_index.bin",
            collection_path / "temporal_progress.json",
        ]

        # Create preserved files
        preserved_files = [
            collection_path / "collection_meta.json",
            collection_path / "projection_matrix.npy",
        ]

        for meta_file in existing_files + preserved_files:
            meta_file.write_text("stale content")

        # Verify exactly 2 deletable files exist
        assert sum(1 for f in existing_files if f.exists()) == 2

        all_commits = [
            CommitInfo("commit1", 1000, "A", "a@test.com", "M1", ""),
        ]

        # Act
        with patch(
            "src.code_indexer.services.temporal.temporal_reconciliation.logger"
        ) as mock_logger:
            missing_commits = reconcile_temporal_index(
                vector_store, all_commits, "code-indexer-temporal"
            )

        # Assert: All deletable files deleted
        for meta_file in existing_files:
            assert not meta_file.exists()

        # Assert: Preserved files still exist
        for meta_file in preserved_files:
            assert meta_file.exists()

        # Assert: Logger reports exactly 2 files deleted
        mock_logger.info.assert_any_call(
            "Reconciliation: Deleted 2 stale metadata files"
        )

        # Assert: Reconciliation completed
        assert len(missing_commits) == 1
