"""
Enhanced metadata schema for git-aware vector indexing.

This module defines the schema for git-aware metadata stored in vector database payloads,
provides validation utilities, and supports migration from legacy metadata formats.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import re


class MetadataSchemaVersion:
    """Schema version definitions for metadata evolution."""

    LEGACY = "1.0"  # Original file-based metadata
    GIT_AWARE = "2.0"  # Git-aware metadata with branch/commit info

    CURRENT = GIT_AWARE


class GitAwareMetadataSchema:
    """
    Enhanced metadata schema supporting git-aware indexing.

    This schema extends the original metadata with git-specific fields while
    maintaining backward compatibility with non-git projects.
    """

    # Core metadata fields (required)
    REQUIRED_FIELDS = {
        "path",  # Absolute file path
        "content",  # Text content of the chunk
        "language",  # Programming language/file extension
        "file_size",  # File size in bytes
        "chunk_index",  # Index of chunk within file
        "total_chunks",  # Total number of chunks in file
        "indexed_at",  # ISO timestamp when indexed
        "project_id",  # Unique project identifier
        "file_hash",  # Content hash of the file
        "git_available",  # Whether git metadata is available
        "schema_version",  # Metadata schema version
    }

    # Git-specific fields (optional, when git_available=True)
    GIT_FIELDS = {
        "git_commit_hash",  # Full git commit hash
        "git_branch",  # Git branch name
        "git_blob_hash",  # Git blob hash for file content
    }

    # Filesystem fallback fields (optional, when git_available=False)
    FILESYSTEM_FIELDS = {
        "filesystem_mtime",  # File modification timestamp
        "filesystem_size",  # File size from filesystem
    }

    # All possible fields
    ALL_FIELDS = REQUIRED_FIELDS | GIT_FIELDS | FILESYSTEM_FIELDS

    @classmethod
    def validate_metadata(cls, metadata: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Validate metadata against the git-aware schema.

        Args:
            metadata: Metadata dictionary to validate

        Returns:
            Dictionary with 'errors' and 'warnings' lists
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in metadata:
                errors.append(f"Missing required field: {field}")
            elif metadata[field] is None:
                errors.append(f"Required field cannot be None: {field}")

        # Validate specific field formats
        if "indexed_at" in metadata:
            if not cls._is_valid_iso_timestamp(metadata["indexed_at"]):
                errors.append("Field 'indexed_at' must be valid ISO timestamp")

        if "git_available" in metadata:
            if not isinstance(metadata["git_available"], bool):
                errors.append("Field 'git_available' must be boolean")
            else:
                # Validate git-specific requirements
                if metadata["git_available"]:
                    cls._validate_git_metadata(metadata, errors, warnings)
                else:
                    cls._validate_filesystem_metadata(metadata, errors, warnings)

        if "chunk_index" in metadata:
            if (
                not isinstance(metadata["chunk_index"], int)
                or metadata["chunk_index"] < 0
            ):
                errors.append("Field 'chunk_index' must be non-negative integer")

        if "total_chunks" in metadata:
            if (
                not isinstance(metadata["total_chunks"], int)
                or metadata["total_chunks"] < 1
            ):
                errors.append("Field 'total_chunks' must be positive integer")

        if "file_size" in metadata:
            if not isinstance(metadata["file_size"], int) or metadata["file_size"] < 0:
                errors.append("Field 'file_size' must be non-negative integer")

        # Check for unknown fields
        unknown_fields = set(metadata.keys()) - cls.ALL_FIELDS
        if unknown_fields:
            warnings.append(f"Unknown fields found: {', '.join(unknown_fields)}")

        return {"errors": errors, "warnings": warnings}

    @classmethod
    def _validate_git_metadata(
        cls, metadata: Dict[str, Any], errors: List[str], warnings: List[str]
    ):
        """Validate git-specific metadata fields."""
        if "git_commit_hash" in metadata:
            commit_hash = metadata["git_commit_hash"]
            if commit_hash and not cls._is_valid_git_hash(commit_hash):
                errors.append(
                    "Field 'git_commit_hash' must be valid 40-character git hash"
                )

        if "git_blob_hash" in metadata:
            blob_hash = metadata["git_blob_hash"]
            if blob_hash and not cls._is_valid_git_hash(blob_hash):
                errors.append(
                    "Field 'git_blob_hash' must be valid 40-character git hash"
                )

        if "git_branch" in metadata:
            branch = metadata["git_branch"]
            if branch and not cls._is_valid_git_branch_name(branch):
                warnings.append(f"Field 'git_branch' has unusual format: {branch}")

        # Check for missing recommended git fields
        recommended_git_fields = {"git_commit_hash", "git_branch"}
        missing_git_fields = recommended_git_fields - set(metadata.keys())
        if missing_git_fields:
            warnings.append(
                f"Recommended git fields missing: {', '.join(missing_git_fields)}"
            )

    @classmethod
    def _validate_filesystem_metadata(
        cls, metadata: Dict[str, Any], errors: List[str], warnings: List[str]
    ):
        """Validate filesystem-specific metadata fields."""
        if "filesystem_mtime" in metadata:
            mtime = metadata["filesystem_mtime"]
            if mtime and not isinstance(mtime, (int, float)):
                errors.append("Field 'filesystem_mtime' must be numeric timestamp")

        if "filesystem_size" in metadata:
            size = metadata["filesystem_size"]
            if size and not isinstance(size, int):
                errors.append("Field 'filesystem_size' must be integer")

    @classmethod
    def _is_valid_iso_timestamp(cls, timestamp: str) -> bool:
        """Check if string is valid ISO timestamp."""
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return True
        except (ValueError, AttributeError):
            return False

    @classmethod
    def _is_valid_git_hash(cls, hash_str: str) -> bool:
        """Check if string is valid git hash (40 hex characters)."""
        if not isinstance(hash_str, str):
            return False
        return re.match(r"^[a-f0-9]{40}$", hash_str) is not None

    @classmethod
    def _is_valid_git_branch_name(cls, branch_name: str) -> bool:
        """Check if string is valid git branch name."""
        if not isinstance(branch_name, str) or not branch_name:
            return False

        # Basic git branch name validation
        # Cannot start with '.', cannot contain '..'
        if branch_name.startswith(".") or ".." in branch_name:
            return False

        # Cannot contain certain characters
        invalid_chars = ["~", "^", ":", "?", "*", "[", "\\", " "]
        if any(char in branch_name for char in invalid_chars):
            return False

        return True

    @classmethod
    def create_legacy_metadata(
        cls,
        path: str,
        content: str,
        language: str,
        file_size: int,
        chunk_index: int,
        total_chunks: int,
    ) -> Dict[str, Any]:
        """
        Create legacy-compatible metadata for backward compatibility.

        Args:
            path: Relative file path
            content: Chunk content
            language: Programming language
            file_size: File size in bytes
            chunk_index: Chunk index
            total_chunks: Total chunks in file

        Returns:
            Legacy metadata dictionary
        """
        return {
            "path": path,
            "content": content,
            "language": language,
            "file_size": file_size,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "indexed_at": datetime.utcnow().isoformat() + "Z",
            "schema_version": MetadataSchemaVersion.LEGACY,
        }

    @classmethod
    def create_git_aware_metadata(
        cls,
        path: str,
        content: str,
        language: str,
        file_size: int,
        chunk_index: int,
        total_chunks: int,
        project_id: str,
        file_hash: str,
        git_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create git-aware metadata with full schema support.

        Args:
            path: Absolute file path
            content: Chunk content
            language: Programming language
            file_size: File size in bytes
            chunk_index: Chunk index
            total_chunks: Total chunks in file
            project_id: Project identifier
            file_hash: File content hash
            git_metadata: Optional git-specific metadata

        Returns:
            Git-aware metadata dictionary
        """
        metadata = {
            "path": path,
            "content": content,
            "language": language,
            "file_size": file_size,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "indexed_at": datetime.utcnow().isoformat() + "Z",
            "project_id": project_id,
            "file_hash": file_hash,
            "git_available": git_metadata is not None,
            "schema_version": MetadataSchemaVersion.GIT_AWARE,
        }

        if git_metadata:
            # Add git-specific fields
            if "commit_hash" in git_metadata:
                metadata["git_commit_hash"] = git_metadata["commit_hash"]
            if "branch" in git_metadata:
                metadata["git_branch"] = git_metadata["branch"]
            if "git_hash" in git_metadata:
                metadata["git_blob_hash"] = git_metadata["git_hash"]
        else:
            # Add filesystem fallback fields if available
            # Note: In this case git_metadata is None, so no filesystem metadata to add
            pass

        return metadata

    @classmethod
    def migrate_legacy_metadata(cls, legacy_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate legacy metadata to git-aware schema.

        Args:
            legacy_metadata: Legacy metadata dictionary

        Returns:
            Git-aware metadata dictionary with defaults for missing fields
        """
        # Start with legacy metadata
        migrated = legacy_metadata.copy()

        # Add required new fields with defaults
        migrated.setdefault("project_id", "unknown")
        migrated.setdefault("file_hash", "unknown")
        migrated.setdefault("git_available", False)
        migrated.setdefault("schema_version", MetadataSchemaVersion.GIT_AWARE)

        # Ensure indexed_at is present
        if "indexed_at" not in migrated:
            migrated["indexed_at"] = datetime.utcnow().isoformat() + "Z"

        return migrated


class MetadataValidator:
    """Utility class for validating metadata in various contexts."""

    @staticmethod
    def validate_point_payload(payload: Dict[str, Any]) -> bool:
        """
        Quick validation for Qdrant point payloads.

        Args:
            payload: Point payload dictionary

        Returns:
            True if payload is valid, False otherwise
        """
        validation_result = GitAwareMetadataSchema.validate_metadata(payload)
        return len(validation_result["errors"]) == 0

    @staticmethod
    def validate_batch_payloads(payloads: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Validate a batch of payloads and return summary statistics.

        Args:
            payloads: List of payload dictionaries

        Returns:
            Dictionary with validation statistics
        """
        valid_count = 0
        error_count = 0
        warning_count = 0

        for payload in payloads:
            result = GitAwareMetadataSchema.validate_metadata(payload)
            if len(result["errors"]) == 0:
                valid_count += 1
            else:
                error_count += 1

            if len(result["warnings"]) > 0:
                warning_count += 1

        return {
            "total": len(payloads),
            "valid": valid_count,
            "errors": error_count,
            "warnings": warning_count,
        }

    @staticmethod
    def get_schema_version(metadata: Dict[str, Any]) -> str:
        """
        Determine the schema version of metadata.

        Args:
            metadata: Metadata dictionary

        Returns:
            Schema version string
        """
        return str(metadata.get("schema_version", MetadataSchemaVersion.LEGACY))

    @staticmethod
    def needs_migration(metadata: Dict[str, Any]) -> bool:
        """
        Check if metadata needs migration to current schema.

        Args:
            metadata: Metadata dictionary

        Returns:
            True if migration is needed, False otherwise
        """
        current_version = MetadataValidator.get_schema_version(metadata)
        return current_version != MetadataSchemaVersion.CURRENT
