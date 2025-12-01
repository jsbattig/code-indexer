"""Factory for creating vector storage backends."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .vector_store_backend import VectorStoreBackend
from .filesystem_backend import FilesystemBackend

if TYPE_CHECKING:
    from ..config import Config

logger = logging.getLogger(__name__)


class BackendFactory:
    """Factory for creating vector storage backend from configuration."""

    @staticmethod
    def create(
        config: "Config", project_root: Path, hnsw_cache: Optional[Any] = None
    ) -> VectorStoreBackend:
        """Create appropriate backend from configuration.

        Args:
            config: Configuration object
            project_root: Root directory of the project being indexed
            hnsw_cache: Optional HNSW cache instance (server mode passes this)

        Returns:
            FilesystemBackend instance

        Raises:
            ValueError: If configuration is invalid
        """
        if config.vector_store is None:
            raise ValueError("Invalid configuration: missing vector_store field")

        provider = config.vector_store.provider

        if provider == "filesystem":
            logger.info("Creating FilesystemBackend")
            return FilesystemBackend(
                project_root=project_root, hnsw_index_cache=hnsw_cache
            )
        else:
            raise ValueError(f"Unsupported vector store provider: {provider}")

    @staticmethod
    def create_from_legacy_config(
        config: "Config", project_root: Path
    ) -> VectorStoreBackend:
        """Reject legacy configuration attempts.

        Args:
            config: Configuration object
            project_root: Root directory of the project being indexed

        Raises:
            ValueError: Always
        """
        raise ValueError("Invalid configuration")
