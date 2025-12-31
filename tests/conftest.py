"""
Shared pytest fixtures for Code Indexer tests.

Provides common fixtures for E2E tests including service management,
configuration setup, and cleanup.
"""

import os
import subprocess
import time
import shutil
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from code_indexer.config import Config

# Load environment variables from .env files
from . import load_env  # noqa: F401 - Used for side effects


# Global helper functions for local tmp directory management
def get_local_tmp_dir() -> Path:
    """Get the ~/.tmp directory for test temporary files."""
    home_dir = Path.home()
    tmp_dir = home_dir / ".tmp"
    tmp_dir.mkdir(exist_ok=True)
    return tmp_dir


def local_temporary_directory(prefix: str = "test_"):
    """Context manager that creates a temporary directory in ~/.tmp.

    Args:
        prefix: Prefix for the directory name

    Yields:
        Path: Temporary directory path
    """
    from contextlib import contextmanager

    @contextmanager
    def _context():
        tmp_dir = get_local_tmp_dir()
        test_dir = tmp_dir / f"{prefix}{int(time.time() * 1000)}"
        test_dir.mkdir(parents=True, exist_ok=True)

        try:
            yield test_dir
        finally:
            if test_dir.exists():
                shutil.rmtree(test_dir, ignore_errors=True)

    return _context()


@pytest.fixture
def local_tmp_path() -> Generator[Path, None, None]:
    """Pytest fixture that provides a temporary directory in local .tmp."""
    with local_temporary_directory() as tmp_path:
        yield tmp_path


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
    # Skip if we're in automated testing environment
    if os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true":
        pytest.skip(
            "E2E tests require services which are not available in automated testing"
        )

    # Create temporary directory for E2E tests in local .tmp
    tmp_dir = get_local_tmp_dir()
    config_dir = tmp_dir / f"e2e_test_{int(time.time() * 1000)}"
    config_dir.mkdir(parents=True, exist_ok=True)

    original_cwd = Path.cwd()
    try:
        # Change to the temp directory
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
        except Exception:
            pass

        # Clean up temporary directory
        if config_dir.exists():
            shutil.rmtree(config_dir, ignore_errors=True)


@pytest.fixture
def e2e_config(e2e_environment: E2EServiceManager) -> Config:
    """Fixture that provides a properly configured Config for E2E tests."""
    # Ensure services are running
    if not e2e_environment.ensure_services_running():
        pytest.skip("Could not start required services for E2E testing")

    # Create config for the test environment
    config = Config(
        codebase_dir=e2e_environment.config_dir,
        embedding_provider="voyage-ai",  # Use VoyageAI for E2E tests
    )

    return config


@pytest.fixture
def e2e_temp_repo() -> Generator[Path, None, None]:
    """Fixture that creates a temporary git repository for E2E testing in local .tmp directory."""
    import shutil

    # Create .tmp directory in the project root
    project_root = Path(__file__).parent.parent  # Go up from tests/ to project root
    tmp_dir = project_root / ".tmp"
    tmp_dir.mkdir(exist_ok=True)

    # Use shared test repo directory
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


# Authentication Test Helpers - Following MESSI Rule #1: Real components only
# StandardTestAuth has been REMOVED due to 401 authentication failures
# Use RealComponentTestInfrastructure from tests.fixtures.test_infrastructure instead


@pytest.fixture(autouse=True)
def clear_rate_limiters():
    """Clear rate limiter state before each test to prevent cross-test contamination."""
    try:
        from code_indexer.server.auth.rate_limiter import (
            password_change_rate_limiter,
            refresh_token_rate_limiter,
        )

        # Complete state reset for password change rate limiter
        password_change_rate_limiter._attempts.clear()

        # Complete state reset for refresh token rate limiter
        refresh_token_rate_limiter._attempts.clear()

        # Also clear any app module instances that might have cached rate limiters
        import code_indexer.server.app as app_module

        if hasattr(app_module, "password_change_rate_limiter"):
            app_module.password_change_rate_limiter._attempts.clear()
        if hasattr(app_module, "refresh_token_rate_limiter"):
            app_module.refresh_token_rate_limiter._attempts.clear()

    except (ImportError, AttributeError):
        pass  # Rate limiter might not be available in all test contexts


@pytest.fixture
def temp_audit_dir():
    """Provide temporary directory for audit logging tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def shared_container_test_environment():
    """
    Stub fixture for removed container infrastructure.

    Tests importing this will skip since container support was removed.
    This stub prevents collection errors.
    """
    pytest.skip("Container infrastructure was removed - test cannot run")


@pytest.fixture(scope="session")
def mock_oidc_server():
    """Provide a lightweight mock OIDC server for integration testing.

    The server runs in a background thread and provides:
    - Discovery endpoint (.well-known/openid-configuration)
    - Authorization endpoint (/authorize)
    - Token endpoint (/token)
    - Userinfo endpoint (/userinfo)

    Returns:
        MockOIDCServer: Configured and running mock server
    """
    from tests.fixtures.mock_oidc_server import MockOIDCServer

    server = MockOIDCServer(port=8888)
    server.start()

    yield server

    server.stop()
