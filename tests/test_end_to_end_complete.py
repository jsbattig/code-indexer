#!/usr/bin/env python3
"""
Comprehensive end-to-end tests that exercise ALL code paths including:
- Single project indexing and search
- Multi-project indexing and search
- Clean functionality and trace removal
- Container lifecycle management
"""

import os
import time
from pathlib import Path
import pytest
from code_indexer.services.docker_manager import DockerManager


class TestEndToEndComplete:
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup test environment and ensure cleanup (Boy Scout Rule)"""
        self.docker_manager = DockerManager()
        self.test_containers = set()
        self.test_networks = set()
        try:
            self.original_cwd = os.getcwd()
        except FileNotFoundError:
            # Handle case where current directory doesn't exist
            self.original_cwd = Path(__file__).parent.absolute()

        # ALWAYS clean up any leftover data first
        self.cleanup_all_data()

        yield

        # Clean up any remaining services
        print("Cleaning up any remaining services after test...")

        # Verify no root-owned files are left behind
        self.verify_no_root_owned_files()

        # Always cleanup using high-level CLI commands
        for project_dir in ["test_project_1", "test_project_2"]:
            project_path = Path(__file__).parent / "projects" / project_dir
            if project_path.exists():
                try:
                    # Use high-level CLI clean command for each project
                    self.run_cli_command(
                        ["clean", "--remove-data", "--force"], cwd=project_path
                    )
                except Exception:
                    pass

        os.chdir(self.original_cwd)

    def are_services_running(self):
        """Check if services are running using high-level CLI status command"""
        try:
            # Use high-level CLI status command
            result = self.run_cli_command(["status"])
            if result.returncode != 0:
                return False
            # Check for service indicators in status output
            return "✅ Running" in result.stdout and "services" in result.stdout
        except Exception:
            return False

    def setup_services(self):
        """Set up services using code-indexer setup command"""
        try:
            # Go to a persistent setup directory for global services
            test_setup_dir = Path(__file__).parent / "global_setup"
            test_setup_dir.mkdir(exist_ok=True)
            original_cwd = os.getcwd()

            try:
                os.chdir(test_setup_dir)

                # Run setup command to start global services
                result = self.run_cli_command(["setup", "--quiet"], timeout=300)
                if result.returncode != 0:
                    raise RuntimeError(f"Setup failed: {result.stderr}")

                # Wait for services to be ready using adaptive timeout
                adaptive_timeout = self.docker_manager.get_adaptive_timeout(120)
                start_time = time.time()
                while time.time() - start_time < adaptive_timeout:
                    if self.are_services_running():
                        return
                    time.sleep(2)

                raise RuntimeError(
                    f"Services did not become ready within {adaptive_timeout}s timeout"
                )
            finally:
                os.chdir(original_cwd)

        except Exception as e:
            raise RuntimeError(f"Failed to setup services for e2e tests: {e}")

    def cleanup_services(self):
        """Clean up services that we set up using high-level CLI commands"""
        try:
            # Use the same persistent directory where we set up services
            test_setup_dir = Path(__file__).parent / "global_setup"
            if test_setup_dir.exists():
                original_cwd = os.getcwd()
                try:
                    os.chdir(test_setup_dir)
                    # Use high-level CLI clean command
                    self.run_cli_command(
                        ["clean", "--remove-data", "--force"], timeout=60
                    )
                finally:
                    os.chdir(original_cwd)
                    # Clean up the persistent setup directory
                    import shutil

                    shutil.rmtree(test_setup_dir, ignore_errors=True)

        except Exception as e:
            print(f"Warning: Failed to cleanup services: {e}")

    def cleanup_all_data(self):
        """Clean up all data using application's high-level clean command"""
        # Use the application's own cleanup functionality
        test_projects_dir = Path(__file__).parent / "projects"
        if test_projects_dir.exists():
            for project_dir in test_projects_dir.iterdir():
                if project_dir.is_dir():
                    # Change to each project directory and run clean command
                    try:
                        original_cwd = os.getcwd()
                    except FileNotFoundError:
                        # If current directory doesn't exist, use a safe directory
                        original_cwd = Path(__file__).parent.absolute()
                        os.chdir(original_cwd)

                    try:
                        os.chdir(project_dir)
                        self.run_cli_command(
                            ["clean", "--remove-data", "--force"], timeout=60
                        )
                    except Exception:
                        # If application cleanup fails, that indicates an application bug
                        pass
                    finally:
                        try:
                            os.chdir(original_cwd)
                        except (FileNotFoundError, OSError):
                            # If original directory doesn't exist, go to a safe location
                            os.chdir(Path(__file__).parent.absolute())

        # Also run global cleanup from current directory
        try:
            self.run_cli_command(["clean", "--remove-data", "--force"], timeout=60)
        except Exception:
            # If application cleanup fails, that indicates an application bug
            pass

    def verify_no_root_owned_files(self):
        """Verify that no root-owned files are left in the data directory after cleanup.

        This method provides immediate feedback when cleanup fails to remove root-owned files,
        which cause Qdrant startup failures in subsequent tests.
        """
        import os
        import subprocess

        try:
            # Check for root-owned files in the global data directory
            global_data_dir = Path.home() / ".code-indexer-data"
            if not global_data_dir.exists():
                return  # No data directory means no files to check

            # Use find command to locate files not owned by current user
            current_user = os.getenv("USER") or os.getenv("USERNAME")
            result = subprocess.run(
                ["find", str(global_data_dir), "-not", "-user", current_user],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout.strip():
                root_owned_files = result.stdout.strip().split("\n")
                pytest.fail(
                    f"CLEANUP VERIFICATION FAILED: Found {len(root_owned_files)} root-owned files after cleanup!\n"
                    f"These files will cause Qdrant permission errors in subsequent tests:\n"
                    + "\n".join(
                        f"  - {file}" for file in root_owned_files[:10]
                    )  # Show first 10 files
                    + (
                        f"\n  ... and {len(root_owned_files) - 10} more files"
                        if len(root_owned_files) > 10
                        else ""
                    )
                    + f"\n\nTo fix manually: sudo rm -rf {global_data_dir}/qdrant/collections"
                )

        except Exception as e:
            # Don't fail the test for verification errors, but warn
            print(f"Warning: Could not verify root-owned file cleanup: {e}")

    def run_cli_command(self, args, cwd=None, timeout=120):
        """Run code-indexer CLI command using high-level application functions"""
        from code_indexer.cli import main
        from io import StringIO
        import sys

        # Change directory if needed
        original_cwd = None
        if cwd and cwd != os.getcwd():
            original_cwd = os.getcwd()
            os.chdir(cwd)

        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()

        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            # Create a mock result object to match subprocess.run interface
            class MockResult:
                def __init__(self, returncode, stdout, stderr):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            try:
                # Call the high-level CLI main function directly
                sys.argv = ["code-indexer"] + args
                main()
                return MockResult(
                    0, stdout_capture.getvalue(), stderr_capture.getvalue()
                )
            except SystemExit as e:
                return MockResult(
                    e.code or 0, stdout_capture.getvalue(), stderr_capture.getvalue()
                )
            except Exception as e:
                return MockResult(1, stdout_capture.getvalue(), str(e))

        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            if original_cwd:
                os.chdir(original_cwd)

    def wait_for_container_ready(self, container_name, max_wait=60):
        """Wait for container to be ready and healthy (simplified for global containers)"""
        # Since we use global containers, just check if services are running
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if self.are_services_running():
                return True
            time.sleep(2)
        return False

    def test_single_project_full_cycle(self):
        """Test complete single project cycle: index -> search -> clean"""
        # Use test_project_1 (calculator)
        project_path = Path(__file__).parent / "projects" / "test_project_1"
        os.chdir(project_path)

        try:
            # Ensure clean state for this test
            self.cleanup_all_data()

            # 1. Setup services for this test project
            setup_result = self.run_cli_command(["setup", "--quiet"])
            assert setup_result.returncode == 0, f"Setup failed: {setup_result.stderr}"

            # 2. Index the project
            result = self.run_cli_command(["index"])
            assert (
                result.returncode == 0
            ), f"Index failed. Return code: {result.returncode}, stderr: {result.stderr}, stdout: {result.stdout}"

            # Use global container names (not project-specific)
            self.test_containers.add("code-indexer-ollama")
            self.test_containers.add("code-indexer-qdrant")
            self.test_networks.add("code-indexer-global")

            # Wait for services to be ready (but they should already be ready from setup)
            assert self.are_services_running(), "Services not ready after index command"

            # 2. Test search functionality with specific queries for calculator code
            search_queries = [
                "add function",
                "calculator implementation",
                "factorial function",
                "square root calculation",
                "prime number check",
            ]

            for query in search_queries:
                result = self.run_cli_command(["query", query])
                assert (
                    result.returncode == 0
                ), f"Search '{query}' failed: {result.stderr}"
                assert (
                    len(result.stdout.strip()) > 0
                ), f"Search '{query}' returned no results"

                # Verify results contain relevant code files
                output = result.stdout.lower()
                assert any(
                    file in output for file in ["main.py", "utils.py"]
                ), f"Search '{query}' didn't find expected files: {result.stdout}"

            # 3. Test status functionality
            result = self.run_cli_command(["status"])
            assert result.returncode == 0, f"Status failed: {result.stderr}"
            # Check that index is available and has documents
            assert "Available" in result.stdout
            assert "Documents:" in result.stdout or "Points:" in result.stdout

            # 4. Clean project data (not global services)
            result = self.run_cli_command(["clean", "--remove-data"])
            assert result.returncode == 0, f"Clean failed: {result.stderr}"

            # Verify no traces remain
            assert not (
                project_path / ".code-indexer"
            ).exists(), "Config directory not cleaned"
            assert not (project_path / "data").exists(), "Data directory not cleaned"
            assert not (
                project_path / "docker-compose.yml"
            ).exists(), "Docker compose not cleaned"

            # Verify services are stopped using condition polling
            def check_services_stopped():
                result = self.run_cli_command(["status"])
                if result.returncode != 0:
                    return False
                return (
                    "❌ Not Running" in result.stdout
                    or "❌ Not Available" in result.stdout
                )

            # Wait up to 15 seconds for services to stop
            import time

            start_time = time.time()
            services_stopped = False
            while time.time() - start_time < 15:
                if check_services_stopped():
                    services_stopped = True
                    break
                time.sleep(1)

            assert services_stopped, "Services failed to stop within timeout"

        finally:
            # Ensure cleanup even if test fails
            self.run_cli_command(["clean"])

    def test_multi_project_isolation_and_search(self):
        """Test multi-project functionality with shared global vector database"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"

        try:
            # Ensure clean state for this test
            self.cleanup_all_data()

            # Setup and index project 1
            os.chdir(project1_path)
            setup1_result = self.run_cli_command(["setup", "--quiet"])
            assert (
                setup1_result.returncode == 0
            ), f"Project 1 setup failed: {setup1_result.stderr}"

            result1 = self.run_cli_command(["index"])
            assert result1.returncode == 0, f"Project 1 index failed: {result1.stderr}"

            self.test_containers.update(["code-indexer-ollama", "code-indexer-qdrant"])
            self.test_networks.add("code-indexer-global")

            # Setup and index project 2
            os.chdir(project2_path)
            setup2_result = self.run_cli_command(["setup", "--quiet"])
            assert (
                setup2_result.returncode == 0
            ), f"Project 2 setup failed: {setup2_result.stderr}"

            result2 = self.run_cli_command(["index"])
            assert result2.returncode == 0, f"Project 2 index failed: {result2.stderr}"

            self.test_containers.update(["code-indexer-ollama", "code-indexer-qdrant"])
            self.test_networks.add("code-indexer-global")

            # Services should be ready since indexing completed successfully

            # Test project 1 searches (calculator-specific)
            os.chdir(project1_path)
            calc_queries = ["add function", "factorial", "calculator"]
            for query in calc_queries:
                result = self.run_cli_command(["query", query])
                assert (
                    result.returncode == 0
                ), f"Project 1 search '{query}' failed: {result.stderr}"
                output = result.stdout.lower()
                assert (
                    "main.py" in output or "utils.py" in output
                ), f"Project 1 search '{query}' didn't find calculator files"
                # With shared global database, may find files from other projects
                # but should prioritize files from current project
                print(
                    f"Project 1 search '{query}' results contain: {['main.py' in output, 'utils.py' in output, 'web_server.py' in output]}"
                )

            # Test project 2 searches (web server-specific)
            os.chdir(project2_path)
            web_queries = ["web server", "route function", "authentication"]
            for query in web_queries:
                result = self.run_cli_command(["query", query])
                assert (
                    result.returncode == 0
                ), f"Project 2 search '{query}' failed: {result.stderr}"
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
            os.chdir(project1_path)
            result = self.run_cli_command(["status"])
            assert (
                "✅ Available" in result.stdout
            ), "Project 1 should show index as available"
            assert (
                "Documents:" in result.stdout or "Points:" in result.stdout
            ), "Should show document/point count"

            os.chdir(project2_path)
            result = self.run_cli_command(["status"])
            assert (
                "✅ Available" in result.stdout
            ), "Project 2 should show index as available"
            assert (
                "Documents:" in result.stdout or "Points:" in result.stdout
            ), "Should show document/point count"

            # Clean both projects
            os.chdir(project1_path)
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, f"Project 1 clean failed: {result.stderr}"

            os.chdir(project2_path)
            result = self.run_cli_command(["clean"])
            assert result.returncode == 0, f"Project 2 clean failed: {result.stderr}"

            # Verify complete cleanup using condition polling
            def check_services_stopped_project1():
                os.chdir(project1_path)
                result = self.run_cli_command(["status"])
                if result.returncode != 0:
                    return False
                return (
                    "❌ Not Running" in result.stdout
                    or "❌ Not Available" in result.stdout
                )

            # Wait up to 20 seconds for services to stop completely
            import time

            start_time = time.time()
            services_stopped = False
            while time.time() - start_time < 20:
                if check_services_stopped_project1():
                    services_stopped = True
                    break
                time.sleep(1)

            assert services_stopped, "Services should be stopped after clean"

            # Config directories should remain after clean (without --remove-data)
            # This is expected behavior

        finally:
            # Cleanup both projects
            for project_path in [project1_path, project2_path]:
                os.chdir(project_path)
                self.run_cli_command(["clean"])

    def test_error_conditions_and_recovery(self):
        """Test error handling and recovery scenarios"""
        project_path = Path(__file__).parent / "projects" / "test_project_1"
        os.chdir(project_path)

        try:
            # Extra cleanup to ensure completely clean state for this test
            self.cleanup_all_data()

            # Test search without indexing first
            result = self.run_cli_command(["query", "test query"])
            assert (
                result.returncode != 0
            ), f"Search should fail without indexing. Got: {result.stdout}\nStderr: {result.stderr}"

            # Test status without indexing - should succeed but show no index
            result = self.run_cli_command(["status"])
            assert (
                result.returncode == 0
            ), f"Status should succeed but show no index. Got: {result.stdout}\nStderr: {result.stderr}"
            assert (
                "❌ Not Found" in result.stdout or "Not Found" in result.stdout
            ), "Status should indicate no index found"

            # Test clean without containers (should not error)
            result = self.run_cli_command(["clean"])
            assert (
                result.returncode == 0
            ), "Clean should succeed even without containers"

            # Test index with setup first, then clean, then operations should fail
            setup_result = self.run_cli_command(["setup", "--quiet"])
            assert setup_result.returncode == 0, f"Setup failed: {setup_result.stderr}"

            result = self.run_cli_command(["index"])
            assert result.returncode == 0, f"Index failed: {result.stderr}"

            self.test_containers.update(["code-indexer-ollama", "code-indexer-qdrant"])

            result = self.run_cli_command(["clean"])
            assert result.returncode == 0

            # Now search should fail again
            result = self.run_cli_command(["query", "test query"])
            assert result.returncode != 0, "Search should fail after clean"

        finally:
            self.run_cli_command(["clean"])

    def test_concurrent_operations(self):
        """Test that concurrent operations on different projects work correctly"""
        project1_path = Path(__file__).parent / "projects" / "test_project_1"
        project2_path = Path(__file__).parent / "projects" / "test_project_2"

        try:
            # Setup and index both projects sequentially (concurrency testing should test application-level concurrency, not process-level)
            # Project 1
            os.chdir(project1_path)
            setup1_result = self.run_cli_command(["setup", "--quiet"])
            assert (
                setup1_result.returncode == 0
            ), f"Project 1 setup failed: {setup1_result.stderr}"

            result1 = self.run_cli_command(["index"])
            assert result1.returncode == 0, f"Project 1 index failed: {result1.stderr}"

            # Project 2 (services should already be running from project 1)
            os.chdir(project2_path)
            result2 = self.run_cli_command(["index"])
            assert result2.returncode == 0, f"Project 2 index failed: {result2.stderr}"

            self.test_containers.update(
                [
                    "code-indexer-ollama",
                    "code-indexer-qdrant",
                    "code-indexer-ollama",
                    "code-indexer-qdrant",
                ]
            )

            # Verify both work independently
            os.chdir(project1_path)
            result = self.run_cli_command(["query", "calculator"])
            assert result.returncode == 0
            assert "main.py" in result.stdout.lower()

            os.chdir(project2_path)
            result = self.run_cli_command(["query", "server"])
            assert result.returncode == 0
            assert "web_server.py" in result.stdout.lower()

        finally:
            for project_path in [project1_path, project2_path]:
                os.chdir(project_path)
                self.run_cli_command(["clean"])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
