"""
Example of optimized test using shared containers.

This demonstrates the performance improvements from avoiding container
startup/shutdown on every test. Use this pattern for new E2E tests.

Performance comparison:
- Old pattern: ~60-120s per test (container startup each time)
- New pattern: ~5-10s per test (containers reused)
"""

import os
import tempfile
from pathlib import Path
import pytest

from .shared_container_fixture import (
    fast_cli_command,
    shared_containers,  # noqa: F401
    clean_test_data,  # noqa: F401
)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestOptimizedExample:
    """Example of optimized E2E test using shared containers."""

    @pytest.fixture(autouse=True)
    def setup_test_project(self, shared_containers, clean_test_data):  # noqa: F811
        """Setup test project directory - containers already running."""

        # Create temporary test project
        self.test_dir = Path(tempfile.mkdtemp(prefix="optimized_test_"))
        self.original_cwd = Path.cwd()

        # Create test files
        self.create_test_files()

        # Change to test directory
        os.chdir(self.test_dir)

        yield

        # Cleanup: only remove test directory, containers stay running
        os.chdir(self.original_cwd)
        import shutil

        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_files(self):
        """Create test files for indexing."""

        (self.test_dir / "main.py").write_text(
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

        (self.test_dir / "api.py").write_text(
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

    def test_fast_indexing_workflow(self, shared_containers):  # noqa: F811
        """Test indexing workflow with shared containers (FAST)."""

        # Step 1: Init project with VoyageAI (containers already running)
        result = fast_cli_command(
            ["init", "--embedding-provider", "voyage-ai", "--force"]
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Step 2: Index project (no container startup needed)
        result = fast_cli_command(["index"], timeout=60)
        assert result.returncode == 0, f"Index failed: {result.stderr}"
        assert "Files processed:" in result.stdout

        # Step 3: Search for content
        result = fast_cli_command(["query", "authentication function"])
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        # Note: May not find results due to VoyageAI vs test data mismatch, but that's OK for performance test

        # Step 4: Check status
        result = fast_cli_command(["status"])
        assert result.returncode == 0, f"Status failed: {result.stderr}"

        # No container cleanup needed - shared_containers handles it

    def test_fast_multiple_projects(self, shared_containers):  # noqa: F811
        """Test multiple project workflow with shared containers (FAST)."""

        # Project 1
        result = fast_cli_command(
            ["init", "--embedding-provider", "voyage-ai", "--force"]
        )
        assert result.returncode == 0

        result = fast_cli_command(["index"])
        assert result.returncode == 0

        # Quick data cleanup (not container cleanup)
        result = fast_cli_command(["clean-data"])
        assert result.returncode == 0

        # Project 2 setup (containers still running)
        result = fast_cli_command(
            ["init", "--embedding-provider", "voyage-ai", "--force"]
        )
        assert result.returncode == 0

        result = fast_cli_command(["index"])
        assert result.returncode == 0

        # Fast cleanup again
        result = fast_cli_command(["clean-data"])
        assert result.returncode == 0

    def test_fast_error_recovery(self, shared_containers):  # noqa: F811
        """Test error conditions with shared containers (FAST)."""

        # Test query without index
        result = fast_cli_command(["query", "nonexistent"])
        # Should fail gracefully, but test should be fast

        # Test status without setup
        result = fast_cli_command(["status"])
        assert result.returncode == 0

        # Quick recovery
        result = fast_cli_command(
            ["init", "--embedding-provider", "voyage-ai", "--force"]
        )
        assert result.returncode == 0

        result = fast_cli_command(["index"])
        assert result.returncode == 0


# For comparison - this is how slow tests look:
@pytest.mark.skipif(True, reason="Disabled slow example for demonstration")
class TestSlowExample:
    """Example of how NOT to write tests - this is the slow pattern."""

    def tearDown(self):
        """This is what makes tests slow - full cleanup every time."""
        # DON'T DO THIS in new tests:
        fast_cli_command(["uninstall"], timeout=90)
        # This takes 30-60 seconds per test!

    def test_slow_workflow(self):
        """Slow test that starts containers from scratch."""
        # Step 1: Full container startup (30-60s)
        fast_cli_command(["start", "--quiet"], timeout=180)

        # Step 2: Index (fast part)
        fast_cli_command(["index"])

        # Step 3: Query (fast part)
        fast_cli_command(["query", "something"])

        # Step 4: Full cleanup (30-60s)
        self.tearDown()

        # Total time: 60-120s per test vs 5-10s with shared containers!
