"""DeploymentLock - deployment concurrency control via PID-based lock file."""

from code_indexer.server.middleware.correlation import get_correlation_id
from pathlib import Path
import os
import logging

logger = logging.getLogger(__name__)


class DeploymentLock:
    """Manages deployment lock using PID-based lock file mechanism."""

    def __init__(self, lock_file: Path):
        """Initialize DeploymentLock.

        Args:
            lock_file: Path to lock file
        """
        self.lock_file = lock_file

    def acquire(self) -> bool:
        """Attempt to acquire deployment lock.

        Returns:
            True if lock acquired, False if another deployment is in progress

        Raises:
            IOError: If lock file operations fail
        """
        # Check if lock file exists
        if self.lock_file.exists():
            # Read PID from lock file
            try:
                with open(self.lock_file, "r") as f:
                    pid_str = f.read().strip()

                # Try to parse PID
                try:
                    pid = int(pid_str)
                except ValueError:
                    # Invalid PID - treat as stale
                    logger.warning(f"Invalid PID in lock file: {pid_str}", extra={"correlation_id": get_correlation_id()})
                    self.lock_file.unlink()
                else:
                    # Check if process is alive
                    try:
                        os.kill(pid, 0)
                        # Process is alive - lock is held
                        logger.info(f"Lock held by active process {pid}", extra={"correlation_id": get_correlation_id()})
                        return False
                    except OSError:
                        # Process is dead - stale lock
                        logger.info(f"Removing stale lock (PID {pid})", extra={"correlation_id": get_correlation_id()})
                        self.lock_file.unlink()

            except IOError as e:
                logger.error(f"Error reading lock file: {e}", extra={"correlation_id": get_correlation_id()})
                raise

        # Create lock file with current PID
        try:
            with open(self.lock_file, "w") as f:
                f.write(str(os.getpid()))
            logger.info(f"Lock acquired (PID {os.getpid()})", extra={"correlation_id": get_correlation_id()})
            return True
        except IOError as e:
            logger.error(f"Error creating lock file: {e}", extra={"correlation_id": get_correlation_id()})
            raise

    def release(self) -> None:
        """Release deployment lock by removing lock file.

        Does not raise exceptions if lock file doesn't exist or can't be deleted.
        """
        if not self.lock_file.exists():
            logger.debug("Lock file doesn't exist, nothing to release", extra={"correlation_id": get_correlation_id()})
            return

        try:
            self.lock_file.unlink()
            logger.info("Lock released", extra={"correlation_id": get_correlation_id()})
        except (IOError, OSError, PermissionError) as e:
            logger.warning(f"Error removing lock file: {e}", extra={"correlation_id": get_correlation_id()})

    def is_stale(self) -> bool:
        """Check if lock file represents a stale lock (process is dead).

        Returns:
            True if lock is stale, False if lock is active or doesn't exist
        """
        if not self.lock_file.exists():
            return False

        try:
            with open(self.lock_file, "r") as f:
                pid_str = f.read().strip()

            # Try to parse PID
            try:
                pid = int(pid_str)
            except ValueError:
                # Invalid PID - consider stale
                return True

            # Check if process is alive
            try:
                os.kill(pid, 0)
                # Process is alive - not stale
                return False
            except OSError:
                # Process is dead - stale
                return True

        except IOError:
            # Can't read lock file - assume not stale
            return False
