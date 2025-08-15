"""
Unit tests for ContainerManager dual-container support.

Tests the core functionality for maintaining two persistent container sets
(Docker and Podman) to eliminate permission conflicts and container startup failures.
"""

import pytest
from unittest.mock import Mock, patch

# Import the ContainerManager class that we'll implement
try:
    from code_indexer.services.container_manager import ContainerManager, ContainerType
except ImportError:
    # The class doesn't exist yet - this is expected for TDD
    ContainerManager = None
    ContainerType = None


class TestContainerManagerDualSupport:
    """Test ContainerManager dual-container architecture."""

    def test_container_manager_imports(self):
        """Test that ContainerManager can be imported."""
        # This test will fail until we implement the ContainerManager
        assert (
            ContainerManager is not None
        ), "ContainerManager class should be importable"
        assert ContainerType is not None, "ContainerType enum should be importable"

    def test_container_manager_initialization_with_dual_mode(self):
        """Test ContainerManager initializes with dual-container mode."""
        # This test will fail until we implement the ContainerManager
        manager = ContainerManager(dual_container_mode=True)

        assert manager.dual_container_mode is True
        assert hasattr(manager, "docker_containers")
        assert hasattr(manager, "podman_containers")
        assert hasattr(manager, "active_container_sets")

    def test_container_manager_directory_based_isolation(self):
        """Test that ContainerManager uses directory-based container isolation."""
        manager = ContainerManager(dual_container_mode=True)

        # Test Docker directory isolation
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        assert "docker" in str(docker_dir).lower()

        # Test Podman directory isolation
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)
        assert (
            "podman" in str(podman_dir).lower() or "rootless" in str(podman_dir).lower()
        )

        # Directories should be different
        assert docker_dir != podman_dir

    def test_get_shared_test_directory_function_exists(self):
        """Test that get_shared_test_directory function provides proper isolation."""
        from code_indexer.services.container_manager import get_shared_test_directory

        # Test default (Podman) directory
        podman_dir = get_shared_test_directory(force_docker=False)
        assert podman_dir.exists() or podman_dir.parent.exists()

        # Test Docker directory
        docker_dir = get_shared_test_directory(force_docker=True)
        assert docker_dir.exists() or docker_dir.parent.exists()

        # Should be different directories
        assert podman_dir != docker_dir

    def test_container_routing_based_on_test_category(self):
        """Test that manager routes to appropriate container set based on test category."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock container sets
        manager.docker_containers = {"qdrant": Mock(), "ollama": Mock()}
        manager.podman_containers = {"qdrant": Mock(), "ollama": Mock()}

        # Test Docker routing
        docker_set = manager.get_container_set(ContainerType.DOCKER)
        assert docker_set is manager.docker_containers

        # Test Podman routing
        podman_set = manager.get_container_set(ContainerType.PODMAN)
        assert podman_set is manager.podman_containers

    def test_docker_container_set_persistence(self):
        """Test that Docker container set is maintained without recreation."""
        manager = ContainerManager(dual_container_mode=True)

        # Initialize Docker containers
        manager.initialize_container_set(ContainerType.DOCKER)
        docker_containers_1 = manager.get_container_set(ContainerType.DOCKER)

        # Request same containers again
        docker_containers_2 = manager.get_container_set(ContainerType.DOCKER)

        # Should be the same instance (no recreation)
        assert docker_containers_1 is docker_containers_2

    def test_podman_container_set_persistence(self):
        """Test that Podman container set is maintained without recreation."""
        manager = ContainerManager(dual_container_mode=True)

        # Initialize Podman containers
        manager.initialize_container_set(ContainerType.PODMAN)
        podman_containers_1 = manager.get_container_set(ContainerType.PODMAN)

        # Request same containers again
        podman_containers_2 = manager.get_container_set(ContainerType.PODMAN)

        # Should be the same instance (no recreation)
        assert podman_containers_1 is podman_containers_2

    def test_both_container_sets_can_coexist(self):
        """Test that both Docker and Podman container sets can be initialized simultaneously."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock container startup to avoid actual CLI calls
        with patch.object(manager, "_start_containers") as mock_start:
            mock_start.return_value = True

            # Initialize both container sets
            docker_success = manager.initialize_container_set(ContainerType.DOCKER)
            podman_success = manager.initialize_container_set(ContainerType.PODMAN)

            assert docker_success is True
            assert podman_success is True

            # Both should be available
            docker_set = manager.get_container_set(ContainerType.DOCKER)
            podman_set = manager.get_container_set(ContainerType.PODMAN)

            assert docker_set is not None
            assert podman_set is not None
            assert docker_set != podman_set

    def test_container_health_verification_docker(self):
        """Test container health verification for Docker containers."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock Docker container health checks
        with patch.object(manager, "_check_container_health") as mock_health:
            mock_health.return_value = True

            # Verify Docker containers
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            assert is_healthy is True
            mock_health.assert_called_with(ContainerType.DOCKER)

    def test_container_health_verification_podman(self):
        """Test container health verification for Podman containers."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock Podman container health checks
        with patch.object(manager, "_check_container_health") as mock_health:
            mock_health.return_value = True

            # Verify Podman containers
            is_healthy = manager.verify_container_health(ContainerType.PODMAN)
            assert is_healthy is True
            mock_health.assert_called_with(ContainerType.PODMAN)

    def test_collection_reset_clears_qdrant_only(self):
        """Test that collection reset only clears Qdrant collections, not containers."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock collection reset
        with patch.object(manager, "_reset_qdrant_collections") as mock_reset:
            mock_reset.return_value = True

            # Reset collections for Docker containers
            success = manager.reset_collections(ContainerType.DOCKER)
            assert success is True
            mock_reset.assert_called_with(ContainerType.DOCKER)

    def test_containers_remain_running_between_tests(self):
        """Test that containers remain running between test operations."""
        manager = ContainerManager(dual_container_mode=True)

        # Initialize containers
        manager.initialize_container_set(ContainerType.DOCKER)
        initial_containers = manager.get_container_set(ContainerType.DOCKER)

        # Simulate test operation (collection reset)
        manager.reset_collections(ContainerType.DOCKER)

        # Containers should still be the same instances
        final_containers = manager.get_container_set(ContainerType.DOCKER)
        assert initial_containers is final_containers

    def test_cli_commands_for_container_operations(self):
        """Test that ContainerManager uses CLI commands for operations."""
        manager = ContainerManager(dual_container_mode=True)

        # Mock CLI command execution
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(returncode=0, stdout="success")

            # Test init command
            manager.run_cli_command(["init", "--force"], ContainerType.DOCKER)

            # Should have called subprocess.run with cidx command
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert "init" in args
            assert "--force" in args

    def test_container_startup_failure_elimination(self):
        """Test that subsequent container requests don't fail due to startup issues."""
        manager = ContainerManager(dual_container_mode=True)

        # Initialize container set
        with patch.object(manager, "_start_containers") as mock_start:
            mock_start.return_value = True

            # First initialization should trigger startup
            success_1 = manager.initialize_container_set(ContainerType.DOCKER)
            assert success_1 is True

            containers_1 = manager.get_container_set(ContainerType.DOCKER)
            assert containers_1 is not None

            # Second initialization should not trigger startup again (already initialized)
            success_2 = manager.initialize_container_set(ContainerType.DOCKER)
            assert success_2 is True

            containers_2 = manager.get_container_set(ContainerType.DOCKER)
            assert containers_2 is containers_1

            # Start should only be called once
            mock_start.assert_called_once()


class TestContainerManagerErrorHandling:
    """Test ContainerManager error handling and edge cases."""

    def test_invalid_container_type_raises_error(self):
        """Test that invalid container type raises appropriate error."""
        manager = ContainerManager(dual_container_mode=True)

        with pytest.raises(ValueError, match="Invalid container type"):
            manager.get_container_set("invalid_type")

    def test_non_dual_mode_falls_back_to_single_container(self):
        """Test that non-dual mode uses single container management."""
        manager = ContainerManager(dual_container_mode=False)

        assert manager.dual_container_mode is False
        # Should fall back to existing DockerManager behavior
        assert hasattr(manager, "docker_manager")

    def test_container_health_check_failure_handling(self):
        """Test handling of container health check failures."""
        manager = ContainerManager(dual_container_mode=True)

        with patch.object(manager, "_check_container_health") as mock_health:
            mock_health.return_value = False

            # Health check failure should be handled gracefully
            is_healthy = manager.verify_container_health(ContainerType.DOCKER)
            assert is_healthy is False

    def test_collection_reset_failure_handling(self):
        """Test handling of collection reset failures."""
        manager = ContainerManager(dual_container_mode=True)

        with patch.object(manager, "_reset_qdrant_collections") as mock_reset:
            mock_reset.return_value = False

            # Reset failure should be handled gracefully
            success = manager.reset_collections(ContainerType.DOCKER)
            assert success is False


class TestContainerManagerIntegration:
    """Integration tests for ContainerManager with real CLI commands."""

    @pytest.mark.integration
    def test_container_manager_with_real_directories(self):
        """Test ContainerManager with real directory creation."""
        manager = ContainerManager(dual_container_mode=True)

        # Get directories for both container types
        docker_dir = manager.get_container_directory(ContainerType.DOCKER)
        podman_dir = manager.get_container_directory(ContainerType.PODMAN)

        # Directories should be creatable
        docker_dir.mkdir(parents=True, exist_ok=True)
        podman_dir.mkdir(parents=True, exist_ok=True)

        assert docker_dir.exists()
        assert podman_dir.exists()
        assert docker_dir != podman_dir

    @pytest.mark.integration
    def test_get_shared_test_directory_real_paths(self):
        """Test get_shared_test_directory with real path creation."""
        from code_indexer.services.container_manager import get_shared_test_directory

        # Test both directory types
        podman_dir = get_shared_test_directory(force_docker=False)
        docker_dir = get_shared_test_directory(force_docker=True)

        # Should be able to create the directories
        podman_dir.mkdir(parents=True, exist_ok=True)
        docker_dir.mkdir(parents=True, exist_ok=True)

        assert podman_dir.exists()
        assert docker_dir.exists()
        assert podman_dir != docker_dir
