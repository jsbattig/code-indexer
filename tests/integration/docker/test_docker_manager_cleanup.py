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

from ...conftest import get_local_tmp_dir, local_temporary_directory
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
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
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
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
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
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("shutil.rmtree") as mock_rmtree,
            patch.object(
                docker_manager, "_cleanup_global_directories"
            ) as mock_global_cleanup,
        ):
            mock_exists.return_value = True
            mock_global_cleanup.return_value = True

            result = docker_manager._cleanup_data_directories(verbose=True, force=True)

            assert result is True
            mock_rmtree.assert_called()
            mock_global_cleanup.assert_called_with(True, True)

    def test_cleanup_data_directories_failure(self, docker_manager, mock_console):
        """Test data directory cleanup with failures"""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("shutil.rmtree") as mock_rmtree,
            patch.object(
                docker_manager, "_cleanup_global_directories"
            ) as mock_global_cleanup,
        ):
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
        with (
            patch.object(
                docker_manager.health_checker, "wait_for_ports_available"
            ) as mock_ports,
            patch("subprocess.run") as mock_run,
        ):
            # Mock port binding failure (ports still in use)
            mock_ports.return_value = False

            # Mock containers still exist
            mock_run.return_value = Mock(returncode=0, stdout="cidx-abc123-ollama")

            result = docker_manager._validate_cleanup(verbose=True)

            assert result is False
            mock_console.print.assert_called()

    def test_cleanup_global_directories_test_mode(self, docker_manager, mock_console):
        """Test global directory cleanup in test mode"""
        with (
            patch.dict(os.environ, {"CODE_INDEXER_DUAL_ENGINE_TEST_MODE": "true"}),
            patch("pathlib.Path.exists") as mock_exists,
            patch("shutil.rmtree") as mock_rmtree,
            patch.object(
                docker_manager, "_fix_directory_permissions"
            ) as mock_fix_perms,
        ):
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
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("shutil.rmtree") as mock_rmtree,
        ):
            mock_exists.return_value = True

            result = docker_manager._cleanup_global_directories(
                verbose=True, force=False
            )

            assert result is True
            mock_rmtree.assert_called()

    def test_enhanced_cleanup_integration(self, docker_manager, mock_console):
        """Test the full enhanced cleanup process"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(
                docker_manager, "_validate_complete_cleanup"
            ) as mock_complete_validate,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_volumes.return_value = True
            mock_cleanup_data.return_value = True
            mock_validate.return_value = True
            mock_complete_validate.return_value = True
            mock_stop_main.return_value = True
            mock_stop_data_cleaner.return_value = True
            mock_data_cleaner.return_value = True
            mock_force_cleanup.return_value = True
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            # Test cleanup with all flags
            result = docker_manager.cleanup(
                remove_data=True, force=True, verbose=True, validate=True
            )

            assert result is True
            # The new implementation uses orchestrated shutdown with data cleaner instead of _cleanup_data_directories
            mock_data_cleaner.assert_called()
            # The new implementation uses _validate_complete_cleanup for uninstall operations
            mock_complete_validate.assert_called_with(True)
            mock_complete_validate.assert_called_with(
                True
            )  # Should also call complete validation

    def test_enhanced_cleanup_with_failures(self, docker_manager, mock_console):
        """Test enhanced cleanup when some operations fail"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
        ):
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
            mock_force_cleanup.return_value = False  # Force cleanup also fails

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

    def test_cleanup_includes_remove_orphans_for_uninstall_operations(
        self, docker_manager, mock_console
    ):
        """Test that --remove-orphans flag is included for uninstall operations (remove_data=True)"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()  # Mock the unlink operation
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_volumes.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = True
            mock_stop_data_cleaner.return_value = True
            # Mock config manager to avoid import issues
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            # Call cleanup with remove_data=True (uninstall operation)
            _ = docker_manager.cleanup(remove_data=True, force=False, verbose=False)

            # Find the docker-compose down call (this should always work, regardless of result)
            down_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0] and "down" in call[0][0]
            ]

            assert (
                len(down_calls) == 1
            ), f"Expected exactly one 'down' call, got {len(down_calls)}"

            # Verify the down command includes -v and --remove-orphans for uninstall
            # This is the failing assertion we expect in TDD before implementing the fix
            down_cmd = down_calls[0][0][0]
            assert (
                "-v" in down_cmd
            ), f"Expected -v flag for volume removal in uninstall, got: {down_cmd}"
            assert (
                "--remove-orphans" in down_cmd
            ), f"Expected --remove-orphans flag for uninstall, got: {down_cmd}"

    def test_cleanup_excludes_remove_orphans_for_regular_operations(
        self, docker_manager, mock_console
    ):
        """Test that --remove-orphans flag is NOT included for regular cleanup operations (remove_data=False)"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
        ):
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()  # Mock the unlink operation
            mock_run.return_value = Mock(returncode=0)

            # Call cleanup with remove_data=False (regular cleanup operation)
            result = docker_manager.cleanup(
                remove_data=False, force=False, verbose=False
            )

            # Verify success
            assert result is True

            # Find the docker-compose down call (should be after the stop call)
            down_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0] and "down" in call[0][0]
            ]

            assert (
                len(down_calls) == 1
            ), f"Expected exactly one 'down' call, got {len(down_calls)}"

            # Verify the down command excludes -v and --remove-orphans for regular cleanup
            down_cmd = down_calls[0][0][0]
            assert (
                "-v" not in down_cmd
            ), f"Expected NO -v flag for regular cleanup, got: {down_cmd}"
            assert (
                "--remove-orphans" not in down_cmd
            ), f"Expected NO --remove-orphans flag for regular cleanup, got: {down_cmd}"

    def test_cleanup_force_flag_behavior_with_uninstall(
        self, docker_manager, mock_console
    ):
        """Test that force flag still works correctly when combined with uninstall operations"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()  # Mock the unlink operation
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_volumes.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = True
            mock_stop_data_cleaner.return_value = True
            mock_force_cleanup.return_value = True
            # Mock config manager to avoid import issues
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            # Call cleanup with both remove_data=True and force=True
            result = docker_manager.cleanup(remove_data=True, force=True, verbose=False)

            # Verify success
            assert result is True

            # Find the docker-compose down call
            down_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0] and "down" in call[0][0]
            ]

            assert (
                len(down_calls) == 1
            ), f"Expected exactly one 'down' call, got {len(down_calls)}"

            # Verify the down command includes -v, --remove-orphans, AND --timeout for force+uninstall
            down_cmd = down_calls[0][0][0]
            assert (
                "-v" in down_cmd
            ), f"Expected -v flag for volume removal in uninstall, got: {down_cmd}"
            assert (
                "--remove-orphans" in down_cmd
            ), f"Expected --remove-orphans flag for uninstall, got: {down_cmd}"
            assert (
                "--timeout" in down_cmd
            ), f"Expected --timeout flag for force operation, got: {down_cmd}"
            assert "10" in down_cmd, f"Expected timeout value of 10, got: {down_cmd}"

    def test_validate_complete_cleanup_no_containers_remaining(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup when no cidx containers remain"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock empty container list - no containers remaining
            mock_run.return_value = Mock(returncode=0, stdout="")

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=True)

            assert result is True
            mock_console.print.assert_any_call(
                "✅ Complete cleanup validation passed - no containers remain"
            )

    def test_validate_complete_cleanup_containers_still_exist(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup when cidx containers still exist"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock container list showing remaining containers with states
            mock_run.return_value = Mock(
                returncode=0,
                stdout="cidx-abc123-ollama\texited\ncidx-abc123-qdrant\trunning",
            )

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=True)

            assert result is False
            mock_console.print.assert_any_call(
                "❌ Remaining containers found after cleanup:"
            )
            mock_console.print.assert_any_call("  - cidx-abc123-ollama (state: exited)")
            mock_console.print.assert_any_call(
                "  - cidx-abc123-qdrant (state: running)"
            )

    def test_validate_complete_cleanup_docker_engine(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup with docker engine"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="docker"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock empty container list for docker
            mock_run.return_value = Mock(returncode=0, stdout="")

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=False)

            assert result is True
            # Should use docker command
            mock_run.assert_called_with(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--format",
                    "{{.Names}}\t{{.State}}",
                    "--filter",
                    "name=cidx-",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

    def test_validate_complete_cleanup_subprocess_error(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup handles subprocess errors gracefully"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock subprocess error
            mock_run.side_effect = subprocess.CalledProcessError(1, "podman")

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=True)

            # Should return False when unable to verify cleanup
            assert result is False

    def test_validate_complete_cleanup_timeout_error(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup handles timeout errors"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock timeout error
            mock_run.side_effect = subprocess.TimeoutExpired("podman", 10)

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=True)

            # Should return False when command times out
            assert result is False

    def test_validate_complete_cleanup_non_verbose_mode(
        self, docker_manager, mock_console
    ):
        """Test _validate_complete_cleanup in non-verbose mode doesn't print details"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock container list showing remaining containers
            mock_run.return_value = Mock(
                returncode=0, stdout="cidx-abc123-ollama\texited"
            )

            # This should fail because the method doesn't exist yet (TDD red phase)
            result = docker_manager._validate_complete_cleanup(verbose=False)

            assert result is False
            # Should not print detailed container information when verbose=False
            mock_console.print.assert_not_called()

    def test_cleanup_integration_with_complete_validation_success(
        self, docker_manager, mock_console
    ):
        """Test that cleanup integrates complete validation for uninstall operations and succeeds"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(
                docker_manager, "_validate_complete_cleanup"
            ) as mock_complete_validate,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup mocks for successful cleanup
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_volumes.return_value = True
            mock_cleanup_data.return_value = True
            mock_validate.return_value = True
            mock_complete_validate.return_value = True  # Complete validation passes
            mock_force_cleanup.return_value = True
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = True
            mock_stop_data_cleaner.return_value = True
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            # Test uninstall operation (remove_data=True) with validation
            result = docker_manager.cleanup(
                remove_data=True, force=False, verbose=True, validate=True
            )

            assert result is True
            # Only complete validation should be called for uninstall operations (remove_data=True)
            mock_complete_validate.assert_called_with(True)

    def test_cleanup_integration_with_complete_validation_failure(
        self, docker_manager, mock_console
    ):
        """Test that cleanup integrates complete validation for uninstall operations and fails properly"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(
                docker_manager, "_validate_complete_cleanup"
            ) as mock_complete_validate,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup mocks for failed complete validation
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(returncode=0)
            mock_cleanup_volumes.return_value = True
            mock_cleanup_data.return_value = True
            mock_validate.return_value = True
            mock_complete_validate.return_value = False  # Complete validation fails
            mock_force_cleanup.return_value = True
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = True
            mock_stop_data_cleaner.return_value = True
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            # Test uninstall operation with validation failure
            result = docker_manager.cleanup(
                remove_data=True, force=False, verbose=True, validate=True
            )

            assert result is False  # Should fail due to complete validation failure
            mock_complete_validate.assert_called_with(True)
            # Should print warning about validation failure
            mock_console.print.assert_any_call(
                "⚠️  Complete cleanup validation failed - some cidx containers may still exist",
                style="yellow",
            )

    def test_cleanup_regular_operation_skips_complete_validation(
        self, docker_manager, mock_console
    ):
        """Test that regular cleanup operations (remove_data=False) skip complete validation"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(
                docker_manager, "_validate_complete_cleanup"
            ) as mock_complete_validate,
        ):
            # Setup mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(returncode=0)
            mock_validate.return_value = True

            # Test regular cleanup operation (remove_data=False)
            result = docker_manager.cleanup(
                remove_data=False, force=False, verbose=True, validate=True
            )

            assert result is True
            # For regular cleanup (remove_data=False), complete validation should not be called
            mock_complete_validate.assert_not_called()  # Should NOT be called for regular cleanup


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
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.side_effect = subprocess.TimeoutExpired("podman", 10)

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is False

    def test_permission_error_handling(self, docker_manager):
        """Test handling of permission errors during cleanup"""
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("shutil.rmtree") as mock_rmtree,
        ):
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


class TestComprehensiveErrorReporting:
    """Test comprehensive error reporting enhancements for Story 6"""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing"""
        return Mock(spec=Console)

    @pytest.fixture
    def docker_manager(self, mock_console):
        """Create a DockerManager instance for testing"""
        with patch("code_indexer.services.docker_manager.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path(str(get_local_tmp_dir() / "test"))
            manager = DockerManager(
                console=mock_console, project_name="test_shared", force_docker=False
            )
            return manager

    def test_force_cleanup_captures_docker_command_output_on_failure(
        self, docker_manager, mock_console
    ):
        """Test that force cleanup captures and reports Docker command outputs on failures"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock container listing success, but container kill/remove failures
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-abc123-ollama\ncidx-abc123-qdrant\n",
                    stderr="",
                ),  # List command succeeds
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: container not found: cidx-abc123-ollama",
                ),  # Kill fails
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: no container with name or ID cidx-abc123-ollama found: no such container",
                ),  # Remove fails
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: cannot kill container cidx-abc123-qdrant: container state improper",
                ),  # Kill fails
                Mock(returncode=0, stdout="", stderr=""),  # Remove succeeds
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is False
            # Should capture and report specific Docker command outputs on failures
            mock_console.print.assert_any_call(
                "❌ Failed to kill container cidx-abc123-ollama: Error: container not found: cidx-abc123-ollama",
                style="red",
            )
            mock_console.print.assert_any_call(
                "❌ Failed to remove container cidx-abc123-ollama: Error: no container with name or ID cidx-abc123-ollama found: no such container",
                style="red",
            )
            mock_console.print.assert_any_call(
                "❌ Failed to kill container cidx-abc123-qdrant: Error: cannot kill container cidx-abc123-qdrant: container state improper",
                style="red",
            )

    def test_cleanup_provides_comprehensive_status_summary(
        self, docker_manager, mock_console
    ):
        """Test that cleanup provides comprehensive status of cleanup results"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup partial failure scenario
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(
                returncode=1, stderr="Container removal failed: permission denied"
            )
            mock_cleanup_volumes.return_value = False  # Volume cleanup fails
            mock_cleanup_data.return_value = True  # Data cleanup succeeds
            mock_validate.return_value = False  # Validation fails
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = False  # Data cleaner fails
            mock_stop_data_cleaner.return_value = True
            mock_force_cleanup.return_value = True
            mock_runtime.return_value = "podman"
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            result = docker_manager.cleanup(
                remove_data=True, verbose=True, validate=True
            )

            assert result is False
            # Should provide comprehensive status summary reporting specific failures
            mock_console.print.assert_any_call(
                "📊 Cleanup Status Summary:", style="cyan"
            )
            mock_console.print.assert_any_call(
                "  ✅ Container Orchestration: Success", style="green"
            )
            mock_console.print.assert_any_call(
                "  ❌ Data Cleaner: Failed - Data cleaner reported failures",
                style="red",
            )
            mock_console.print.assert_any_call(
                "  ❌ Container Removal: Failed - Container removal failed: permission denied",
                style="red",
            )
            mock_console.print.assert_any_call(
                "  ✅ Data Directory Cleanup: Success", style="green"
            )
            mock_console.print.assert_any_call(
                "  ❌ Named Volume Cleanup: Failed - Named volume cleanup failed",
                style="red",
            )
            mock_console.print.assert_any_call(
                "  ❌ Cleanup Validation: Failed - Cleanup validation failed",
                style="red",
            )

    def test_cleanup_provides_actionable_guidance_for_failures(
        self, docker_manager, mock_console
    ):
        """Test that cleanup provides actionable guidance when manual cleanup is required"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_named_volumes"
            ) as mock_cleanup_volumes,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "_validate_cleanup") as mock_validate,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup failure scenario
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(returncode=1, stderr="permission denied")
            mock_cleanup_volumes.return_value = False
            mock_cleanup_data.return_value = False
            mock_validate.return_value = False
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = False
            mock_stop_data_cleaner.return_value = True
            mock_force_cleanup.return_value = True
            mock_runtime.return_value = "podman"
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            result = docker_manager.cleanup(
                remove_data=True, verbose=True, validate=True
            )

            assert result is False
            # Should provide actionable guidance
            mock_console.print.assert_any_call(
                "🔧 Manual Cleanup Required:", style="yellow"
            )
            mock_console.print.assert_any_call(
                "1. Check for remaining containers: podman ps -a --filter name=cidx-"
            )
            mock_console.print.assert_any_call(
                "2. Manually remove containers: podman rm -f <container-name>"
            )
            mock_console.print.assert_any_call(
                "3. Check for remaining volumes: podman volume ls --filter name=cidx-"
            )
            mock_console.print.assert_any_call(
                "4. Manually remove volumes: podman volume rm <volume-name>"
            )
            mock_console.print.assert_any_call(
                "5. Check for root-owned files: sudo find .code-indexer -user root"
            )
            mock_console.print.assert_any_call(
                "6. Remove root files: sudo rm -rf .code-indexer/qdrant/"
            )

    def test_data_cleaner_reports_specific_failures(self, docker_manager, mock_console):
        """Test that data cleaner reports specific container names and failure details"""
        with (
            patch.object(docker_manager, "start_data_cleaner") as mock_start,
            patch.object(
                docker_manager.health_checker, "wait_for_service_ready"
            ) as mock_health,
            patch("subprocess.run") as mock_run,
            patch.object(docker_manager, "_get_service_url") as mock_get_url,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
        ):
            mock_start.return_value = True
            mock_health.return_value = False  # Health check fails
            mock_get_url.return_value = "http://localhost:8091"
            mock_runtime.return_value = "podman"

            # Mock container status showing specific state
            mock_run.return_value = Mock(
                returncode=0, stdout="cidx-abc123-data-cleaner\texited(1)"
            )

            result = docker_manager.clean_with_data_cleaner(["/data/test"])

            assert result is False
            # Should report specific container name and failure details
            mock_console.print.assert_any_call(
                "❌ Data cleaner container failed: cidx-abc123-data-cleaner (state: exited(1))",
                style="red",
            )
            mock_console.print.assert_any_call(
                "💡 To debug: podman logs cidx-abc123-data-cleaner", style="blue"
            )

    def test_container_name_and_state_reporting_during_operations(
        self, docker_manager, mock_console
    ):
        """Test that container names and states are reported during operations"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock container listing with states
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-abc123-ollama\trunning\ncidx-abc123-qdrant\texited",
                    stderr="",
                ),  # List command with states
                Mock(returncode=0, stdout="", stderr=""),  # Kill container 1
                Mock(returncode=0, stdout="", stderr=""),  # Remove container 1
                Mock(returncode=0, stdout="", stderr=""),  # Kill container 2
                Mock(returncode=0, stdout="", stderr=""),  # Remove container 2
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is True
            # Should report specific container names and states during operations
            mock_console.print.assert_any_call("🔍 Found containers to cleanup:")
            mock_console.print.assert_any_call(
                "  - cidx-abc123-ollama (state: running)"
            )
            mock_console.print.assert_any_call("  - cidx-abc123-qdrant (state: exited)")
            mock_console.print.assert_any_call("🛑 Stopping and removing containers...")

    def test_docker_compose_command_output_captured_on_failure(
        self, docker_manager, mock_console
    ):
        """Test that docker-compose command outputs are captured and reported on failures"""
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(
                docker_manager, "clean_with_data_cleaner"
            ) as mock_data_cleaner,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_data_cleaner,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("code_indexer.config.ConfigManager") as mock_config_manager,
        ):
            # Setup docker-compose failure
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_compose_file.unlink = Mock()
            mock_run.return_value = Mock(
                returncode=1,
                stderr="Error: failed to remove network cidx-network: network is in use",
                stdout="",
            )
            mock_stop_main.return_value = True
            mock_data_cleaner.return_value = True
            mock_stop_data_cleaner.return_value = True
            mock_runtime.return_value = "podman"
            mock_config_manager.create_with_backtrack.return_value.load.return_value = (
                None
            )

            result = docker_manager.cleanup(remove_data=True, verbose=True)

            assert result is False
            # Should capture and report docker-compose command output on failure
            mock_console.print.assert_any_call(
                "❌ Container removal failed: Error: failed to remove network cidx-network: network is in use",
                style="red",
            )
            mock_console.print.assert_any_call(
                "💡 Manual network cleanup: podman network rm cidx-network --force",
                style="blue",
            )

    def test_volume_cleanup_reports_specific_volume_failures(
        self, docker_manager, mock_console
    ):
        """Test that volume cleanup reports specific volume names and failure details"""
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock volume listing and removal failures
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-abc123-qdrant-data\ncidx-abc123-ollama-models",
                    stderr="",
                ),  # List volumes
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: volume cidx-abc123-qdrant-data is being used",
                ),  # Remove volume 1 fails
                Mock(returncode=0, stdout="", stderr=""),  # Remove volume 2 succeeds
            ]

            result = docker_manager._cleanup_named_volumes(verbose=True)

            assert result is False
            # Should report specific volume names and failure details
            mock_console.print.assert_any_call("🗂️  Found named volumes to cleanup:")
            mock_console.print.assert_any_call("  - cidx-abc123-qdrant-data")
            mock_console.print.assert_any_call("  - cidx-abc123-ollama-models")
            mock_console.print.assert_any_call(
                "❌ Failed to remove volume cidx-abc123-qdrant-data: Error: volume cidx-abc123-qdrant-data is being used",
                style="red",
            )
            mock_console.print.assert_any_call(
                "✅ Removed volume: cidx-abc123-ollama-models", style="green"
            )


if __name__ == "__main__":
    pytest.main([__file__])
