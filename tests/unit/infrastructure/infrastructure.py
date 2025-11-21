"""
Shared test infrastructure for unit and integration tests.

Provides common components for testing including embedding provider enums,
container management, and test environment setup.
"""

from enum import Enum
from pathlib import Path
from typing import Dict
import os

from code_indexer.services.docker_manager import DockerManager
from code_indexer.config import Config


class EmbeddingProvider(Enum):
    """Enumeration of embedding providers for testing."""

    VOYAGE_AI = "voyage_ai"
    VOYAGE = "voyage"
    MOCK = "mock"


class SharedContainerManager:
    """Manages shared containers for test environments."""

    def __init__(self):
        self.containers_by_provider: Dict[EmbeddingProvider, DockerManager] = {}
        self.base_test_path = get_shared_test_directory()

    def get_shared_folder_for_provider(
        self, provider: EmbeddingProvider, test_name: str
    ) -> Path:
        """Get the shared test folder for a specific provider.

        Args:
            provider: The embedding provider enum
            test_name: Name of the test (for debugging)

        Returns:
            Path to the shared test directory
        """
        # Use provider-specific directories to isolate containers
        provider_path = self.base_test_path / f"provider_{provider.value}"
        provider_path.mkdir(parents=True, exist_ok=True)
        return provider_path

    def complete_cleanup_between_tests(self, test_folder: Path) -> None:
        """Perform complete cleanup between tests.

        Args:
            test_folder: The test folder to clean
        """
        # Clean up any existing collections and test data
        if test_folder.exists():
            # Clean collections but keep containers running
            config_file = test_folder / ".code-indexer-config.yaml"
            if config_file.exists():
                try:
                    config = Config(str(config_file))
                    # Clean Filesystem collections if configured
                    if hasattr(config, "filesystem") and config.filesystem:
                        # Collection cleanup would happen here
                        pass
                except Exception:
                    pass  # Ignore cleanup errors

    def setup_shared_test_environment(
        self, test_folder: Path, provider: EmbeddingProvider
    ) -> None:
        """Setup shared test environment for a provider.

        Args:
            test_folder: The test folder to setup
            provider: The embedding provider to use
        """
        # Create test folder if it doesn't exist
        test_folder.mkdir(parents=True, exist_ok=True)

        # Setup would initialize containers if needed
        # but keep them running for subsequent tests
        if provider not in self.containers_by_provider:
            # Initialize container manager for this provider
            docker_manager = DockerManager(
                project_name=f"test_{provider.value}",
                force_docker=os.environ.get("FORCE_DOCKER", "false").lower() == "true",
            )
            docker_manager.set_indexing_root(test_folder)
            self.containers_by_provider[provider] = docker_manager


def get_shared_test_directory(force_docker: bool = False) -> Path:
    """Get the shared test directory for all tests.

    Args:
        force_docker: If True, use Docker-specific directory

    Returns:
        Path to the shared test directory
    """
    home_dir = Path.home()
    base_dir = home_dir / ".tmp" / "code_indexer_tests"

    # Use separate directories for Docker vs Podman to avoid permission conflicts
    if force_docker or os.environ.get("FORCE_DOCKER", "false").lower() == "true":
        test_dir = base_dir / "docker"
    else:
        test_dir = base_dir / "podman"

    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir
