#!/usr/bin/env python3
"""
Comprehensive end-to-end tests that exercise ALL code paths including:
- Single project indexing and search
- Multi-project indexing and search
- Clean functionality and trace removal
- Container lifecycle management

Converted to use shared container strategy for improved performance.
"""

import os
import subprocess
import pytest

# Import shared container infrastructure
from ...conftest import shared_container_test_environment
from .infrastructure import EmbeddingProvider

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


def create_test_files_calculator(project_dir):
    """Create calculator test files in the specified directory."""
    (project_dir / "main.py").write_text(
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

    (project_dir / "utils.py").write_text(
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


def create_test_files_webserver(project_dir):
    """Create web server test files in the specified directory."""
    (project_dir / "web_server.py").write_text(
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

    (project_dir / "auth.py").write_text(
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


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_single_project_complete_workflow():
    """Test core single project workflow: init -> start -> index -> query -> status."""
    with shared_container_test_environment(
        "test_single_project_complete_workflow", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create calculator test files
        create_test_files_calculator(project_path)

        print("🔧 Single project test: Initializing project...")
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        print("🚀 Single project test: Starting services...")
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        print("📚 Single project test: Indexing project...")
        index_result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"
        assert (
            "Files processed:" in index_result.stdout
            or "Processing complete" in index_result.stdout
        )

        print("🔍 Single project test: Testing search functionality...")
        search_queries = ["add function", "calculator", "factorial"]

        successful_queries = 0
        for query in search_queries:
            result = subprocess.run(
                ["cidx", "query", query, "--quiet"],
                cwd=project_path,
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

        print("📊 Single project test: Testing status functionality...")
        status_result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "Available" in status_result.stdout or "✅" in status_result.stdout

        print("✅ Single project workflow test completed successfully")


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_complete_lifecycle_clean_data():
    """Test complete data lifecycle: init -> index -> clean-data -> verify cleanup."""
    with shared_container_test_environment(
        "test_complete_lifecycle_clean_data", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        # Create calculator test files
        create_test_files_calculator(project_path)

        print("🔧 Lifecycle test: Initializing project...")
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        print("🚀 Lifecycle test: Starting services...")
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        print("📚 Lifecycle test: Indexing project...")
        index_result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Verify indexing worked
        print("🔍 Lifecycle test: Verifying indexed data...")
        query_result = subprocess.run(
            ["cidx", "query", "calculator", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert query_result.returncode == 0, "Query before cleanup should work"

        # Clean data
        print("🗑️ Lifecycle test: Cleaning data...")
        clean_result = subprocess.run(
            ["cidx", "clean-data"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert clean_result.returncode == 0, f"Clean-data failed: {clean_result.stderr}"

        # Verify status after cleanup (services should still be running)
        print("📊 Lifecycle test: Verifying services still running...")
        status_result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "Available" in status_result.stdout or "✅" in status_result.stdout

        # Re-index to verify services work after cleanup
        print("📚 Lifecycle test: Re-indexing after cleanup...")
        reindex_result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            reindex_result.returncode == 0
        ), f"Re-index failed: {reindex_result.stderr}"

        print("✅ Complete lifecycle test completed successfully")


@pytest.mark.skip(
    reason="Complex multi-project test with dual providers - skipped for release stability"
)
def test_multi_project_isolation_and_search():
    """Test multi-project functionality with proper isolation using different providers."""

    # Project 1: Calculator with VoyageAI
    with shared_container_test_environment(
        "test_multi_project_isolation_calc", EmbeddingProvider.VOYAGE_AI
    ) as project1_path:
        create_test_files_calculator(project1_path)

        print("🔧 Multi-project test: Setup Project 1 (Calculator + VoyageAI)...")
        init_result1 = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result1.returncode == 0
        ), f"Project 1 init failed: {init_result1.stderr}"

        start_result1 = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result1.returncode == 0
        ), f"Project 1 start failed: {start_result1.stderr}"

        index_result1 = subprocess.run(
            ["cidx", "index"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result1.returncode == 0
        ), f"Project 1 index failed: {index_result1.stderr}"

        print("🔍 Multi-project test: Testing Project 1 searches...")
        calc_queries = ["add function", "factorial", "calculator"]
        project1_success = 0
        for query in calc_queries:
            result = subprocess.run(
                ["cidx", "query", query, "--quiet"],
                cwd=project1_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and len(result.stdout.strip()) > 0:
                output = result.stdout.lower()
                if any(file in output for file in ["main.py", "utils.py"]):
                    project1_success += 1
                    print(f"✅ Project 1 query '{query}' found calculator files")

        assert project1_success > 0, "Project 1 should find calculator-related content"

    # Project 2: Web Server with Ollama for true isolation
    with shared_container_test_environment(
        "test_multi_project_isolation_web", EmbeddingProvider.OLLAMA
    ) as project2_path:
        create_test_files_webserver(project2_path)

        print("🔧 Multi-project test: Setup Project 2 (Web Server + Ollama)...")
        init_result2 = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "ollama"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result2.returncode == 0
        ), f"Project 2 init failed: {init_result2.stderr}"

        start_result2 = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result2.returncode == 0
        ), f"Project 2 start failed: {start_result2.stderr}"

        index_result2 = subprocess.run(
            ["cidx", "index"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result2.returncode == 0
        ), f"Project 2 index failed: {index_result2.stderr}"

        print("🔍 Multi-project test: Testing Project 2 searches...")
        web_queries = ["web server", "route function", "authentication"]
        project2_success = 0
        for query in web_queries:
            result = subprocess.run(
                ["cidx", "query", query, "--quiet"],
                cwd=project2_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and len(result.stdout.strip()) > 0:
                output = result.stdout.lower()
                if any(file in output for file in ["web_server.py", "auth.py"]):
                    project2_success += 1
                    print(f"✅ Project 2 query '{query}' found web server files")

        assert project2_success > 0, "Project 2 should find web server-related content"

    print("✅ Multi-project isolation test completed successfully")


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_error_conditions_and_recovery():
    """Test error handling and recovery scenarios."""
    with shared_container_test_environment(
        "test_error_conditions_and_recovery", EmbeddingProvider.VOYAGE_AI
    ) as project_path:
        create_test_files_calculator(project_path)

        print("🔧 Error test: Initialize project...")
        init_result = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

        print("🚀 Error test: Start services...")
        start_result = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert start_result.returncode == 0, f"Start failed: {start_result.stderr}"

        # Test 1: Query with non-existent term before indexing
        print("🔍 Error test: Query non-existent term before indexing...")
        query_result = subprocess.run(
            ["cidx", "query", "nonexistent_unique_term_12345", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Should not crash, may return no results or handle gracefully
        assert (
            query_result.returncode == 0
        ), "Query should not crash with non-existent term"

        # Test 2: Status should work before indexing
        print("📊 Error test: Status before indexing...")
        status_result = subprocess.run(
            ["cidx", "status"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "Available" in status_result.stdout or "✅" in status_result.stdout

        # Test 3: Index the project
        print("📚 Error test: Index project...")
        index_result = subprocess.run(
            ["cidx", "index"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert index_result.returncode == 0, f"Index failed: {index_result.stderr}"

        # Test 4: Verify indexing worked
        print("🔍 Error test: Verify indexing with real query...")
        verify_result = subprocess.run(
            ["cidx", "query", "calculator", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert verify_result.returncode == 0, "Query after indexing should work"

        # Test 5: Query with non-existent term after indexing
        print("🔍 Error test: Query non-existent term after indexing...")
        no_result_query = subprocess.run(
            ["cidx", "query", "completely_nonexistent_term_xyz_999", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            no_result_query.returncode == 0
        ), "Query should handle no results gracefully"

        # Test 6: Test query with special characters
        print("🔍 Error test: Query with special characters...")
        special_query = subprocess.run(
            ["cidx", "query", "!@#$%^&*()", "--quiet"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert (
            special_query.returncode == 0
        ), "Query should handle special characters gracefully"

        print("✅ Error conditions and recovery test completed successfully")


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_concurrent_operations_workflow():
    """Test concurrent workflow operations with shared containers."""

    # Concurrent Project 1: Calculator
    with shared_container_test_environment(
        "test_concurrent_operations_calc", EmbeddingProvider.VOYAGE_AI
    ) as project1_path:
        create_test_files_calculator(project1_path)

        print("🔧 Concurrent test: Setup Project 1 (Calculator)...")
        init_result1 = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result1.returncode == 0
        ), f"Project 1 init failed: {init_result1.stderr}"

        start_result1 = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result1.returncode == 0
        ), f"Project 1 start failed: {start_result1.stderr}"

        index_result1 = subprocess.run(
            ["cidx", "index"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result1.returncode == 0
        ), f"Project 1 index failed: {index_result1.stderr}"

        # Test Project 1 searches
        print("🔍 Concurrent test: Testing Project 1 searches...")
        result1 = subprocess.run(
            ["cidx", "query", "calculator", "--quiet"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result1.returncode == 0, "Project 1 query should work"

        # Multiple operations on same project to test concurrency handling
        print("🔄 Concurrent test: Multiple operations on Project 1...")
        status_result1 = subprocess.run(
            ["cidx", "status"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert status_result1.returncode == 0, "Project 1 status should work"

        # Clean data to test cleanup during concurrent operations
        clean_result1 = subprocess.run(
            ["cidx", "clean-data"],
            cwd=project1_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert clean_result1.returncode == 0, "Project 1 clean-data should work"

    # Concurrent Project 2: Web Server (services should be reused)
    with shared_container_test_environment(
        "test_concurrent_operations_web", EmbeddingProvider.VOYAGE_AI
    ) as project2_path:
        create_test_files_webserver(project2_path)

        print("🔧 Concurrent test: Setup Project 2 (Web Server)...")
        init_result2 = subprocess.run(
            ["cidx", "init", "--force", "--embedding-provider", "voyage-ai"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert (
            init_result2.returncode == 0
        ), f"Project 2 init failed: {init_result2.stderr}"

        # Services should already be running from Project 1
        start_result2 = subprocess.run(
            ["cidx", "start", "--quiet"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            start_result2.returncode == 0
        ), f"Project 2 start failed: {start_result2.stderr}"

        index_result2 = subprocess.run(
            ["cidx", "index"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert (
            index_result2.returncode == 0
        ), f"Project 2 index failed: {index_result2.stderr}"

        # Test Project 2 searches
        print("🔍 Concurrent test: Testing Project 2 searches...")
        result2 = subprocess.run(
            ["cidx", "query", "server", "--quiet"],
            cwd=project2_path,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result2.returncode == 0, "Project 2 query should work"

        # Test rapid successive operations
        print("🔄 Concurrent test: Rapid operations on Project 2...")
        for i in range(3):
            rapid_status = subprocess.run(
                ["cidx", "status"],
                cwd=project2_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
            assert rapid_status.returncode == 0, f"Rapid status {i+1} should work"

        print("✅ Concurrent operations test completed successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
