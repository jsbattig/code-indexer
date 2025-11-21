"""Abstract base class for vector storage backends.

Defines the interface that all vector storage backends must implement,
allowing code-indexer to work with different storage solutions (filesystem, Filesystem, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class VectorStoreBackend(ABC):
    """Abstract interface for vector storage backends.

    This interface allows code-indexer to support multiple vector storage solutions:
    - FilesystemBackend: Container-free storage using local filesystem
    - FilesystemContainerBackend: Container-based storage using Docker/Podman + Filesystem

    All backends must implement these methods to ensure consistent behavior across
    different storage solutions.
    """

    def __init__(self, project_root: Path):
        """Initialize the backend with a project root directory.

        Args:
            project_root: Root directory of the project being indexed
        """
        self.project_root = Path(project_root)

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the backend storage.

        For FilesystemBackend: Creates directory structure
        For FilesystemContainerBackend: Sets up container configuration

        Raises:
            RuntimeError: If initialization fails
        """
        pass

    @abstractmethod
    def start(self) -> bool:
        """Start the backend services.

        For FilesystemBackend: No-op, returns True immediately
        For FilesystemContainerBackend: Starts Docker/Podman containers

        Returns:
            True if services started successfully, False otherwise
        """
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Stop the backend services.

        For FilesystemBackend: No-op, returns True immediately
        For FilesystemContainerBackend: Stops Docker/Podman containers

        Returns:
            True if services stopped successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get current status of backend services.

        Returns:
            Dictionary containing status information (service state, health, etc.)
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up backend resources.

        For FilesystemBackend: Removes vectors directory
        For FilesystemContainerBackend: Removes containers and volumes

        Raises:
            RuntimeError: If cleanup fails
        """
        pass

    @abstractmethod
    def get_vector_store_client(self) -> Any:
        """Get the vector store client instance.

        For FilesystemBackend: Returns filesystem-based client
        For FilesystemContainerBackend: Returns Filesystem client instance

        Returns:
            Client instance for interacting with vector storage
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if backend is healthy and operational.

        For FilesystemBackend: Verifies write access to vectors directory
        For FilesystemContainerBackend: Checks container health and connectivity

        Returns:
            True if backend is healthy, False otherwise
        """
        pass

    @abstractmethod
    def get_service_info(self) -> Dict[str, Any]:
        """Get information about backend services.

        Returns:
            Dictionary containing service information (URLs, ports, provider, etc.)
        """
        pass

    def optimize(self) -> bool:
        """Optimize the vector storage (optional operation).

        For FilesystemBackend: No-op, returns True
        For FilesystemContainerBackend: Triggers Filesystem optimization

        Returns:
            True if optimization succeeded or is not applicable
        """
        # Default implementation: no-op
        return True

    def force_flush(self) -> bool:
        """Force flush pending operations to storage (optional operation).

        For FilesystemBackend: No-op, returns True
        For FilesystemContainerBackend: Forces Filesystem to flush to disk

        Returns:
            True if flush succeeded or is not applicable
        """
        # Default implementation: no-op
        return True
