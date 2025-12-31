"""DeploymentExecutor - deployment command execution for auto-update service."""

from pathlib import Path
import subprocess
import logging

logger = logging.getLogger(__name__)


class DeploymentExecutor:
    """Executes deployment commands: git pull, pip install, systemd restart."""

    def __init__(self, repo_path: Path, service_name: str = "cidx-server"):
        """Initialize DeploymentExecutor.

        Args:
            repo_path: Path to git repository
            service_name: Systemd service name (default: cidx-server)
        """
        self.repo_path = repo_path
        self.service_name = service_name

    def git_pull(self) -> bool:
        """Execute git pull to update repository.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "pull", "origin", "master"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Git pull failed: {result.stderr}")
                return False

            logger.info(f"Git pull successful: {result.stdout.strip()}")
            return True

        except Exception as e:
            logger.exception(f"Git pull exception: {e}")
            return False

    def pip_install(self) -> bool:
        """Execute pip install to update dependencies.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["python3", "-m", "pip", "install", "--break-system-packages", "-e", "."],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Pip install failed: {result.stderr}")
                return False

            logger.info("Pip install successful")
            return True

        except Exception as e:
            logger.exception(f"Pip install exception: {e}")
            return False

    def restart_server(self) -> bool:
        """Restart CIDX server via systemctl.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", self.service_name],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(f"Server restart failed: {result.stderr}")
                return False

            logger.info("Server restarted successfully")
            return True

        except Exception as e:
            logger.exception(f"Server restart exception: {e}")
            return False

    def execute(self) -> bool:
        """Execute complete deployment: git pull + pip install.

        Returns:
            True if all steps successful, False otherwise
        """
        logger.info("Starting deployment execution")

        # Step 1: Git pull
        if not self.git_pull():
            logger.error("Deployment failed at git pull step")
            return False

        # Step 2: Pip install
        if not self.pip_install():
            logger.error("Deployment failed at pip install step")
            return False

        logger.info("Deployment execution completed successfully")
        return True
