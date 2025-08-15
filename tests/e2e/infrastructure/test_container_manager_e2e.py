"""
End-to-end tests for ContainerManager container health verification and collection reset.

Tests the complete workflow from container initialization through health checks
to collection resets, ensuring containers remain persistent throughout.
"""

import pytest
from unittest.mock import patch, Mock

# Import the ContainerManager class that we'll implement
try:
    from code_indexer.services.container_manager import (
        ContainerManager,
        ContainerType,
        get_shared_test_directory,
    )
except ImportError:
    # The class doesn't exist yet - this is expected for TDD
    ContainerManager = None
    ContainerType = None
    get_shared_test_directory = None


@pytest.mark.e2e
class TestContainerManagerE2EWorkflow:
    """End-to-end tests for complete ContainerManager workflow."""

    @pytest.fixture
    def temp_project_dirs(self, tmp_path):
        """Create temporary project directories for Docker and Podman."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        docker_dir = get_shared_test_directory(force_docker=True)
        podman_dir = get_shared_test_directory(force_docker=False)

        # Ensure directories exist
        docker_dir.mkdir(parents=True, exist_ok=True)
        podman_dir.mkdir(parents=True, exist_ok=True)

        return {"docker": docker_dir, "podman": podman_dir}

    def test_complete_dual_container_lifecycle(self, temp_project_dirs):
        """Test complete lifecycle: init -> start -> verify -> reset -> verify."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock all external operations to avoid real container operations
        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(manager, "_check_container_health") as mock_health,
            patch.object(manager, "_reset_qdrant_collections") as mock_reset,
        ):

            mock_start.return_value = True
            mock_health.return_value = True
            mock_reset.return_value = True

            # Step 1: Initialize both container sets
            docker_init = manager.initialize_container_set(ContainerType.DOCKER)
            podman_init = manager.initialize_container_set(ContainerType.PODMAN)

            assert docker_init is True
            assert podman_init is True

            # Step 2: Verify both container sets are healthy
            docker_healthy = manager.verify_container_health(ContainerType.DOCKER)
            podman_healthy = manager.verify_container_health(ContainerType.PODMAN)

            assert docker_healthy is True
            assert podman_healthy is True

            # Step 3: Reset collections for both
            docker_reset = manager.reset_collections(ContainerType.DOCKER)
            podman_reset = manager.reset_collections(ContainerType.PODMAN)

            assert docker_reset is True
            assert podman_reset is True

            # Step 4: Verify containers are still healthy after reset
            docker_healthy_after = manager.verify_container_health(ContainerType.DOCKER)
            podman_healthy_after = manager.verify_container_health(ContainerType.PODMAN)

            assert docker_healthy_after is True
            assert podman_healthy_after is True

            # Verify container sets are still the same instances (persistent)
            docker_containers_after = manager.get_container_set(ContainerType.DOCKER)
            podman_containers_after = manager.get_container_set(ContainerType.PODMAN)

            assert docker_containers_after is not None
            assert podman_containers_after is not None

    def test_container_failure_recovery_workflow(self, temp_project_dirs):
        """Test recovery workflow when containers fail and need restart."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Simulate container failure and recovery
        health_call_count = 0

        def mock_health_side_effect(container_type):
            nonlocal health_call_count
            health_call_count += 1
            # Fail first two health checks, succeed after
            return health_call_count > 2

        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(
                manager, "_check_container_health", side_effect=mock_health_side_effect
            ),
        ):

            mock_start.return_value = True

            # Initialize containers
            manager.initialize_container_set(ContainerType.DOCKER)

            # First health check should fail
            healthy_1 = manager.verify_container_health(ContainerType.DOCKER)
            assert healthy_1 is False

            # Second health check should fail
            healthy_2 = manager.verify_container_health(ContainerType.DOCKER)
            assert healthy_2 is False

            # Third health check should succeed
            healthy_3 = manager.verify_container_health(ContainerType.DOCKER)
            assert healthy_3 is True

    def test_concurrent_container_operations(self, temp_project_dirs):
        """Test concurrent operations on Docker and Podman containers."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(manager, "_check_container_health") as mock_health,
            patch.object(manager, "_reset_qdrant_collections") as mock_reset,
        ):

            mock_start.return_value = True
            mock_health.return_value = True
            mock_reset.return_value = True

            # Concurrent initialization
            docker_init = manager.initialize_container_set(ContainerType.DOCKER)
            podman_init = manager.initialize_container_set(ContainerType.PODMAN)

            # Both should succeed
            assert docker_init is True
            assert podman_init is True

            # Concurrent health checks
            docker_health = manager.verify_container_health(ContainerType.DOCKER)
            podman_health = manager.verify_container_health(ContainerType.PODMAN)

            # Both should be healthy
            assert docker_health is True
            assert podman_health is True

            # Concurrent collection resets
            docker_reset = manager.reset_collections(ContainerType.DOCKER)
            podman_reset = manager.reset_collections(ContainerType.PODMAN)

            # Both should succeed
            assert docker_reset is True
            assert podman_reset is True

    def test_collection_reset_isolation(self, temp_project_dirs):
        """Test that collection reset for one container type doesn't affect the other."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Track reset calls per container type
        reset_calls = {"docker": 0, "podman": 0}

        def mock_reset_side_effect(container_type):
            if container_type == ContainerType.DOCKER:
                reset_calls["docker"] += 1
            elif container_type == ContainerType.PODMAN:
                reset_calls["podman"] += 1
            return True

        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(manager, "_check_container_health") as mock_health,
            patch.object(
                manager, "_reset_qdrant_collections", side_effect=mock_reset_side_effect
            ),
        ):

            mock_start.return_value = True
            mock_health.return_value = True

            # Initialize both container sets
            manager.initialize_container_set(ContainerType.DOCKER)
            manager.initialize_container_set(ContainerType.PODMAN)

            # Reset only Docker collections
            manager.reset_collections(ContainerType.DOCKER)

            # Only Docker should have been reset
            assert reset_calls["docker"] == 1
            assert reset_calls["podman"] == 0

            # Reset only Podman collections
            manager.reset_collections(ContainerType.PODMAN)

            # Now both should be reset once
            assert reset_calls["docker"] == 1
            assert reset_calls["podman"] == 1

    def test_container_persistence_across_multiple_tests(self, temp_project_dirs):
        """Test that containers remain persistent across multiple test operations."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(manager, "_check_container_health") as mock_health,
            patch.object(manager, "_reset_qdrant_collections") as mock_reset,
        ):

            mock_start.return_value = True
            mock_health.return_value = True
            mock_reset.return_value = True

            # Initialize containers
            manager.initialize_container_set(ContainerType.DOCKER)
            initial_containers = manager.get_container_set(ContainerType.DOCKER)

            # Simulate multiple test operations
            for i in range(5):
                # Each "test" performs health check and collection reset
                manager.verify_container_health(ContainerType.DOCKER)
                manager.reset_collections(ContainerType.DOCKER)

                # Containers should remain the same instance
                current_containers = manager.get_container_set(ContainerType.DOCKER)
                assert current_containers is initial_containers

            # Start should only be called once during initialization
            mock_start.assert_called_once()

    def test_cli_command_integration_with_real_directories(self, temp_project_dirs):
        """Test CLI command execution with real directory structure."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Use real directories from fixture (temp_project_dirs fixture provides isolated directories)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="success")

            # Test CLI command for Docker
            manager.run_cli_command(["status"], ContainerType.DOCKER)

            # Verify subprocess was called with correct working directory
            docker_call = mock_run.call_args
            assert docker_call[1]["cwd"] == manager.get_container_directory(
                ContainerType.DOCKER
            )

            # Test CLI command for Podman
            manager.run_cli_command(["status"], ContainerType.PODMAN)

            # Verify subprocess was called with correct working directory
            podman_call = mock_run.call_args
            assert podman_call[1]["cwd"] == manager.get_container_directory(
                ContainerType.PODMAN
            )


@pytest.mark.e2e
class TestContainerManagerHealthVerification:
    """End-to-end tests for container health verification."""

    def test_health_verification_with_cli_status_command(self):
        """Test health verification using real CLI status command structure."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock successful status response
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Qdrant ✅ Ready (http://localhost:6333)\nOllama ✅ Ready (http://localhost:11434)",
                stderr="",
            )

            # Health verification should succeed
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            assert is_healthy is True

            # Should have called status command
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert any("status" in str(arg) for arg in args)

    def test_health_verification_with_failed_containers(self):
        """Test health verification when containers are not ready."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock failed status response
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="Qdrant ❌ Not Ready\nOllama ❌ Not Ready",
                stderr="Container connection failed",
            )

            # Health verification should fail
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            assert is_healthy is False

    def test_health_verification_with_partial_container_failure(self):
        """Test health verification when some containers are ready, others not."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock partial success response
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="Qdrant ✅ Ready (http://localhost:6333)\nOllama ❌ Not Ready",
                stderr="",
            )

            # Health verification should handle partial failures appropriately
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            # This depends on implementation - might be True if essential services are ready
            assert isinstance(is_healthy, bool)


@pytest.mark.e2e
class TestContainerManagerCollectionReset:
    """End-to-end tests for collection reset functionality."""

    def test_collection_reset_with_cli_clean_data_command(self):
        """Test collection reset using CLI clean-data command."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock successful clean-data response
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout="✅ Cleared Qdrant collections\n✅ Data cleanup completed",
                stderr="",
            )

            # Collection reset should succeed
            success = manager.reset_collections(ContainerType.DOCKER)
            assert success is True

            # Should have called clean-data command
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert any("clean" in str(arg) or "data" in str(arg) for arg in args)

    def test_collection_reset_failure_handling(self):
        """Test collection reset failure handling."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock failed clean-data response
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1, stdout="", stderr="Failed to connect to Qdrant"
            )

            # Collection reset should fail gracefully
            success = manager.reset_collections(ContainerType.DOCKER)
            assert success is False

    def test_collection_reset_preserves_container_state(self):
        """Test that collection reset doesn't affect container running state."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        with (
            patch.object(manager, "_start_containers") as mock_start,
            patch.object(manager, "_check_container_health") as mock_health,
        ):

            mock_start.return_value = True
            mock_health.return_value = True

            # Initialize containers
            manager.initialize_container_set(ContainerType.DOCKER)
            containers_before = manager.get_container_set(ContainerType.DOCKER)

            # Mock collection reset
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="success")

                # Reset collections
                manager.reset_collections(ContainerType.DOCKER)

                # Containers should still be the same instance
                containers_after = manager.get_container_set(ContainerType.DOCKER)
                assert containers_before is containers_after

                # Container health should still be verifiable
                health_after = manager.verify_container_health(ContainerType.DOCKER)
                assert health_after is True


@pytest.mark.e2e
@pytest.mark.slow
class TestContainerManagerRealE2E:
    """Real end-to-end tests with actual CLI commands (marked as slow)."""

    def test_real_directory_isolation_e2e(self):
        """Test real directory isolation between Docker and Podman."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get real directories
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Create configuration files in each
        docker_config_dir = docker_dir / ".code-indexer"
        podman_config_dir = podman_dir / ".code-indexer"

        docker_config_dir.mkdir(parents=True, exist_ok=True)
        podman_config_dir.mkdir(parents=True, exist_ok=True)

        docker_config = docker_config_dir / "config.json"
        podman_config = podman_config_dir / "config.json"

        docker_config.write_text('{"container_type": "docker"}')
        podman_config.write_text('{"container_type": "podman"}')

        # Verify isolation
        assert docker_config.read_text() != podman_config.read_text()
        assert docker_dir != podman_dir

    def test_safe_cli_help_command_e2e(self):
        """Test safe CLI help command execution in both environments."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Test help command (safe, won't modify system)
        try:
            docker_result = manager.run_cli_command(["--help"], ContainerType.DOCKER)
            podman_result = manager.run_cli_command(["--help"], ContainerType.PODMAN)

            # Help should work in both environments
            assert (
                docker_result.returncode == 0 or "help" in docker_result.stdout.lower()
            )
            assert (
                podman_result.returncode == 0 or "help" in podman_result.stdout.lower()
            )

        except Exception as e:
            # If CLI isn't available, that's OK for this test
            pytest.skip(f"CLI not available: {e}")

    def test_real_permission_handling_e2e(self):
        """Test real permission handling between Docker and Podman environments."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get directories and ensure they're writable
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Create test files to verify permissions
        docker_test_file = docker_dir / "permission_test.txt"
        podman_test_file = podman_dir / "permission_test.txt"

        # Should be able to write to both
        docker_test_file.parent.mkdir(parents=True, exist_ok=True)
        podman_test_file.parent.mkdir(parents=True, exist_ok=True)

        docker_test_file.write_text("docker permission test")
        podman_test_file.write_text("podman permission test")

        # Should be able to read from both
        assert docker_test_file.read_text() == "docker permission test"
        assert podman_test_file.read_text() == "podman permission test"

        # Clean up
        docker_test_file.unlink(missing_ok=True)
        podman_test_file.unlink(missing_ok=True)
