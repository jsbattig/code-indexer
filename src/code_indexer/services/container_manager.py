"""
Container Manager for dual-container support.

Manages two persistent container sets (Docker and Podman) to eliminate
permission conflicts and container startup failures in test environments.
"""

import subprocess
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass

from rich.console import Console

logger = logging.getLogger(__name__)


# Test integration availability flag
TESTING_INTEGRATION_AVAILABLE = False
try:
    from ..testing.fixtures import get_fixture_manager  # noqa: F401

    TESTING_INTEGRATION_AVAILABLE = True
except ImportError:
    pass


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

        # Performance monitoring
        self.health_check_metrics: Dict[ContainerType, Dict[str, Any]] = {}
        self._operation_metrics: Dict[str, List[Dict[str, Any]]] = {}
        self._failure_statistics: Dict[str, int] = {}
        self._startup_time_metrics: Dict[ContainerType, Dict[str, Any]] = {}

        # Initialize performance monitoring for each container type
        for container_type in [ContainerType.DOCKER, ContainerType.PODMAN]:
            self.health_check_metrics[container_type] = {
                "check_history": [],
                "total_checks": 0,
                "successful_checks": 0,
                "failed_checks": 0,
            }
            self._startup_time_metrics[container_type] = {
                "startup_history": [],
                "total_startups": 0,
                "average_startup_time": 0.0,
                "fastest_startup": float("inf"),
                "slowest_startup": 0.0,
            }

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

    def get_container_set_for_category(self, category: str) -> ContainerType:
        """
        Get the appropriate container type for a test category.

        Integrates with the test categorization system to route tests
        to appropriate container sets.

        Args:
            category: Test category string (from TestCategory enum)

        Returns:
            ContainerType: The container type to use for this category
        """
        # Map test categories to container types
        category_mapping = {
            "shared_safe": ContainerType.PODMAN,  # Prefer rootless for shared tests
            "docker_only": ContainerType.DOCKER,
            "podman_only": ContainerType.PODMAN,
            "destructive": ContainerType.DOCKER,  # Use Docker for isolation
        }

        return category_mapping.get(category, ContainerType.PODMAN)

    def initialize_container_set(self, container_type: ContainerType) -> bool:
        """
        Initialize a container set for the specified type.

        Args:
            container_type: Type of container to initialize

        Returns:
            True if initialization succeeded, False otherwise
        """
        success, _ = self.initialize_container_set_with_timing(container_type)
        return success

    def initialize_container_set_with_timing(
        self, container_type: ContainerType
    ) -> Tuple[bool, float]:
        """
        Initialize a container set with timing measurement.

        Args:
            container_type: Type of container to initialize

        Returns:
            Tuple of (success, startup_time_in_seconds)
        """
        start_time = time.time()
        success = False

        try:
            # Check if already initialized
            if container_type in self.active_container_sets:
                container_info = self.active_container_sets[container_type]
                if container_info.is_initialized:
                    logger.info(
                        f"Container set {container_type.value} already initialized"
                    )
                    return True, 0.0  # No startup time for already initialized

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
            else:
                logger.error(f"Failed to start {container_type.value} containers")

            return success, time.time() - start_time

        except Exception as e:
            logger.error(
                f"Error initializing {container_type.value} container set: {e}"
            )
            return False, time.time() - start_time
        finally:
            duration = time.time() - start_time
            self._record_startup_time(container_type, duration, success)

    def verify_container_health(self, container_type: ContainerType) -> bool:
        """
        Verify health of containers for the specified type.

        Args:
            container_type: Type of container to check

        Returns:
            True if containers are healthy, False otherwise
        """
        try:
            result, _ = self.verify_container_health_with_timing(container_type)
            return result
        except Exception as e:
            logger.error(f"Error checking {container_type.value} container health: {e}")
            return False

    def verify_container_health_with_timing(
        self, container_type: ContainerType
    ) -> Tuple[bool, float]:
        """
        Verify health of containers with timing measurement.

        Args:
            container_type: Type of container to check

        Returns:
            Tuple of (health_result, duration_in_seconds)
        """
        start_time = time.time()
        success = False

        try:
            success = self._check_container_health(container_type)
            return success, time.time() - start_time
        except Exception as e:
            logger.error(f"Error checking {container_type.value} container health: {e}")
            return False, time.time() - start_time
        finally:
            duration = time.time() - start_time
            self._record_health_check(container_type, success, duration)

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

    def reset_collections_with_verification(
        self, container_type: ContainerType
    ) -> bool:
        """
        Reset Qdrant collections with verification for the specified container type.

        Performs reset and then verifies that collections are actually empty.

        Args:
            container_type: Type of container to reset collections for

        Returns:
            True if reset succeeded and verification passed, False otherwise
        """
        try:
            # First, perform the reset
            reset_success = self.reset_collections(container_type)
            if not reset_success:
                logger.error(f"Reset failed for {container_type.value}")
                return False

            # Then verify collections are empty
            verification_success = self._verify_collections_empty(container_type)
            if not verification_success:
                logger.error(
                    f"Verification failed for {container_type.value} - collections not empty"
                )
                return False

            logger.info(
                f"Successfully reset and verified {container_type.value} collections"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error in reset with verification for {container_type.value}: {e}"
            )
            return False

    def reset_all_container_sets(self) -> bool:
        """
        Reset collections for all available container sets.

        Returns:
            True if all available container sets were reset successfully, False if any failed
        """
        try:
            available_sets = self.detect_available_container_sets()
            if not available_sets:
                logger.warning("No available container sets detected")
                return True  # No containers to reset is not an error

            all_success = True
            for container_type in available_sets:
                success = self.reset_collections_with_verification(container_type)
                if not success:
                    logger.error(
                        f"Failed to reset {container_type.value} container set"
                    )
                    all_success = False

            return all_success

        except Exception as e:
            logger.error(f"Error resetting all container sets: {e}")
            return False

    def detect_available_container_sets(self) -> List[ContainerType]:
        """
        Detect which container sets are available and healthy.

        Returns:
            List of ContainerType enums for available container sets
        """
        available_sets = []

        for container_type in [ContainerType.DOCKER, ContainerType.PODMAN]:
            try:
                if self.verify_container_health(container_type):
                    available_sets.append(container_type)
                    logger.info(f"{container_type.value} container set is available")
                else:
                    logger.debug(
                        f"{container_type.value} container set is not available"
                    )
            except Exception as e:
                logger.debug(f"Error checking {container_type.value} availability: {e}")

        return available_sets

    def reset_collections_with_progress(
        self, container_type: ContainerType, progress_callback
    ) -> bool:
        """
        Reset collections with progress reporting.

        Args:
            container_type: Type of container to reset collections for
            progress_callback: Callback function for progress updates

        Returns:
            True if reset succeeded, False otherwise
        """
        try:
            # Report start
            progress_callback(0, 0, Path(""), info="Starting reset operation...")

            # Perform reset
            progress_callback(
                0, 0, Path(""), info=f"Resetting {container_type.value} collections..."
            )
            reset_success = self.reset_collections(container_type)

            if not reset_success:
                progress_callback(
                    0, 0, Path(""), info=f"Reset failed for {container_type.value}"
                )
                return False

            # Verify if requested
            progress_callback(
                0, 0, Path(""), info=f"Verifying {container_type.value} collections..."
            )
            verification_success = self._verify_collections_empty(container_type)

            if verification_success:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"Reset completed successfully for {container_type.value}",
                )
            else:
                progress_callback(
                    0,
                    0,
                    Path(""),
                    info=f"Verification failed for {container_type.value}",
                )

            return verification_success

        except Exception as e:
            progress_callback(0, 0, Path(""), info=f"Error during reset: {e}")
            logger.error(
                f"Error in reset with progress for {container_type.value}: {e}"
            )
            return False

    def reset_collections_graceful(self, container_type: ContainerType) -> bool:
        """
        Gracefully reset collections, handling cases where containers aren't running.

        Args:
            container_type: Type of container to reset collections for

        Returns:
            True if reset succeeded or containers weren't running, False on actual errors
        """
        try:
            # Check if containers are running
            if not self.verify_container_health(container_type):
                logger.info(
                    f"{container_type.value} containers not running, skipping reset"
                )
                return True  # Not an error condition

            # Containers are running, perform reset
            return self.reset_collections(container_type)

        except Exception as e:
            logger.error(f"Error in graceful reset for {container_type.value}: {e}")
            return False

    def reset_with_cache_cleanup(self, container_type: ContainerType) -> bool:
        """
        Reset collections and clean up cache directories.

        Args:
            container_type: Type of container to reset collections and cache for

        Returns:
            True if both reset and cache cleanup succeeded, False otherwise
        """
        try:
            # Reset collections first
            reset_success = self.reset_collections(container_type)
            if not reset_success:
                return False

            # Clean up cache directories
            cache_success = self._cleanup_cache_directories(container_type)
            if not cache_success:
                logger.warning(
                    f"Cache cleanup failed for {container_type.value}, but reset succeeded"
                )
                return True  # Reset succeeded, cache cleanup is secondary

            logger.info(
                f"Successfully reset collections and cleaned cache for {container_type.value}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Error in reset with cache cleanup for {container_type.value}: {e}"
            )
            return False

    def _verify_collections_empty(self, container_type: ContainerType) -> bool:
        """
        Verify that collections are empty after reset.

        Args:
            container_type: Type of container to verify

        Returns:
            True if collections are empty, False otherwise
        """
        try:
            # Use CLI status to verify collections are empty
            status_result = self.run_cli_command(["status"], container_type, timeout=30)

            if status_result.returncode != 0:
                logger.error(f"Status check failed for {container_type.value}")
                return False

            # Check output for collection status
            output = status_result.stdout.lower()

            # Look for indicators that collections are empty
            # This is a simplified check - in real implementation,
            # we might need to parse the actual collection counts
            if (
                "empty" in output
                or "0 documents" in output
                or "no collections" in output
            ):
                return True

            # If we can't determine status, assume verification failed
            logger.warning(
                f"Could not verify collection status for {container_type.value}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Error verifying collections empty for {container_type.value}: {e}"
            )
            return False

    def _cleanup_cache_directories(self, container_type: ContainerType) -> bool:
        """
        Clean up cache directories for the specified container type.

        Args:
            container_type: Type of container to clean cache for

        Returns:
            True if cache cleanup succeeded, False otherwise
        """
        try:
            import shutil

            # Get container working directory
            working_dir = self.get_container_directory(container_type)

            # Clean up common cache directories
            cache_dirs = [
                working_dir / ".code-indexer" / "cache",
                working_dir / ".cache",
                working_dir / "tmp",
            ]

            for cache_dir in cache_dirs:
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    logger.info(f"Cleaned cache directory: {cache_dir}")

            return True

        except Exception as e:
            logger.error(
                f"Error cleaning cache directories for {container_type.value}: {e}"
            )
            return False

    def _record_health_check(
        self, container_type: ContainerType, success: bool, duration: float
    ):
        """Record health check metrics."""
        metrics = self.health_check_metrics[container_type]
        metrics["check_history"].append(
            {"success": success, "duration": duration, "timestamp": time.time()}
        )
        metrics["total_checks"] += 1

        if success:
            metrics["successful_checks"] += 1
        else:
            metrics["failed_checks"] += 1

    def _record_startup_time(
        self, container_type: ContainerType, duration: float, success: bool
    ):
        """Record container startup time metrics."""
        metrics = self._startup_time_metrics[container_type]
        metrics["startup_history"].append(
            {"duration": duration, "success": success, "timestamp": time.time()}
        )
        metrics["total_startups"] += 1

        if success:
            metrics["average_startup_time"] = (
                metrics["average_startup_time"] * (metrics["total_startups"] - 1)
                + duration
            ) / metrics["total_startups"]
            metrics["fastest_startup"] = min(metrics["fastest_startup"], duration)
            metrics["slowest_startup"] = max(metrics["slowest_startup"], duration)

    def get_health_check_metrics(self, container_type: ContainerType) -> Dict[str, Any]:
        """
        Get health check metrics for the specified container type.

        Args:
            container_type: Type of container to get metrics for

        Returns:
            Dictionary containing health check metrics
        """
        if container_type not in self.health_check_metrics:
            return {
                "total_checks": 0,
                "successful_checks": 0,
                "failed_checks": 0,
                "success_rate": 0.0,
                "average_duration": 0.0,
                "min_duration": 0.0,
                "max_duration": 0.0,
            }

        metrics = self.health_check_metrics[container_type]
        check_history = metrics["check_history"]

        if not check_history:
            return {
                "total_checks": metrics["total_checks"],
                "successful_checks": metrics["successful_checks"],
                "failed_checks": metrics["failed_checks"],
                "success_rate": 0.0,
                "average_duration": 0.0,
                "min_duration": 0.0,
                "max_duration": 0.0,
            }

        durations = [check["duration"] for check in check_history]
        success_rate = (
            metrics["successful_checks"] / metrics["total_checks"]
            if metrics["total_checks"] > 0
            else 0.0
        )

        return {
            "total_checks": metrics["total_checks"],
            "successful_checks": metrics["successful_checks"],
            "failed_checks": metrics["failed_checks"],
            "success_rate": success_rate,
            "average_duration": sum(durations) / len(durations),
            "min_duration": min(durations),
            "max_duration": max(durations),
        }

    def get_startup_time_metrics(self, container_type: ContainerType) -> Dict[str, Any]:
        """
        Get startup time metrics for the specified container type.

        Args:
            container_type: Type of container to get metrics for

        Returns:
            Dictionary containing startup time metrics
        """
        if container_type not in self._startup_time_metrics:
            return {
                "total_startups": 0,
                "average_startup_time": 0.0,
                "fastest_startup": 0.0,
                "slowest_startup": 0.0,
                "startup_history": [],
            }

        metrics = self._startup_time_metrics[container_type]
        return {
            "total_startups": metrics["total_startups"],
            "average_startup_time": metrics["average_startup_time"],
            "fastest_startup": (
                metrics["fastest_startup"]
                if metrics["fastest_startup"] != float("inf")
                else 0.0
            ),
            "slowest_startup": metrics["slowest_startup"],
            "startup_history": metrics["startup_history"].copy(),
        }

    def categorize_test_failure(self, error_message: str) -> str:
        """
        Categorize a test failure as infrastructure or code related.

        Args:
            error_message: Error message to categorize

        Returns:
            Failure category ('infrastructure', 'code', 'unknown')
        """
        error_lower = error_message.lower()

        # Code failure indicators (check these first - specific Python exceptions)
        code_indicators = [
            "assertionerror:",
            "valueerror:",
            "indexerror:",
            "keyerror:",
            "typeerror:",
            "attributeerror:",
            "nameerror:",
            "runtimeerror:",
        ]

        # Infrastructure failure indicators (more specific patterns)
        infrastructure_indicators = [
            "connection refused",
            "connection timeout",
            "connection failed",
            "connect to container",
            "timeout",
            "container not found",
            "container failed",
            "container error",
            "container",
            "port already in use",
            "port binding",
            "bind: address already in use",
            "port 6333",
            "socket",
            "network",
            "daemon",
            "unavailable",
            "refused",
            "unreachable",
            "mount",
            "volume",
            "permission denied",
            "resource",
            "docker",
            "podman",
            "qdrant",
            "ollama",
            "service not ready",
            "service unavailable",
        ]

        # Check for code failures first (Python exceptions)
        for indicator in code_indicators:
            if indicator in error_lower:
                category = "code"
                self._failure_statistics[category] = (
                    self._failure_statistics.get(category, 0) + 1
                )
                return category

        # Check for infrastructure failures
        for indicator in infrastructure_indicators:
            if indicator in error_lower:
                category = "infrastructure"
                self._failure_statistics[category] = (
                    self._failure_statistics.get(category, 0) + 1
                )
                return category

        category = "unknown"
        self._failure_statistics[category] = (
            self._failure_statistics.get(category, 0) + 1
        )
        return category

    def is_container_infrastructure_failure(self, error_message: str) -> bool:
        """
        Check if an error is a container infrastructure failure.

        Args:
            error_message: Error message to check

        Returns:
            True if container infrastructure failure, False otherwise
        """
        return self.categorize_test_failure(error_message) == "infrastructure"

    def record_operation_result(
        self,
        container_type: ContainerType,
        operation: str,
        success: bool,
        duration: float,
    ):
        """
        Record operation result for stability analysis.

        Args:
            container_type: Type of container the operation was performed on
            operation: Name of the operation
            success: Whether the operation succeeded
            duration: Operation duration in seconds
        """
        operation_key = f"{container_type.value}_{operation}"

        if operation_key not in self._operation_metrics:
            self._operation_metrics[operation_key] = []

        self._operation_metrics[operation_key].append(
            {"success": success, "duration": duration, "timestamp": time.time()}
        )

    def get_stability_metrics(
        self, container_type: ContainerType, operation: str
    ) -> Dict[str, Any]:
        """
        Get stability metrics for a specific container type and operation.

        Args:
            container_type: Type of container
            operation: Name of the operation

        Returns:
            Dictionary containing stability metrics
        """
        operation_key = f"{container_type.value}_{operation}"

        if operation_key not in self._operation_metrics:
            return {
                "total_operations": 0,
                "successful_operations": 0,
                "failed_operations": 0,
            }

        operations = self._operation_metrics[operation_key]
        total = len(operations)
        successful = sum(1 for op in operations if op["success"])
        failed = total - successful

        return {
            "total_operations": total,
            "successful_operations": successful,
            "failed_operations": failed,
        }

    def calculate_success_rates(
        self, container_type: ContainerType, operation: str
    ) -> Dict[str, float]:
        """
        Calculate success/failure rates for a specific container type and operation.

        Args:
            container_type: Type of container
            operation: Name of the operation

        Returns:
            Dictionary with success_rate and failure_rate
        """
        stability_metrics = self.get_stability_metrics(container_type, operation)
        total = stability_metrics["total_operations"]

        if total == 0:
            return {"success_rate": 0.0, "failure_rate": 0.0}

        success_rate = stability_metrics["successful_operations"] / total
        failure_rate = stability_metrics["failed_operations"] / total

        return {"success_rate": success_rate, "failure_rate": failure_rate}

    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get detailed failure statistics."""
        total_failures = sum(self._failure_statistics.values())

        return {
            "total_failures": total_failures,
            "infrastructure_failures": self._failure_statistics.get(
                "infrastructure", 0
            ),
            "code_failures": self._failure_statistics.get("code", 0),
            "unknown_failures": self._failure_statistics.get("unknown", 0),
            "failure_breakdown": self._failure_statistics.copy(),
        }

    def analyze_performance_trends(
        self, container_type: ContainerType, operation: str
    ) -> Dict[str, Any]:
        """
        Analyze performance trends for a specific container type and operation.

        Args:
            container_type: Type of container
            operation: Name of the operation

        Returns:
            Dictionary with trend analysis
        """
        operation_key = f"{container_type.value}_{operation}"

        if operation_key not in self._operation_metrics:
            return {"trend_direction": "unknown", "degradation_detected": False}

        operations = self._operation_metrics[operation_key]
        if len(operations) < 5:
            return {
                "trend_direction": "insufficient_data",
                "degradation_detected": False,
            }

        # Simple trend analysis: compare first half vs second half
        mid_point = len(operations) // 2
        first_half_durations = [op["duration"] for op in operations[:mid_point]]
        second_half_durations = [op["duration"] for op in operations[mid_point:]]

        first_half_avg = sum(first_half_durations) / len(first_half_durations)
        second_half_avg = sum(second_half_durations) / len(second_half_durations)

        trend_direction = "stable"
        degradation_detected = False
        change_percent = 0.0

        if first_half_avg > 0:
            change_percent = (second_half_avg - first_half_avg) / first_half_avg

            if change_percent > 0.2:  # 20% slower
                trend_direction = "degrading"
                degradation_detected = True
            elif change_percent < -0.2:  # 20% faster
                trend_direction = "improving"

        return {
            "trend_direction": trend_direction,
            "degradation_detected": degradation_detected,
            "change_percent": change_percent,
        }

    def detect_degradation_patterns(
        self, container_type: ContainerType
    ) -> Dict[str, Any]:
        """
        Detect performance degradation patterns for a container type.

        Args:
            container_type: Type of container to analyze

        Returns:
            Dictionary with degradation analysis
        """
        patterns = {}

        # Analyze all operations for this container type
        for operation_key, operations in self._operation_metrics.items():
            if operation_key.startswith(container_type.value):
                operation_name = operation_key.replace(f"{container_type.value}_", "")
                trends = self.analyze_performance_trends(container_type, operation_name)
                if trends["degradation_detected"]:
                    patterns[operation_name] = trends

        return {
            "degraded_operations": patterns,
            "degradation_count": len(patterns),
            "overall_degradation": len(patterns) > 0,
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive performance summary for all container types and operations.

        Returns:
            Dictionary with comprehensive performance summary
        """
        summary: Dict[str, Any] = {
            "overall_health": "good",
            "container_performance": {},
            "operation_performance": {},
            "recommendations": [],
        }

        degradation_count = 0

        for container_type in [ContainerType.DOCKER, ContainerType.PODMAN]:
            # Health check metrics
            health_metrics = self.get_health_check_metrics(container_type)
            startup_metrics = self.get_startup_time_metrics(container_type)
            degradation_patterns = self.detect_degradation_patterns(container_type)

            summary["container_performance"][container_type.value] = {
                "health_metrics": health_metrics,
                "startup_metrics": startup_metrics,
                "degradation_patterns": degradation_patterns,
            }

            degradation_count += degradation_patterns["degradation_count"]

            # Generate recommendations
            recommendations = summary["recommendations"]
            if health_metrics["success_rate"] < 0.8:
                recommendations.append(
                    f"Low health check success rate for {container_type.value} containers"
                )

            if startup_metrics["average_startup_time"] > 30.0:
                recommendations.append(
                    f"Slow container startup times for {container_type.value}"
                )

        # Overall health assessment
        if degradation_count > 2:
            summary["overall_health"] = "poor"
        elif degradation_count > 0:
            summary["overall_health"] = "degraded"

        # Operation performance summary
        operation_performance = summary["operation_performance"]
        for operation_key, operations in self._operation_metrics.items():
            if operations:
                avg_duration = sum(op["duration"] for op in operations) / len(
                    operations
                )
                success_rate = sum(1 for op in operations if op["success"]) / len(
                    operations
                )

                operation_performance[operation_key] = {
                    "average_duration": avg_duration,
                    "success_rate": success_rate,
                    "total_operations": len(operations),
                }

        summary["failure_statistics"] = self.get_failure_statistics()

        return summary


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
