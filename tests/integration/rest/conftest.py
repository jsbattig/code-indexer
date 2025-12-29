"""
Shared fixtures for REST API integration tests.

Provides common test fixtures for:
- Test git repository setup (real clone of txt-db)
- Mock user for authentication bypass
- FastAPI test application
- TestClient for HTTP requests
- Activated repository registration
"""

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.repositories.activated_repo_manager import ActivatedRepoManager

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module")
def test_repo_dir() -> Generator[Path, None, None]:
    """
    Create a real git repository for testing.

    Clones git@github.com:jsbattig/txt-db.git to a temporary directory.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="cidx_git_test_"))
    repo_path = temp_dir / "txt-db"

    try:
        # Clone the test repository
        subprocess.run(
            ["git", "clone", "git@github.com:jsbattig/txt-db.git", str(repo_path)],
            check=True,
            capture_output=True,
            timeout=60
        )

        # Configure git user for commits
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True
        )

        yield repo_path

    finally:
        # Cleanup: Remove test directory
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def mock_user():
    """Create mock User object for authentication bypass."""
    user = Mock()
    user.username = "testuser"
    user.role = "user"
    user.email = "testuser@example.com"
    return user


@pytest.fixture(scope="module")
def test_app(mock_user):
    """Create FastAPI test app with authentication bypass."""
    def mock_get_current_user_dep():
        return mock_user

    # Create app
    app = create_app()

    # Override authentication dependency
    app.dependency_overrides[get_current_user] = mock_get_current_user_dep

    yield app

    # Cleanup
    app.dependency_overrides.clear()


@pytest.fixture(scope="module")
def client(test_app):
    """Create TestClient for making HTTP requests."""
    return TestClient(test_app)


@pytest.fixture(scope="function")
def activated_repo(test_repo_dir: Path) -> Generator[str, None, None]:
    """
    Mock activated repository to return test repository path.

    This allows integration tests to use real git operations on the test repo
    without requiring golden repository setup.

    Returns:
        Repository alias for use in API calls
    """
    from unittest.mock import patch

    alias = "test-git-repo"

    # Mock ActivatedRepoManager.get_activated_repo_path to return test path
    with patch.object(
        ActivatedRepoManager,
        'get_activated_repo_path',
        return_value=str(test_repo_dir)
    ):
        yield alias
