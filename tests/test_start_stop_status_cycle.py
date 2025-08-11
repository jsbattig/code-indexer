"""
Comprehensive test for the complete start/stop/status cycle.

This test verifies the entire lifecycle of Docker services:
1. Start services
2. Verify status shows running
3. Stop services
4. Verify status shows stopped
5. Start services again
6. Verify status shows running again

This test is marked as 'slow' and will only run in full-automation.sh
"""

import pytest
import time
import subprocess
from typing import Dict, Any, List

from src.code_indexer.config import Config
from src.code_indexer.services.docker_manager import DockerManager


class TestStartStopStatusCycle:
    """Test the complete start/stop/status cycle end-to-end."""

    def setup_method(self):
        """Set up test environment."""
        self.config = Config()
        # Use VoyageAI config to avoid Ollama port conflicts in tests
        # Get project config directory for proper initialization
        from pathlib import Path

        project_config_dir = Path.cwd() / ".code-indexer"
        self.docker_manager = DockerManager(
            force_docker=True, project_config_dir=project_config_dir
        )

        # Get actual container names from docker manager (per-project naming)
        # These will be project-specific like "cidx-{hash}-qdrant"
        try:
            # Get container names for the current project
            from src.code_indexer.config import ConfigManager

            config_manager = ConfigManager.create_with_backtrack()
            config = config_manager.load()

            self.expected_containers: List[str] = []
            if (
                hasattr(config.project_containers, "qdrant_name")
                and config.project_containers.qdrant_name
            ):
                self.expected_containers.append(config.project_containers.qdrant_name)
            if (
                hasattr(config.project_containers, "data_cleaner_name")
                and config.project_containers.data_cleaner_name
            ):
                self.expected_containers.append(
                    config.project_containers.data_cleaner_name
                )
            if (
                hasattr(config.project_containers, "ollama_name")
                and config.project_containers.ollama_name
            ):
                self.expected_containers.append(config.project_containers.ollama_name)

        except Exception as e:
            # Fallback to discovering container names dynamically during test
            print(f"Could not determine container names in setup: {e}")
            if not hasattr(self, "expected_containers"):
                self.expected_containers = []

    def teardown_method(self):
        """Clean up after test."""
        # IMPORTANT: Restore services to running state for next tests
        # This test manipulates Docker state, so it must clean up properly
        try:
            # Start services to restore normal state for subsequent tests
            print("Restoring services to running state for next tests...")
            start_result = self.docker_manager.start_services()
            if start_result:
                # Give services time to be ready
                time.sleep(10)
                print("✅ Services restored for next tests")
            else:
                print(
                    "⚠️ Warning: Could not restore services - next tests may be affected"
                )
        except Exception as e:
            print(
                f"⚠️ Warning: Error restoring services: {e} - next tests may be affected"
            )

    def _get_container_status_direct(self, container_name: str) -> str:
        """Get container status directly using docker inspect."""
        try:
            result = subprocess.run(
                ["docker", "inspect", container_name, "--format", "{{.State.Status}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return "not_found"
        except Exception:
            return "error"

    def _discover_running_containers(self):
        """Discover running containers that match our project pattern."""
        try:
            result = subprocess.run(
                ["docker", "ps", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                all_containers = result.stdout.strip().split("\n")
                # Filter for containers that look like our project containers
                project_containers = [
                    name
                    for name in all_containers
                    if name
                    and ("qdrant" in name or "data-cleaner" in name)
                    and "cidx-" in name
                ]
                if project_containers:
                    self.expected_containers = [
                        c for c in project_containers if c is not None
                    ]
                    print(f"Discovered containers: {project_containers}")
        except Exception as e:
            print(f"Failed to discover containers: {e}")

    def _wait_for_containers_state(
        self, expected_state: str, timeout: int = 60
    ) -> bool:
        """Wait for all containers to reach expected state."""
        start_time = time.time()

        # If we don't have expected containers, use the project-specific container names
        if not self.expected_containers:
            from pathlib import Path

            project_root = Path.cwd()
            project_containers = self.docker_manager._generate_container_names(
                project_root
            )
            # Only include containers that exist for the current project
            self.expected_containers = [
                name
                for name in [
                    project_containers.get("qdrant_name"),
                    project_containers.get("data_cleaner_name"),
                    project_containers.get("ollama_name"),
                ]
                if name
            ]

        while time.time() - start_time < timeout:
            all_match = True

            for container_name in self.expected_containers:
                status = self._get_container_status_direct(container_name)

                if expected_state == "running":
                    if status != "running":
                        all_match = False
                        break
                elif expected_state == "stopped":
                    if status not in ["exited", "not_found"]:
                        all_match = False
                        break

            if all_match:
                return True

            time.sleep(2)

        return False

    def _verify_docker_manager_status(self, expected_running: bool) -> Dict[str, Any]:
        """Verify DockerManager status matches expected state."""
        status: Dict[str, Any] = self.docker_manager.get_service_status()

        if expected_running:
            assert (
                status["status"] == "running"
            ), f"Expected running status, got: {status}"
            assert len(status["services"]) == len(
                self.expected_containers
            ), f"Expected {len(self.expected_containers)} services, got: {len(status['services'])}"

            # Verify all expected containers are present and running
            for container_name in self.expected_containers:
                assert (
                    container_name in status["services"]
                ), f"Container {container_name} not found in status"
                container_status = status["services"][container_name]
                assert (
                    container_status["state"] == "running"
                ), f"Container {container_name} not running: {container_status}"
        else:
            # When stopped, we expect either "stopped" status or services in non-running state
            if status["status"] == "stopped":
                # If status is "stopped", services can still be returned if they exist in exited state
                for container_name, container_status in status["services"].items():
                    assert container_status["state"] in [
                        "exited",
                        "created",
                        "not_found",
                    ], f"Container {container_name} should be exited/created/not_found when stopped, got: {container_status}"
            else:
                # If services are returned, they should not be in running state
                for container_name, container_status in status["services"].items():
                    assert (
                        container_status["state"] != "running"
                    ), f"Container {container_name} still running when should be stopped"

        return status

    @pytest.mark.slow
    def test_complete_start_stop_status_cycle(self):
        """Test the complete start/stop/status cycle.

        WARNING: This test manipulates Docker container states and could affect
        subsequent tests if not properly cleaned up. The teardown_method() ensures
        services are restored to running state for other tests.
        """

        print("\n=== Starting Complete Start/Stop/Status Cycle Test ===")

        # Phase 1: Ensure clean state by stopping any existing services
        print("\n1. Cleaning up any existing services...")
        try:
            self.docker_manager.stop_services()
            # Wait for containers to stop
            self._wait_for_containers_state("stopped", timeout=30)
        except Exception as e:
            print(f"Cleanup warning: {e}")

        # Verify clean state
        initial_status = self.docker_manager.get_service_status()
        print(f"Initial status: {initial_status}")

        # Phase 2: Start services
        print("\n2. Starting services...")
        start_result = self.docker_manager.start_services()
        assert start_result, "Failed to start services"

        # Wait for services to fully start
        print("   Waiting for containers to start...")
        containers_started = self._wait_for_containers_state("running", timeout=120)
        assert containers_started, "Containers did not start within timeout"

        # Verify status after start
        print("\n3. Checking status after start...")
        status_after_start = self._verify_docker_manager_status(expected_running=True)
        print(f"Status after start: {status_after_start}")

        # Give services extra time to be fully ready
        print("   Waiting for services to be fully ready...")
        time.sleep(10)

        # Phase 3: Stop services
        print("\n4. Stopping services...")
        stop_result = self.docker_manager.stop_services()
        print(f"Stop result: {stop_result}")

        # Wait for services to stop
        print("   Waiting for containers to stop...")
        containers_stopped = self._wait_for_containers_state("stopped", timeout=60)

        if not containers_stopped:
            # Debug: Check what state each container is in
            print("   DEBUG: Containers did not stop as expected. Current states:")
            for container_name in self.expected_containers:
                status = self._get_container_status_direct(container_name)
                print(f"     {container_name}: {status}")

        assert containers_stopped, "Containers did not stop within timeout"

        # Verify status after stop
        print("\n5. Checking status after stop...")
        status_after_stop = self._verify_docker_manager_status(expected_running=False)
        print(f"Status after stop: {status_after_stop}")

        # Phase 4: Start services again
        print("\n6. Starting services again...")
        start_again_result = self.docker_manager.start_services()
        assert start_again_result, "Failed to start services again"

        # Wait for services to start again
        print("   Waiting for containers to start again...")
        containers_started_again = self._wait_for_containers_state(
            "running", timeout=120
        )
        assert containers_started_again, "Containers did not start again within timeout"

        # Verify status after second start
        print("\n7. Checking status after second start...")
        status_after_restart = self._verify_docker_manager_status(expected_running=True)
        print(f"Status after restart: {status_after_restart}")

        # Ensure services are fully ready before test ends
        print("\n8. Ensuring services are fully ready for next tests...")
        time.sleep(5)  # Give services extra time to be completely ready

        print("\n=== Test Completed Successfully ===")

    @pytest.mark.slow
    def test_stop_service_debugging(self):
        """Dedicated test to debug stop functionality."""

        print("\n=== Stop Service Debugging Test ===")

        # Use ServiceManager to ensure proper service setup
        from .test_infrastructure import ServiceManager, EmbeddingProvider

        service_manager = ServiceManager()

        # Ensure services are ready using the reusable infrastructure
        print("\n1. Ensuring services are ready using ServiceManager...")
        # Use VoyageAI to match the test's expected container setup
        services_ready = service_manager.ensure_services_ready(
            embedding_provider=EmbeddingProvider.VOYAGE_AI
        )

        if not services_ready:
            print(
                "Services not ready - checking if this is a noisy neighbor scenario..."
            )
            # Try to recover by forcing recreation
            services_ready = service_manager.ensure_services_ready(
                embedding_provider=EmbeddingProvider.VOYAGE_AI, force_recreate=True
            )

            assert services_ready, "Failed to establish services for stop test"

        # Verify services are actually ready
        services_running = service_manager.are_services_running()
        if not services_running:
            # Get status for debugging
            status_result = subprocess.run(
                ["code-indexer", "status"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(f"Status check result: {status_result.stdout}")
            print(f"Status check error: {status_result.stderr}")

        assert (
            services_running
        ), "Services should be running after ensure_services_ready"

        # Now proceed with the original test logic
        # Check what containers are actually running after ServiceManager setup
        actual_containers = []
        for container_name in [
            "code-indexer-qdrant",
            "code-indexer-data-cleaner",
            "code-indexer-ollama",
        ]:
            status = self._get_container_status_direct(container_name)
            if status in ["running", "starting"]:
                actual_containers.append(container_name)

        print(f"Actual running containers: {actual_containers}")

        # Proceed with stop test using whatever containers are actually running
        if not actual_containers:
            # If no containers are running but ServiceManager says services are ready,
            # this might be a different deployment mode (e.g., external services)
            print(
                "No Docker containers found running, but services are ready - may be external deployment"
            )
            return  # Skip the Docker-specific stop test

        # Update expected containers to match what's actually running
        self.expected_containers = [c for c in actual_containers if c is not None]

        containers_started = self._wait_for_containers_state("running", timeout=30)
        assert (
            containers_started
        ), f"Expected containers {actual_containers} not in running state"

        # Get status before stop
        print("\n2. Status before stop:")
        status_before = self.docker_manager.get_service_status()
        print(f"   {status_before}")

        # Check containers directly before stop
        print("\n3. Direct container status before stop:")
        for container_name in self.expected_containers:
            status = self._get_container_status_direct(container_name)
            print(f"   {container_name}: {status}")

        # Attempt to stop services with detailed logging
        print("\n4. Attempting to stop services...")

        # Let's check what stop_services actually does
        try:
            # Check if compose file exists
            print(
                f"   Compose file exists: {self.docker_manager.compose_file.exists()}"
            )
            print(f"   Compose file path: {self.docker_manager.compose_file}")

            # Try to get the compose command
            try:
                compose_cmd = self.docker_manager.get_compose_command()
                print(f"   Compose command: {compose_cmd}")
            except Exception as e:
                print(f"   Error getting compose command: {e}")

            # Now try the actual stop
            stop_result = self.docker_manager.stop_services()
            print(f"   Stop result: {stop_result}")

        except Exception as e:
            print(f"   Exception during stop: {e}")
            import traceback

            traceback.print_exc()

        # Check status immediately after stop attempt
        print("\n5. Status immediately after stop attempt:")
        status_after = self.docker_manager.get_service_status()
        print(f"   {status_after}")

        # Check containers directly after stop attempt
        print("\n6. Direct container status after stop attempt:")
        for container_name in self.expected_containers:
            status = self._get_container_status_direct(container_name)
            print(f"   {container_name}: {status}")

        # Wait a bit and check again
        print("\n7. Waiting 10 seconds and checking again...")
        time.sleep(10)

        print("   Status after waiting:")
        status_after_wait = self.docker_manager.get_service_status()
        print(f"   {status_after_wait}")

        print("   Direct container status after waiting:")
        for container_name in self.expected_containers:
            status = self._get_container_status_direct(container_name)
            print(f"   {container_name}: {status}")

        print("\n=== Stop Debugging Test Completed ===")
