"""
Test to compare search_with_branch_topology and search_with_branch_context methods.
"""

import pytest
import os
import subprocess

from .test_infrastructure import (
    CLIHelper,
    TestProjectInventory,
    create_test_project_with_inventory,
    adaptive_service_setup,
    InfrastructureConfig,
    EmbeddingProvider,
)


def test_compare_search_methods():
    """Compare search_with_branch_topology and search_with_branch_context methods."""

    # Skip if no VoyageAI key
    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required")

    config = InfrastructureConfig(embedding_provider=EmbeddingProvider.VOYAGE_AI)
    helper = CLIHelper(config)

    # Use isolated project directory using inventory system
    from .conftest import local_temporary_directory

    with local_temporary_directory() as temp_dir:
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.COMPARE_SEARCH_METHODS
        )
        project_path = temp_dir

        # Create git repository manually since DirectoryManager is static
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

        # Project collections are automatically registered by inventory system

        # Initialize and start services using CLI
        print("Setting up services...")

        # Make sure init completes successfully - configure for VoyageAI to match test requirements
        init_result = helper.run_cli_command(
            ["init", "--force", "--embedding-provider", "voyage-ai"], cwd=project_path
        )
        print(f"Init result:\n{init_result.stdout}")
        if init_result.stderr:
            print(f"Init stderr:\n{init_result.stderr}")

        # Check if services are already running before trying to start
        if not adaptive_service_setup(project_path, helper):
            print("❌ Failed to set up services")
            return

        # Index the project
        print("Indexing project...")
        result = helper.run_cli_command(["index", "--clear"], cwd=project_path)
        assert "files processed" in result.stdout or "indexed" in result.stdout

        # Get status to verify indexing worked
        status_result = helper.run_cli_command(["status"], cwd=project_path)
        print(f"Status after indexing:\n{status_result.stdout}")

        # Test search functionality through CLI
        print("\n=== Testing search via CLI ===")
        search_result = helper.run_cli_command(
            ["query", "Hello World", "--limit", "5"], cwd=project_path
        )

        # Verify we got search results
        search_output = search_result.stdout
        print(f"Search results:\n{search_output}")

        # Basic validation - should find our content
        assert search_result.returncode == 0, f"Search failed: {search_result.stderr}"
        assert "main.py" in search_output, "Should find main.py in search results"

        # Test with different search terms
        print("\n=== Testing alternate search ===")
        search_result2 = helper.run_cli_command(
            ["query", "greet function", "--limit", "3"], cwd=project_path
        )

        search_output2 = search_result2.stdout
        print(f"Alternate search results:\n{search_output2}")

        # Should also find results
        assert (
            search_result2.returncode == 0
        ), f"Second search failed: {search_result2.stderr}"

        print("\n✅ Search functionality working correctly through CLI!")


if __name__ == "__main__":
    test_compare_search_methods()
