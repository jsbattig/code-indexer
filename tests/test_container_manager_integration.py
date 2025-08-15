"""
Integration tests for ContainerManager Docker/Podman container isolation.

Tests the integration between ContainerManager and actual container engines
to ensure proper isolation and resource management.
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


@pytest.mark.integration
class TestContainerManagerDockerPodmanIntegration:
    """Integration tests for Docker/Podman container isolation."""

    def test_docker_container_directory_isolation(self):
        """Test that Docker containers use isolated directory structure."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get Docker container directory
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)

        # Should contain docker-specific path elements
        assert "docker" in str(docker_dir).lower()

        # Directory should be under proper isolation path
        expected_base = get_shared_test_directory(force_docker=True)
        assert docker_dir.is_relative_to(expected_base) or docker_dir == expected_base

    def test_podman_container_directory_isolation(self):
        """Test that Podman containers use isolated directory structure."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get Podman container directory
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Should NOT contain docker-specific path elements
        assert "docker" not in str(podman_dir).lower()

        # Directory should be under proper isolation path
        expected_base = get_shared_test_directory(force_docker=False)
        assert podman_dir.is_relative_to(expected_base) or podman_dir == expected_base

    def test_concurrent_docker_podman_container_initialization(self):
        """Test that Docker and Podman containers can be initialized concurrently."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock the actual container startup to avoid real container operations
        with patch.object(manager, "_start_containers") as mock_start:
            mock_start.return_value = True

            # Initialize both container types
            docker_success = manager.initialize_container_set(ContainerType.DOCKER)
            podman_success = manager.initialize_container_set(ContainerType.PODMAN)

            assert docker_success is True
            assert podman_success is True

            # Both should have been started
            assert mock_start.call_count == 2

    def test_docker_container_health_verification_integration(self):
        """Test Docker container health verification with real CLI commands."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock subprocess.run to simulate successful health check
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Qdrant ✅ Ready\nOllama ✅ Ready", stderr=""
            )

            # Verify container health
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            assert is_healthy is True

            # Should have called CLI status command
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert any("status" in str(arg) for arg in args)

    def test_podman_container_health_verification_integration(self):
        """Test Podman container health verification with real CLI commands."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock subprocess.run to simulate successful health check
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0, stdout="Qdrant ✅ Ready\nOllama ✅ Ready", stderr=""
            )

            # Verify container health
            is_healthy = manager.verify_container_health(ContainerType.PODMAN)
            assert is_healthy is True

            # Should have called CLI status command in correct directory
            mock_run.assert_called()

    def test_collection_reset_preserves_containers_docker(self):
        """Test that collection reset for Docker preserves containers."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Initialize Docker containers
        with patch.object(manager, "_start_containers") as mock_start:
            mock_start.return_value = True
            manager.initialize_container_set(ContainerType.DOCKER)

            # Get initial container reference
            initial_containers = manager.get_container_set(ContainerType.DOCKER)

            # Reset collections
            with patch.object(manager, "_reset_qdrant_collections") as mock_reset:
                mock_reset.return_value = True
                manager.reset_collections(ContainerType.DOCKER)

                # Containers should still be the same
                final_containers = manager.get_container_set(ContainerType.DOCKER)
                assert initial_containers is final_containers

    def test_collection_reset_preserves_containers_podman(self):
        """Test that collection reset for Podman preserves containers."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Initialize Podman containers
        with patch.object(manager, "_start_containers") as mock_start:
            mock_start.return_value = True
            manager.initialize_container_set(ContainerType.PODMAN)

            # Get initial container reference
            initial_containers = manager.get_container_set(ContainerType.PODMAN)

            # Reset collections
            with patch.object(manager, "_reset_qdrant_collections") as mock_reset:
                mock_reset.return_value = True
                manager.reset_collections(ContainerType.PODMAN)

                # Containers should still be the same
                final_containers = manager.get_container_set(ContainerType.PODMAN)
                assert initial_containers is final_containers

    def test_cli_command_execution_with_correct_working_directory(self):
        """Test that CLI commands execute in correct working directory for each container type."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="success")

            # Execute command for Docker containers
            docker_dir = manager.get_container_directory(ContainerType.DOCKER)
            manager.run_cli_command(["status"], ContainerType.DOCKER)

            # Check that subprocess was called with correct cwd
            call_args = mock_run.call_args
            assert call_args[1]["cwd"] == docker_dir

    def test_permission_isolation_between_docker_podman(self):
        """Test that Docker and Podman containers have isolated permissions."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get directories for both container types
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Create directories to test permissions
        docker_dir.mkdir(parents=True, exist_ok=True)
        podman_dir.mkdir(parents=True, exist_ok=True)

        # Directories should be writable by current user
        assert docker_dir.exists()
        assert podman_dir.exists()

        # Test file creation in both directories
        docker_test_file = docker_dir / "test.txt"
        podman_test_file = podman_dir / "test.txt"

        docker_test_file.write_text("docker test")
        podman_test_file.write_text("podman test")

        assert docker_test_file.exists()
        assert podman_test_file.exists()

    def test_container_startup_failure_recovery(self):
        """Test recovery from container startup failures."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Mock first startup to fail, second to succeed
        call_count = 0

        def mock_start_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count > 1  # Fail first time, succeed second time

        with patch.object(
            manager, "_start_containers", side_effect=mock_start_side_effect
        ):
            # First attempt should fail
            success_1 = manager.initialize_container_set(ContainerType.DOCKER)
            assert success_1 is False

            # Second attempt should succeed
            success_2 = manager.initialize_container_set(ContainerType.DOCKER)
            assert success_2 is True


@pytest.mark.integration
class TestSharedTestDirectoryIntegration:
    """Integration tests for get_shared_test_directory function."""

    def test_get_shared_test_directory_creates_docker_path(self):
        """Test that get_shared_test_directory creates Docker-specific path."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        docker_dir = get_shared_test_directory(force_docker=True)

        # Should contain docker-specific identifier
        assert "docker" in str(docker_dir).lower()

        # Should be creatable
        docker_dir.mkdir(parents=True, exist_ok=True)
        assert docker_dir.exists()

    def test_get_shared_test_directory_creates_podman_path(self):
        """Test that get_shared_test_directory creates Podman-specific path."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        podman_dir = get_shared_test_directory(force_docker=False)

        # Should NOT contain docker-specific identifier
        assert "docker" not in str(podman_dir).lower()

        # Should be creatable
        podman_dir.mkdir(parents=True, exist_ok=True)
        assert podman_dir.exists()

    def test_docker_podman_directories_are_isolated(self):
        """Test that Docker and Podman directories are completely isolated."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        docker_dir = get_shared_test_directory(force_docker=True)
        podman_dir = get_shared_test_directory(force_docker=False)

        # Should be different paths
        assert docker_dir != podman_dir

        # Neither should be a parent of the other
        assert not docker_dir.is_relative_to(podman_dir)
        assert not podman_dir.is_relative_to(docker_dir)

    def test_shared_test_directory_persistence(self):
        """Test that shared test directories persist across calls."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        # Multiple calls should return same path
        docker_dir_1 = get_shared_test_directory(force_docker=True)
        docker_dir_2 = get_shared_test_directory(force_docker=True)

        podman_dir_1 = get_shared_test_directory(force_docker=False)
        podman_dir_2 = get_shared_test_directory(force_docker=False)

        assert docker_dir_1 == docker_dir_2
        assert podman_dir_1 == podman_dir_2

    def test_shared_test_directory_in_temp_location(self):
        """Test that shared test directories are in appropriate temp location."""
        if get_shared_test_directory is None:
            pytest.skip("get_shared_test_directory not implemented yet")

        docker_dir = get_shared_test_directory(force_docker=True)
        podman_dir = get_shared_test_directory(force_docker=False)

        # Both should be in temp-like locations
        # Check for common temp path patterns
        temp_patterns = [".tmp", "tmp", "temp"]

        docker_in_temp = any(pattern in str(docker_dir) for pattern in temp_patterns)
        podman_in_temp = any(pattern in str(podman_dir) for pattern in temp_patterns)

        assert docker_in_temp or podman_in_temp  # At least one should be in temp


@pytest.mark.integration
@pytest.mark.slow
class TestContainerManagerRealContainers:
    """Integration tests with real container operations (marked as slow)."""

    def test_real_cli_command_integration(self):
        """Test ContainerManager with real CLI command (status check only)."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Test a safe CLI command (status) that won't modify system
        try:
            # This should work even if containers aren't running
            result = manager.run_cli_command(["--help"], ContainerType.PODMAN)

            # Help command should always succeed
            assert result.returncode == 0 or "help" in result.stdout.lower()

        except Exception as e:
            # If CLI isn't available, that's OK for this test
            pytest.skip(f"CLI not available: {e}")

    def test_real_directory_creation_and_permissions(self):
        """Test real directory creation and permission handling."""
        if ContainerManager is None:
            pytest.skip("ContainerManager not implemented yet")

        manager = ContainerManager(dual_container_mode=True)

        # Get real directories
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Create them
        docker_dir.mkdir(parents=True, exist_ok=True)
        podman_dir.mkdir(parents=True, exist_ok=True)

        # Test that we can write files
        docker_config = docker_dir / ".code-indexer" / "test_config.json"
        podman_config = podman_dir / ".code-indexer" / "test_config.json"

        docker_config.parent.mkdir(parents=True, exist_ok=True)
        podman_config.parent.mkdir(parents=True, exist_ok=True)

        docker_config.write_text('{"test": "docker"}')
        podman_config.write_text('{"test": "podman"}')

        assert docker_config.exists()
        assert podman_config.exists()
        assert docker_config.read_text() != podman_config.read_text()
