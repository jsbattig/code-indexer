"""End-to-end tests for VoyageAI provider with cloud vectorization service.

Refactored to use NEW STRATEGY with test infrastructure for better performance.
"""

import os
import pytest

import json
import time

# Import new test infrastructure
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def voyage_ai_test_repo():
    """Create a test repository for VoyageAI E2E tests."""
    from pathlib import Path

    # Create a fresh temporary directory to avoid permission conflicts
    temp_base = Path.home() / ".tmp" / f"voyage_ai_test_{int(time.time())}"
    temp_base.mkdir(parents=True, exist_ok=True)

    try:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_base, TestProjectInventory.VOYAGE_AI_E2E
        )
        yield temp_base
    finally:
        # Clean up
        import shutil

        shutil.rmtree(temp_base, ignore_errors=True)


def create_test_codebase(test_dir):
    """Create a simple test codebase using test infrastructure."""
    # Create test files in the test directory
    test_files = {
        "main.py": '''def hello_world():
    """Print hello world message."""
    print("Hello, World!")

def calculate_fibonacci(n):
    """Calculate fibonacci number."""
    if n <= 1:
        return n
    return calculate_fibonacci(n-1) + calculate_fibonacci(n-2)

if __name__ == "__main__":
    hello_world()
    print(f"Fibonacci(10) = {calculate_fibonacci(10)}")''',
        "utils.py": '''import math

def calculate_distance(x1, y1, x2, y2):
    """Calculate Euclidean distance between two points."""
    return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

def format_number(num, decimals=2):
    """Format number with specified decimal places."""
    return f"{num:.{decimals}f}"''',
        "README.md": """# Test Project

This is a test project for VoyageAI E2E testing.

## Features
- Hello world function
- Fibonacci calculation
- Distance calculation utilities""",
    }

    # Create test files in the test directory
    for filename, content in test_files.items():
        file_path = test_dir / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)


def create_voyage_ai_config(test_dir):
    """Create configuration for VoyageAI provider."""
    config_dir = test_dir / ".code-indexer"
    config_dir.mkdir(exist_ok=True)

    # Load existing config if it exists (preserves container ports)
    config_file = config_dir / "config.json"
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
            "exclude_patterns": [
                "*.git*",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
            ],
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
def test_voyage_ai_full_workflow(voyage_ai_test_repo):
    """Test complete VoyageAI workflow with real API using test infrastructure."""
    # Use real VoyageAI API key from environment
    test_dir = voyage_ai_test_repo

    # Create test codebase
    create_test_codebase(test_dir)

    # Create VoyageAI configuration
    create_voyage_ai_config(test_dir)

    # Initialize project with VoyageAI provider
    import subprocess

    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Verify provider configuration
    status_result = subprocess.run(
        ["code-indexer", "status"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"

    # Verify Voyage-AI provider is shown and Ollama shows "Not needed"
    status_lower = status_result.stdout.lower()
    if "ollama" in status_lower:
        assert (
            "not needed" in status_lower
        ), f"Ollama should show 'Not needed' status: {status_result.stdout}"
    assert (
        "voyage" in status_result.stdout.lower()
        or "voyage-ai" in status_result.stdout.lower()
    ), f"VoyageAI should be in status: {status_result.stdout}"

    # Start services before indexing (may already be running)
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Allow start to fail if services are already running
    if start_result.returncode != 0:
        # Check if it's just because services are already running
        if (
            "already in use" in start_result.stdout
            or "already running" in start_result.stdout
        ):
            print("Services already running, continuing with test...")
        else:
            assert (
                False
            ), f"Start failed with return code {start_result.returncode}. stderr: {start_result.stderr}, stdout: {start_result.stdout}"

    # Test indexing workflow
    index_result = subprocess.run(
        ["code-indexer", "index"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

    # Test querying
    query_result = subprocess.run(
        ["code-indexer", "query", "hello world", "--quiet"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert query_result.returncode == 0, f"Query failed: {query_result.stderr}"
    assert len(query_result.stdout.strip()) > 0, "Query should return results"


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_voyage_ai_docker_compose_validation(voyage_ai_test_repo):
    """Test Docker Compose validation for VoyageAI provider."""
    test_dir = voyage_ai_test_repo

    # Create test codebase
    create_test_codebase(test_dir)

    # Create VoyageAI configuration
    create_voyage_ai_config(test_dir)

    # Initialize project
    import subprocess

    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Test start command
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_voyage_ai_idempotent_start(voyage_ai_test_repo):
    """Test idempotent start behavior with VoyageAI provider."""
    test_dir = voyage_ai_test_repo

    # Create test codebase
    create_test_codebase(test_dir)

    # Create VoyageAI configuration
    create_voyage_ai_config(test_dir)

    # Initialize project
    import subprocess

    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Test multiple start commands are idempotent
    for i in range(2):
        start_result = subprocess.run(
            ["code-indexer", "start"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result.returncode == 0
        ), f"Start #{i+1} failed: {start_result.stderr}"
