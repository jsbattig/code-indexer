"""
Unit tests for metadata schema enhancement with universal timestamps.

Tests the requirement for metadata schema to include file_last_modified
and indexed_timestamp fields for all file types.

Following TDD methodology: These tests MUST FAIL initially, then be made to pass.
"""

import time
from datetime import datetime, timezone

from code_indexer.services.metadata_schema import (
    GitAwareMetadataSchema,
    MetadataSchemaVersion,
)


class TestMetadataSchemaTimestampFields:
    """Test metadata schema includes universal timestamp fields."""

    def test_schema_includes_universal_timestamp_fields_in_all_fields(self):
        """
        Test that universal timestamp fields are included in ALL_FIELDS.

        This test MUST FAIL initially because the fields don't exist yet.
        """
        # MUST FAIL: Universal timestamp fields not in schema yet
        assert "file_last_modified" in GitAwareMetadataSchema.ALL_FIELDS
        assert "indexed_timestamp" in GitAwareMetadataSchema.ALL_FIELDS

    def test_schema_includes_timestamp_fields_in_universal_fields(self):
        """
        Test that universal timestamp fields are properly categorized.

        Both file_last_modified and indexed_timestamp should be in UNIVERSAL_TIMESTAMP_FIELDS
        but optional for backward compatibility with existing data.
        """
        assert "indexed_timestamp" in GitAwareMetadataSchema.UNIVERSAL_TIMESTAMP_FIELDS
        assert "file_last_modified" in GitAwareMetadataSchema.UNIVERSAL_TIMESTAMP_FIELDS

        # Neither should be required for backward compatibility
        assert "file_last_modified" not in GitAwareMetadataSchema.REQUIRED_FIELDS
        assert "indexed_timestamp" not in GitAwareMetadataSchema.REQUIRED_FIELDS

    def test_create_git_aware_metadata_includes_universal_timestamps(self):
        """
        Test that create_git_aware_metadata includes universal timestamp fields.

        Both git and non-git projects should get universal timestamps.
        """
        file_mtime = 1640995200.0
        indexed_time = time.time()

        # Test git project
        git_metadata = {
            "commit_hash": "abc123def456",
            "branch": "main",
            "git_hash": "blob789",
        }

        # Now method should accept timestamp parameters
        metadata = GitAwareMetadataSchema.create_git_aware_metadata(
            path="/test/file.py",
            content="test content",
            language="python",
            file_size=100,
            chunk_index=0,
            total_chunks=1,
            project_id="test-project",
            file_hash="file123",
            git_metadata=git_metadata,
            line_start=1,
            line_end=5,
            file_last_modified=file_mtime,  # NEW parameter
            indexed_timestamp=indexed_time,  # NEW parameter
        )

        # Verify universal timestamp fields are included
        assert "file_last_modified" in metadata
        assert metadata["file_last_modified"] == file_mtime
        assert "indexed_timestamp" in metadata
        assert metadata["indexed_timestamp"] == indexed_time

    def test_create_git_aware_metadata_handles_none_file_last_modified(self):
        """
        Test that create_git_aware_metadata handles None file_last_modified.

        When file stat() fails, file_last_modified should be None.
        """
        indexed_time = time.time()

        # Now method should handle None file_last_modified
        metadata = GitAwareMetadataSchema.create_git_aware_metadata(
            path="/error/file.py",
            content="test content",
            language="python",
            file_size=100,
            chunk_index=0,
            total_chunks=1,
            project_id="test-project",
            file_hash="file123",
            git_metadata=None,
            line_start=1,
            line_end=5,
            file_last_modified=None,  # stat() failed
            indexed_timestamp=indexed_time,  # indexing timestamp still works
        )

        assert metadata["file_last_modified"] is None
        assert metadata["indexed_timestamp"] == indexed_time

    def test_validate_metadata_allows_optional_indexed_timestamp(self):
        """
        Test that metadata validation allows missing indexed_timestamp for backward compatibility.

        Missing indexed_timestamp should NOT be a validation error.
        """
        metadata = {
            "path": "/test/file.py",
            "content": "test content",
            "language": "python",
            "file_size": 100,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2022-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "file123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
            # Missing indexed_timestamp - should be allowed for backward compatibility
        }

        validation_result = GitAwareMetadataSchema.validate_metadata(metadata)
        # Should not have errors about missing indexed_timestamp
        error_messages = validation_result.get("errors", [])
        timestamp_errors = [err for err in error_messages if "indexed_timestamp" in err]
        assert len(timestamp_errors) == 0

    def test_validate_metadata_accepts_optional_file_last_modified(self):
        """
        Test that metadata validation accepts optional file_last_modified.

        Missing file_last_modified should not be a validation error.
        """
        indexed_time = time.time()
        metadata = {
            "path": "/test/file.py",
            "content": "test content",
            "language": "python",
            "file_size": 100,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": "test-project",
            "file_hash": "file123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
            "indexed_timestamp": indexed_time,
            # file_last_modified is optional
        }

        # MUST FAIL: indexed_timestamp validation doesn't exist yet
        validation_result = GitAwareMetadataSchema.validate_metadata(metadata)

        # Should not have errors about file_last_modified being missing
        error_messages = validation_result.get("errors", [])
        file_modified_errors = [
            err for err in error_messages if "file_last_modified" in err
        ]
        assert len(file_modified_errors) == 0

    def test_validate_metadata_validates_timestamp_types(self):
        """
        Test that metadata validation checks timestamp field types.

        Timestamps should be numeric (int/float), not strings.
        """
        metadata = {
            "path": "/test/file.py",
            "content": "test content",
            "language": "python",
            "file_size": 100,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": "test-project",
            "file_hash": "file123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
            "file_last_modified": "invalid_timestamp",  # String instead of number
            "indexed_timestamp": "also_invalid",  # String instead of number
        }

        # MUST FAIL: Timestamp type validation doesn't exist yet
        validation_result = GitAwareMetadataSchema.validate_metadata(metadata)
        error_messages = validation_result.get("errors", [])

        # Should have type validation errors
        timestamp_errors = [
            err
            for err in error_messages
            if "file_last_modified" in err or "indexed_timestamp" in err
        ]
        assert len(timestamp_errors) > 0

    def test_validate_metadata_accepts_valid_timestamp_types(self):
        """
        Test that metadata validation accepts valid timestamp types.

        Should accept int, float, and None for file_last_modified.
        Should accept int and float for indexed_timestamp.
        """
        base_metadata = {
            "path": "/test/file.py",
            "content": "test content",
            "language": "python",
            "file_size": 100,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": "test-project",
            "file_hash": "file123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
        }

        # Test with float timestamps
        metadata_float = base_metadata.copy()
        metadata_float.update(
            {"file_last_modified": 1640995200.5, "indexed_timestamp": time.time()}
        )

        # MUST FAIL: Timestamp validation doesn't exist yet
        validation_result = GitAwareMetadataSchema.validate_metadata(metadata_float)
        timestamp_errors = [
            err
            for err in validation_result.get("errors", [])
            if "file_last_modified" in err or "indexed_timestamp" in err
        ]
        assert len(timestamp_errors) == 0

        # Test with int timestamps
        metadata_int = base_metadata.copy()
        metadata_int.update(
            {"file_last_modified": 1640995200, "indexed_timestamp": int(time.time())}
        )

        validation_result = GitAwareMetadataSchema.validate_metadata(metadata_int)
        timestamp_errors = [
            err
            for err in validation_result.get("errors", [])
            if "file_last_modified" in err or "indexed_timestamp" in err
        ]
        assert len(timestamp_errors) == 0

        # Test with None file_last_modified
        metadata_none = base_metadata.copy()
        metadata_none.update(
            {"file_last_modified": None, "indexed_timestamp": time.time()}
        )

        validation_result = GitAwareMetadataSchema.validate_metadata(metadata_none)
        file_modified_errors = [
            err
            for err in validation_result.get("errors", [])
            if "file_last_modified" in err
        ]
        assert len(file_modified_errors) == 0

    def test_metadata_schema_supports_universal_timestamp_collection_use_case(self):
        """
        Test that metadata schema supports the universal timestamp collection use case.

        Should enable storing timestamps for both git and non-git projects.
        """
        indexed_time = time.time()
        file_mtime = 1640995200.0

        # Test non-git project
        non_git_metadata = {
            "path": "/non-git/file.py",
            "content": "non-git content",
            "language": "python",
            "file_size": 150,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": "non-git-project",
            "file_hash": "file456",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
            "file_last_modified": file_mtime,
            "indexed_timestamp": indexed_time,
        }

        # Test git project
        git_metadata = {
            "path": "/git/file.py",
            "content": "git content",
            "language": "python",
            "file_size": 200,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "project_id": "git-project",
            "file_hash": "file789",
            "git_available": True,
            "git_commit_hash": "abc123def456789012345678901234567890abcd",  # 40-char hash
            "git_branch": "main",
            "schema_version": MetadataSchemaVersion.CURRENT,
            "type": "content",
            "file_last_modified": file_mtime,
            "indexed_timestamp": indexed_time,
        }

        # MUST FAIL: Universal timestamp validation doesn't exist yet
        # Both should validate successfully with universal timestamps
        non_git_result = GitAwareMetadataSchema.validate_metadata(non_git_metadata)
        git_result = GitAwareMetadataSchema.validate_metadata(git_metadata)

        assert len(non_git_result["errors"]) == 0
        assert len(git_result["errors"]) == 0

        # Both should have the same universal timestamp fields
        assert (
            non_git_metadata["file_last_modified"] == git_metadata["file_last_modified"]
        )
        assert (
            non_git_metadata["indexed_timestamp"] == git_metadata["indexed_timestamp"]
        )
