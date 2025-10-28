"""Factory for creating vector storage backends.

Provides backward compatibility for legacy configs while supporting new filesystem backend.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .vector_store_backend import VectorStoreBackend
from .filesystem_backend import FilesystemBackend
from .qdrant_container_backend import QdrantContainerBackend

if TYPE_CHECKING:
    from ..config import Config

logger = logging.getLogger(__name__)


class BackendFactory:
    """Factory for creating appropriate vector storage backend from configuration.

    Handles backward compatibility:
    - New configs (with vector_store field): Use specified provider
    - Legacy configs (without vector_store field): Default to Qdrant for backward compatibility

    Note: New projects should explicitly set vector_store via cidx init --vector-store flag.
    """

    @staticmethod
    def create(config: "Config", project_root: Path) -> VectorStoreBackend:
        """Create appropriate backend from configuration.

        For new configurations (with vector_store field):
        - filesystem: Returns FilesystemBackend
        - qdrant: Returns QdrantContainerBackend

        For legacy configurations (vector_store=None):
        - Returns QdrantContainerBackend (backward compatibility)
        - Old configs don't have vector_store field and used Qdrant

        Args:
            config: Configuration object
            project_root: Root directory of the project being indexed

        Returns:
            Appropriate VectorStoreBackend implementation

        Raises:
            ValueError: If provider is unsupported
        """
        # Handle new configs with vector_store field
        if config.vector_store is not None:
            provider = config.vector_store.provider

            if provider == "filesystem":
                logger.info("Creating FilesystemBackend (container-free)")
                return FilesystemBackend(project_root=project_root)
            elif provider == "qdrant":
                logger.info("Creating QdrantContainerBackend (containers required)")
                return QdrantContainerBackend(project_root=project_root)
            else:
                raise ValueError(f"Unsupported vector store provider: {provider}")
        else:
            # Backward compatibility: legacy configs without vector_store field default to Qdrant
            logger.info(
                "No vector_store config - defaulting to QdrantContainerBackend (backward compatibility)"
            )
            return QdrantContainerBackend(project_root=project_root)

    @staticmethod
    def create_from_legacy_config(
        config: "Config", project_root: Path
    ) -> VectorStoreBackend:
        """Create backend from legacy configuration without vector_store field.

        This method explicitly handles legacy configs for backward compatibility testing.

        Args:
            config: Configuration object (without vector_store field)
            project_root: Root directory of the project being indexed

        Returns:
            QdrantContainerBackend (for backward compatibility)
        """
        logger.info(
            "Creating backend from legacy config - defaulting to QdrantContainerBackend"
        )
        return QdrantContainerBackend(project_root=project_root)
