"""Background index rebuilder with atomic file swapping.

Provides unified background rebuild strategy for all index types (HNSW, ID, FTS)
with file locking for cross-process coordination and atomic swap to prevent
blocking query operations.

Key Features:
- File locking using fcntl for cross-process coordination
- Atomic file swap using os.rename (kernel-level atomic operation)
- Lock held for entire rebuild duration (not just swap)
- Queries don't need locks (OS-level atomic rename guarantees)
- Cleanup of orphaned .tmp files after crashes

Architecture:
    1. Acquire exclusive lock (.index_rebuild.lock)
    2. Build index to .tmp file
    3. Atomic rename .tmp → target (OS guarantees atomicity)
    4. Release lock

This pattern serializes all rebuild workers across processes while allowing
queries to continue reading the old index without blocking.
"""

import contextlib
import fcntl
import logging
import os
import time
from pathlib import Path
from typing import Callable, Generator

logger = logging.getLogger(__name__)


class BackgroundIndexRebuilder:
    """Manages background index rebuilding with atomic swaps and file locking.

    Provides:
    - Cross-process exclusive locking for rebuild serialization
    - Atomic file swap (build to .tmp, rename atomically)
    - Cleanup of orphaned .tmp files after crashes
    - Support for both file-based and directory-based indexes
    """

    def __init__(
        self, collection_path: Path, lock_filename: str = ".index_rebuild.lock"
    ):
        """Initialize BackgroundIndexRebuilder.

        Args:
            collection_path: Path to collection directory
            lock_filename: Name of lock file (default: .index_rebuild.lock)
        """
        self.collection_path = Path(collection_path)
        self.lock_file = self.collection_path / lock_filename

        # Ensure collection directory exists
        self.collection_path.mkdir(parents=True, exist_ok=True)

        # Create lock file if it doesn't exist
        self.lock_file.touch(exist_ok=True)

    @contextlib.contextmanager
    def acquire_lock(self) -> Generator[None, None, None]:
        """Acquire exclusive lock for rebuild operations.

        Uses fcntl.flock() for cross-process coordination. Blocks if another
        process/thread holds the lock.

        Yields:
            None (context manager for 'with' statement)

        Note:
            Lock is automatically released when context exits.
        """
        with open(self.lock_file, "r") as lock_f:
            try:
                # Acquire exclusive lock (blocks if another process holds it)
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
                logger.debug(f"Acquired rebuild lock: {self.lock_file}")
                yield
            finally:
                # Release lock
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                logger.debug(f"Released rebuild lock: {self.lock_file}")

    def atomic_swap(self, temp_file: Path, target_file: Path) -> None:
        """Atomically swap temp file to target file.

        Uses os.rename() which is guaranteed to be atomic at the kernel level.
        Old target file (if exists) is automatically unlinked by the OS when
        no processes have it open.

        Args:
            temp_file: Path to temporary file to swap from
            target_file: Path to target file to swap to

        Note:
            If target_file exists, it will be atomically replaced. The OS
            handles cleanup of the old file once all file handles are closed.
        """
        # Verify temp file exists
        if not temp_file.exists():
            raise FileNotFoundError(f"Temp file does not exist: {temp_file}")

        # Atomic rename (kernel-level atomic operation)
        # This is why queries don't need locks - the rename is instantaneous
        os.rename(temp_file, target_file)

        logger.debug(f"Atomic swap: {temp_file} → {target_file}")

    def rebuild_with_lock(
        self, build_fn: Callable[[Path], None], target_file: Path
    ) -> None:
        """Rebuild index in background with lock held for entire duration.

        Pattern:
            1. Acquire exclusive lock
            2. Cleanup orphaned .tmp files from crashes (AC9)
            3. Build index to .tmp file
            4. Atomic swap .tmp → target
            5. Release lock

        Args:
            build_fn: Function that builds index to temp file
                     Signature: build_fn(temp_file: Path) -> None
            target_file: Path to target index file

        Note:
            Lock is held for ENTIRE rebuild, not just atomic swap. This
            serializes all rebuild workers across processes. Queries DON'T
            need locks because they read from the target file and OS-level
            atomic rename guarantees they see either old or new index.
        """
        temp_file = Path(str(target_file) + ".tmp")

        try:
            with self.acquire_lock():
                logger.info(f"Starting background rebuild: {target_file}")

                # FIRST: Cleanup orphaned .tmp files from crashes (AC9)
                # This prevents disk space leaks and ensures clean rebuild state
                removed_count = self.cleanup_orphaned_temp_files()
                if removed_count > 0:
                    logger.info(
                        f"Cleaned up {removed_count} orphaned temp files before rebuild"
                    )

                # Build index to temp file
                build_fn(temp_file)

                # Atomic swap
                self.atomic_swap(temp_file, target_file)

                logger.info(f"Completed background rebuild: {target_file}")

        except Exception:
            # Cleanup temp file on error
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temp file after error: {temp_file}")
            raise

    def cleanup_orphaned_temp_files(self, age_threshold_seconds: int = 3600) -> int:
        """Clean up orphaned .tmp files/directories after crashes.

        Scans collection directory for .tmp files and directories older than
        threshold and removes them. This handles cleanup after process crashes
        that left temp files/directories behind.

        Args:
            age_threshold_seconds: Age threshold in seconds (default: 1 hour)

        Returns:
            Number of temp files/directories removed

        Note:
            Only removes files/directories ending in .tmp that are older than threshold.
            Recent temp files (from active rebuilds) are preserved.
            Handles both file-based indexes (HNSW, ID) and directory-based indexes (FTS).
        """
        import shutil

        removed_count = 0
        current_time = time.time()

        # Find all .tmp files and directories
        for temp_path in self.collection_path.glob("*.tmp"):
            # Get file/directory age
            file_mtime = temp_path.stat().st_mtime
            file_age_seconds = current_time - file_mtime

            # Remove if older than threshold
            if file_age_seconds > age_threshold_seconds:
                try:
                    if temp_path.is_dir():
                        # Remove directory recursively (for FTS indexes)
                        shutil.rmtree(temp_path)
                        logger.info(
                            f"Removed orphaned temp directory (age: {file_age_seconds:.0f}s): {temp_path}"
                        )
                    else:
                        # Remove file (for HNSW/ID indexes)
                        temp_path.unlink()
                        logger.info(
                            f"Removed orphaned temp file (age: {file_age_seconds:.0f}s): {temp_path}"
                        )
                    removed_count += 1
                except Exception as e:
                    logger.warning(
                        f"Failed to remove orphaned temp path {temp_path}: {e}"
                    )

        if removed_count > 0:
            logger.info(
                f"Cleanup complete: removed {removed_count} orphaned temp files/directories"
            )

        return removed_count
