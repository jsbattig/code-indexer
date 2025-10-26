"""Filesystem-based vector storage backend.

Provides container-free vector storage using the local filesystem.
Suitable for environments where Docker/Podman containers are not available.
"""

import logging
import shutil
from pathlib import Path
from typing import Any, Dict

from .vector_store_backend import VectorStoreBackend

logger = logging.getLogger(__name__)


class FilesystemBackend(VectorStoreBackend):
    """Filesystem-based vector storage backend.

    Stores vector data in .code-indexer/index/ directory using local filesystem.
    No containers required - suitable for container-restricted environments.

    Directory structure:
        project_root/
        └── .code-indexer/
            └── index/
                └── (vector storage files)
    """

    def __init__(self, project_root: Path):
        """Initialize FilesystemBackend.

        Args:
            project_root: Root directory of the project being indexed
        """
        super().__init__(project_root)
        self.vectors_dir = self.project_root / ".code-indexer" / "index"

    def initialize(self) -> None:
        """Initialize filesystem storage by creating index directory.

        Creates .code-indexer/index/ directory structure.

        Raises:
            RuntimeError: If directory creation fails
        """
        try:
            self.vectors_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Initialized filesystem backend at {self.vectors_dir}")
        except Exception as e:
            raise RuntimeError(f"Failed to initialize filesystem backend: {e}")

    def start(self) -> bool:
        """Start backend services (no-op for filesystem).

        Returns:
            True (always succeeds immediately)
        """
        logger.debug("FilesystemBackend.start() - no-op")
        return True

    def stop(self) -> bool:
        """Stop backend services (no-op for filesystem).

        Returns:
            True (always succeeds immediately)
        """
        logger.debug("FilesystemBackend.stop() - no-op")
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get current status of filesystem backend.

        Returns:
            Dictionary containing:
                - provider: "filesystem"
                - status: "ready" if vectors_dir exists, "not_initialized" otherwise
                - vectors_dir: Path to vectors directory
                - writable: Whether vectors_dir is writable
        """
        if not self.vectors_dir.exists():
            return {
                "provider": "filesystem",
                "status": "not_initialized",
                "vectors_dir": str(self.vectors_dir),
                "writable": False,
            }

        # Check if directory is writable
        writable = self._check_writable()

        return {
            "provider": "filesystem",
            "status": "ready" if writable else "error",
            "vectors_dir": str(self.vectors_dir),
            "writable": writable,
        }

    def cleanup(self) -> None:
        """Clean up filesystem storage by removing index directory.

        Removes .code-indexer/index/ and all its contents.

        Raises:
            RuntimeError: If cleanup fails
        """
        try:
            if self.vectors_dir.exists():
                shutil.rmtree(self.vectors_dir)
                logger.info(f"Cleaned up filesystem backend at {self.vectors_dir}")
        except Exception as e:
            raise RuntimeError(f"Failed to cleanup filesystem backend: {e}")

    def get_vector_store_client(self) -> Any:
        """Get the vector store client instance.

        For filesystem backend, this returns a FilesystemVectorStore instance.

        Returns:
            FilesystemVectorStore instance configured for this project
        """
        from ..storage.filesystem_vector_store import FilesystemVectorStore

        return FilesystemVectorStore(
            base_path=self.vectors_dir,
            project_root=self.project_root
        )

    def health_check(self) -> bool:
        """Check if backend is healthy and operational.

        Verifies:
        - vectors directory exists
        - vectors directory is writable

        Returns:
            True if backend is healthy, False otherwise
        """
        if not self.vectors_dir.exists():
            logger.warning(f"Health check failed: {self.vectors_dir} does not exist")
            return False

        writable = self._check_writable()
        if not writable:
            logger.warning(f"Health check failed: {self.vectors_dir} is not writable")

        return writable

    def get_service_info(self) -> Dict[str, Any]:
        """Get information about filesystem backend.

        Returns:
            Dictionary containing:
                - provider: "filesystem"
                - vectors_dir: Path to vectors directory
                - requires_containers: False
        """
        return {
            "provider": "filesystem",
            "vectors_dir": str(self.vectors_dir),
            "requires_containers": False,
        }

    def optimize(self) -> bool:
        """Optimize vector storage (no-op for filesystem).

        Returns:
            True (always succeeds, no optimization needed)
        """
        logger.debug("FilesystemBackend.optimize() - no-op")
        return True

    def force_flush(self) -> bool:
        """Force flush pending operations (no-op for filesystem).

        Returns:
            True (always succeeds, no flush needed)
        """
        logger.debug("FilesystemBackend.force_flush() - no-op")
        return True

    def _check_writable(self) -> bool:
        """Check if vectors directory is writable.

        Returns:
            True if writable, False otherwise
        """
        try:
            # Try to create a test file to verify write access
            test_file = self.vectors_dir / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except Exception:
            return False
