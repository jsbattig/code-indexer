"""
Test automatic migration of legacy indexing_progress.json files.

Tests the migration from pre-v8.0 format (qdrant_point_ids) to v8.0+ format (vector_point_ids).
"""

import json
import tempfile
from pathlib import Path

from code_indexer.services.indexing_progress_log import (
    IndexingProgressLog,
    FileIndexingRecord,
    FileIndexingStatus,
)


class TestLegacyProgressMigration:
    """Test migration from legacy qdrant_point_ids to vector_point_ids."""

    def test_legacy_format_detection_and_migration(self):
        """Test that legacy format is detected and migrated automatically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create legacy format JSON
            legacy_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 2,
                },
                "file_records": {
                    "test1.py": {
                        "file_path": "test1.py",
                        "status": "completed",
                        "chunks_created": 5,
                        "qdrant_point_ids": ["id1", "id2", "id3"],
                    },
                    "test2.py": {
                        "file_path": "test2.py",
                        "status": "completed",
                        "chunks_created": 3,
                        "qdrant_point_ids": ["id4", "id5"],
                    },
                },
                "last_updated": 1234567890.0,
            }

            # Write legacy format
            with open(progress_file, "w") as f:
                json.dump(legacy_data, f)

            # Load via IndexingProgressLog (should trigger migration)
            progress_log = IndexingProgressLog(config_dir)

            # Verify migration happened
            assert progress_log.current_session is not None
            assert progress_log.current_session.session_id == "full_1234567890"

            # Verify file records were migrated correctly
            assert "test1.py" in progress_log.file_records
            assert "test2.py" in progress_log.file_records

            record1 = progress_log.file_records["test1.py"]
            assert record1.file_path == "test1.py"
            assert record1.status == FileIndexingStatus.COMPLETED
            assert record1.chunks_created == 5
            assert record1.vector_point_ids == ["id1", "id2", "id3"]

            record2 = progress_log.file_records["test2.py"]
            assert record2.file_path == "test2.py"
            assert record2.status == FileIndexingStatus.COMPLETED
            assert record2.chunks_created == 3
            assert record2.vector_point_ids == ["id4", "id5"]

    def test_migration_saves_new_format(self):
        """Test that migrated data is saved in new format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create legacy format JSON
            legacy_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 1,
                },
                "file_records": {
                    "test.py": {
                        "file_path": "test.py",
                        "status": "completed",
                        "chunks_created": 5,
                        "qdrant_point_ids": ["id1", "id2", "id3"],
                    }
                },
                "last_updated": 1234567890.0,
            }

            # Write legacy format
            with open(progress_file, "w") as f:
                json.dump(legacy_data, f)

            # Load and trigger migration
            progress_log = IndexingProgressLog(config_dir)

            # Force save to write migrated format
            progress_log._save_progress()

            # Read saved file and verify new format
            with open(progress_file, "r") as f:
                saved_data = json.load(f)

            # Verify new format is used
            assert "file_records" in saved_data
            assert "test.py" in saved_data["file_records"]
            file_record = saved_data["file_records"]["test.py"]

            # Should have vector_point_ids, not qdrant_point_ids
            assert "vector_point_ids" in file_record
            assert "qdrant_point_ids" not in file_record
            assert file_record["vector_point_ids"] == ["id1", "id2", "id3"]

    def test_mixed_format_migration(self):
        """Test migration when some files have old field and some don't."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create mixed format JSON
            mixed_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 3,
                },
                "file_records": {
                    "legacy.py": {
                        "file_path": "legacy.py",
                        "status": "completed",
                        "chunks_created": 5,
                        "qdrant_point_ids": ["id1", "id2"],
                    },
                    "new.py": {
                        "file_path": "new.py",
                        "status": "completed",
                        "chunks_created": 3,
                        "vector_point_ids": ["id3", "id4"],
                    },
                    "pending.py": {
                        "file_path": "pending.py",
                        "status": "pending",
                        "chunks_created": 0,
                    },
                },
                "last_updated": 1234567890.0,
            }

            # Write mixed format
            with open(progress_file, "w") as f:
                json.dump(mixed_data, f)

            # Load and trigger migration
            progress_log = IndexingProgressLog(config_dir)

            # Verify all records loaded correctly
            assert len(progress_log.file_records) == 3

            # Legacy record should be migrated
            legacy_record = progress_log.file_records["legacy.py"]
            assert legacy_record.vector_point_ids == ["id1", "id2"]

            # New format record should be unchanged
            new_record = progress_log.file_records["new.py"]
            assert new_record.vector_point_ids == ["id3", "id4"]

            # Pending record should work (no point IDs)
            pending_record = progress_log.file_records["pending.py"]
            assert pending_record.vector_point_ids == []

    def test_corrupted_json_fallback(self):
        """Test that corrupted JSON is handled gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Write corrupted JSON
            with open(progress_file, "w") as f:
                f.write("{ invalid json content }")

            # Load should not crash, should start with empty state
            progress_log = IndexingProgressLog(config_dir)

            # Should have clean state
            assert progress_log.current_session is None
            assert len(progress_log.file_records) == 0

            # Corrupted file should be deleted
            assert not progress_file.exists()

    def test_empty_vector_point_ids_migration(self):
        """Test migration when qdrant_point_ids is empty or null."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create legacy format with empty/null point IDs
            legacy_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 3,
                },
                "file_records": {
                    "empty_list.py": {
                        "file_path": "empty_list.py",
                        "status": "completed",
                        "chunks_created": 0,
                        "qdrant_point_ids": [],
                    },
                    "null_value.py": {
                        "file_path": "null_value.py",
                        "status": "completed",
                        "chunks_created": 0,
                        "qdrant_point_ids": None,
                    },
                    "missing_field.py": {
                        "file_path": "missing_field.py",
                        "status": "pending",
                        "chunks_created": 0,
                    },
                },
                "last_updated": 1234567890.0,
            }

            # Write legacy format
            with open(progress_file, "w") as f:
                json.dump(legacy_data, f)

            # Load and trigger migration
            progress_log = IndexingProgressLog(config_dir)

            # Verify all records loaded correctly
            assert len(progress_log.file_records) == 3

            # All should have empty list as default
            assert progress_log.file_records["empty_list.py"].vector_point_ids == []
            assert progress_log.file_records["null_value.py"].vector_point_ids == []
            assert progress_log.file_records["missing_field.py"].vector_point_ids == []

    def test_migration_logging(self, caplog):
        """Test that migration is logged for debugging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create legacy format
            legacy_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 1,
                },
                "file_records": {
                    "test.py": {
                        "file_path": "test.py",
                        "status": "completed",
                        "chunks_created": 5,
                        "qdrant_point_ids": ["id1", "id2"],
                    }
                },
            }

            # Write legacy format
            with open(progress_file, "w") as f:
                json.dump(legacy_data, f)

            # Load and check logs
            with caplog.at_level("WARNING"):
                IndexingProgressLog(config_dir)

            # Should have logged migration warning
            assert any(
                "migrat" in record.message.lower() for record in caplog.records
            ), f"Migration log not found. Captured logs: {[r.message for r in caplog.records]}"

    def test_no_migration_needed_for_new_format(self):
        """Test that new format files are not unnecessarily migrated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Create new format JSON
            new_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 1,
                },
                "file_records": {
                    "test.py": {
                        "file_path": "test.py",
                        "status": "completed",
                        "chunks_created": 5,
                        "vector_point_ids": ["id1", "id2", "id3"],
                    }
                },
                "last_updated": 1234567890.0,
            }

            # Write new format
            with open(progress_file, "w") as f:
                json.dump(new_data, f)

            # Load (should not trigger migration)
            progress_log = IndexingProgressLog(config_dir)

            # Verify data loaded correctly
            assert progress_log.current_session is not None
            assert "test.py" in progress_log.file_records
            assert progress_log.file_records["test.py"].vector_point_ids == [
                "id1",
                "id2",
                "id3",
            ]

    def test_e2e_legacy_file_upgrade(self):
        """End-to-end test: create legacy file, load, verify migration, save, reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / ".code-indexer"
            config_dir.mkdir(parents=True, exist_ok=True)
            progress_file = config_dir / "indexing_progress.json"

            # Step 1: Create legacy format file
            legacy_data = {
                "current_session": {
                    "session_id": "full_1234567890",
                    "operation_type": "full",
                    "started_at": 1234567890.0,
                    "embedding_provider": "voyageai",
                    "embedding_model": "voyage-3",
                    "total_files": 2,
                },
                "file_records": {
                    "file1.py": {
                        "file_path": "file1.py",
                        "status": "completed",
                        "chunks_created": 10,
                        "qdrant_point_ids": ["legacy1", "legacy2", "legacy3"],
                    },
                    "file2.py": {
                        "file_path": "file2.py",
                        "status": "pending",
                        "chunks_created": 0,
                    },
                },
            }

            with open(progress_file, "w") as f:
                json.dump(legacy_data, f)

            # Step 2: Load (triggers migration)
            progress_log_1 = IndexingProgressLog(config_dir)

            # Step 3: Verify migration in memory
            assert progress_log_1.file_records["file1.py"].vector_point_ids == [
                "legacy1",
                "legacy2",
                "legacy3",
            ]

            # Step 4: Make a change and save
            progress_log_1.mark_file_completed("file2.py", chunks_created=5)

            # Step 5: Create new instance (should load migrated format)
            progress_log_2 = IndexingProgressLog(config_dir)

            # Step 6: Verify new instance has correct data in new format
            assert progress_log_2.file_records["file1.py"].vector_point_ids == [
                "legacy1",
                "legacy2",
                "legacy3",
            ]
            assert progress_log_2.file_records["file2.py"].chunks_created == 5

            # Step 7: Verify saved file uses new format
            with open(progress_file, "r") as f:
                final_data = json.load(f)

            assert "qdrant_point_ids" not in str(final_data)
            assert "vector_point_ids" in final_data["file_records"]["file1.py"]

    def test_file_indexing_record_from_dict_with_legacy_field(self):
        """Test FileIndexingRecord.from_dict handles legacy field name."""
        legacy_dict = {
            "file_path": "test.py",
            "status": "completed",
            "chunks_created": 5,
            "qdrant_point_ids": ["id1", "id2", "id3"],
        }

        # This should work after implementing migration in from_dict
        record = FileIndexingRecord.from_dict(legacy_dict)

        assert record.file_path == "test.py"
        assert record.status == FileIndexingStatus.COMPLETED
        assert record.chunks_created == 5
        assert record.vector_point_ids == ["id1", "id2", "id3"]
