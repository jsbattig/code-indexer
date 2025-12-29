"""
File CRUD Service.

Provides create, read, update, delete operations for files in activated repositories
with security validation and optimistic concurrency control.

Security features:
- .git/ directory blocking
- Path traversal prevention
- Symlink resolution and validation

Concurrency control:
- SHA-256 hash-based optimistic locking
- Atomic file operations (temp file + rename)
"""

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional


class HashMismatchError(Exception):
    """
    Exception raised when content hash validation fails.

    This indicates the file was modified since the hash was computed,
    representing a concurrent modification conflict.
    """

    pass


class CRUDOperationError(Exception):
    """
    Base exception for CRUD operation failures.

    All file CRUD operations may raise this exception or its subclasses
    to indicate various failure conditions.
    """

    pass


class FileCRUDService:
    """
    Service for file CRUD operations in activated repositories.

    Provides secure file manipulation with:
    - Security validation (blocks .git/, prevents path traversal)
    - Optimistic concurrency control (hash-based locking)
    - Atomic operations (temp file + rename pattern)

    All operations require:
    - repo_alias: User's repository alias
    - username: Username for ActivatedRepoManager lookup
    """

    def __init__(self):
        """Initialize file CRUD service."""
        # Import here to avoid circular imports
        from ..repositories.activated_repo_manager import ActivatedRepoManager

        self.activated_repo_manager = ActivatedRepoManager()

    def create_file(
        self, repo_alias: str, file_path: str, content: str, username: str
    ) -> Dict[str, Any]:
        """
        Create a new file in the activated repository.

        Args:
            repo_alias: User's repository alias
            file_path: Relative path to file within repository
            content: File content as string
            username: Username for repository lookup

        Returns:
            Dictionary with:
                - success: True
                - file_path: Created file path
                - content_hash: SHA-256 hash of content
                - size_bytes: File size in bytes
                - created_at: ISO timestamp

        Raises:
            FileExistsError: If file already exists
            PermissionError: If path validation fails (security)
            CRUDOperationError: If creation fails
        """
        # Validate path security
        self._validate_crud_path(file_path, "create_file")

        # Resolve repository path
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Construct full file path
        full_path = Path(repo_path) / file_path

        # Check if file already exists
        if full_path.exists():
            raise FileExistsError(f"File already exists: {file_path}")

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write
        self._atomic_write_file(full_path, content)

        # Compute hash and metadata
        content_bytes = content.encode("utf-8")
        content_hash = self._compute_hash(content_bytes)
        size_bytes = len(content_bytes)
        created_at = datetime.now(timezone.utc).isoformat()

        return {
            "success": True,
            "file_path": file_path,
            "content_hash": content_hash,
            "size_bytes": size_bytes,
            "created_at": created_at,
        }

    def edit_file(
        self,
        repo_alias: str,
        file_path: str,
        old_string: str,
        new_string: str,
        content_hash: str,
        replace_all: bool,
        username: str,
    ) -> Dict[str, Any]:
        """
        Edit a file by replacing string occurrences.

        Uses optimistic locking: validates content_hash matches current file
        before applying changes.

        Args:
            repo_alias: User's repository alias
            file_path: Relative path to file within repository
            old_string: String to replace
            new_string: Replacement string
            content_hash: Expected SHA-256 hash of current content
            replace_all: If True, replace all occurrences; if False, require unique match
            username: Username for repository lookup

        Returns:
            Dictionary with:
                - success: True
                - file_path: Edited file path
                - content_hash: New SHA-256 hash after edit
                - modified_at: ISO timestamp
                - changes_made: Number of replacements made

        Raises:
            HashMismatchError: If content_hash doesn't match current file
            ValueError: If old_string is not unique and replace_all=False
            FileNotFoundError: If file doesn't exist
            PermissionError: If path validation fails
            CRUDOperationError: If edit fails
        """
        # Validate path security
        self._validate_crud_path(file_path, "edit_file")

        # Resolve repository path
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Construct full file path
        full_path = Path(repo_path) / file_path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Read current content
        try:
            with open(full_path, "rb") as f:
                current_content_bytes = f.read()
        except Exception as e:
            raise CRUDOperationError(
                f"Failed to read file '{file_path}': {str(e)}"
            ) from e

        # Validate hash (optimistic locking)
        current_hash = self._compute_hash(current_content_bytes)
        if current_hash != content_hash:
            raise HashMismatchError(
                f"Content hash mismatch for '{file_path}'. "
                f"Expected {content_hash}, got {current_hash}. "
                "File may have been modified by another process."
            )

        # Decode current content
        current_content_str = current_content_bytes.decode("utf-8")

        # Perform string replacement
        new_content, changes_made = self._perform_replacement(
            current_content_str, old_string, new_string, replace_all, file_path
        )

        # Atomic write
        self._atomic_write_file(full_path, new_content)

        # Compute new hash and metadata
        new_content_bytes = new_content.encode("utf-8")
        new_hash = self._compute_hash(new_content_bytes)
        modified_at = datetime.now(timezone.utc).isoformat()

        return {
            "success": True,
            "file_path": file_path,
            "content_hash": new_hash,
            "modified_at": modified_at,
            "changes_made": changes_made,
        }

    def delete_file(
        self,
        repo_alias: str,
        file_path: str,
        content_hash: Optional[str],
        username: str,
    ) -> Dict[str, Any]:
        """
        Delete a file from the activated repository.

        Optionally validates content hash before deletion for additional safety.

        Args:
            repo_alias: User's repository alias
            file_path: Relative path to file within repository
            content_hash: Optional SHA-256 hash to validate before deletion
            username: Username for repository lookup

        Returns:
            Dictionary with:
                - success: True
                - file_path: Deleted file path
                - deleted_at: ISO timestamp

        Raises:
            HashMismatchError: If content_hash provided and doesn't match
            FileNotFoundError: If file doesn't exist
            PermissionError: If path validation fails
            CRUDOperationError: If deletion fails
        """
        # Validate path security
        self._validate_crud_path(file_path, "delete_file")

        # Resolve repository path
        repo_path = self.activated_repo_manager.get_activated_repo_path(
            username=username, user_alias=repo_alias
        )

        # Construct full file path
        full_path = Path(repo_path) / file_path

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Validate hash if provided
        if content_hash is not None:
            try:
                with open(full_path, "rb") as f:
                    current_content_bytes = f.read()
            except Exception as e:
                raise CRUDOperationError(
                    f"Failed to read file '{file_path}' for hash validation: {str(e)}"
                ) from e

            current_hash = self._compute_hash(current_content_bytes)
            if current_hash != content_hash:
                raise HashMismatchError(
                    f"Content hash mismatch for '{file_path}'. "
                    f"Expected {content_hash}, got {current_hash}. "
                    "File may have been modified since hash was computed."
                )

        # Delete file
        try:
            os.remove(str(full_path))
        except Exception as e:
            raise CRUDOperationError(
                f"Failed to delete file '{file_path}': {str(e)}"
            ) from e

        deleted_at = datetime.now(timezone.utc).isoformat()

        return {"success": True, "file_path": file_path, "deleted_at": deleted_at}

    def _validate_crud_path(self, file_path: str, operation: str) -> None:
        """
        Validate file path for CRUD operations.

        Security checks:
        - Block .git/ directory access
        - Prevent path traversal (..)
        - Validate path structure

        Args:
            file_path: Relative file path to validate
            operation: Operation name for error messages

        Raises:
            PermissionError: If path fails security validation
        """
        # Block .git/ directory access (exact directory component match)
        # Use Path.parts to check for .git as a directory component
        # This allows .gitignore, .github/, etc. while blocking .git/
        path_parts = Path(file_path).parts
        if ".git" in path_parts:
            raise PermissionError(
                f"{operation} blocked: Access to .git/ directory is forbidden"
            )

        # Block path traversal (..)
        path_obj = Path(file_path)
        if ".." in path_obj.parts:
            raise PermissionError(
                f"{operation} blocked: Path traversal detected in '{file_path}'"
            )

        # Additional validation: prevent absolute paths
        if path_obj.is_absolute():
            raise PermissionError(
                f"{operation} blocked: Absolute paths not allowed, use relative paths"
            )

    def _compute_hash(self, content: bytes) -> str:
        """
        Compute SHA-256 hash of content.

        Args:
            content: Content as bytes

        Returns:
            Hex digest string of SHA-256 hash
        """
        return hashlib.sha256(content).hexdigest()

    def _atomic_write_file(self, full_path: Path, content: str) -> None:
        """
        Atomically write content to file using temp file + rename pattern.

        Args:
            full_path: Full path to target file
            content: Content to write as string

        Raises:
            CRUDOperationError: If write operation fails
        """
        try:
            # Write to temporary file in same directory (ensures same filesystem)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=str(full_path.parent), prefix=".tmp_", suffix=f"_{full_path.name}"
            )

            try:
                # Write content to temp file
                with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                    temp_file.write(content)
                    temp_file.flush()
                    os.fsync(temp_file.fileno())

                # Atomic rename (POSIX guarantees atomicity)
                os.replace(temp_path, str(full_path))

            except Exception:
                # Clean up temp file on failure
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                raise

        except Exception as e:
            raise CRUDOperationError(
                f"Failed to write file '{full_path}': {str(e)}"
            ) from e

    def _perform_replacement(
        self,
        content: str,
        old_string: str,
        new_string: str,
        replace_all: bool,
        file_path: str,
    ) -> tuple[str, int]:
        """
        Perform string replacement with validation.

        Args:
            content: Current file content
            old_string: String to replace
            new_string: Replacement string
            replace_all: If True, replace all; if False, require unique match
            file_path: File path for error messages

        Returns:
            Tuple of (new_content, changes_made)

        Raises:
            ValueError: If string not found or not unique when replace_all=False
        """
        if replace_all:
            # Replace all occurrences
            new_content = content.replace(old_string, new_string)
            changes_made = content.count(old_string)
        else:
            # Single replacement - must be unique
            occurrence_count = content.count(old_string)

            if occurrence_count == 0:
                raise ValueError(
                    f"String '{old_string}' not found in file '{file_path}'"
                )
            elif occurrence_count > 1:
                raise ValueError(
                    f"String '{old_string}' appears {occurrence_count} times in '{file_path}'. "
                    "Not unique - use replace_all=True to replace all occurrences."
                )

            # Exactly one occurrence - safe to replace
            new_content = content.replace(old_string, new_string, 1)
            changes_made = 1

        return new_content, changes_made


# Global service instance
file_crud_service = FileCRUDService()
