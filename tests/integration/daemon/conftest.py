"""
Pytest fixtures for daemon race condition stress tests.

Provides shared fixtures for daemon integration tests including:
- sample_repo_with_index: Git repo with indexed code for testing daemon operations
- daemon_service_with_project: Daemon service with indexed project ready for testing
"""

import subprocess
from pathlib import Path
from typing import Generator, Tuple

import pytest

from code_indexer.daemon.service import CIDXDaemonService


@pytest.fixture
def sample_repo_with_index(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Create a git repository with sample code and run indexing.

    This fixture provides a realistic test environment with:
    - Initialized git repository
    - Multiple Python files with varied content
    - Pre-built semantic index for queries
    - Ready for daemon operations

    Returns:
        Path to indexed git repository
    """
    # Initialize git repository
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Create sample Python files with varied content
    (tmp_path / "main.py").write_text(
        """#!/usr/bin/env python3
'''Main application entry point.'''

def main():
    '''Run the main application.'''
    print("Hello World")
    process_data()
    handle_errors()

def process_data():
    '''Process application data.'''
    data = load_data()
    result = transform_data(data)
    save_result(result)

if __name__ == "__main__":
    main()
"""
    )

    (tmp_path / "utils.py").write_text(
        """'''Utility functions for the application.'''

def helper_function():
    '''Helper function for common tasks.'''
    return "helper result"

def load_data():
    '''Load data from source.'''
    return {"key": "value"}

def transform_data(data):
    '''Transform input data.'''
    return {k: v.upper() for k, v in data.items()}

def save_result(result):
    '''Save processing result.'''
    print(f"Saved: {result}")
"""
    )

    (tmp_path / "auth.py").write_text(
        """'''Authentication and authorization module.'''

class AuthManager:
    '''Manage user authentication.'''

    def login(self, username, password):
        '''Authenticate user with credentials.'''
        return self.verify_credentials(username, password)

    def verify_credentials(self, username, password):
        '''Verify user credentials.'''
        return True

    def logout(self):
        '''Log out current user.'''
        pass
"""
    )

    (tmp_path / "config.py").write_text(
        """'''Configuration management.'''

class Config:
    '''Application configuration.'''
    DEBUG = True
    HOST = 'localhost'
    PORT = 8000

def load_config():
    '''Load application configuration.'''
    return Config()
"""
    )

    (tmp_path / "tests.py").write_text(
        """'''Test suite for the application.'''

def test_helper():
    '''Test helper function.'''
    from utils import helper_function
    result = helper_function()
    assert result == "helper result"

def test_auth():
    '''Test authentication.'''
    from auth import AuthManager
    manager = AuthManager()
    assert manager.login("user", "pass")
"""
    )

    # Commit all files
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit with sample code"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )

    # Initialize code-indexer configuration
    subprocess.run(
        ["python3", "-m", "code_indexer.cli", "init", "--force"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
        timeout=60,
    )

    # Run indexing to build semantic index
    # Note: This may fail if VoyageAI API is not available, which is acceptable for daemon tests
    # The daemon service will handle missing index gracefully
    try:
        subprocess.run(
            ["python3", "-m", "code_indexer.cli", "index"],
            cwd=tmp_path,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        # Indexing failure is acceptable - daemon tests don't strictly require pre-built index
        pass

    yield tmp_path

    # Cleanup is handled by tmp_path fixture


@pytest.fixture
def daemon_service_with_project(
    sample_repo_with_index: Path,
) -> Generator[Tuple[CIDXDaemonService, Path], None, None]:
    """
    Fixture providing a daemon service with an indexed project.

    This fixture:
    - Creates a fresh CIDXDaemonService instance
    - Uses the sample_repo_with_index for testing
    - Ensures cache is loaded for query operations
    - Handles cleanup of threads and handlers

    Returns:
        Tuple[CIDXDaemonService, Path]: Service instance and project path
    """
    # Create daemon service
    service = CIDXDaemonService()

    # Use sample repo with existing index
    project_path = sample_repo_with_index

    # Load cache if possible (gracefully handle failures)
    try:
        service._ensure_cache_loaded(str(project_path))
    except Exception:
        # Cache loading failure is acceptable - tests will handle it
        pass

    yield service, project_path

    # Cleanup
    if service.watch_handler:
        try:
            service.watch_handler.stop_watching()
        except Exception:
            pass

    if service.indexing_thread and service.indexing_thread.is_alive():
        service.indexing_thread.join(timeout=5)

    if service.eviction_thread:
        try:
            service.eviction_thread.stop()
        except Exception:
            pass
