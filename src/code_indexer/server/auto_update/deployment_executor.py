"""DeploymentExecutor - deployment command execution for auto-update service."""

from code_indexer.server.middleware.correlation import get_correlation_id
from pathlib import Path
import subprocess
import logging
import time

import requests

logger = logging.getLogger(__name__)


class DeploymentExecutor:
    """Executes deployment commands: git pull, pip install, systemd restart.

    Story #734: Supports graceful drain mode during auto-update.
    """

    def __init__(
        self,
        repo_path: Path,
        service_name: str = "cidx-server",
        server_url: str = "http://localhost:8000",
        drain_timeout: int = 300,
        drain_poll_interval: int = 10,
    ):
        """Initialize DeploymentExecutor.

        Args:
            repo_path: Path to git repository
            service_name: Systemd service name (default: cidx-server)
            server_url: CIDX server URL for maintenance API (default: http://localhost:8000)
            drain_timeout: Max seconds to wait for drain (default: 300)
            drain_poll_interval: Seconds between drain status checks (default: 10)
        """
        self.repo_path = repo_path
        self.service_name = service_name
        self.server_url = server_url
        self.drain_timeout = drain_timeout
        self.drain_poll_interval = drain_poll_interval

    def _enter_maintenance_mode(self) -> bool:
        """Enter maintenance mode via server API.

        Returns:
            True if successful, False on error (e.g., connection refused)
        """
        try:
            url = f"{self.server_url}/api/admin/maintenance/enter"
            response = requests.post(url, timeout=10)

            if response.status_code == 200:
                logger.info(
                    "Entered maintenance mode",
                    extra={"correlation_id": get_correlation_id()},
                )
                return True

            logger.error(
                f"Failed to enter maintenance mode: {response.status_code}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Could not connect to server for maintenance mode - proceeding anyway",
                extra={"correlation_id": get_correlation_id()},
            )
            return False
        except Exception as e:
            logger.error(
                f"Error entering maintenance mode: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _wait_for_drain(self) -> bool:
        """Wait for jobs to drain before restart.

        Returns:
            True if drained, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < self.drain_timeout:
            try:
                url = f"{self.server_url}/api/admin/maintenance/drain-status"
                response = requests.get(url, timeout=10)

                if response.status_code == 200:
                    data = response.json()
                    if data.get("drained", False):
                        logger.info(
                            "System drained, ready for restart",
                            extra={"correlation_id": get_correlation_id()},
                        )
                        return True

                    logger.info(
                        f"Waiting for drain: {data.get('running_jobs', 0)} running, "
                        f"{data.get('queued_jobs', 0)} queued",
                        extra={"correlation_id": get_correlation_id()},
                    )

            except requests.exceptions.ConnectionError:
                logger.warning(
                    "Could not connect to server for drain status",
                    extra={"correlation_id": get_correlation_id()},
                )
            except Exception as e:
                logger.error(
                    f"Error checking drain status: {e}",
                    extra={"correlation_id": get_correlation_id()},
                )

            time.sleep(self.drain_poll_interval)

        logger.warning(
            f"Drain timeout ({self.drain_timeout}s) exceeded",
            extra={"correlation_id": get_correlation_id()},
        )
        return False

    def _exit_maintenance_mode(self) -> bool:
        """Exit maintenance mode via server API.

        Returns:
            True if successful, False on error
        """
        try:
            url = f"{self.server_url}/api/admin/maintenance/exit"
            response = requests.post(url, timeout=10)

            if response.status_code == 200:
                logger.info(
                    "Exited maintenance mode",
                    extra={"correlation_id": get_correlation_id()},
                )
                return True

            logger.error(
                f"Failed to exit maintenance mode: {response.status_code}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

        except Exception as e:
            logger.error(
                f"Error exiting maintenance mode: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def _get_running_jobs_for_logging(self) -> list:
        """Get running jobs from drain-status endpoint for logging.

        Story #734 AC4: Fetch job details to log when forcing restart.

        Returns:
            List of job dicts with job_id, operation_type, started_at, progress
        """
        try:
            url = f"{self.server_url}/api/admin/maintenance/drain-status"
            response = requests.get(url, timeout=10)

            if response.status_code == 200:
                data = response.json()
                jobs: list = data.get("jobs", [])
                return jobs

            return []

        except requests.exceptions.ConnectionError:
            logger.warning(
                "Could not connect to server to get running jobs",
                extra={"correlation_id": get_correlation_id()},
            )
            return []
        except Exception as e:
            logger.error(
                f"Error getting running jobs: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return []

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
                logger.error(
                    f"Git pull failed: {result.stderr}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            logger.info(
                f"Git pull successful: {result.stdout.strip()}",
                extra={"correlation_id": get_correlation_id()},
            )
            return True

        except Exception as e:
            logger.exception(
                f"Git pull exception: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def pip_install(self) -> bool:
        """Execute pip install to update dependencies.

        Returns:
            True if successful, False otherwise
        """
        try:
            result = subprocess.run(
                [
                    "python3",
                    "-m",
                    "pip",
                    "install",
                    "--break-system-packages",
                    "-e",
                    ".",
                ],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(
                    f"Pip install failed: {result.stderr}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            logger.info(
                "Pip install successful", extra={"correlation_id": get_correlation_id()}
            )
            return True

        except Exception as e:
            logger.exception(
                f"Pip install exception: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def restart_server(self) -> bool:
        """Restart CIDX server via systemctl with graceful drain.

        Story #734: Uses maintenance mode flow:
        1. Enter maintenance mode (stop accepting new jobs)
        2. Wait for drain (running jobs to complete)
        3. Restart server

        Returns:
            True if successful, False otherwise
        """
        # Step 1: Enter maintenance mode
        entered_maintenance = self._enter_maintenance_mode()
        if entered_maintenance:
            logger.info(
                "Maintenance mode entered, waiting for drain",
                extra={"correlation_id": get_correlation_id()},
            )

            # Step 2: Wait for drain
            drained = self._wait_for_drain()
            if not drained:
                # AC4: Log running jobs at WARNING level before forcing restart
                running_jobs = self._get_running_jobs_for_logging()
                for job in running_jobs:
                    job_id = job.get("job_id", "unknown")
                    operation_type = job.get("operation_type", "unknown")
                    started_at = job.get("started_at", "unknown")
                    progress = job.get("progress", 0)
                    logger.warning(
                        f"Forcing restart - running job: job_id={job_id}, "
                        f"operation_type={operation_type}, started_at={started_at}, "
                        f"progress={progress}%",
                        extra={"correlation_id": get_correlation_id()},
                    )
                logger.warning(
                    "Drain timeout exceeded, forcing restart",
                    extra={"correlation_id": get_correlation_id()},
                )
            else:
                logger.info(
                    "System drained successfully, proceeding with restart",
                    extra={"correlation_id": get_correlation_id()},
                )
        else:
            logger.warning(
                "Could not enter maintenance mode, proceeding with restart",
                extra={"correlation_id": get_correlation_id()},
            )

        # Step 3: Execute restart
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "restart", self.service_name],
                capture_output=True,
                text=True,
            )

            if result.returncode != 0:
                logger.error(
                    f"Server restart failed: {result.stderr}",
                    extra={"correlation_id": get_correlation_id()},
                )
                return False

            logger.info(
                "Server restarted successfully",
                extra={"correlation_id": get_correlation_id()},
            )
            return True

        except Exception as e:
            logger.exception(
                f"Server restart exception: {e}",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

    def execute(self) -> bool:
        """Execute complete deployment: git pull + pip install.

        Returns:
            True if all steps successful, False otherwise
        """
        logger.info(
            "Starting deployment execution",
            extra={"correlation_id": get_correlation_id()},
        )

        # Step 1: Git pull
        if not self.git_pull():
            logger.error(
                "Deployment failed at git pull step",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

        # Step 2: Pip install
        if not self.pip_install():
            logger.error(
                "Deployment failed at pip install step",
                extra={"correlation_id": get_correlation_id()},
            )
            return False

        logger.info(
            "Deployment execution completed successfully",
            extra={"correlation_id": get_correlation_id()},
        )
        return True
