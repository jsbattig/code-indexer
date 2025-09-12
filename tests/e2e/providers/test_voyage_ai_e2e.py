"""End-to-end tests for VoyageAI provider with cloud vectorization service.

Converted to use shared container strategy for 41% complete milestone.
These tests validate VoyageAI-specific functionality within shared container context.
"""

import os
import subprocess
import pytest

from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def create_voyage_ai_test_codebase(test_dir):
    """Create VoyageAI-specific test codebase for shared container tests."""
    # Create test files optimized for VoyageAI semantic understanding
    test_files = {
        "main.py": '''def hello_world():
    """Print hello world message."""
    print("Hello, World!")

def calculate_fibonacci(n):
    """Calculate fibonacci number recursively."""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

def authenticate_user(username, password):
    """User authentication with basic validation."""
    return username == "admin" and password == "secret"

if __name__ == "__main__":
    hello_world()
    print(f"Fibonacci(10) = {calculate_fibonacci(10)}")''',
        "utils.py": '''import math

def calculate_distance(x1, y1, x2, y2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def format_number(num, decimals=2):
    """Format number with specified decimal places."""
    return f"{num:.{decimals}f}"

def validate_email(email):
    """Basic email validation function."""
    return "@" in email and "." in email.split("@")[1]''',
        "api.py": '''from fastapi import FastAPI
app = FastAPI()

@app.post("/login")
async def login_endpoint(username: str, password: str):
    """REST API login endpoint for user authentication."""
    # Authentication logic here
    return {"status": "success", "token": "abc123"}

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    """Get user by ID endpoint."""
    return {"id": user_id, "username": f"user_{user_id}"}''',
        "README.md": """# VoyageAI Test Project

This is a test project for VoyageAI E2E testing with shared containers.

## Features
- Hello world function
- Fibonacci calculation
- User authentication
- Distance calculation utilities
- Email validation
- REST API endpoints
""",
    }

    # Create test files in the test directory
    for filename, content in test_files.items():
        file_path = test_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_voyage_ai_shared_container_full_workflow():
    """Test complete VoyageAI workflow using shared container strategy."""
    with shared_container_test_environment(
        "test_voyage_ai_shared_container_full_workflow", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create VoyageAI-optimized test codebase
        create_voyage_ai_test_codebase(project_path)

        # Step 1: Initialize project with VoyageAI provider
        result = subprocess.run(
            ["cidx", "init", "--embedding-provider", "voyage-ai", "--force"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Step 2: Verify provider configuration and status
        result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Status failed: {result.stderr}"

        # Verify VoyageAI provider is configured and Ollama shows "Not needed"
        status_lower = result.stdout.lower()
        if "ollama" in status_lower:
            assert (
                "not needed" in status_lower
            ), f"Ollama should show 'Not needed' status: {result.stdout}"
        assert (
            "voyage" in status_lower or "voyage-ai" in status_lower
        ), f"VoyageAI should be in status: {result.stdout}"

        # Step 3: Start services (should be fast with shared containers)
        result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Step 4: Test indexing workflow with VoyageAI
        result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Index failed: {result.stderr}"
        assert (
            "Files processed:" in result.stdout
            or "Processing complete" in result.stdout
        ), "Index should show completion message"

        # Step 5: Test semantic querying with VoyageAI
        result = subprocess.run(
            ["cidx", "query", "authentication function", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        # VoyageAI should find semantic matches for authentication

        # Step 6: Test another query to verify VoyageAI functionality
        result = subprocess.run(
            ["cidx", "query", "hello world", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Query failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0, "Query should return results"


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_voyage_ai_shared_container_service_validation():
    """Test VoyageAI service validation within shared container environment."""
    with shared_container_test_environment(
        "test_voyage_ai_shared_container_service_validation",
        EmbeddingProvider.VOYAGE_AI,
    ) as project_path:
        # Create test codebase for service validation
        create_voyage_ai_test_codebase(project_path)

        # Step 1: Initialize project with VoyageAI
        result = subprocess.run(
            ["cidx", "init", "--embedding-provider", "voyage-ai", "--force"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Step 2: Test Docker Compose/container validation via start command
        result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Start failed: {result.stderr}"

        # Step 3: Verify services are running properly for VoyageAI
        result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Status failed: {result.stderr}"

        # Verify containers/services are properly configured for VoyageAI
        status_output = result.stdout.lower()
        assert "running" in status_output, "Services should be running"

        # Step 4: Test that VoyageAI-specific services work correctly
        # Test basic indexing to validate container setup
        result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            result.returncode == 0
        ), f"Index failed, indicating service issues: {result.stderr}"

        # Step 5: Validate that containers can be restarted (idempotent start)
        result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, f"Restart failed: {result.stderr}"


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_voyage_ai_shared_container_idempotent_operations():
    """Test idempotent operations with VoyageAI in shared container environment."""
    with shared_container_test_environment(
        "test_voyage_ai_shared_container_idempotent_operations",
        EmbeddingProvider.VOYAGE_AI,
    ) as project_path:
        # Create test codebase
        create_voyage_ai_test_codebase(project_path)

        # Step 1: Initialize project with VoyageAI
        result = subprocess.run(
            ["cidx", "init", "--embedding-provider", "voyage-ai", "--force"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, f"Init failed: {result.stderr}"

        # Step 2: Test multiple start commands are idempotent (critical for shared containers)
        for i in range(3):
            result = subprocess.run(
                ["cidx", "start", "--quiet"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"Start #{i + 1} failed: {result.stderr}"

            # Each start should be fast due to shared containers
            # Verify status after each start
            status_result = subprocess.run(
                ["cidx", "status"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert status_result.returncode == 0, f"Status failed after start #{i + 1}"

        # Step 3: Test idempotent indexing operations
        for i in range(2):
            result = subprocess.run(
                ["cidx", "index"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, f"Index #{i + 1} failed: {result.stderr}"

        # Step 4: Test idempotent querying
        for i in range(2):
            result = subprocess.run(
                ["cidx", "query", "authentication", "--quiet"],
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, f"Query #{i + 1} failed: {result.stderr}"

        # Step 5: Verify final state is consistent
        result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Final status failed: {result.stderr}"
        assert "voyage" in result.stdout.lower(), "VoyageAI should still be active"
