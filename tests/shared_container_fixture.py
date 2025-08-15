"""
Shared container fixture for optimized test performance.

This provides session-scoped container management to avoid the expensive
container startup/shutdown cycles that make tests slow.
"""

import os
import pytest

from code_indexer.services.docker_manager import DockerManager


class SharedTestContainers:
    """Manages shared containers across test session."""

    def __init__(self):
        self.docker_manager = None
        self.containers_started = False

    def start_containers(self, force_docker=False):
        """Start containers once per test session."""
        if self.containers_started:
            return True

        self.docker_manager = DockerManager(
            force_docker=force_docker, project_name="test_shared"
        )
        # Use a consistent path for all test containers to avoid creating multiple container sets
        from .test_infrastructure import get_shared_test_directory

        shared_test_path = get_shared_test_directory(force_docker=force_docker)
        shared_test_path.mkdir(parents=True, exist_ok=True)
        self.docker_manager.set_indexing_root(shared_test_path)

        # Try cleanup first in case of orphaned containers
        try:
            self.docker_manager.cleanup_containers()
        except Exception:
            pass  # Ignore cleanup errors

        # Use start_services with recreate flag to ensure clean state
        if self.docker_manager.start_services(recreate=True):
            self.containers_started = True
            return True
        return False

    def cleanup_data_between_tests(self):
        """Fast cleanup between tests - only clear data, keep containers."""
        if self.docker_manager:
            return self.docker_manager.clean_data_only(all_projects=False)
        return True

    def stop_containers(self):
        """Stop containers at end of session."""
        if self.docker_manager and self.containers_started:
            # Use stop instead of remove for faster shutdown
            self.docker_manager.stop_services()
            self.containers_started = False


# Global instance for session sharing
_shared_containers = SharedTestContainers()


@pytest.fixture(scope="session")
def shared_containers():
    """Session-scoped fixture for shared container management."""

    # Skip if no VOYAGE_API_KEY (same condition as tests)
    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required for E2E tests")

    # Start containers once per session
    if not _shared_containers.start_containers():
        pytest.fail("Failed to start shared containers")

    yield _shared_containers

    # Cleanup at end of session
    _shared_containers.stop_containers()


@pytest.fixture
def clean_test_data(shared_containers):
    """Per-test fixture that ensures clean data without stopping containers."""

    # Clean data before test
    shared_containers.cleanup_data_between_tests()

    yield

    # Clean data after test (leave containers running)
    shared_containers.cleanup_data_between_tests()


def fast_cli_command(args, cwd=None, timeout=60):
    """
    Helper function for running CLI commands in tests.

    This assumes containers are already running from shared_containers fixture,
    so it can skip the expensive container startup process.
    """
    import subprocess
    import sys

    cmd = [sys.executable, "-m", "code_indexer.cli"] + args

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Command timed out: {' '.join(cmd)}")
