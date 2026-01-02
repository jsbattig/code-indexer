"""AutoUpdateService - polling service for automatic CIDX server deployment."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from .change_detector import ChangeDetector
    from .deployment_lock import DeploymentLock
    from .deployment_executor import DeploymentExecutor

logger = logging.getLogger(__name__)


class ServiceState(Enum):
    """Service state machine states."""

    IDLE = "idle"
    CHECKING = "checking"
    DEPLOYING = "deploying"
    RESTARTING = "restarting"


class AutoUpdateService:
    """Auto-update service for polling and deploying CIDX server updates."""

    def __init__(
        self,
        repo_path: Path,
        check_interval: int,
        lock_file: Optional[Path] = None,
    ):
        """Initialize AutoUpdateService.

        Args:
            repo_path: Path to git repository
            check_interval: Polling interval in seconds
            lock_file: Path to lock file (default: /tmp/cidx-auto-update.lock)
        """
        self.repo_path = repo_path
        self.check_interval = check_interval
        self.lock_file = lock_file or Path("/tmp/cidx-auto-update.lock")
        self.current_state = ServiceState.IDLE
        self.last_deployment: Optional[datetime] = None
        self.last_error: Optional[Exception] = None

        # Components injected for testing (must be set before calling poll_once)
        self.change_detector: Optional["ChangeDetector"] = None
        self.deployment_lock: Optional["DeploymentLock"] = None
        self.deployment_executor: Optional["DeploymentExecutor"] = None

    def transition_to(self, new_state: ServiceState) -> None:
        """Transition to a new state.

        Args:
            new_state: Target state to transition to
        """
        logger.info(
            f"State transition: {self.current_state.value} -> {new_state.value}"
        )

        # Record timestamp when entering DEPLOYING state
        if new_state == ServiceState.DEPLOYING:
            self.last_deployment = datetime.now()

        self.current_state = new_state

    def poll_once(self) -> None:
        """Execute one polling iteration.

        Checks for changes and triggers deployment if needed.
        Only runs when in IDLE state to prevent concurrent operations.
        """
        # Validate components are injected before use
        assert (
            self.change_detector is not None
        ), "change_detector must be set before calling poll_once()"
        assert (
            self.deployment_lock is not None
        ), "deployment_lock must be set before calling poll_once()"
        assert (
            self.deployment_executor is not None
        ), "deployment_executor must be set before calling poll_once()"

        # Skip if not in IDLE state
        if self.current_state != ServiceState.IDLE:
            logger.debug(f"Skipping poll - current state: {self.current_state.value}")
            return

        try:
            # Transition to CHECKING state
            self.transition_to(ServiceState.CHECKING)

            # Check for changes
            has_changes = self.change_detector.has_changes()

            if not has_changes:
                # No changes - return to IDLE
                logger.debug("No changes detected")
                self.transition_to(ServiceState.IDLE)
                return

            # Changes detected - attempt deployment
            logger.info("Changes detected, attempting deployment")

            # Try to acquire deployment lock
            if not self.deployment_lock.acquire():
                logger.warning("Another deployment in progress, skipping")
                self.transition_to(ServiceState.IDLE)
                return

            try:
                # Execute deployment
                self.transition_to(ServiceState.DEPLOYING)
                success = self.deployment_executor.execute()

                if success:
                    # Restart server after successful deployment
                    self.transition_to(ServiceState.RESTARTING)
                    self.deployment_executor.restart_server()
                    logger.info("Deployment and restart completed successfully")
                else:
                    logger.error("Deployment failed")

            except Exception as e:
                # Record error and continue
                logger.exception(f"Deployment error: {e}")
                self.last_error = e

            finally:
                # Always release lock
                self.deployment_lock.release()
                # Return to IDLE state
                self.transition_to(ServiceState.IDLE)

        except Exception as e:
            # Catch any unexpected errors during polling
            logger.exception(f"Unexpected error during polling: {e}")
            self.last_error = e
            self.transition_to(ServiceState.IDLE)
