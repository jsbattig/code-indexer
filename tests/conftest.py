"""
Shared pytest fixtures for Code Indexer tests.

Provides common fixtures for E2E tests including service management,
configuration setup, and cleanup.
"""

import os
import subprocess
import time
import shutil
from pathlib import Path
from typing import Generator, Optional
from contextlib import contextmanager

import pytest
import requests  # type: ignore

from code_indexer.config import Config
from code_indexer.services.docker_manager import DockerManager

# Load environment variables from .env files
from . import load_env  # noqa: F401 - Used for side effects


def detect_running_qdrant_port() -> Optional[int]:
    """Detect the port of a running Qdrant service.

    Returns:
        Port number if found, None otherwise
    """
    # Common Qdrant ports including the current project's assigned port
    qdrant_ports = [
        7221,
        7249,
        6560,
        6333,
        6334,
        6335,
        6902,
    ]  # Add current project port first

    for port in qdrant_ports:
        try:
            response = requests.get(f"http://localhost:{port}/cluster", timeout=2)
            if response.status_code == 200 and "status" in response.json():
                return port
        except Exception:
            continue

    return None


def get_test_qdrant_config() -> dict:
    """Get Qdrant configuration for tests that auto-detects running service.

    Returns:
        Qdrant config dict with detected host or default
    """
    detected_port = detect_running_qdrant_port()
    if detected_port:
        return {
            "host": f"http://localhost:{detected_port}",
            "collection": "test_collection",
            "vector_size": 1024,
        }
    else:
        # Fallback to default
        return {
            "host": "http://localhost:6333",
            "collection": "test_collection",
            "vector_size": 1024,
        }


# Global helper functions for local tmp directory management
def get_local_tmp_dir() -> Path:
    """Get the ~/.tmp directory (outside git context, accessible to containers)."""
    home_dir = Path.home()
    tmp_dir = home_dir / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    return tmp_dir


@contextmanager
def local_temporary_directory(prefix: str = "test_", force_docker: bool = False):
    """Context manager that creates a temporary directory in ~/.tmp (outside git context).

    Args:
        prefix: Prefix for the directory name (unused for shared directories)
        force_docker: If True, use Docker-specific shared directory
    """
    # Import here to avoid circular dependency
    from code_indexer.services.container_manager import get_shared_test_directory

    # Use shared test directory to avoid creating multiple container sets
    # Docker and Podman get separate directories to avoid permission conflicts
    temp_path = get_shared_test_directory(force_docker)

    # Ensure directory exists but DON'T delete it if containers are using it
    temp_path.mkdir(parents=True, exist_ok=True)

    # Only clean up test files, not the entire directory structure
    # This preserves .code-indexer/qdrant that containers might be using
    for item in temp_path.iterdir():
        if item.name != ".code-indexer":
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            else:
                item.unlink(missing_ok=True)

    try:
        yield temp_path
    finally:
        # Don't clean up here - let the next test clean it up
        # This ensures container reuse between tests
        pass


@contextmanager
def isolated_temporary_directory(test_name: str):
    """Create completely isolated temp directory per test.

    This fixture provides complete test isolation with zero shared state.
    Each test gets a unique directory with timestamp and UUID.

    DEPRECATED: Use shared_container_test_environment for better performance.

    Args:
        test_name: Name of the test (will be made unique)

    Yields:
        Path: Unique temporary directory for this test
    """
    import uuid
    import time

    test_id = f"{test_name}_{uuid.uuid4().hex[:8]}_{int(time.time())}"
    temp_path = Path.home() / ".tmp" / "isolated_tests" / test_id
    temp_path.mkdir(parents=True, exist_ok=True)

    try:
        yield temp_path
    finally:
        # Complete cleanup - no sharing
        if temp_path.exists():
            shutil.rmtree(temp_path, ignore_errors=True)


@contextmanager
def shared_container_test_environment(test_name: str, embedding_provider=None):
    """Create shared container test environment with complete state cleanup.

    This is the preferred approach for test isolation that provides:
    - Container reuse for performance (same provider = same containers)
    - Complete state cleanup between tests (collections + files)
    - Containers stay running for next test

    Args:
        test_name: Name of the test (for debugging)
        embedding_provider: EmbeddingProvider enum (default: VOYAGE_AI)

    Yields:
        Path: Shared test directory for this embedding provider
    """
    # Import here to avoid circular imports
    from .unit.infrastructure.infrastructure import (
        SharedContainerManager,
        EmbeddingProvider,
    )

    if embedding_provider is None:
        embedding_provider = EmbeddingProvider.VOYAGE_AI

    manager = SharedContainerManager()
    test_folder = manager.get_shared_folder_for_provider(embedding_provider, test_name)

    # Complete cleanup BEFORE test runs (not after)
    manager.complete_cleanup_between_tests(test_folder)

    # Setup shared environment (reuses containers if available)
    manager.setup_shared_test_environment(test_folder, embedding_provider)

    yield test_folder

    # Note: No cleanup in finally block - leave environment for next test
    # The next test will clean up before it starts


@pytest.fixture
def local_tmp_path() -> Generator[Path, None, None]:
    """Pytest fixture that provides a temporary directory in local .tmp (accessible to containers)."""
    with local_temporary_directory() as tmp_path:
        yield tmp_path


class E2EServiceManager:
    """Manages service lifecycle for E2E tests."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.services_started = False

    def clean_legacy_containers(self, force_docker: bool = False) -> bool:
        """Clean any legacy containers that might interfere with CoW tests."""
        try:
            print("🧹 Cleaning legacy containers...")
            docker_manager = DockerManager(
                project_name="test_shared", force_docker=force_docker
            )
            # Import here to avoid circular dependency
            from .unit.infrastructure.infrastructure import get_shared_test_directory

            # Use a consistent path for all test containers to avoid creating multiple container sets
            shared_test_path = get_shared_test_directory(force_docker)
            shared_test_path.mkdir(parents=True, exist_ok=True)
            docker_manager.set_indexing_root(shared_test_path)
            success = docker_manager.remove_containers(remove_volumes=True)
            if success:
                print("✅ Legacy containers cleaned")
            else:
                print("⚠️  Failed to clean legacy containers")
            return bool(success)
        except Exception as e:
            print(f"⚠️  Error cleaning legacy containers: {e}")
            return False

    def ensure_services_running(self) -> bool:
        """Ensure services are running, start them if needed."""
        if self.services_started:
            return True

        # Clean legacy containers first to avoid CoW conflicts
        self.clean_legacy_containers()

        # Check if services are already running
        if self._check_services_running():
            print("✅ Services already running")
            self.services_started = True
            return True

        # Start services
        print("🔧 Starting services for E2E tests...")
        try:
            # Use CLI to start services (this handles all the setup)
            setup_result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "start", "--force-recreate"],
                cwd=self.config_dir,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )

            if setup_result.returncode == 0:
                print("✅ Services started successfully")
                # Wait a bit for services to stabilize
                time.sleep(5)
                self.services_started = True
                return True
            else:
                print(f"❌ Failed to start services: {setup_result.stderr}")
                return False

        except subprocess.TimeoutExpired:
            print("❌ Service startup timed out")
            return False
        except Exception as e:
            print(f"❌ Error starting services: {e}")
            return False

    def stop_services(self) -> None:
        """Stop services if they were started by this manager."""
        if not self.services_started:
            return

        print("🛑 Stopping services...")
        try:
            stop_result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "stop"],
                cwd=self.config_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if stop_result.returncode == 0:
                print("✅ Services stopped successfully")
            else:
                print(f"⚠️ Stop command completed with warnings: {stop_result.stderr}")
        except Exception as e:
            print(f"⚠️ Error stopping services: {e}")

        self.services_started = False

    def _check_services_running(self) -> bool:
        """Check if services are already running."""
        try:
            # Check if we can get status
            status_result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "status"],
                cwd=self.config_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            # If status succeeds and doesn't say "not running", assume services are up
            if status_result.returncode == 0:
                output = status_result.stdout.lower()
                if "running" in output and "not running" not in output:
                    return True

            return False

        except Exception:
            return False


@pytest.fixture(scope="session")
def e2e_environment() -> Generator[E2EServiceManager, None, None]:
    """
    Session-scoped fixture that provides E2E testing environment.

    Sets up a temporary directory, initializes configuration, and manages
    service lifecycle for all E2E tests in the session.
    """
    # Skip if we're in automated testing environment or if Docker is not available
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        pytest.skip(
            "E2E tests require Docker services which are not available in automated testing"
        )

    # Create temporary directory for E2E tests in local .tmp
    with local_temporary_directory("code_indexer_e2e_") as config_dir:
        try:
            # Change to the temp directory
            original_cwd = Path.cwd()
            os.chdir(config_dir)

            # Create some basic files for testing
            (config_dir / "test_file.py").write_text(
                "def hello_world():\n    return 'Hello, World!'\n"
            )

            # Initialize configuration
            print(f"🔧 Setting up E2E environment in {config_dir}")
            init_result = subprocess.run(
                ["python3", "-m", "code_indexer.cli", "init", "--force"],
                cwd=config_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if init_result.returncode != 0:
                pytest.skip(
                    f"Failed to initialize E2E environment: {init_result.stderr}"
                )

            # Create service manager and clean legacy containers
            service_manager = E2EServiceManager(config_dir)
            service_manager.clean_legacy_containers()

            yield service_manager

        finally:
            # Cleanup
            try:
                service_manager.stop_services()
            except Exception:
                pass

            try:
                os.chdir(original_cwd)
            except Exception:
                pass


@pytest.fixture
def e2e_config(e2e_environment: E2EServiceManager) -> Config:
    """Fixture that provides a properly configured Config for E2E tests."""
    # Ensure services are running
    if not e2e_environment.ensure_services_running():
        pytest.skip("Could not start required services for E2E testing")

    # Create config for the test environment
    config = Config(
        codebase_dir=e2e_environment.config_dir,
        embedding_provider="ollama",  # Use Ollama by default for E2E tests
    )

    return config


@pytest.fixture
def e2e_temp_repo() -> Generator[Path, None, None]:
    """Fixture that creates a temporary git repository for E2E testing in local .tmp directory."""
    import shutil

    # Create .tmp directory in the project root (accessible to container)
    project_root = Path(__file__).parent.parent  # Go up from tests/ to project root
    tmp_dir = project_root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Use shared test repo directory for container sharing
    repo_name = "shared_test_repo"
    repo_path = tmp_dir / repo_name

    # Clean up existing directory if it exists
    if repo_path.exists():
        shutil.rmtree(repo_path)

    repo_path.mkdir(parents=True)

    try:
        # Initialize git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Create initial files
        (repo_path / "README.md").write_text(
            "# Test Repository\n\nThis is a test repository for branch topology testing."
        )
        (repo_path / "main.py").write_text(
            'def main():\n    print("Hello World")\n\nif __name__ == "__main__":\n    main()'
        )

        # Create .gitignore to prevent committing .code-indexer directory
        (repo_path / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        yield repo_path

    finally:
        # Cleanup: remove the test repo directory
        if repo_path.exists():
            shutil.rmtree(repo_path, ignore_errors=True)
