"""
Concurrency protection for password change operations.

Implements row-level locking to prevent concurrent password modifications.
Following CLAUDE.md principles: NO MOCKS - Real concurrency protection.
"""

import os
import time
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional


class PasswordChangeConcurrencyProtection:
    """
    Concurrency protection for password change operations.

    Security requirements:
    - Prevent concurrent password changes for the same user
    - Return 409 Conflict for concurrent attempts
    - Clean up abandoned locks automatically
    - Thread-safe implementation
    """

    def __init__(self, lock_dir: Optional[str] = None):
        """
        Initialize concurrency protection.

        Args:
            lock_dir: Optional custom directory for lock files
        """
        if lock_dir:
            self.lock_dir = Path(lock_dir)
        else:
            # Default lock directory
            server_dir = Path.home() / ".cidx-server" / "locks"
            self.lock_dir = server_dir

        # Ensure lock directory exists
        self.lock_dir.mkdir(parents=True, exist_ok=True)

        self._lock_timeout_seconds = 30  # Maximum time to hold a lock

    @contextmanager
    def acquire_password_change_lock(
        self, username: str
    ) -> Generator[bool, None, None]:
        """
        Acquire exclusive lock for password change operation.

        Args:
            username: Username to lock for password change

        Yields:
            True if lock acquired successfully

        Raises:
            ConcurrencyConflictError: If lock cannot be acquired (concurrent change in progress)
        """
        lock_file_path = self.lock_dir / f"password_change_{username}.lock"
        lock_file = None

        try:
            # Create lock file
            lock_file = open(lock_file_path, "w")

            try:
                # Try to acquire exclusive lock (non-blocking)
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Write current process info to lock file
                lock_file.write(f"pid={os.getpid()}\n")
                lock_file.write(f"timestamp={time.time()}\n")
                lock_file.flush()

                # Lock acquired successfully
                yield True

            except (IOError, OSError):
                # Lock is already held by another process
                raise ConcurrencyConflictError(
                    f"Password change already in progress for user '{username}'. Please try again in a few moments."
                )

        finally:
            # Always clean up lock file and handle
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                except (IOError, OSError):
                    pass  # Ignore unlock errors

                try:
                    lock_file.close()
                except (IOError, OSError):
                    pass  # Ignore close errors

            # Remove lock file
            try:
                if lock_file_path.exists():
                    lock_file_path.unlink()
            except (IOError, OSError):
                pass  # Ignore file deletion errors

    def cleanup_stale_locks(self, max_age_seconds: int = 300) -> int:
        """
        Clean up stale lock files that are older than max_age_seconds.

        Args:
            max_age_seconds: Maximum age for lock files before cleanup

        Returns:
            Number of stale locks cleaned up
        """
        current_time = time.time()
        cleaned_count = 0

        try:
            for lock_file_path in self.lock_dir.glob("password_change_*.lock"):
                try:
                    # Check file modification time
                    file_mtime = lock_file_path.stat().st_mtime

                    if current_time - file_mtime > max_age_seconds:
                        # Try to remove stale lock file
                        lock_file_path.unlink()
                        cleaned_count += 1

                except (IOError, OSError):
                    # If we can't access/remove the file, skip it
                    continue

        except (IOError, OSError):
            # If we can't access the lock directory, return 0
            return 0

        return cleaned_count

    def is_user_locked(self, username: str) -> bool:
        """
        Check if a user currently has a password change lock.

        Args:
            username: Username to check

        Returns:
            True if user has an active lock, False otherwise
        """
        lock_file_path = self.lock_dir / f"password_change_{username}.lock"

        if not lock_file_path.exists():
            return False

        try:
            # Try to open and lock the file
            with open(lock_file_path, "r") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # If we can acquire the lock, it means no one else has it
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                return False

        except (IOError, OSError):
            # If we can't acquire the lock, someone else has it
            return True


class ConcurrencyConflictError(Exception):
    """Exception raised when a concurrency conflict occurs during password change."""

    pass


# Global concurrency protection instance
password_change_concurrency_protection = PasswordChangeConcurrencyProtection()
