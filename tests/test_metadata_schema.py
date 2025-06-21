"""
Tests for the enhanced metadata schema module.
"""

from code_indexer.services.metadata_schema import (
    GitAwareMetadataSchema,
    MetadataSchemaVersion,
    MetadataValidator,
)


class TestGitAwareMetadataSchema:
    def test_validate_valid_git_metadata(self):
        """Test validation of valid git-aware metadata."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": True,
            "git_commit_hash": "a" * 40,
            "git_branch": "main",
            "git_blob_hash": "b" * 40,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0

    def test_validate_valid_filesystem_metadata(self):
        """Test validation of valid filesystem-only metadata."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "filesystem_mtime": 1640995200,
            "filesystem_size": 15,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0

    def test_validate_missing_required_fields(self):
        """Test validation with missing required fields."""
        metadata = {
            "content": "print('hello')",
            "language": "py",
            # Missing other required fields
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) > 0
        error_messages = " ".join(result["errors"])
        assert "Missing required field: path" in error_messages
        assert "Missing required field: file_size" in error_messages

    def test_validate_invalid_git_hash(self):
        """Test validation with invalid git hash."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": True,
            "git_commit_hash": "invalid_hash",  # Invalid format
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) > 0
        assert "git_commit_hash" in " ".join(result["errors"])

    def test_validate_invalid_timestamp(self):
        """Test validation with invalid timestamp."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "not-a-timestamp",  # Invalid format
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) > 0
        assert "indexed_at" in " ".join(result["errors"])

    def test_validate_negative_chunk_index(self):
        """Test validation with negative chunk index."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": -1,  # Invalid
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) > 0
        assert "chunk_index" in " ".join(result["errors"])

    def test_validate_unknown_fields_warning(self):
        """Test that unknown fields generate warnings."""
        metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
            "unknown_field": "some_value",  # Unknown field
        }

        result = GitAwareMetadataSchema.validate_metadata(metadata)

        assert len(result["errors"]) == 0
        assert len(result["warnings"]) > 0
        assert "unknown_field" in " ".join(result["warnings"])

    def test_create_legacy_metadata(self):
        """Test creation of legacy metadata format."""
        metadata = GitAwareMetadataSchema.create_legacy_metadata(
            path="src/main.py",
            content="print('hello')",
            language="py",
            file_size=15,
            chunk_index=0,
            total_chunks=1,
        )

        assert metadata["path"] == "src/main.py"
        assert metadata["content"] == "print('hello')"
        assert metadata["schema_version"] == MetadataSchemaVersion.LEGACY
        assert "indexed_at" in metadata
        assert "project_id" not in metadata  # Not in legacy format

    def test_create_git_aware_metadata_with_git(self):
        """Test creation of git-aware metadata with git info."""
        git_metadata = {
            "commit_hash": "a" * 40,
            "branch": "main",
            "git_hash": "b" * 40,
        }

        metadata = GitAwareMetadataSchema.create_git_aware_metadata(
            path="src/main.py",
            content="print('hello')",
            language="py",
            file_size=15,
            chunk_index=0,
            total_chunks=1,
            project_id="test-project",
            file_hash="sha256:abc123",
            git_metadata=git_metadata,
        )

        assert metadata["git_available"] is True
        assert metadata["git_commit_hash"] == "a" * 40
        assert metadata["git_branch"] == "main"
        assert metadata["git_blob_hash"] == "b" * 40
        assert metadata["schema_version"] == MetadataSchemaVersion.GIT_AWARE

    def test_create_git_aware_metadata_without_git(self):
        """Test creation of git-aware metadata without git info."""
        metadata = GitAwareMetadataSchema.create_git_aware_metadata(
            path="src/main.py",
            content="print('hello')",
            language="py",
            file_size=15,
            chunk_index=0,
            total_chunks=1,
            project_id="test-project",
            file_hash="sha256:abc123",
            git_metadata=None,
        )

        assert metadata["git_available"] is False
        assert "git_commit_hash" not in metadata
        assert "git_branch" not in metadata
        assert metadata["schema_version"] == MetadataSchemaVersion.GIT_AWARE

    def test_migrate_legacy_metadata(self):
        """Test migration of legacy metadata to git-aware format."""
        legacy_metadata = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
        }

        migrated = GitAwareMetadataSchema.migrate_legacy_metadata(legacy_metadata)

        # Should have all original fields
        assert migrated["path"] == "src/main.py"
        assert migrated["content"] == "print('hello')"

        # Should have new required fields with defaults
        assert migrated["project_id"] == "unknown"
        assert migrated["file_hash"] == "unknown"
        assert migrated["git_available"] is False
        assert migrated["schema_version"] == MetadataSchemaVersion.GIT_AWARE

    def test_is_valid_git_hash(self):
        """Test git hash validation."""
        assert GitAwareMetadataSchema._is_valid_git_hash("a" * 40) is True
        assert GitAwareMetadataSchema._is_valid_git_hash("123abc" + "d" * 34) is True
        assert GitAwareMetadataSchema._is_valid_git_hash("short") is False
        assert (
            GitAwareMetadataSchema._is_valid_git_hash("g" * 40) is False
        )  # Invalid hex
        assert GitAwareMetadataSchema._is_valid_git_hash(None) is False
        assert GitAwareMetadataSchema._is_valid_git_hash(123) is False

    def test_is_valid_git_branch_name(self):
        """Test git branch name validation."""
        assert GitAwareMetadataSchema._is_valid_git_branch_name("main") is True
        assert GitAwareMetadataSchema._is_valid_git_branch_name("feature/abc") is True
        assert GitAwareMetadataSchema._is_valid_git_branch_name("bugfix-123") is True
        assert (
            GitAwareMetadataSchema._is_valid_git_branch_name(".main") is False
        )  # Starts with dot
        assert (
            GitAwareMetadataSchema._is_valid_git_branch_name("main..dev") is False
        )  # Contains '..'
        assert (
            GitAwareMetadataSchema._is_valid_git_branch_name("main branch") is False
        )  # Contains space
        assert (
            GitAwareMetadataSchema._is_valid_git_branch_name("main~1") is False
        )  # Contains ~
        assert GitAwareMetadataSchema._is_valid_git_branch_name("") is False
        assert GitAwareMetadataSchema._is_valid_git_branch_name(None) is False

    def test_is_valid_iso_timestamp(self):
        """Test ISO timestamp validation."""
        assert (
            GitAwareMetadataSchema._is_valid_iso_timestamp("2024-01-01T12:00:00Z")
            is True
        )
        assert (
            GitAwareMetadataSchema._is_valid_iso_timestamp("2024-01-01T12:00:00+00:00")
            is True
        )
        assert (
            GitAwareMetadataSchema._is_valid_iso_timestamp("2024-01-01T12:00:00")
            is True
        )
        assert GitAwareMetadataSchema._is_valid_iso_timestamp("not-a-date") is False
        assert GitAwareMetadataSchema._is_valid_iso_timestamp("") is False
        assert GitAwareMetadataSchema._is_valid_iso_timestamp(None) is False


class TestMetadataValidator:
    def test_validate_point_payload_valid(self):
        """Test validation of valid point payload."""
        payload = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        assert MetadataValidator.validate_point_payload(payload) is True

    def test_validate_point_payload_invalid(self):
        """Test validation of invalid point payload."""
        payload = {
            "content": "print('hello')",
            # Missing required fields
        }

        assert MetadataValidator.validate_point_payload(payload) is False

    def test_validate_batch_payloads(self):
        """Test batch validation of payloads."""
        valid_payload = {
            "path": "src/main.py",
            "content": "print('hello')",
            "language": "py",
            "file_size": 15,
            "chunk_index": 0,
            "total_chunks": 1,
            "indexed_at": "2024-01-01T12:00:00Z",
            "project_id": "test-project",
            "file_hash": "sha256:abc123",
            "git_available": False,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        invalid_payload = {
            "content": "print('hello')",
            # Missing required fields
        }

        payload_with_warning = valid_payload.copy()
        payload_with_warning["unknown_field"] = "value"

        payloads = [valid_payload, invalid_payload, payload_with_warning]
        result = MetadataValidator.validate_batch_payloads(payloads)

        assert result["total"] == 3
        assert result["valid"] == 2
        assert result["errors"] == 1
        assert result["warnings"] == 1

    def test_get_schema_version(self):
        """Test schema version detection."""
        legacy_metadata = {"path": "test"}
        git_metadata = {"schema_version": MetadataSchemaVersion.GIT_AWARE}

        assert (
            MetadataValidator.get_schema_version(legacy_metadata)
            == MetadataSchemaVersion.LEGACY
        )
        assert (
            MetadataValidator.get_schema_version(git_metadata)
            == MetadataSchemaVersion.GIT_AWARE
        )

    def test_needs_migration(self):
        """Test migration need detection."""
        legacy_metadata = {"path": "test"}
        current_metadata = {"schema_version": MetadataSchemaVersion.CURRENT}

        assert MetadataValidator.needs_migration(legacy_metadata) is True
        assert MetadataValidator.needs_migration(current_metadata) is False
