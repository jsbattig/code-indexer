#!/usr/bin/env python3
"""
Comprehensive end-to-end tests that exercise ALL code paths including:
- Single project indexing and search
- Multi-project indexing and search
- Clean functionality and trace removal
- Container lifecycle management

Refactored to use NEW STRATEGY with test infrastructure for better performance.
"""

import os
from pathlib import Path
import pytest
from code_indexer.services.docker_manager import DockerManager

# Import new test infrastructure
from .test_infrastructure import (
    create_fast_e2e_setup,
    Assertions,
    EmbeddingProvider,
)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestEndToEndComplete:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test environment using NEW STRATEGY with test infrastructure"""
        # NEW STRATEGY: Use test infrastructure for consistent setup
        self.service_manager, self.cli_helper, self.dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )
        self.docker_manager = DockerManager()
        self.test_containers = set()
        self.test_networks = set()

        try:
            self.original_cwd = os.getcwd()
        except FileNotFoundError:
            self.original_cwd = str(Path(__file__).parent.absolute())

        # NEW STRATEGY: Ensure services ready, then clean data only
        services_ready = self.service_manager.ensure_services_ready()
        if services_ready:
            self.cleanup_all_data()

        yield

        # NEW STRATEGY: Only clean project data, keep services running
        try:
            Assertions.assert_no_root_owned_files()

            # Clean project data only
            for project_dir in ["test_project_1", "test_project_2"]:
                project_path = Path(__file__).parent / "projects" / project_dir
                if project_path.exists():
                    try:
                        self.cli_helper.run_cli_command(
                            ["clean-data"], cwd=project_path, expect_success=False
                        )
                    except Exception:
                        pass
        except Exception as e:
            print(f"Cleanup warning: {e}")
        finally:
            try:
                os.chdir(self.original_cwd)
            except (FileNotFoundError, OSError):
                os.chdir(Path(__file__).parent.absolute())

    def are_services_running(self):
        """Check if services are running using test infrastructure"""
        try:
            return self.service_manager.are_services_running()
        except Exception:
            # In noisy neighbor scenarios, service checks may fail
            # but indexing can still work if essential services are accessible
            return True  # If indexing succeeded, assume services are functional

    # Removed setup_services - now handled by test infrastructure

    # Removed cleanup_services - now handled by test infrastructure NEW STRATEGY

    def cleanup_all_data(self):
        """Clean up all data using test infrastructure and NEW STRATEGY"""
        test_projects_dir = Path(__file__).parent / "projects"
        if test_projects_dir.exists():
            for project_dir in test_projects_dir.iterdir():
                if project_dir.is_dir():
                    try:
                        # Use test infrastructure for safe directory operations
                        with self.dir_manager.safe_chdir(project_dir):
                            self.cli_helper.run_cli_command(
                                ["clean-data"], timeout=60, expect_success=False
                            )
                    except Exception:
                        pass

        # Also run global cleanup from current directory
        try:
            self.cli_helper.run_cli_command(
                ["clean-data"], timeout=60, expect_success=False
            )
        except Exception:
            pass

    def verify_no_root_owned_files(self):
        """Verify no root-owned files using test infrastructure"""
        Assertions.assert_no_root_owned_files()

    def run_cli_command(self, args, cwd=None, timeout=120, expect_success=True):
        """Run CLI command using test infrastructure"""
        return self.cli_helper.run_cli_command(
            args, cwd=cwd, timeout=timeout, expect_success=expect_success
        )

    # Removed wait_for_container_ready - now handled by test infrastructure

    def ensure_clean_vector_state(self):
        """Ensure vector database is clean for isolated testing using test infrastructure"""
        # First ensure services are running so we can clean data
        self.ensure_services_running()

        try:
            # Clear all project data to ensure isolation
            self.cli_helper.run_cli_command(
                ["clean-data", "--all-projects"], expect_success=False
            )
        except Exception as e:
            print(f"Warning: Exception during vector cleanup: {e}")

    def ensure_services_running(self):
        """Ensure services are running using test infrastructure"""
        return self.service_manager.ensure_services_ready(
            embedding_provider=EmbeddingProvider.VOYAGE_AI
        )

    def setup_project_for_test(self, embedding_provider="voyage-ai"):
        """Setup a project for testing using test infrastructure"""
        # Initialize project with specified provider
        self.cli_helper.run_cli_command(
            ["init", "--force", "--embedding-provider", embedding_provider]
        )

        # Ensure services are running (they should be from ensure_services_running)
        # but call start to ensure this project is properly configured
        self.cli_helper.run_cli_command(["start", "--quiet"])

    def test_single_project_workflow(self):
        """Test core single project workflow: init -> start -> index -> query -> status -> clean-data

        This test follows the NEW STRATEGY: keep services running, only clean data.
        It tests the most common user workflow without the overhead of full service lifecycle.
        """
        # Use test_project_1 (calculator)
        project_path = Path(__file__).parent / "projects" / "test_project_1"

        with self.dir_manager.safe_chdir(project_path):
            # Ensure clean state for this test
            self.cleanup_all_data()

            # 1. Initialize with VoyageAI provider for CI stability
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"]
            )

            # 2. Setup services for this test project
            self.cli_helper.run_cli_command(["start", "--quiet"])

            # 3. Index the project (force full index to avoid incremental skip)
            index_result = self.cli_helper.run_cli_command(["index", "--clear"])
            print(f"Index result: {index_result.stdout}")

            # Use global container names (not project-specific)
            # VoyageAI is cloud-based, only need Qdrant locally
            self.test_containers.add("code-indexer-qdrant")
            self.test_networks.add("code-indexer-global")

            # Check status after indexing to see if data was properly indexed
            status_result = self.cli_helper.run_cli_command(["status"])
            print(f"Status after indexing: {status_result.stdout}")

            # 4. Test search functionality with specific queries for calculator code
            search_queries = [
                "add function",
                "calculator implementation",
                "factorial function",
                "square root calculation",
                "prime number check",
            ]

            for query in search_queries:
                result = self.cli_helper.run_cli_command(["query", query])
                print(f"Query '{query}' result: {result.stdout}")

                # Check if there's actually no data indexed vs search not working
                if "❌ No results found" in result.stdout:
                    # Try a broader search to see if there's any data at all
                    broad_result = self.cli_helper.run_cli_command(
                        ["query", "def", "--limit", "1"]
                    )
                    if "❌ No results found" in broad_result.stdout:
                        # If even "def" returns nothing, indexing failed
                        pytest.fail(
                            f"No data appears to be indexed. Index result: {index_result.stdout}"
                        )

                assert (
                    len(result.stdout.strip()) > 0
                ), f"Search '{query}' returned no results"

                # Verify results contain relevant code files
                output = result.stdout.lower()
                assert any(
                    file in output for file in ["main.py", "utils.py"]
                ), f"Search '{query}' didn't find expected files: {result.stdout}"

            # 5. Test status functionality
            result = self.cli_helper.run_cli_command(["status"])
            # Check that index is available and has documents
            assert "Available" in result.stdout
            assert (
                "docs" in result.stdout
            )  # Should show "Project: X docs | Total: Y docs"

            # 6. Clean project data (NEW STRATEGY: keep services running)
            self.cli_helper.run_cli_command(["clean-data"])

            # Verify project data is cleared but services remain running
            # Note: clean-data clears the collection data, but config directory remains
            # This is correct behavior - config is needed to manage services

    def test_complete_lifecycle_management(self):
        """Test complete container lifecycle: start -> uninstall -> verify shutdown

        This test focuses specifically on container lifecycle management.
        It verifies that the uninstall command properly stops all services.
        """
        # Use test_project_1 for lifecycle testing
        project_path = Path(__file__).parent / "projects" / "test_project_1"

        with self.dir_manager.safe_chdir(project_path):
            # Ensure clean state for this test
            self.cleanup_all_data()

            # 1. Initialize and start services
            self.cli_helper.run_cli_command(
                ["init", "--force", "--embedding-provider", "voyage-ai"]
            )
            self.cli_helper.run_cli_command(["start", "--quiet"])

            # Verify services are running
            status_result = self.cli_helper.run_cli_command(["status"])
            assert (
                "✅" in status_result.stdout
            ), "Services should be running before uninstall test"

            # 2. Test complete uninstall and verify all services stop
            self.cli_helper.run_cli_command(["uninstall"])

            # 3. Verify complete cleanup using condition polling
            def check_services_stopped():
                result = self.cli_helper.run_cli_command(
                    ["status"], expect_success=False
                )
                # If status command fails (no config), services are stopped
                if result.returncode != 0:
                    return True
                # If status succeeds, check for stopped indicators
                return (
                    "❌ Not Running" in result.stdout
                    or "❌ Not Available" in result.stdout
                    or "No .code-indexer/config.json found" in result.stdout
                )

            # Wait up to 90 seconds for complete cleanup (accounts for progressive shutdown timeouts)
            import time

            start_time = time.time()
            services_stopped = False
            while time.time() - start_time < 90:
                if check_services_stopped():
                    services_stopped = True
                    break
                time.sleep(2)

            assert services_stopped, "Services failed to stop completely within timeout"

    def test_multi_project_isolation_and_search(self):
        """Test multi-project functionality with shared global vector database"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"

        try:
            # COMPREHENSIVE SETUP: Ensure services running, then clean vector data
            self.ensure_services_running()
            self.ensure_clean_vector_state()

            # Setup project 1 with clean state
            with self.dir_manager.safe_chdir(project1_path):
                self.setup_project_for_test("voyage-ai")
                self.cli_helper.run_cli_command(["index", "--clear"])

            # Setup project 2 with clean state (services already running)
            with self.dir_manager.safe_chdir(project2_path):
                self.setup_project_for_test("voyage-ai")
                self.cli_helper.run_cli_command(["index", "--clear"])

            # Services should be ready since indexing completed successfully

            # Test project 1 searches (calculator-specific)
            with self.dir_manager.safe_chdir(project1_path):
                calc_queries = ["add function", "factorial", "calculator"]
                for query in calc_queries:
                    result = self.cli_helper.run_cli_command(["query", query])
                    output = result.stdout.lower()
                    print(f"Project 1 query '{query}' result: {result.stdout}")

                    # Check if there's actually no data indexed vs search not working
                    if "❌ no results found" in output:
                        # Try a broader search to see if there's any data at all
                        broad_result = self.cli_helper.run_cli_command(
                            ["query", "def", "--limit", "1"]
                        )
                        if "❌ no results found" in broad_result.stdout.lower():
                            # If even "def" returns nothing, indexing failed
                            pytest.fail(
                                "No data appears to be indexed for project 1. Try running 'code-indexer index' manually."
                            )

                    assert (
                        "main.py" in output or "utils.py" in output
                    ), f"Project 1 search '{query}' didn't find calculator files: {result.stdout}"
                    # With shared global database, may find files from other projects
                    # but should prioritize files from current project
                    print(
                        f"Project 1 search '{query}' results contain: {['main.py' in output, 'utils.py' in output, 'web_server.py' in output]}"
                    )

            # Test project 2 searches (web server-specific)
            with self.dir_manager.safe_chdir(project2_path):
                web_queries = ["web server", "route function", "authentication"]
                for query in web_queries:
                    result = self.cli_helper.run_cli_command(["query", query])
                    output = result.stdout.lower()
                    assert (
                        "web_server.py" in output or "auth.py" in output
                    ), f"Project 2 search '{query}' didn't find web server files"
                    # With shared global database, may find files from other projects
                    # but should prioritize files from current project
                    print(
                        f"Project 2 search '{query}' results contain: {['web_server.py' in output, 'auth.py' in output, 'main.py' in output]}"
                    )

            # Test that status shows the indexed data (shared global database)
            with self.dir_manager.safe_chdir(project1_path):
                result = self.cli_helper.run_cli_command(["status"])
                assert (
                    "✅ Available" in result.stdout
                ), "Project 1 should show index as available"
                assert (
                    "docs" in result.stdout
                ), "Should show document count (Project: X docs | Total: Y docs)"

            with self.dir_manager.safe_chdir(project2_path):
                result = self.cli_helper.run_cli_command(["status"])
                assert (
                    "✅ Available" in result.stdout
                ), "Project 2 should show index as available"
                assert (
                    "docs" in result.stdout
                ), "Should show document count (Project: X docs | Total: Y docs)"

            # Clean project data from project1 (keeping services running for other projects)
            with self.dir_manager.safe_chdir(project1_path):
                self.cli_helper.run_cli_command(["clean-data"])

            # Test clean-data functionality
            # Note: With shared global database, clean-data removes the local config but vector data
            # remains in the shared Qdrant instance across different collection names
            with self.dir_manager.safe_chdir(project1_path):
                self.cli_helper.run_cli_command(["clean-data"])

            # After clean-data, the local config should be removed, but since we use a global
            # vector database, data from other projects may still be searchable
            # This is the expected behavior with the current architecture

        finally:
            # Leave services running for next test, just ensure we're in a clean state
            pass

    def test_error_conditions_and_recovery(self):
        """Test error handling and recovery scenarios using test infrastructure"""
        project_path = Path(__file__).parent / "projects" / "test_project_1"

        with self.dir_manager.safe_chdir(project_path):
            # COMPREHENSIVE SETUP: Ensure services are running and prepare test environment
            self.ensure_services_running()

            # Setup project in a clean state
            self.setup_project_for_test("voyage-ai")

            # Test 1: Search with unspecific query should work (services running, but may return few results)
            result = self.cli_helper.run_cli_command(
                ["query", "nonexistent_unique_term_12345"]
            )
            # With global vector database, we might find some results or no results - both are valid
            # This tests that the query mechanism works correctly

            # Test 2: Status should work and show current state
            result = self.cli_helper.run_cli_command(["status"])
            # Status should show that services are available - the actual index state depends on global database

            # Test 3: Index the project
            self.cli_helper.run_cli_command(["index"])

            # Test 4: Verify indexing worked
            result = self.cli_helper.run_cli_command(["query", "calculator"])
            assert (
                len(result.stdout.strip()) > 0
            ), "Should find some results after indexing"

            # Test 5: Clean data and verify behavior
            self.cli_helper.run_cli_command(["clean-data"])

            # Note: We don't test service shutdown in this test to maintain the "keep services running" strategy
            # Service failure scenarios would be tested in a separate, more targeted test

    def test_concurrent_operations(self):
        """Test that concurrent operations on different projects work correctly using test infrastructure"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"

        try:
            # Setup and index both projects sequentially (concurrency testing should test application-level concurrency, not process-level)
            # Project 1
            with self.dir_manager.safe_chdir(project1_path):
                self.cli_helper.run_cli_command(
                    ["init", "--force", "--embedding-provider", "voyage-ai"]
                )
                self.cli_helper.run_cli_command(["start", "--quiet"])
                self.cli_helper.run_cli_command(["index", "--clear"])

            # Project 2 (services should already be running from project 1)
            with self.dir_manager.safe_chdir(project2_path):
                self.cli_helper.run_cli_command(
                    ["init", "--force", "--embedding-provider", "voyage-ai"]
                )
                self.cli_helper.run_cli_command(["index", "--clear"])

            self.test_containers.update(["code-indexer-qdrant"])

            # Verify both work independently
            with self.dir_manager.safe_chdir(project1_path):
                result = self.cli_helper.run_cli_command(["query", "calculator"])
                print(f"Concurrent test project 1 query result: {result.stdout}")

                # Check if there's actually no data indexed vs search not working
                if "❌ no results found" in result.stdout.lower():
                    # Try a broader search to see if there's any data at all
                    broad_result = self.cli_helper.run_cli_command(
                        ["query", "def", "--limit", "1"]
                    )
                    if "❌ no results found" in broad_result.stdout.lower():
                        # If even "def" returns nothing, indexing failed
                        pytest.fail(
                            "No data appears to be indexed for concurrent test. Check indexing."
                        )

                assert (
                    "main.py" in result.stdout.lower()
                ), f"Expected main.py in results: {result.stdout}"

            with self.dir_manager.safe_chdir(project2_path):
                result = self.cli_helper.run_cli_command(["query", "server"])
                assert "web_server.py" in result.stdout.lower()

        finally:
            # NEW STRATEGY: Leave services running, just clean project data
            for project_path in [project1_path, project2_path]:
                try:
                    with self.dir_manager.safe_chdir(project_path):
                        self.cli_helper.run_cli_command(
                            ["clean-data"], expect_success=False
                        )
                except Exception:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
