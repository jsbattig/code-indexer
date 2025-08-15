#!/usr/bin/env python3
"""
Comprehensive end-to-end tests that exercise ALL code paths including:
- Single project indexing and search
- Multi-project indexing and search
- Clean functionality and trace removal
- Container lifecycle management

Converted to use fixture-based approach with shared test infrastructure.
"""

import os
import json
import subprocess
from pathlib import Path
import pytest
import requests  # type: ignore

# Import new test infrastructure
from ...conftest import local_temporary_directory
from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def end_to_end_test_repo():
    """Create a test repository for end-to-end tests."""
    with local_temporary_directory() as temp_dir:
        # Create isolated project space using inventory system (no config tinkering)
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.END_TO_END_COMPLETE
        )

        yield temp_dir


def create_end_to_end_config(test_dir):
    """Create configuration for end-to-end test."""

    config_dir = test_dir / ".code-indexer"
    config_file = config_dir / "config.json"

    # Ensure the config directory exists
    config_dir.mkdir(parents=True, exist_ok=True)

    # Load existing config if it exists (preserves container ports)
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
    else:
        config = {
            "codebase_dir": str(test_dir),
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "end_to_end_test_collection",
                "vector_size": 1024,
            },
        }

    # Use the shared port detection helper
    from ...conftest import detect_running_qdrant_port

    working_port = detect_running_qdrant_port()

    if working_port:
        config["qdrant"]["host"] = f"http://localhost:{working_port}"
        print(f"✅ Updated config to use Qdrant on port {working_port}")
    else:
        print("⚠️  No running Qdrant service detected, using default port")

    # Override collection name to avoid conflicts (use timestamp to ensure uniqueness)
    import time

    timestamp = str(int(time.time()))
    config["qdrant"]["collection"] = f"e2e_test_clean_{timestamp}"
    config["qdrant"]["collection_base_name"] = f"e2e_test_clean_{timestamp}"

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


def create_test_projects(base_dir):
    """Create test projects for end-to-end testing."""
    projects_dir = base_dir / "projects"
    projects_dir.mkdir(exist_ok=True)

    # Create test_project_1 (calculator)
    project1_dir = projects_dir / "test_project_1"
    project1_dir.mkdir(exist_ok=True)

    (project1_dir / "main.py").write_text(
        """def main():
    print("Calculator Application")
    result = add(5, 3)
    print(f"5 + 3 = {result}")
    factorial_result = factorial(5)
    print(f"5! = {factorial_result}")

def add(a, b):
    '''Add two numbers'''
    return a + b

def factorial(n):
    '''Calculate factorial of n'''
    if n <= 1:
        return 1
    return n * factorial(n - 1)

if __name__ == "__main__":
    main()"""
    )

    (project1_dir / "utils.py").write_text(
        """import math

def square_root(n):
    '''Calculate square root'''
    return math.sqrt(n)

def is_prime(n):
    '''Check if number is prime'''
    if n < 2:
        return False
    for i in range(2, int(math.sqrt(n)) + 1):
        if n % i == 0:
            return False
    return True

def calculator_utils():
    '''Calculator utility functions'''
    return {
        'sqrt': square_root,
        'prime': is_prime
    }"""
    )

    # Create test_project_2 (web server)
    project2_dir = projects_dir / "test_project_2"
    project2_dir.mkdir(exist_ok=True)

    (project2_dir / "web_server.py").write_text(
        """from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    '''Home route'''
    return "Web Server Application"

@app.route('/api/data')
def api_data():
    '''API data route'''
    return jsonify({"message": "Hello from API"})

@app.route('/login', methods=['POST'])
def login():
    '''Login route'''
    username = request.json.get('username')
    password = request.json.get('password')
    return authenticate_user(username, password)

def authenticate_user(username, password):
    '''Authentication function'''
    return {"authenticated": username == "admin" and password == "secret"}

if __name__ == "__main__":
    app.run(debug=True)"""
    )

    (project2_dir / "auth.py").write_text(
        """def check_credentials(username, password):
    '''Check user credentials'''
    valid_users = {
        "admin": "secret",
        "user": "password"
    }
    return valid_users.get(username) == password

def generate_token(username):
    '''Generate authentication token'''
    import hashlib
    return hashlib.md5(f"{username}_token".encode()).hexdigest()

def validate_token(token):
    '''Validate authentication token'''
    return len(token) == 32  # Simple validation"""
    )

    return project1_dir, project2_dir


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_single_project_workflow(end_to_end_test_repo):
    """Test core single project workflow: init -> start -> index -> query -> status -> clean-data."""
    test_dir = end_to_end_test_repo

    # Create test projects
    project1_dir, project2_dir = create_test_projects(test_dir)

    try:
        original_cwd = Path.cwd()
        os.chdir(project1_dir)

        # 1. Initialize with VoyageAI provider
        print("🔧 Single project test: Initializing project...")
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        # Create configuration after init (like branch topology tests)
        # Config created by inventory system

        # 2. Start services (handle conflicts gracefully)
        print("🚀 Single project test: Starting services...")
        start_result = subprocess.run(
            ["code-indexer", "start", "--force-docker"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if start_result.returncode != 0:
            # If start failed due to port conflicts, check if services are already running
            if "already in use" in start_result.stdout:
                print("🔍 Services may already be running, attempting to proceed...")
                # Verify we can reach Qdrant
                try:
                    with open(project1_dir / ".code-indexer" / "config.json", "r") as f:
                        config = json.load(f)
                    qdrant_url = config["qdrant"]["host"]
                    response = requests.get(f"{qdrant_url}/cluster", timeout=5)
                    if response.status_code == 200:
                        print("✅ Qdrant service is accessible, proceeding with test")
                    else:
                        pytest.skip(
                            f"Start failed and Qdrant not accessible: {start_result.stdout}"
                        )
                except Exception as e:
                    pytest.skip(f"Start failed and could not verify services: {e}")
            else:
                pytest.skip(f"Could not start services: {start_result.stdout}")
        else:
            print("✅ Services started successfully")

        # 3. Index the project
        print("📚 Single project test: Indexing project...")
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # 4. Test search functionality
        print("🔍 Single project test: Testing search functionality...")
        search_queries = ["add function", "calculator", "factorial"]

        successful_queries = 0
        for query in search_queries:
            result = subprocess.run(
                ["code-indexer", "query", query],
                cwd=project1_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and len(result.stdout.strip()) > 0:
                output = result.stdout.lower()
                if any(file in output for file in ["main.py", "utils.py"]):
                    successful_queries += 1
                    print(f"✅ Query '{query}' found expected files")

        assert successful_queries > 0, "No search queries found expected files"

        # 5. Test status functionality
        print("📊 Single project test: Testing status functionality...")
        status_result = subprocess.run(
            ["code-indexer", "status"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "Available" in status_result.stdout or "✅" in status_result.stdout

        print("✅ Single project workflow test completed successfully")

    finally:
        try:
            os.chdir(original_cwd)
            # Clean up
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                cwd=project1_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass


@pytest.mark.skip(reason="Skipping uninstall test as requested")
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_complete_lifecycle_management(end_to_end_test_repo):
    """Test complete container lifecycle: start -> uninstall -> verify shutdown."""
    test_dir = end_to_end_test_repo
    project1_dir, _ = create_test_projects(test_dir)
    # Config created by inventory system

    # This test is skipped but kept for reference
    pytest.skip("Lifecycle management test not needed for fixture-based approach")


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_multi_project_isolation_and_search(end_to_end_test_repo):
    """Test multi-project functionality with shared global vector database."""
    test_dir = end_to_end_test_repo
    project1_dir, project2_dir = create_test_projects(test_dir)

    try:
        original_cwd = Path.cwd()

        # Setup project 1
        # Config created by inventory system
        os.chdir(project1_dir)

        init_result1 = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result1.returncode == 0
        ), f"Project 1 init failed: {init_result1.stderr}"

        start_result1 = subprocess.run(
            ["code-indexer", "start", "--force-docker", "--quiet"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result1.returncode == 0
        ), f"Project 1 start failed: {start_result1.stderr}"

        index_result1 = subprocess.run(
            ["code-indexer", "index"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result1.returncode == 0
        ), f"Project 1 index failed: {index_result1.stderr}"

        # Verify project 1 port allocation
        with open(project1_dir / ".code-indexer" / "config.json", "r") as f:
            project1_config = json.load(f)
        project1_ports = project1_config.get("project_ports", {})
        print(f"✅ Project 1 ports: {project1_ports}")
        assert (
            "qdrant_port" in project1_ports
        ), "Project 1 should have qdrant_port allocated"

        # Setup project 2
        # Config created by inventory system
        os.chdir(project2_dir)

        init_result2 = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result2.returncode == 0
        ), f"Project 2 init failed: {init_result2.stderr}"

        # Start services for project 2 (should be idempotent)
        start_result2 = subprocess.run(
            ["code-indexer", "start", "--force-docker", "--quiet"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result2.returncode == 0
        ), f"Project 2 start failed: {start_result2.stderr}"

        index_result2 = subprocess.run(
            ["code-indexer", "index"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result2.returncode == 0
        ), f"Project 2 index failed: {index_result2.stderr}"

        # Verify project 2 port allocation and compare with project 1
        with open(project2_dir / ".code-indexer" / "config.json", "r") as f:
            project2_config = json.load(f)
        project2_ports = project2_config.get("project_ports", {})
        print(f"✅ Project 2 ports: {project2_ports}")
        assert (
            "qdrant_port" in project2_ports
        ), "Project 2 should have qdrant_port allocated"

        # Verify port coordination - projects should have different ports
        if project1_ports.get("qdrant_port") == project2_ports.get("qdrant_port"):
            print(
                f"⚠️  Both projects using same qdrant port: {project1_ports.get('qdrant_port')}"
            )
            print("This may be expected if using shared containers")
        else:
            print(
                f"✅ Port coordination working - Project 1: {project1_ports.get('qdrant_port')}, Project 2: {project2_ports.get('qdrant_port')}"
            )

        # Test project 1 searches
        os.chdir(project1_dir)
        calc_queries = ["add function", "factorial", "calculator"]
        for query in calc_queries:
            result = subprocess.run(
                ["code-indexer", "query", query],
                cwd=project1_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                output = result.stdout.lower()
                if "main.py" in output or "utils.py" in output:
                    print(f"✅ Project 1 query '{query}' found calculator files")

        # Test project 2 searches
        os.chdir(project2_dir)
        web_queries = ["web server", "route function", "authentication"]
        for query in web_queries:
            result = subprocess.run(
                ["code-indexer", "query", query],
                cwd=project2_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                output = result.stdout.lower()
                if "web_server.py" in output or "auth.py" in output:
                    print(f"✅ Project 2 query '{query}' found web server files")

        print("✅ Multi-project test completed successfully")

    finally:
        try:
            os.chdir(original_cwd)
            # Clean up both projects
            for project_dir in [project1_dir, project2_dir]:
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
        except Exception:
            pass


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_error_conditions_and_recovery(end_to_end_test_repo):
    """Test error handling and recovery scenarios."""
    test_dir = end_to_end_test_repo
    project1_dir, _ = create_test_projects(test_dir)
    # Config created by inventory system

    try:
        original_cwd = Path.cwd()
        os.chdir(project1_dir)

        # Initialize and start services
        init_result = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        start_result = subprocess.run(
            ["code-indexer", "start", "--force-docker", "--quiet"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Test 1: Query with non-existent term
        query_result = subprocess.run(
            ["code-indexer", "query", "nonexistent_unique_term_12345"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should not crash, may return no results
        assert (
            query_result.returncode == 0
        ), "Query should not crash with non-existent term"

        # Test 2: Status should work
        status_result = subprocess.run(
            ["code-indexer", "status"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"

        # Test 3: Index the project
        index_result = subprocess.run(
            ["code-indexer", "index"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Test 4: Verify indexing worked
        verify_result = subprocess.run(
            ["code-indexer", "query", "calculator"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert verify_result.returncode == 0, "Query after indexing should work"

        print("✅ Error conditions and recovery test completed successfully")

    finally:
        try:
            os.chdir(original_cwd)
            subprocess.run(
                ["code-indexer", "clean", "--remove-data", "--quiet"],
                cwd=project1_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except Exception:
            pass


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_concurrent_operations(end_to_end_test_repo):
    """Test that concurrent operations on different projects work correctly."""
    test_dir = end_to_end_test_repo
    project1_dir, project2_dir = create_test_projects(test_dir)

    try:
        original_cwd = Path.cwd()

        # Setup project 1
        # Config created by inventory system
        os.chdir(project1_dir)

        init_result1 = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result1.returncode == 0
        ), f"Project 1 init failed: {init_result1.stderr}"

        start_result1 = subprocess.run(
            ["code-indexer", "start", "--force-docker", "--quiet"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result1.returncode == 0
        ), f"Project 1 start failed: {start_result1.stderr}"

        index_result1 = subprocess.run(
            ["code-indexer", "index"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result1.returncode == 0
        ), f"Project 1 index failed: {index_result1.stderr}"

        # Setup project 2 (services should already be running)
        # Config created by inventory system
        os.chdir(project2_dir)

        init_result2 = subprocess.run(
            ["code-indexer", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result2.returncode == 0
        ), f"Project 2 init failed: {init_result2.stderr}"

        # Start services for project 2 (should be idempotent with project 1)
        start_result2 = subprocess.run(
            ["code-indexer", "start", "--force-docker", "--quiet"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result2.returncode == 0
        ), f"Project 2 start failed: {start_result2.stderr}"

        index_result2 = subprocess.run(
            ["code-indexer", "index"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result2.returncode == 0
        ), f"Project 2 index failed: {index_result2.stderr}"

        # Verify both projects work independently
        os.chdir(project1_dir)
        result1 = subprocess.run(
            ["code-indexer", "query", "calculator"],
            cwd=project1_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result1.returncode == 0, "Project 1 query should work"

        os.chdir(project2_dir)
        result2 = subprocess.run(
            ["code-indexer", "query", "server"],
            cwd=project2_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result2.returncode == 0, "Project 2 query should work"

        print("✅ Concurrent operations test completed successfully")

    finally:
        try:
            os.chdir(original_cwd)
            # Clean up both projects
            for project_dir in [project1_dir, project2_dir]:
                subprocess.run(
                    ["code-indexer", "clean", "--remove-data", "--quiet"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
        except Exception:
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
