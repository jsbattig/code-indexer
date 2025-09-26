#!/usr/bin/env python3
"""
TDD Tests for enhanced force cleanup container states handling.
These tests demonstrate the current issues and define the expected behavior.
"""
import pytest
import subprocess
from unittest.mock import Mock, patch
from rich.console import Console
from code_indexer.services.docker_manager import DockerManager


class TestForceCleanupContainerStates:
    """Test force cleanup for different container states."""

    @pytest.fixture
    def docker_manager(self):
        """Create a DockerManager instance for testing."""
        console = Mock(spec=Console)
        return DockerManager(console=console, project_name="test_project")

    @pytest.fixture
    def mock_console(self):
        """Mock console for testing output."""
        return Mock(spec=Console)

    def test_cleanup_created_state_containers(self, docker_manager, mock_console):
        """Test that Created state containers (never started) are properly removed.

        FAILING TEST: Current implementation doesn't use --filter flag to find ALL containers.
        Created state containers block name reuse and must be removed.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock container listing with Created state container (NEW FORMAT: Name\tState)
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-18e970d8-ollama\tCreated\ncidx-18e970d8-qdrant\tExited\n",  # NEW: includes states
                    stderr="",
                ),  # List command
                Mock(
                    returncode=1, stdout="", stderr="No such container"
                ),  # Kill fails (Created state)
                Mock(returncode=0, stdout="", stderr=""),  # Remove succeeds
                Mock(returncode=0, stdout="", stderr=""),  # Kill container 2
                Mock(returncode=0, stdout="", stderr=""),  # Remove container 2
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should succeed even when kill fails for Created containers
            assert result is True

            # Verify the method was called with proper filter approach
            # FAILING: Current implementation doesn't use --filter "name=cidx-"
            calls = mock_run.call_args_list
            list_call = calls[0]

            # New implementation correctly uses project-scoped filtering with state info
            actual_cmd = list_call[0][0]

            # Verify command structure (project hash will be dynamic)
            assert actual_cmd[0] == "podman"
            assert actual_cmd[1] == "ps"
            assert actual_cmd[2] == "-a"
            assert actual_cmd[3] == "--format"
            assert actual_cmd[4] == "{{.Names}}\t{{.State}}"  # NEW: includes state
            assert actual_cmd[5] == "--filter"
            assert actual_cmd[6].startswith("name=cidx-")  # NEW: project-scoped
            assert actual_cmd[6].endswith(
                "-"
            )  # Ensures it ends with - for proper scoping

    def test_cleanup_mixed_container_states(self, docker_manager, mock_console):
        """Test cleanup handles mixed container states (Created, Running, Exited, Paused).

        FAILING TEST: Current implementation may not handle all states properly.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock multiple containers in different states (NEW FORMAT: Name\tState)
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-18e970d8-created-test\tCreated\ncidx-18e970d8-running-test\tRunning\ncidx-18e970d8-exited-test\tExited\ncidx-18e970d8-paused-test\tPaused\n",
                    stderr="",
                ),  # List command with enhanced format
                # Created container: kill fails, rm succeeds
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Cannot kill container: container not running",
                ),
                Mock(returncode=0, stdout="", stderr=""),
                # Running container: kill succeeds, rm succeeds
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                # Exited container: kill fails, rm succeeds
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Cannot kill container: container not running",
                ),
                Mock(returncode=0, stdout="", stderr=""),
                # Paused container: kill succeeds, rm succeeds
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                # Network cleanup: check network exists
                Mock(returncode=0, stdout="cidx-18e970d8-network\n", stderr=""),
                # Network cleanup: remove network
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should succeed for all container states
            assert result is True

            # Verify proper command sequence: 1 list + 4 containers × (kill + rm) + 2 network ops
            assert mock_run.call_count == 11  # 1 + 8 + 2

    def test_cleanup_container_with_exit_codes(self, docker_manager, mock_console):
        """Test cleanup handles containers with specific exit codes like 137.

        FAILING TEST: Current implementation should handle containers that exited with codes.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock containers that exited with different codes (NEW FORMAT: Name\tState)
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-18e970d8-exit137-test\tExited\ncidx-18e970d8-exit0-test\tExited\n",
                    stderr="",
                ),  # List command with enhanced format
                # Container with exit code 137: kill fails, rm succeeds
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Cannot kill container: container not running",
                ),
                Mock(returncode=0, stdout="", stderr=""),
                # Container with exit code 0: kill fails, rm succeeds
                Mock(
                    returncode=1,
                    stdout="",
                    stderr="Cannot kill container: container not running",
                ),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should handle containers with any exit code
            assert result is True

    def test_cleanup_comprehensive_error_handling(self, docker_manager, mock_console):
        """Test comprehensive error handling prevents partial cleanup failures.

        FAILING TEST: Current implementation may not handle all error scenarios properly.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock scenario where some operations fail (NEW FORMAT: Name\tState)
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-18e970d8-test1\tRunning\ncidx-18e970d8-test2\tCreated\ncidx-18e970d8-test3\tExited\n",
                    stderr="",
                ),  # List command with enhanced format
                # Container 1: kill succeeds, rm succeeds
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
                # Container 2: kill fails, rm fails - should continue with others
                Mock(returncode=1, stdout="", stderr="Kill failed"),
                Mock(returncode=1, stdout="", stderr="Remove failed"),
                # Container 3: kill fails, rm succeeds - should still succeed
                Mock(returncode=1, stdout="", stderr="Kill failed"),
                Mock(returncode=0, stdout="", stderr=""),
                # Network cleanup: check network exists
                Mock(returncode=0, stdout="cidx-18e970d8-network\n", stderr=""),
                # Network cleanup: remove network
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should return False when some removals fail, but continue processing all
            assert result is False  # One container completely failed

            # Should have attempted all containers
            assert mock_run.call_count == 9  # 1 list + 3 containers × 2 ops + 2 network ops

    def test_cleanup_uses_enhanced_filtering(self, docker_manager, mock_console):
        """Test that cleanup uses enhanced filtering to find ALL cidx containers.

        FAILING TEST: Current implementation doesn't use --filter "name=cidx-" approach.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="docker"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock enhanced discovery format
            mock_run.side_effect = [
                Mock(returncode=0, stdout="cidx-18e970d8-test1\tRunning\n", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),  # kill
                Mock(returncode=0, stdout="", stderr=""),  # rm
            ]

            docker_manager._force_cleanup_containers(verbose=True)

            # Verify the new implementation uses project-scoped filtering with state info
            list_call = mock_run.call_args_list[0]
            actual_cmd = list_call[0][0]

            # Verify command structure (project hash will be dynamic)
            assert actual_cmd[0] == "docker"
            assert actual_cmd[1] == "ps"
            assert actual_cmd[2] == "-a"
            assert actual_cmd[3] == "--format"
            assert actual_cmd[4] == "{{.Names}}	{{.State}}"  # NEW: includes state
            assert actual_cmd[5] == "--filter"
            assert actual_cmd[6].startswith("name=cidx-")  # NEW: project-scoped
            assert actual_cmd[6].endswith("-")  # Ensures proper scoping

    def test_cleanup_handles_timeout_scenarios(self, docker_manager, mock_console):
        """Test cleanup handles timeout scenarios gracefully.

        FAILING TEST: Current implementation may not handle timeouts properly.
        """
        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock timeout exception
            mock_run.side_effect = [
                Mock(
                    returncode=0, stdout="cidx-18e970d8-test1\tRunning\n", stderr=""
                ),  # List succeeds with enhanced format
                subprocess.TimeoutExpired("podman", 10),  # Kill times out
                Mock(returncode=0, stdout="", stderr=""),  # Remove succeeds
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            # Should handle timeout gracefully and continue
            assert result is True  # Should succeed despite timeout

    def test_cleanup_verbose_output_for_all_states(self, docker_manager, mock_console):
        """Test verbose output provides clear feedback for all container states.

        FAILING TEST: Current implementation may not provide detailed state-aware output.
        """
        docker_manager.console = mock_console

        with (
            patch.object(
                docker_manager, "_get_available_runtime", return_value="podman"
            ),
            patch("subprocess.run") as mock_run,
        ):
            # Mock containers with state info (NEW FORMAT: Name\tState)
            mock_run.side_effect = [
                Mock(
                    returncode=0,
                    stdout="cidx-18e970d8-created\tCreated\ncidx-18e970d8-running\tRunning\n",
                    stderr="",
                ),
                # Created: kill fails, rm succeeds
                Mock(returncode=1, stdout="", stderr="Cannot kill: not running"),
                Mock(returncode=0, stdout="", stderr=""),
                # Running: kill succeeds, rm succeeds
                Mock(returncode=0, stdout="", stderr=""),
                Mock(returncode=0, stdout="", stderr=""),
            ]

            result = docker_manager._force_cleanup_containers(verbose=True)

            assert result is True

            # Should provide clear feedback about container removal
            print_calls = [call[0][0] for call in mock_console.print.call_args_list]

            # Should indicate successful removal for both containers
            removed_messages = [
                msg for msg in print_calls if "Removed container" in msg
            ]
            assert len(removed_messages) == 2
            assert "cidx-18e970d8-created" in str(removed_messages)
            assert "cidx-18e970d8-running" in str(removed_messages)
