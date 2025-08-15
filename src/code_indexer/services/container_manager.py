"""
Container Manager for dual-container support.

Manages two persistent container sets (Docker and Podman) to eliminate
permission conflicts and container startup failures in test environments.
"""

import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass

from rich.console import Console

logger = logging.getLogger(__name__)


class ContainerType(Enum):
    """Enumeration of supported container types."""

    DOCKER = "docker"
    PODMAN = "podman"


@dataclass
class ContainerSetInfo:
    """Information about a container set."""

    container_type: ContainerType
    working_directory: Path
    containers: Dict[str, Any]
    is_initialized: bool = False
    is_healthy: bool = False


class ContainerManager:
    """
    Manages dual-container architecture for test infrastructure.

    Maintains two persistent container sets (Docker and Podman) to avoid
    permission conflicts and enable reliable test execution.
    """

    def __init__(
        self, dual_container_mode: bool = True, console: Optional[Console] = None
    ):
        """
        Initialize ContainerManager.

        Args:
            dual_container_mode: Enable dual-container support
            console: Rich console for output
        """
        self.dual_container_mode = dual_container_mode
        self.console = console or Console()

        # Container sets for dual-container mode - make them different objects
        self.docker_containers: Dict[str, Any] = {"type": "docker"}
        self.podman_containers: Dict[str, Any] = {"type": "podman"}
        self.active_container_sets: Dict[ContainerType, ContainerSetInfo] = {}

        # Fall back to existing DockerManager for non-dual mode
        if not dual_container_mode:
            from .docker_manager import DockerManager

            self.docker_manager = DockerManager(console=console)

    def get_container_directory(self, container_type: ContainerType) -> Path:
        """
        Get the working directory for a specific container type.

        Args:
            container_type: Type of container

        Returns:
            Path to the container working directory
        """
        if container_type == ContainerType.DOCKER:
            return get_shared_test_directory(force_docker=True)
        elif container_type == ContainerType.PODMAN:
            return get_shared_test_directory(force_docker=False)
        else:
            raise ValueError(f"Invalid container type: {container_type}")

    def get_container_set(self, container_type: ContainerType) -> Dict[str, Any]:
        """
        Get the container set for a specific container type.

        Args:
            container_type: Type of container

        Returns:
            Dictionary of containers for the specified type
        """
        if not isinstance(container_type, ContainerType):
            raise ValueError(f"Invalid container type: {container_type}")

        if container_type == ContainerType.DOCKER:
            return self.docker_containers
        elif container_type == ContainerType.PODMAN:
            return self.podman_containers
        else:
            raise ValueError(f"Invalid container type: {container_type}")

    def initialize_container_set(self, container_type: ContainerType) -> bool:
        """
        Initialize a container set for the specified type.

        Args:
            container_type: Type of container to initialize

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            # Check if already initialized
            if container_type in self.active_container_sets:
                container_info = self.active_container_sets[container_type]
                if container_info.is_initialized:
                    logger.info(
                        f"Container set {container_type.value} already initialized"
                    )
                    return True

            # Create container set info
            working_dir = self.get_container_directory(container_type)
            working_dir.mkdir(parents=True, exist_ok=True)

            # Initialize container set
            success = self._start_containers(container_type)

            if success:
                containers = self.get_container_set(container_type)
                container_info = ContainerSetInfo(
                    container_type=container_type,
                    working_directory=working_dir,
                    containers=containers,
                    is_initialized=True,
                )
                self.active_container_sets[container_type] = container_info
                logger.info(
                    f"Successfully initialized {container_type.value} container set"
                )
                return True
            else:
                logger.error(f"Failed to start {container_type.value} containers")
                return False

        except Exception as e:
            logger.error(
                f"Error initializing {container_type.value} container set: {e}"
            )
            return False

    def verify_container_health(self, container_type: ContainerType) -> bool:
        """
        Verify health of containers for the specified type.

        Args:
            container_type: Type of container to check

        Returns:
            True if containers are healthy, False otherwise
        """
        try:
            return self._check_container_health(container_type)
        except Exception as e:
            logger.error(f"Error checking {container_type.value} container health: {e}")
            return False

    def reset_collections(self, container_type: ContainerType) -> bool:
        """
        Reset Qdrant collections for the specified container type.

        Containers remain running, only collections are cleared.

        Args:
            container_type: Type of container to reset collections for

        Returns:
            True if reset succeeded, False otherwise
        """
        try:
            return self._reset_qdrant_collections(container_type)
        except Exception as e:
            logger.error(f"Error resetting {container_type.value} collections: {e}")
            return False

    def run_cli_command(
        self, args: List[str], container_type: ContainerType, timeout: int = 60
    ) -> subprocess.CompletedProcess:
        """
        Run a CLI command in the context of the specified container type.

        Args:
            args: Command arguments
            container_type: Container type context
            timeout: Command timeout in seconds

        Returns:
            CompletedProcess result
        """
        working_dir = self.get_container_directory(container_type)
        working_dir.mkdir(parents=True, exist_ok=True)

        # Build the full command
        cmd = ["code-indexer"] + args

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, cwd=working_dir, timeout=timeout
            )
            return result
        except subprocess.TimeoutExpired:
            logger.error(f"CLI command timed out: {' '.join(cmd)}")
            raise
        except Exception as e:
            logger.error(f"Error running CLI command: {e}")
            raise

    def _start_containers(self, container_type: ContainerType) -> bool:
        """
        Start containers for the specified type.

        Args:
            container_type: Type of container to start

        Returns:
            True if containers started successfully
        """
        try:
            # Use CLI init and start commands
            # working_dir is set by run_cli_command based on container_type

            # Initialize if needed
            init_result = self.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"],
                container_type,
                timeout=60,
            )

            if init_result.returncode != 0:
                logger.error(
                    f"Init failed for {container_type.value}: {init_result.stderr}"
                )
                return False

            # Start services
            start_result = self.run_cli_command(["start"], container_type, timeout=120)

            if start_result.returncode != 0:
                logger.error(
                    f"Start failed for {container_type.value}: {start_result.stderr}"
                )
                return False

            logger.info(f"Successfully started {container_type.value} containers")
            return True

        except Exception as e:
            logger.error(f"Error starting {container_type.value} containers: {e}")
            return False

    def _check_container_health(self, container_type: ContainerType) -> bool:
        """
        Check health of containers for the specified type.

        Args:
            container_type: Type of container to check

        Returns:
            True if containers are healthy
        """
        try:
            status_result = self.run_cli_command(["status"], container_type, timeout=30)

            if status_result.returncode != 0:
                return False

            # Check for healthy services in output
            output = status_result.stdout.lower()
            qdrant_ready = "qdrant" in output and ("✅" in output or "ready" in output)

            # For basic health check, Qdrant being ready is sufficient
            return qdrant_ready

        except Exception as e:
            logger.error(f"Error checking {container_type.value} health: {e}")
            return False

    def _reset_qdrant_collections(self, container_type: ContainerType) -> bool:
        """
        Reset Qdrant collections for the specified container type.

        Args:
            container_type: Type of container to reset collections for

        Returns:
            True if reset succeeded
        """
        try:
            clean_result = self.run_cli_command(
                ["clean-data", "--all-projects"], container_type, timeout=60
            )

            success = clean_result.returncode == 0
            if success:
                logger.info(f"Successfully reset {container_type.value} collections")
            else:
                logger.error(
                    f"Failed to reset {container_type.value} collections: {clean_result.stderr}"
                )

            return success

        except Exception as e:
            logger.error(f"Error resetting {container_type.value} collections: {e}")
            return False


def get_shared_test_directory(force_docker: bool = False) -> Path:
    """
    Get the shared test directory path with isolation for Docker vs Podman.

    This prevents permission conflicts between Docker (root) and Podman (rootless) tests.

    Args:
        force_docker: If True, return the Docker-specific test directory

    Returns:
        Path to the appropriate shared test directory
    """
    base_dir = Path.home() / ".tmp"

    if force_docker:
        return base_dir / "shared_test_containers_docker"
    else:
        return base_dir / "shared_test_containers_podman"
