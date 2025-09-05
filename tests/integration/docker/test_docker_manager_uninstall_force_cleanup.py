#!/usr/bin/env python3
"""
TDD Tests for Docker cleanup bug fix - Story 2: Mandatory Force Cleanup for Uninstall Operations

These tests demonstrate that force cleanup should ALWAYS run for uninstall operations (remove_data=True)
regardless of docker-compose down results, ensuring no containers are left behind.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from rich.console import Console

from ...conftest import get_local_tmp_dir
from code_indexer.services.docker_manager import DockerManager


class TestUninstallForceCleanup:
    """Test mandatory force cleanup for uninstall operations"""

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
                console=mock_console, project_name="test_uninstall", force_docker=False
            )
            return manager

    def test_force_cleanup_runs_when_uninstall_and_compose_down_succeeds(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Force cleanup should run for uninstall (remove_data=True) even when compose down succeeds

        This tests the MANDATORY aspect - force cleanup should ALWAYS run for uninstall operations,
        not just when docker-compose down fails.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
        ):
            # Setup: Compose down SUCCEEDS (returncode=0)
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")  # SUCCESS
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True
            mock_force_cleanup.return_value = True

            # Act: Call cleanup with remove_data=True (uninstall operation)
            docker_manager.cleanup(remove_data=True, force=False, verbose=True)

            # Assert: Force cleanup should be called even though compose down succeeded
            mock_force_cleanup.assert_called_once_with(True)

            # Verify console message about mandatory force cleanup
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            mandatory_cleanup_messages = [
                call
                for call in console_calls
                if "mandatory force cleanup for uninstall" in call.lower()
            ]
            assert len(mandatory_cleanup_messages) > 0, (
                f"Expected 'mandatory force cleanup for uninstall' message, "
                f"but console calls were: {console_calls}"
            )

    def test_force_cleanup_runs_when_uninstall_and_compose_down_fails(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Force cleanup should run for uninstall (remove_data=True) when compose down fails

        This ensures that even if docker-compose down fails completely,
        force cleanup still runs to remove containers.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
        ):
            # Setup: Compose down FAILS (returncode=1)
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Error: No such container: cidx-abc123-ollama",
            )  # FAILURE
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True
            mock_force_cleanup.return_value = True

            # Act: Call cleanup with remove_data=True (uninstall operation)
            docker_manager.cleanup(remove_data=True, force=False, verbose=True)

            # Assert: Force cleanup should still be called despite compose down failure
            mock_force_cleanup.assert_called_once_with(True)

    def test_force_cleanup_does_not_run_for_regular_cleanup_when_compose_succeeds(
        self, docker_manager, mock_console
    ):
        """
        Test that regular cleanup (remove_data=False) does NOT trigger force cleanup when compose succeeds

        This ensures we don't break existing behavior - force cleanup should only be mandatory for uninstall.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
        ):
            # Setup: Regular cleanup (remove_data=False), compose down succeeds
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(returncode=0, stdout="", stderr="")  # SUCCESS
            mock_force_cleanup.return_value = True

            # Act: Call cleanup with remove_data=False (regular cleanup)
            docker_manager.cleanup(remove_data=False, force=False, verbose=True)

            # Assert: Force cleanup should NOT be called for regular cleanup when compose succeeds
            mock_force_cleanup.assert_not_called()

    def test_force_cleanup_handles_containers_in_different_states(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Force cleanup should handle containers in any state during uninstall

        Tests that force cleanup works with containers in Created, Running, Exited, and Paused states.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
        ):
            # Setup: Various container states
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True
            mock_runtime.return_value = "podman"

            # Mock subprocess calls for different scenarios
            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]
                if "ps" in cmd and "-a" in cmd:
                    # Return containers in different states
                    return Mock(
                        returncode=0,
                        stdout="cidx-abc123-ollama\ncidx-abc123-qdrant\ncidx-abc123-data-cleaner\n",
                        stderr="",
                    )
                elif "kill" in cmd:
                    # Some containers may already be stopped (kill fails)
                    if "ollama" in str(cmd):
                        return Mock(
                            returncode=1, stderr="No such container"
                        )  # Already stopped
                    return Mock(returncode=0, stdout="", stderr="")
                elif "rm" in cmd:
                    # Remove should succeed for all containers
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    # Compose down fails (triggering the issue)
                    return Mock(returncode=1, stderr="Compose down failed")

            mock_run.side_effect = mock_subprocess_calls

            # Act: Call cleanup with remove_data=True (uninstall operation)
            docker_manager.cleanup(remove_data=True, force=False, verbose=True)

            # Assert: Should succeed despite mixed container states
            # The key is that force cleanup runs and handles all containers
            container_related_calls = [
                call
                for call in mock_run.call_args_list
                if any(cmd in str(call) for cmd in ["ps", "kill", "rm"])
            ]
            # Should have: 1 ps call + multiple kill/rm calls for containers
            assert (
                len(container_related_calls) >= 4
            )  # At least ps + kill/rm for multiple containers

    def test_uninstall_requires_no_manual_cleanup_after_completion(
        self, docker_manager, mock_console
    ):
        """
        UPDATED TEST: After uninstall completion, no manual cleanup should be required

        This test ensures that the uninstall process is complete and leaves no containers behind.
        Updated to work with the new comprehensive project hash-based discovery.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            # Mock the project configuration for the new scoped approach
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup project config for the new implementation
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "abc123"
            mock_config.project_containers.qdrant_name = "cidx-abc123-qdrant"
            mock_config.project_containers.ollama_name = "cidx-abc123-ollama"
            mock_config.project_containers.data_cleaner_name = (
                "cidx-abc123-data-cleaner"
            )
            mock_config_mgr.return_value.load.return_value = mock_config

            # Setup for complete uninstall scenario
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True
            mock_runtime.return_value = "podman"

            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-abc123-qdrant",
                    "ollama": "cidx-abc123-ollama",
                    "data-cleaner": "cidx-abc123-data-cleaner",
                }[service]

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]

                    if "down" in cmd:
                        # Compose down fails (the scenario that triggers force cleanup)
                        return Mock(returncode=1, stderr="Compose down failed")
                    elif (
                        "ps" in cmd and "-a" in cmd and "name=cidx-abc123-" in str(cmd)
                    ):
                        # NEW: Comprehensive discovery - return all containers with project hash
                        return Mock(
                            returncode=0,
                            stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\ncidx-abc123-data-cleaner\tRunning\n",
                            stderr="",
                        )
                    elif "kill" in cmd or "rm" in cmd:
                        # Force cleanup operations succeed
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act: Perform uninstall
                docker_manager.cleanup(remove_data=True, force=False, verbose=True)

                # Assert: All containers should be removed by force cleanup
                # Verify that container removal operations were called
                kill_calls = [
                    call for call in mock_run.call_args_list if "kill" in str(call)
                ]
                rm_calls = [
                    call for call in mock_run.call_args_list if "rm" in str(call)
                ]

                # Should have attempted to kill and remove containers (3 containers found via comprehensive discovery)
                assert (
                    len(kill_calls) >= 3
                ), f"Expected kill operations for 3 discovered containers, got: {kill_calls}"
                assert (
                    len(rm_calls) >= 3
                ), f"Expected rm operations for 3 discovered containers, got: {rm_calls}"

                # Verify only project-specific containers were targeted
                all_operations = kill_calls + rm_calls
                project_operations = [
                    op for op in all_operations if "cidx-abc123" in str(op)
                ]
                assert len(project_operations) == len(
                    all_operations
                ), f"All operations should be project-scoped, but found: {all_operations}"

    def test_verbose_messages_indicate_mandatory_force_cleanup(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Verbose output should clearly indicate mandatory force cleanup for uninstall

        Users should understand that force cleanup always runs during uninstall operations.
        """
        with (
            patch.object(docker_manager, "get_compose_command") as mock_compose_cmd,
            patch.object(docker_manager, "compose_file") as mock_compose_file,
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup,
            patch.object(
                docker_manager, "_cleanup_data_directories"
            ) as mock_cleanup_data,
            patch.object(docker_manager, "stop_main_services") as mock_stop_main,
            patch.object(docker_manager, "clean_with_data_cleaner") as mock_clean_data,
            patch.object(docker_manager, "stop_data_cleaner") as mock_stop_cleaner,
        ):
            # Setup
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_run.return_value = Mock(returncode=0)  # Compose succeeds
            mock_force_cleanup.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True

            # Act: Call cleanup with verbose=True
            docker_manager.cleanup(remove_data=True, force=False, verbose=True)

            # Assert: Should show mandatory force cleanup message
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            mandatory_messages = [
                call
                for call in console_calls
                if "mandatory" in call.lower()
                and "force cleanup" in call.lower()
                and "uninstall" in call.lower()
            ]
            assert len(mandatory_messages) > 0, (
                f"Expected mandatory force cleanup message for uninstall, "
                f"but console calls were: {console_calls}"
            )


if __name__ == "__main__":
    pytest.main([__file__])
