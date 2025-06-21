"""
Shared pytest fixtures for Code Indexer tests.

Provides common fixtures for E2E tests including service management,
configuration setup, and cleanup.
"""

import os
import subprocess
import time
import tempfile
import shutil
from pathlib import Path
from typing import Generator

import pytest

from code_indexer.config import Config


class E2EServiceManager:
    """Manages service lifecycle for E2E tests."""

    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.services_started = False

    def ensure_services_running(self) -> bool:
        """Ensure services are running, start them if needed."""
        if self.services_started:
            return True

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
                ["python", "-m", "code_indexer.cli", "start", "--force-recreate"],
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
                ["python", "-m", "code_indexer.cli", "stop"],
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
                ["python", "-m", "code_indexer.cli", "status"],
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

    # Create temporary directory for E2E tests
    temp_dir = tempfile.mkdtemp(prefix="code_indexer_e2e_")
    config_dir = Path(temp_dir)

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
            ["python", "-m", "code_indexer.cli", "init", "--force"],
            cwd=config_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if init_result.returncode != 0:
            pytest.skip(f"Failed to initialize E2E environment: {init_result.stderr}")

        # Create service manager
        service_manager = E2EServiceManager(config_dir)

        yield service_manager

    finally:
        # Cleanup
        try:
            service_manager.stop_services()
        except Exception:
            pass

        try:
            os.chdir(original_cwd)
            shutil.rmtree(temp_dir)
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
def e2e_temp_repo(tmp_path: Path) -> Path:
    """Fixture that creates a temporary git repository for E2E testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True
    )

    # Create initial files
    (repo_path / "README.md").write_text(
        "# Test Repository\n\nThis is a test repository."
    )
    (repo_path / "main.py").write_text(
        "def main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()"
    )

    # Initial commit
    subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

    return repo_path
