"""
Legacy container detection for CoW migration.

This module detects when containers are running in legacy mode (without home directory mount)
and guides users to run the clean-legacy command for migration.
"""

import logging
import subprocess
from pathlib import Path

from .docker_manager import DockerManager

logger = logging.getLogger(__name__)


class LegacyDetector:
    """Detects legacy container configurations that need CoW migration."""

    def __init__(self):
        self.docker_manager = DockerManager()

    async def check_legacy_container(self) -> bool:
        """
        Check if qdrant container is running in legacy mode.

        Returns True if container exists but lacks proper home directory mount.
        Returns False if no container exists (not legacy, just needs to be created).
        """
        try:
            # Check if legacy container exists - legacy detector checks for old container names
            # Use direct container inspection since we're checking for legacy containers
            import subprocess

            container_engine = (
                "docker" if self.docker_manager.force_docker else "podman"
            )
            try:
                result = subprocess.run(
                    [container_engine, "container", "inspect", "code-indexer-qdrant"],
                    capture_output=True,
                    timeout=5,
                )
                container_exists = result.returncode == 0
            except Exception:
                container_exists = False

            if not container_exists:
                logger.debug("No qdrant container exists - not legacy, needs creation")
                return False

            # Container exists, check if it has home directory mount
            has_home_mount = await self._check_container_has_home_mount()

            if has_home_mount:
                logger.debug("Container has home mount - not legacy")
                return False
            else:
                logger.info("Legacy container detected - needs CoW migration")
                return True

        except Exception as e:
            logger.warning(f"Failed to check container legacy status: {e}")
            return False  # Default to not legacy if we can't check

    async def _check_container_has_home_mount(self) -> bool:
        """
        Check if the qdrant container has home directory mounted.

        Returns True if container has proper home mount for CoW collections.
        """
        try:
            # Use docker manager's existing compose command logic for container engine detection
            compose_cmd = self.docker_manager.get_compose_command()
            # Extract just the container engine (podman-compose -> podman, docker -> docker)
            if compose_cmd[0] == "podman-compose":
                container_engine = "podman"
            elif compose_cmd[0] in ["docker", "docker-compose"]:
                container_engine = "docker"
            else:
                container_engine = compose_cmd[0].split("-")[0]  # fallback

            # Get container mount information using the detected engine
            result = subprocess.run(
                [
                    container_engine,
                    "inspect",
                    "code-indexer-qdrant",
                    "--format",
                    '{{range .Mounts}}{{.Source}}:{{.Destination}}:{{.Mode}}{{"NEWLINE"}}{{end}}',
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.warning("Could not inspect container mounts")
                return False

            mounts = result.stdout.strip().split("NEWLINE")
            home_dir = str(Path.home())

            logger.debug(f"Container mounts: {mounts}")
            logger.debug(f"Looking for home mount: {home_dir}")

            # Check if home directory is mounted
            for mount in mounts:
                if not mount.strip():
                    continue

                parts = mount.split(":")
                if len(parts) >= 2:
                    source = parts[0]
                    destination = parts[1]

                    # Check if home directory is mounted to itself (required for CoW)
                    if source == home_dir and destination == home_dir:
                        logger.debug(f"Found home mount: {mount}")
                        return True

            logger.debug("Home directory mount not found in container")
            return False

        except Exception as e:
            logger.error(f"Failed to check container mounts: {e}")
            return False

    def get_legacy_error_message(self) -> str:
        """Get the error message to show users when legacy container is detected."""
        return """
❌ Legacy container detected - CoW migration required

Your containers are running in legacy mode without Copy-on-Write support.
To migrate to the new architecture:

  1. Run: cidx clean-legacy
     (This will stop containers, clean storage, and restart with CoW support)
     
  2. Re-index your projects: cidx index
     (Collections will be stored locally with CoW functionality)

⚠️  WARNING: This will remove all existing collections and require re-indexing.
"""


# Global instance
legacy_detector = LegacyDetector()
