"""
Test to compare search methods using shared containers with complete state cleanup.
"""

import pytest
import os
import subprocess

from .test_infrastructure import (
    SharedContainerManager,
    EmbeddingProvider,
)
from ...conftest import shared_container_test_environment


def test_compare_search_methods():
    """Compare search methods using shared containers with complete state cleanup."""

    # Skip if no VoyageAI key
    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required")

    # Use shared container environment with VoyageAI
    with shared_container_test_environment("test_compare_search_methods", EmbeddingProvider.VOYAGE_AI) as project_path:
        # Seed test files in the shared folder
        
        # Create git repository 
        subprocess.run(["git", "init"], cwd=project_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=project_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=project_path, check=True
        )

        # Create initial file
        main_file = project_path / "main.py"
        main_file.write_text(
            "def hello(): return 'Hello World'\n\ndef greet(name): return f'Hello {name}'"
        )

        subprocess.run(["git", "add", "main.py"], cwd=project_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=project_path, check=True
        )

        # Index the project (containers already running from setup)
        print("Indexing project...")
        result = subprocess.run([
            "code-indexer", "index", "--clear"
        ], cwd=project_path, capture_output=True, text=True, check=True)
        assert "files processed" in result.stdout or "indexed" in result.stdout

        # Get status to verify indexing worked
        status_result = subprocess.run([
            "code-indexer", "status"
        ], cwd=project_path, capture_output=True, text=True, check=True)
        print(f"Status after indexing:\n{status_result.stdout}")

        # Test search functionality through CLI
        print("\n=== Testing search via CLI ===")
        search_result = subprocess.run([
            "code-indexer", "query", "Hello World", "--limit", "5"
        ], cwd=project_path, capture_output=True, text=True, check=True)

        # Verify we got search results
        search_output = search_result.stdout
        print(f"Search results:\n{search_output}")

        # Basic validation - should find our content
        assert search_result.returncode == 0, f"Search failed: {search_result.stderr}"
        assert "main.py" in search_output, "Should find main.py in search results"

        # Test with different search terms
        print("\n=== Testing alternate search ===")
        search_result2 = subprocess.run([
            "code-indexer", "query", "greet function", "--limit", "3"
        ], cwd=project_path, capture_output=True, text=True, check=True)

        search_output2 = search_result2.stdout
        print(f"Alternate search results:\n{search_output2}")

        # Should also find results
        assert (
            search_result2.returncode == 0
        ), f"Second search failed: {search_result2.stderr}"

        print("\n✅ Search functionality working correctly through CLI!")
        
        # Note: Cleanup happens automatically in the context manager


if __name__ == "__main__":
    test_compare_search_methods()