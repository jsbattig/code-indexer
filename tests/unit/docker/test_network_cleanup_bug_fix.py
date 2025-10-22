#!/usr/bin/env python3
"""
TDD Tests for Network Cleanup Bug Fix - Networks left behind after uninstall operations

ISSUE: Networks like 'cidx-{hash}-network' are consistently left behind after uninstall
operations for both Docker and Podman. Manual cleanup required after uninstall completes.

These tests reproduce the network cleanup bug and define the expected behavior.
"""
import pytest
import subprocess
from unittest.mock import Mock, patch
from rich.console import Console
from code_indexer.services.docker_manager import DockerManager


class TestNetworkCleanupBugFix:
    """Test network cleanup bug fix during uninstall operations."""

    @pytest.fixture
    def docker_manager(self):
        """Create a DockerManager instance for testing."""
        console = Mock(spec=Console)
        return DockerManager(console=console, project_name="test_network_cleanup")

    @pytest.fixture
    def mock_console(self):
        """Mock console for testing output."""
        return Mock(spec=Console)

    def test_network_cleanup_fails_when_network_check_command_fails(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Network cleanup should handle network check command failures gracefully.

        Current implementation may not properly handle cases where the network ls command fails,
        causing the entire network cleanup to be skipped.
        """
        docker_manager.console = mock_console

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager.port_registry,
                "_calculate_project_hash",
                return_value="abc123",
            ),
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Mock config manager to force fallback to port registry calculation
            mock_config = Mock()
            mock_config.project_containers = None
            mock_config_mgr.return_value.load.return_value = mock_config
            # Mock: Container discovery finds containers, network check fails
            mock_run.side_effect = [
                # Container discovery succeeds
                Mock(
                    returncode=0,
                    stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\n",
                    stderr="",
                ),
                # Container kill operations succeed
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                # Container rm operations succeed
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                # Network check command FAILS (the bug scenario)
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: network command failed",
                ),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should return True despite network check failure - containers were cleaned
            assert result is True

            # Verify network check was attempted
            network_check_calls = [
                call
                for call in mock_run.call_args_list
                if "network" in str(call) and "ls" in str(call)
            ]
            assert len(network_check_calls) == 1

            # Should show warning about network cleanup failure
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            network_warning_messages = [
                call
                for call in console_calls
                if "network cleanup" in call.lower()
                and (
                    "error" in call.lower()
                    or "failed to check network existence" in call.lower()
                )
            ]
            assert (
                len(network_warning_messages) > 0
            ), f"Expected network cleanup error message, but console calls were: {console_calls}"

    def test_network_cleanup_fails_when_network_remove_fails_but_containers_succeed(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Network removal failure should not cause overall cleanup to fail if containers were cleaned.

        Current implementation may incorrectly fail the entire operation when network removal fails,
        even though containers were successfully removed.
        """
        docker_manager.console = mock_console

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="docker"
            ),
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager.port_registry,
                "_calculate_project_hash",
                return_value="xyz789",
            ),
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Mock config manager to force fallback to port registry calculation
            mock_config = Mock()
            mock_config.project_containers = None
            mock_config_mgr.return_value.load.return_value = mock_config
            # Mock: Container cleanup succeeds, network removal fails
            mock_run.side_effect = [
                # Container discovery succeeds
                Mock(
                    returncode=0,
                    stdout="cidx-xyz789-qdrant\tRunning\ncidx-xyz789-data-cleaner\tExited\n",
                    stderr="",
                ),
                # Container operations succeed
                Mock(returncode=0, stdout="", stderr=""),  # kill qdrant
                Mock(returncode=0, stdout="", stderr=""),  # rm qdrant
                Mock(
                    returncode=1, stdout="", stderr="already stopped"
                ),  # kill data-cleaner (expected failure)
                Mock(returncode=0, stdout="", stderr=""),  # rm data-cleaner
                # Network check succeeds - network exists
                Mock(
                    returncode=0,
                    stdout="cidx-xyz789-network\n",
                    stderr="",
                ),
                # Network removal FAILS (the bug scenario)
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Error: network in use by container",
                ),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should return True - containers were cleaned successfully even if network failed
            assert result is True

            # Verify network removal was attempted (filter out network ls calls)
            network_remove_calls = [
                call
                for call in mock_run.call_args_list
                if "network" in str(call)
                and "rm" in str(call)
                and "ls" not in str(call)
            ]
            assert len(network_remove_calls) == 1

            # Should show warning about network removal failure but not fail overall
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            network_failure_messages = [
                call
                for call in console_calls
                if "failed to remove network" in call.lower()
            ]
            assert (
                len(network_failure_messages) > 0
            ), f"Expected network removal failure message, but console calls were: {console_calls}"

    def test_network_cleanup_succeeds_for_both_docker_and_podman(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Network cleanup should work identically for both Docker and Podman engines.

        Current implementation should use the same network cleanup logic regardless of container engine.
        """
        docker_manager.console = mock_console

        for engine in ["docker", "podman"]:
            with (
                patch.object(
                    docker_manager, "_get_available_runtime", return_value=engine
                ),
                patch("subprocess.run") as mock_run,
                patch.object(
                    docker_manager.port_registry,
                    "_calculate_project_hash",
                    return_value="engine123",
                ),
                patch(
                    "code_indexer.config.ConfigManager.create_with_backtrack"
                ) as mock_config_mgr,
            ):
                # Mock config manager to force fallback to port registry calculation
                mock_config = Mock()
                mock_config.project_containers = None
                mock_config_mgr.return_value.load.return_value = mock_config
                # Mock: Complete successful cleanup
                mock_run.side_effect = [
                    # Container discovery
                    Mock(
                        returncode=0,
                        stdout="cidx-engine123-qdrant\tRunning\n",
                        stderr="",
                    ),
                    # Container operations
                    Mock(returncode=0, stdout="", stderr=""),  # kill
                    Mock(returncode=0, stdout="", stderr=""),  # rm
                    # Network operations
                    Mock(
                        returncode=0,
                        stdout="cidx-engine123-network\n",
                        stderr="",
                    ),  # network check
                    Mock(returncode=0, stdout="", stderr=""),  # network rm
                ]

                result = docker_manager._force_cleanup_containers(verbose=True)

                # Should succeed for both engines
                assert result is True, f"Network cleanup failed for {engine} engine"

                # Verify commands used correct engine
                all_calls = [str(call) for call in mock_run.call_args_list]
                engine_calls = [call for call in all_calls if engine in call]
                assert (
                    len(engine_calls) >= 4
                ), f"Expected {engine} commands for container and network operations"

                # Verify network-specific commands
                network_check_calls = [
                    call
                    for call in all_calls
                    if f"{engine}" in call and "network" in call and "ls" in call
                ]
                network_remove_calls = [
                    call
                    for call in all_calls
                    if f"{engine}" in call and "network" in call and "rm" in call
                ]

                assert (
                    len(network_check_calls) >= 1
                ), f"Expected at least 1 network check call for {engine}"
                assert (
                    len(network_remove_calls) >= 1
                ), f"Expected at least 1 network remove call for {engine}"

    def test_network_cleanup_uses_correct_project_hash_in_network_name(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Network cleanup should use the exact project hash in network name pattern.

        Verifies that the network name pattern 'cidx-{project_hash}-network' matches
        the project hash calculation logic.
        """
        docker_manager.console = mock_console
        project_hash = "test_hash_456"

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager.port_registry,
                "_calculate_project_hash",
                return_value=project_hash,
            ),
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Mock config manager to force fallback to port registry calculation
            mock_config = Mock()
            mock_config.project_containers = None  # Force fallback to port registry
            mock_config_mgr.return_value.load.return_value = mock_config
            # Mock: No containers, network cleanup only
            mock_run.side_effect = [
                # Container discovery finds nothing
                Mock(returncode=0, stdout="", stderr=""),
                # Network check finds the project network
                Mock(
                    returncode=0,
                    stdout=f"cidx-{project_hash}-network\n",
                    stderr="",
                ),
                # Network removal succeeds
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is True

            # Verify correct network name pattern was used
            network_check_calls = [
                call
                for call in mock_run.call_args_list
                if "network" in str(call) and "ls" in str(call)
            ]
            assert (
                len(network_check_calls) == 1
            ), f"Expected 1 network check call, got {len(network_check_calls)}. All calls: {mock_run.call_args_list}"

            network_check_cmd = network_check_calls[0][0][0]
            # Should filter by exact network name
            assert f"cidx-{project_hash}-network" in str(network_check_cmd)

            network_remove_calls = [
                call
                for call in mock_run.call_args_list
                if "network" in str(call)
                and "rm" in str(call)
                and "ls" not in str(call)
            ]
            assert len(network_remove_calls) == 1

            network_remove_cmd = network_remove_calls[0][0][0]
            # Should remove exact network name
            assert f"cidx-{project_hash}-network" in str(network_remove_cmd)

    def test_network_cleanup_handles_no_network_exists_scenario(
        self, docker_manager, mock_console
    ):
        """
        FAILING TEST: Network cleanup should handle scenarios where no project network exists.

        Should not fail when the project network doesn't exist (clean scenario).
        """
        docker_manager.console = mock_console

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="docker"
            ),
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.services.docker_manager.GlobalPortRegistry._calculate_project_hash",
                return_value="no_network_123",
            ),
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Mock config manager to force fallback to port registry calculation
            mock_config = Mock()
            mock_config.project_containers = None  # Force fallback to port registry
            mock_config_mgr.return_value.load.return_value = mock_config
            # Mock: Container cleanup succeeds, no network exists
            mock_run.side_effect = [
                # Container discovery finds containers
                Mock(
                    returncode=0,
                    stdout="cidx-no_network_123-qdrant\tRunning\n",
                    stderr="",
                ),
                # Container operations succeed
                Mock(returncode=0, stdout="", stderr=""),  # kill
                Mock(returncode=0, stdout="", stderr=""),  # rm
                # Network check finds no network (empty output)
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is True

            # Should attempt network check but no network removal
            network_check_calls = [
                call
                for call in mock_run.call_args_list
                if "network" in str(call) and "ls" in str(call)
            ]
            # Check for actual network rm commands (not container rm commands)
            network_remove_calls = []
            for call in mock_run.call_args_list:
                cmd = call[0][0]  # Get the command list
                if len(cmd) >= 3 and cmd[1] == "network" and cmd[2] == "rm":
                    network_remove_calls.append(call)

            assert len(network_check_calls) == 1
            assert (
                len(network_remove_calls) == 0
            )  # No removal attempt when network doesn't exist

            # Should show info message about no network found
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            no_network_messages = [
                call
                for call in console_calls
                if "no project network found" in call.lower()
                or "no network found" in call.lower()
            ]
            assert (
                len(no_network_messages) > 0
            ), f"Expected no network found message, but console calls were: {console_calls}"

    def test_network_cleanup_timeout_handling(self, docker_manager, mock_console):
        """
        FAILING TEST: Network cleanup should handle command timeouts gracefully.

        Network operations can timeout and should not crash the cleanup process.
        """
        docker_manager.console = mock_console

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
            patch.object(
                docker_manager.port_registry,
                "_calculate_project_hash",
                return_value="timeout_test",
            ),
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Mock config manager to force fallback to port registry calculation
            mock_config = Mock()
            mock_config.project_containers = None
            mock_config_mgr.return_value.load.return_value = mock_config
            # Mock: Container cleanup succeeds, network operations timeout
            mock_run.side_effect = [
                # Container discovery succeeds
                Mock(
                    returncode=0,
                    stdout="cidx-timeout_test-qdrant\tRunning\n",
                    stderr="",
                ),
                # Container operations succeed
                Mock(returncode=0, stdout="", stderr=""),  # kill
                Mock(returncode=0, stdout="", stderr=""),  # rm
                # Network check times out
                subprocess.TimeoutExpired("podman", 10),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should still return True - container cleanup succeeded
            assert result is True

            # Should show warning about network operation timeout
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]
            timeout_messages = [
                call
                for call in console_calls
                if "network cleanup" in call.lower()
                and ("timeout" in call.lower() or "timed out" in call.lower())
            ]
            assert (
                len(timeout_messages) > 0
            ), f"Expected network timeout message, but console calls were: {console_calls}"


if __name__ == "__main__":
    pytest.main([__file__])
