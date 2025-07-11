#!/usr/bin/env python3
"""
Unit tests for DockerManager cleanup functionality.
Tests the individual cleanup methods in isolation to ensure they work correctly.
"""

import os
import subprocess
import shutil
from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import pytest

from .conftest import get_local_tmp_dir, local_temporary_directory
from rich.console import Console

from code_indexer.services.docker_manager import DockerManager


class TestDockerManagerCleanup:
    """Unit tests for DockerManager cleanup methods"""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing"""
        return Mock(spec=Console)

    @pytest.fixture
    def docker_manager(self, mock_console):
        """Create a DockerManager instance for testing"""
        with patch("code_indexer.services.docker_manager.Path.cwd") as mock_cwd:
            # Mock current working directory to avoid real filesystem dependencies
            mock_cwd.return_value = Path(str(get_local_tmp_dir() / "test"))

            manager = DockerManager(
                console=mock_console, project_name="test_shared", force_docker=False
            )
            return manager

    @pytest.fixture
    def temp_directory(self):
        """Create a temporary directory for testing"""
        temp_dir = Path(str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}"))
        temp_dir.mkdir(parents=True, exist_ok=True)
        yield temp_dir
        # Clean up after test
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_force_cleanup_containers_success(self, docker_manager, mock_console):
        """Test successful force cleanup of containers"""
        with patch("subprocess.run") as mock_run:
            # Mock container listing showing 2 containers
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-abc123-ollama\ncidx-abc123-qdrant\n",
                    stderr="",
                ),  # List command
                Mock(returncode=0, stdout="", stderr=""),  # Kill container 1
                Mock(returncode=0, stdout="", stderr=""),  # Remove container 1
                Mock(returncode=0, stdout="", stderr=""),  # Kill container 2
                Mock(returncode=0, stdout="", stderr=""),  # Remove container 2
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is True
            # Should have called list + kill and rm for both containers
            assert mock_run.call_count == 5  # 1 list + 2 containers × 2 commands each

            # Check console output
            mock_console.print.assert_called()

    def test_force_cleanup_containers_failure(self, docker_manager, mock_console):
        """Test force cleanup when containers fail to remove"""
        with patch("subprocess.run") as mock_run:
            # Mock subprocess failure
            mock_run.side_effect = subprocess.CalledProcessError(1, "podman")

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is False
            mock_console.print.assert_called()

    def test_fix_directory_permissions(
        self, docker_manager, temp_directory, mock_console
    ):
        """Test fixing directory permissions"""
        # Create test files and directories with restricted permissions
        test_file = temp_directory / "test_file.txt"
        test_subdir = temp_directory / "subdir"
        test_subdir.mkdir()
        test_file.write_text("test content")

        # Restrict permissions
        test_file.chmod(0o000)
        test_subdir.chmod(0o000)

        # Fix permissions
        docker_manager._fix_directory_permissions(temp_directory, verbose=True)

        # Check that we can now access the files
        assert test_file.is_file()
        assert test_subdir.is_dir()

        # Check console output
        mock_console.print.assert_called()

    def test_cleanup_data_directories_success(self, docker_manager, mock_console):
        """Test successful data directory cleanup"""
        with patch("pathlib.Path.exists") as mock_exists, patch(
            "shutil.rmtree"
        ) as mock_rmtree, patch.object(
            docker_manager, "_cleanup_global_directories"
        ) as mock_global_cleanup:
            mock_exists.return_value = True
            mock_global_cleanup.return_value = True

            result = docker_manager._cleanup_data_directories(verbose=True, force=True)

            assert result is True
            mock_rmtree.assert_called()
            mock_global_cleanup.assert_called_with(True, True)

    def test_cleanup_data_directories_failure(self, docker_manager, mock_console):
        """Test data directory cleanup with failures"""
        with patch("pathlib.Path.exists") as mock_exists, patch(
            "shutil.rmtree"
        ) as mock_rmtree, patch.object(
            docker_manager, "_cleanup_global_directories"
        ) as mock_global_cleanup:
            mock_exists.return_value = True
            mock_rmtree.side_effect = PermissionError("Access denied")
            mock_global_cleanup.return_value = False

            result = docker_manager._cleanup_data_directories(verbose=True, force=False)

            assert result is False

    def test_validate_cleanup_ports_free(self, docker_manager, mock_console):
        """Test cleanup validation when ports are free"""
        with patch("socket.socket") as mock_socket:
            # Mock successful port binding (ports are free)
            mock_sock = Mock()
            mock_socket.return_value = mock_sock
            mock_sock.bind.return_value = None

            with patch("subprocess.run") as mock_run:
                # Mock no containers found
                mock_run.return_value = Mock(returncode=0, stdout="")

                result = docker_manager._validate_cleanup(verbose=True)

                assert result is True
                mock_console.print.assert_called()

    def test_validate_cleanup_ports_busy(self, docker_manager, mock_console):
        """Test cleanup validation when ports are still in use"""
        with patch("socket.socket") as mock_socket:
            # Mock port binding failure (ports still in use)
            mock_sock = Mock()
            mock_socket.return_value = mock_sock
            mock_sock.bind.side_effect = OSError("Address already in use")

            with patch("subprocess.run") as mock_run:
                # Mock containers still exist
                mock_run.return_value = Mock(returncode=0, stdout="code-indexer-ollama")

                result = docker_manager._validate_cleanup(verbose=True)

                assert result is False
                mock_console.print.assert_called()

    def test_cleanup_global_directories_test_mode(self, docker_manager, mock_console):
        """Test global directory cleanup in test mode"""
        with patch.dict(
            os.environ, {"CODE_INDEXER_DUAL_ENGINE_TEST_MODE": "true"}
        ), patch("pathlib.Path.exists") as mock_exists, patch(
            "shutil.rmtree"
        ) as mock_rmtree, patch.object(
            docker_manager, "_fix_directory_permissions"
        ) as mock_fix_perms:
            mock_exists.return_value = True

            result = docker_manager._cleanup_global_directories(
                verbose=True, force=True
            )

            assert result is True
            mock_rmtree.assert_called()
            mock_fix_perms.assert_called()

    def test_cleanup_global_directories_production_mode(
        self, docker_manager, mock_console
    ):
        """Test global directory cleanup in production mode"""
        # Don't clear environment variables - it breaks other tests and isn't needed here
        with patch("pathlib.Path.exists") as mock_exists, patch(
            "shutil.rmtree"
        ) as mock_rmtree:
            mock_exists.return_value = True

            result = docker_manager._cleanup_global_directories(
                verbose=True, force=False
            )

            assert result is True
            mock_rmtree.assert_called()

    def test_enhanced_cleanup_integration(self, docker_manager, mock_console):
        """Test the full enhanced cleanup process"""
        with patch.object(
            docker_manager, "get_compose_command"
        ) as mock_compose_cmd, patch.object(
            docker_manager, "compose_file"
        ) as mock_compose_file, patch(
            "subprocess.run"
        ) as mock_run, patch.object(
            docker_manager, "_cleanup_data_directories"
        ) as mock_cleanup_data, patch.object(
            docker_manager, "_validate_cleanup"
        ) as mock_validate:
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_data.return_value = True
            mock_validate.return_value = True

            # Test cleanup with all flags
            result = docker_manager.cleanup(
                remove_data=True, force=True, verbose=True, validate=True
            )

            assert result is True
            mock_cleanup_data.assert_called_with(True, True)
            mock_validate.assert_called_with(True)

    def test_enhanced_cleanup_with_failures(self, docker_manager, mock_console):
        """Test enhanced cleanup when some operations fail"""
        with patch.object(
            docker_manager, "get_compose_command"
        ) as mock_compose_cmd, patch.object(
            docker_manager, "compose_file"
        ) as mock_compose_file, patch(
            "subprocess.run"
        ) as mock_run, patch.object(
            docker_manager, "_cleanup_data_directories"
        ) as mock_cleanup_data, patch.object(
            docker_manager, "_validate_cleanup"
        ) as mock_validate, patch.object(
            docker_manager, "stop_main_services"
        ) as mock_stop_main, patch.object(
            docker_manager, "clean_with_data_cleaner"
        ) as mock_clean_data, patch.object(
            docker_manager, "stop_data_cleaner"
        ) as mock_stop_cleaner:
            # Setup mocks for failure scenarios
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(returncode=1, stderr="Container down failed")
            mock_cleanup_data.return_value = False
            mock_validate.return_value = False
            # Mock the new orchestrated shutdown methods
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True

            # Test cleanup with failures (for remove_data=True path)
            result = docker_manager.cleanup(
                remove_data=True, force=True, verbose=True, validate=True
            )

            assert result is False  # Should fail due to validation failure
            # For remove_data=True, should use orchestrated shutdown
            mock_stop_main.assert_called()  # Should stop main services
            mock_clean_data.assert_called()  # Should use data cleaner
            mock_stop_cleaner.assert_called()  # Should stop data cleaner

    def test_container_name_generation(self, docker_manager):
        """Test container name generation"""
        # Test project-specific container naming
        with local_temporary_directory() as temp_dir:
            test_dir = Path(temp_dir) / "test-project"
            test_dir.mkdir()
            project_config = docker_manager._generate_container_names(test_dir)

            name = docker_manager.get_container_name("ollama", project_config)
            assert name.startswith("cidx-")
            assert name.endswith("-ollama")

            name = docker_manager.get_container_name("qdrant", project_config)
            assert name.startswith("cidx-")
            assert name.endswith("-qdrant")

            name = docker_manager.get_container_name("data-cleaner", project_config)
            assert name.startswith("cidx-")
            assert name.endswith("-data-cleaner")

    def test_verbose_output_generation(
        self, docker_manager, mock_console, temp_directory
    ):
        """Test that verbose mode generates appropriate console output"""
        # Create a test file in temp directory
        test_file = temp_directory / "test.txt"
        test_file.write_text("test")

        # Test with verbose=True - should print output
        docker_manager._fix_directory_permissions(temp_directory, verbose=True)
        mock_console.print.assert_called()

        # Test without verbose - should not print
        mock_console.reset_mock()
        docker_manager._fix_directory_permissions(temp_directory, verbose=False)
        mock_console.print.assert_not_called()


class TestCleanupErrorHandling:
    """Test error handling in cleanup methods"""

    @pytest.fixture
    def docker_manager(self):
        """Create a DockerManager instance for error testing"""
        return DockerManager(
            console=Mock(spec=Console), project_name="test_shared", force_docker=False
        )

    def test_subprocess_timeout_handling(self, docker_manager):
        """Test handling of subprocess timeouts"""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired("podman", 10)

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is False

    def test_permission_error_handling(self, docker_manager):
        """Test handling of permission errors during cleanup"""
        with patch("pathlib.Path.exists") as mock_exists, patch(
            "shutil.rmtree"
        ) as mock_rmtree:
            mock_exists.return_value = True
            mock_rmtree.side_effect = PermissionError("Access denied")

            result = docker_manager._cleanup_data_directories(verbose=True, force=False)

            assert result is False

    def test_network_error_handling(self, docker_manager):
        """Test handling of network-related errors during validation"""
        with patch("socket.socket") as mock_socket:
            mock_socket.side_effect = OSError("Network unreachable")

            # Should not crash, should handle gracefully
            result = docker_manager._validate_cleanup(verbose=True)

            # Result depends on container check, but should not raise exception
            assert isinstance(result, bool)


if __name__ == "__main__":
    pytest.main([__file__])
