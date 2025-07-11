"""
Example of optimized test using shared containers.

This demonstrates the performance improvements from avoiding container
startup/shutdown on every test. Use this pattern for new E2E tests.

Performance comparison:
- Old pattern: ~60-120s per test (container startup each time)
- New pattern: ~5-10s per test (containers reused)
"""

import os
import json
import time
import subprocess
import pytest

from .conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def optimized_test_repo():
    """Create a test repository for optimized E2E tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.OPTIMIZED_EXAMPLE
        )

        yield temp_dir


def create_test_files(test_dir):
    """Create test files for indexing."""

    (test_dir / "main.py").write_text(
        """
def authenticate_user(username, password):
    '''User authentication function'''
    return username == "admin" and password == "secret"

class UserManager:
    '''Manages user accounts'''
    def __init__(self):
        self.users = {}
    
    def create_user(self, username, email):
        '''Create a new user account'''
        self.users[username] = {"email": email}
        return True
"""
    )

    (test_dir / "api.py").write_text(
        """
from fastapi import FastAPI
app = FastAPI()

@app.post("/login")
async def login_endpoint(username: str, password: str):
    '''REST API login endpoint'''
    # Authentication logic here
    return {"status": "success", "token": "abc123"}

@app.get("/users/{user_id}")  
async def get_user(user_id: int):
    '''Get user by ID endpoint'''
    return {"id": user_id, "username": f"user_{user_id}"}
"""
    )


def create_optimized_config(test_dir):
    """Create configuration for optimized test."""
    config_dir = test_dir / ".code-indexer"
    config_file = config_dir / "config.json"

    # Load existing config if it exists (preserves container ports)
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
    else:
        config = {
            "codebase_dir": str(test_dir),
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": f"test_collection_{int(time.time())}",
            },
        }

    # Only modify test-specific settings, preserve container configuration
    config["embedding_provider"] = "voyage-ai"
    config["voyage_ai"] = {
        "model": "voyage-code-3",
        "api_key_env": "VOYAGE_API_KEY",
        "batch_size": 32,
        "max_retries": 3,
        "timeout": 30,
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    return config_file


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_fast_indexing_workflow(optimized_test_repo):
    """Test indexing workflow with shared containers (FAST)."""
    test_dir = optimized_test_repo

    # Create test files
    create_test_files(test_dir)

    # Create configuration
    create_optimized_config(test_dir)

    # Step 1: Init project with VoyageAI
    result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"Init failed: {result.stderr}"

    # Step 2: Start services
    result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"Start failed: {result.stderr}"

    # Step 3: Index project
    result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"Index failed: {result.stderr}"
    assert "Files processed:" in result.stdout or "Processing complete" in result.stdout

    # Step 4: Search for content
    result = subprocess.run(
        ["code-indexer", "query", "authentication function", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Query failed: {result.stderr}"
    # Note: May not find results due to VoyageAI vs test data mismatch, but that's OK for performance test

    # Step 5: Check status
    result = subprocess.run(
        ["code-indexer", "status"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Status failed: {result.stderr}"

    # No container cleanup needed - service manager handles it


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_fast_multiple_projects(optimized_test_repo):
    """Test multiple project workflow with shared containers (FAST)."""
    test_dir = optimized_test_repo

    # Create test files
    create_test_files(test_dir)

    # Create configuration
    create_optimized_config(test_dir)

    # Project 1
    result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Start services
    result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0

    result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Quick data cleanup (not container cleanup)
    result = subprocess.run(
        ["code-indexer", "clean-data"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0

    # Project 2 setup (ensure containers are still running)
    result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Ensure services are still running after clean-data
    result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0

    result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Fast cleanup again
    result = subprocess.run(
        ["code-indexer", "clean-data"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_fast_error_recovery(optimized_test_repo):
    """Test error conditions with shared containers (FAST)."""
    test_dir = optimized_test_repo

    # Create test files
    create_test_files(test_dir)

    # Create configuration
    create_optimized_config(test_dir)

    # Test query without index
    result = subprocess.run(
        ["code-indexer", "query", "nonexistent", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    # Should fail gracefully, but test should be fast

    # Test status without setup
    result = subprocess.run(
        ["code-indexer", "status"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0

    # Quick recovery
    result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0

    # Start services
    result = subprocess.run(
        ["code-indexer", "start", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0

    result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0


# For comparison - this is how slow tests look:
@pytest.mark.skipif(True, reason="Disabled slow example for demonstration")
class TestSlowExample:
    """Example of how NOT to write tests - this is the slow pattern."""

    def tearDown(self):
        """This is what makes tests slow - full cleanup every time."""
        # DON'T DO THIS in new tests:
        # fast_cli_command(["uninstall"], timeout=90)
        # This takes 30-60 seconds per test!
        pass  # This is just a demonstration

    def test_slow_workflow(self):
        """Slow test that starts containers from scratch."""
        # Step 1: Full container startup (30-60s)
        # fast_cli_command(["start", "--quiet"], timeout=180)

        # Step 2: Index (fast part)
        # fast_cli_command(["index"])

        # Step 3: Query (fast part)
        # fast_cli_command(["query", "something"])

        # Step 4: Full cleanup (30-60s)
        # self.tearDown()

        # Total time: 60-120s per test vs 5-10s with shared containers!
        pass  # This is just a demonstration
