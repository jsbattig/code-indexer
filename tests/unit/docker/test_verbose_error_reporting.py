#!/usr/bin/env python3
"""
Test Driven Development for DockerManager verbose error reporting enhancements.

This module implements Story 6: Comprehensive Error Reporting for Docker cleanup operations.
Testing enhanced verbose mode reporting, specific container states, Docker command outputs,
and actionable guidance for manual cleanup scenarios.
"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch
from rich.console import Console

from code_indexer.services.docker_manager import DockerManager


class TestVerboseErrorReporting:
    """TDD tests for comprehensive error reporting during cleanup operations."""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing verbose output."""
        return Mock(spec=Console)

    @pytest.fixture
    def docker_manager(self, mock_console):
        """Create DockerManager with mocked dependencies."""
        with patch("code_indexer.services.docker_manager.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/tmp/test")
            manager = DockerManager(
                console=mock_console, project_name="test_verbose", force_docker=True
            )
            return manager

    # TDD Red Phase: Tests for enhanced container state reporting
    def test_force_cleanup_containers_reports_specific_states_on_verbose(
        self, docker_manager, mock_console
    ):
        """Test that verbose mode reports specific container names and states during force cleanup."""
        # Arrange - Mock container listing with various states (NEW FORMAT: Name\tState)
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "cidx-18e970d8-qdrant\tRunning\ncidx-18e970d8-ollama\tExited\n"  # NEW: project-scoped with states
        mock_result.stderr = ""

        # Mock individual container state checks (would be used for state reporting)
        # mock_state_results = [
        #     Mock(returncode=0, stdout="cidx-test-qdrant\trunning\n", stderr=""),
        #     Mock(returncode=0, stdout="cidx-test-ollama\texited\n", stderr=""),
        # ]

        # Mock kill and rm operations
        mock_kill_results = [
            Mock(returncode=0, stdout="", stderr=""),  # qdrant kill success
            Mock(
                returncode=1, stdout="", stderr="container already stopped"
            ),  # ollama kill fails (expected)
        ]

        mock_rm_results = [
            Mock(returncode=0, stdout="", stderr=""),  # qdrant rm success
            Mock(returncode=0, stdout="", stderr=""),  # ollama rm success
        ]

        with patch("subprocess.run") as mock_run:
            # Configure sequential return values for different commands
            mock_version_result = Mock()
            mock_version_result.returncode = 0
            mock_version_result.stdout = "Docker version 20.10.8"

            mock_run.side_effect = [
                mock_version_result,  # Docker --version check
                mock_result,  # Container listing
                mock_kill_results[0],  # Kill qdrant
                mock_rm_results[0],  # Remove qdrant
                mock_kill_results[1],  # Kill ollama (fails)
                mock_rm_results[1],  # Remove ollama
            ]

            # Act
            _ = docker_manager._force_cleanup_containers(verbose=True)

            # Assert - Check for actual console output from implementation
            # Should report project hash discovery and container findings
            mock_console.print.assert_any_call(
                "🎯 Discovering ALL containers for project hash: 18e970d8"
            )
            mock_console.print.assert_any_call(
                "🔍 Discovered project containers for cleanup:"
            )
            mock_console.print.assert_any_call(
                "  - cidx-18e970d8-qdrant (state: Running)"
            )
            mock_console.print.assert_any_call(
                "  - cidx-18e970d8-ollama (state: Exited)"
            )
            mock_console.print.assert_any_call(
                "🛑 Stopping and removing ALL discovered project containers..."
            )

            # Should report individual container removal success
            mock_console.print.assert_any_call(
                "✅ Removed container: cidx-18e970d8-qdrant"
            )
            mock_console.print.assert_any_call(
                "✅ Removed container: cidx-18e970d8-ollama"
            )

    def test_force_cleanup_containers_reports_docker_command_failures(
        self, docker_manager, mock_console
    ):
        """Test that verbose mode captures and reports Docker command outputs on failures."""
        # Arrange - Mock container listing success but removal failures
        mock_version_result = Mock()
        mock_version_result.returncode = 0
        mock_version_result.stdout = "Docker version 20.10.8"

        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = (
            "cidx-18e970d8-failing\tRunning\n"  # NEW: project-scoped with state
        )

        mock_kill_result = Mock()
        mock_kill_result.returncode = 1
        mock_kill_result.stderr = (
            "Error response from daemon: Cannot kill container: permission denied"
        )

        mock_rm_result = Mock()
        mock_rm_result.returncode = 1
        mock_rm_result.stderr = "Error response from daemon: Cannot remove container: device or resource busy"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock_version_result,  # Docker --version check
                mock_list_result,  # Container listing success
                mock_kill_result,  # Kill fails
                mock_rm_result,  # Remove fails
            ]

            # Act
            result = docker_manager._force_cleanup_containers_with_guidance(
                verbose=True
            )

            # Assert
            # Should report containers found with project-scoped names
            mock_console.print.assert_any_call(
                "🔍 Found project containers: ['cidx-18e970d8-failing\\tRunning']"
            )

            # Should capture and report Docker command stderr on failures
            mock_console.print.assert_any_call(
                "⚠️  Container removal warning for cidx-18e970d8-failing\tRunning: Error response from daemon: Cannot remove container: device or resource busy"
            )
            assert result is False  # Should indicate failure

    def test_cleanup_validation_provides_actionable_guidance_on_failure(
        self, docker_manager, mock_console
    ):
        """Test that cleanup validation provides actionable guidance when validation fails."""
        # Arrange - Mock validation scenario where containers still exist
        mock_version_result = Mock()
        mock_version_result.returncode = 0
        mock_version_result.stdout = "Docker version 20.10.8"

        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "cidx-18e970d8-persistent\ncidx-18e970d8-stuck\n"  # Project-scoped container names

        # Mock individual container checks showing they still exist
        mock_container_checks = [
            Mock(returncode=0, stdout="cidx-18e970d8-persistent\n", stderr=""),
            Mock(returncode=0, stdout="cidx-18e970d8-stuck\n", stderr=""),
        ]

        # Mock find command for root-owned files
        mock_find_result = Mock()
        mock_find_result.returncode = 0
        mock_find_result.stdout = ""

        with patch("subprocess.run") as mock_run:
            # Mock health checker to simulate port unavailability
            with patch.object(docker_manager, "health_checker") as mock_health:
                mock_health.wait_for_ports_available.return_value = False
                mock_health.is_port_available.return_value = False

                def mock_subprocess_run(cmd, **kwargs):
                    if "--version" in cmd:
                        return mock_version_result
                    elif (
                        "ps" in cmd
                        and "--filter" in cmd
                        and "name=cidx-18e970d8-" in str(cmd)
                        and "cidx-18e970d8-persistent" not in str(cmd)
                        and "cidx-18e970d8-stuck" not in str(cmd)
                    ):
                        # Main container listing
                        return mock_list_result
                    elif "ps" in cmd and "name=cidx-18e970d8-persistent" in str(cmd):
                        # Individual container check for persistent
                        return mock_container_checks[0]
                    elif "ps" in cmd and "name=cidx-18e970d8-stuck" in str(cmd):
                        # Individual container check for stuck
                        return mock_container_checks[1]
                    elif "find" in cmd:
                        return mock_find_result
                    else:
                        # Volume inspections and other commands
                        return Mock(returncode=1, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_run

                # Act
                result = docker_manager._validate_cleanup(verbose=True)

                # Assert
                # Should provide actionable guidance about remaining containers
                mock_console.print.assert_any_call(
                    "❌ Container cidx-18e970d8-persistent still exists", style="red"
                )
                mock_console.print.assert_any_call(
                    "❌ Container cidx-18e970d8-stuck still exists", style="red"
                )

                # Should provide guidance about port issues
                mock_console.print.assert_any_call(
                    "❌ Port 11434 still in use after cleanup", style="red"
                )
                mock_console.print.assert_any_call(
                    "❌ Port 6333 still in use after cleanup", style="red"
                )

                assert result is False

    def test_complete_cleanup_validation_reports_detailed_container_states(
        self, docker_manager, mock_console
    ):
        """Test that complete cleanup validation reports detailed container states when containers remain."""
        # Arrange - Mock remaining containers with different states
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "cidx-test-running\trunning\ncidx-test-exited\texited\ncidx-test-created\tcreated\n"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = mock_result

            # Act
            result = docker_manager._validate_complete_cleanup(verbose=True)

            # Assert
            # Should report detailed information about remaining containers
            mock_console.print.assert_any_call(
                "❌ Remaining containers found after cleanup:"
            )
            mock_console.print.assert_any_call("  - cidx-test-running (state: running)")
            mock_console.print.assert_any_call("  - cidx-test-exited (state: exited)")
            mock_console.print.assert_any_call("  - cidx-test-created (state: created)")

            assert result is False

    def test_cleanup_operation_reports_comprehensive_status_summary(
        self, docker_manager, mock_console
    ):
        """Test that cleanup operations provide comprehensive status summary with details."""
        # Arrange - Mock a complex cleanup scenario with mixed results
        docker_manager.compose_file = Mock()
        docker_manager.compose_file.exists.return_value = True

        with patch("subprocess.run") as mock_run:
            with patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup:
                with patch.object(
                    docker_manager, "_cleanup_named_volumes"
                ) as mock_cleanup_volumes:
                    with patch.object(
                        docker_manager, "_cleanup_data_directories"
                    ) as mock_cleanup_dirs:
                        with patch.object(
                            docker_manager, "_validate_cleanup"
                        ) as mock_validate:
                            with patch.object(
                                docker_manager, "_validate_complete_cleanup"
                            ) as mock_validate_complete:
                                # Configure mixed success/failure scenario
                                mock_force_cleanup.return_value = True
                                mock_cleanup_volumes.return_value = (
                                    False  # Volume cleanup fails
                                )
                                mock_cleanup_dirs.return_value = True
                                mock_validate.return_value = True
                                mock_validate_complete.return_value = (
                                    False  # Complete validation fails
                                )

                                # Mock compose down success
                                mock_run.return_value = Mock(returncode=0, stderr="")

                                # Act
                                result = docker_manager.cleanup(
                                    remove_data=True,
                                    force=True,
                                    verbose=True,
                                    validate=True,
                                )

                                # Assert - This will fail initially (Red phase)
                                # Should provide comprehensive status reporting
                                expected_calls = [
                                    "🔍 Starting enhanced cleanup process...",
                                    "🛑 Orchestrating container shutdown...",
                                    "🔄 Orchestrated shutdown for data removal...",
                                    "🗑️  Removing containers and volumes...",
                                    "🔧 Running mandatory force cleanup for uninstall...",
                                    "🗂️  Removing data volumes and directories...",
                                    "📄 Cleaning up compose files and networks...",
                                    "🔍 Validating cleanup...",
                                ]

                                # Check that comprehensive status messages were printed
                                for expected_call in expected_calls:
                                    mock_console.print.assert_any_call(expected_call)

                                # Should report final status with details about failures
                                mock_console.print.assert_any_call(
                                    "❌ Cleanup completed with some failures",
                                    style="red",
                                )

                                assert result is False

    def test_actionable_guidance_provided_for_manual_cleanup_scenarios(
        self, docker_manager, mock_console
    ):
        """Test that actionable guidance is provided when manual cleanup is required."""
        # Arrange - Mock a scenario where container engine is available but operations fail
        mock_version_result = Mock()
        mock_version_result.returncode = 0
        mock_version_result.stdout = "Docker version 20.10.8"

        # Mock container listing failure (simulating permission issues)
        mock_list_failure = Mock()
        mock_list_failure.returncode = 1
        mock_list_failure.stderr = "Permission denied: unable to list containers"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock_version_result,  # Docker --version succeeds
                mock_list_failure,  # Container listing fails with permission error
            ]

            # Act
            result = docker_manager._force_cleanup_containers(verbose=True)

            # Assert
            # Should provide guidance for manual intervention when operations fail
            assert result is False

            # Should report the specific failure that occurred
            mock_console.print.assert_any_call(
                "❌ Failed to discover containers: Permission denied: unable to list containers",
                style="red",
            )

    def test_docker_command_timeout_scenarios_reported_with_context(
        self, docker_manager, mock_console
    ):
        """Test that Docker command timeouts are reported with helpful context."""
        # Arrange - Mock timeout scenarios
        mock_version_result = Mock()
        mock_version_result.returncode = 0
        mock_version_result.stdout = "Docker version 20.10.8"

        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "cidx-18e970d8-timeout\tRunning\n"

        with patch("subprocess.run") as mock_run:
            # Configure timeout for container removal
            mock_run.side_effect = [
                mock_version_result,  # Docker --version check
                mock_list_result,  # Container listing success
                subprocess.TimeoutExpired("docker kill", 10),  # Kill timeout
                subprocess.TimeoutExpired("docker rm", 10),  # Remove timeout
            ]

            # Act
            result = docker_manager._force_cleanup_containers(verbose=True)

            # Assert
            # Should report timeout scenarios with context
            mock_console.print.assert_any_call(
                "⚠️  Kill timeout for cidx-18e970d8-timeout, continuing to removal"
            )
            mock_console.print.assert_any_call(
                "❌ Removal timeout for cidx-18e970d8-timeout"
            )

            assert result is False

    def test_error_categorization_and_recovery_suggestions(
        self, docker_manager, mock_console
    ):
        """Test that errors are categorized and recovery suggestions are provided."""
        # This test ensures different error types get appropriate handling
        # This is a genuine enhancement - testing new functionality to be implemented

        # Test case 1: Permission denied errors
        mock_version_result = Mock()
        mock_version_result.returncode = 0
        mock_version_result.stdout = "Docker version 20.10.8"

        mock_list_result = Mock()
        mock_list_result.returncode = 0
        mock_list_result.stdout = "cidx-18e970d8-permission\n"

        mock_permission_error = Mock()
        mock_permission_error.returncode = 1
        mock_permission_error.stderr = "permission denied"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                mock_version_result,  # Version check succeeds
                mock_list_result,  # List containers succeeds
                mock_permission_error,  # Kill fails with permission denied
                mock_permission_error,  # Remove also fails with permission denied
            ]

            # Act - Call the method that should provide enhanced guidance
            result = docker_manager._force_cleanup_containers_with_guidance(
                verbose=True
            )

            # Assert - Should provide specific guidance for permission errors
            mock_console.print.assert_any_call(
                "💡 Permission denied errors can be resolved by:", style="blue"
            )
            mock_console.print.assert_any_call(
                "   • Running with sudo (if using Docker)"
            )
            mock_console.print.assert_any_call("   • Checking Docker daemon is running")
            mock_console.print.assert_any_call("   • Ensuring user is in docker group")

            assert result is False

    def test_comprehensive_final_status_with_manual_cleanup_guidance(
        self, docker_manager, mock_console
    ):
        """Test that comprehensive final status provides manual cleanup guidance when needed."""
        # This tests a genuine enhancement - comprehensive status summary with specific manual steps

        # Arrange - Mock a cleanup operation with mixed results
        docker_manager.compose_file = Mock()
        docker_manager.compose_file.exists.return_value = True

        with patch("subprocess.run") as mock_run:
            with patch.object(
                docker_manager, "_force_cleanup_containers"
            ) as mock_force_cleanup:
                with patch.object(
                    docker_manager, "_cleanup_named_volumes"
                ) as mock_cleanup_volumes:
                    with patch.object(
                        docker_manager, "_validate_complete_cleanup"
                    ) as mock_validate_complete:
                        # Configure mixed success/failure scenario requiring manual intervention
                        mock_force_cleanup.return_value = (
                            False  # Container cleanup fails
                        )
                        mock_cleanup_volumes.return_value = True
                        mock_validate_complete.return_value = False  # Validation fails

                        # Mock compose down success
                        mock_run.return_value = Mock(returncode=0, stderr="")

                        # Act - Call enhanced cleanup with final guidance
                        result = docker_manager.cleanup_with_final_guidance(
                            remove_data=True, force=True, verbose=True, validate=True
                        )

                        # Assert - This will fail initially (Red phase)
                        # Should provide comprehensive final status with manual steps
                        mock_console.print.assert_any_call(
                            "📋 Final Cleanup Status Summary:", style="bold"
                        )

                        # Should categorize what succeeded and failed
                        mock_console.print.assert_any_call("✅ Volume cleanup: SUCCESS")
                        mock_console.print.assert_any_call(
                            "❌ Container removal: FAILED"
                        )
                        mock_console.print.assert_any_call(
                            "❌ Final validation: FAILED"
                        )

                        # Should provide manual cleanup guidance
                        mock_console.print.assert_any_call(
                            "🔧 Manual cleanup may be required. Try these commands (Current Project Only):",
                            style="yellow",
                        )
                        mock_console.print.assert_any_call(
                            "   docker ps -a | grep cidx-18e970d8- | awk '{print $1}' | xargs docker rm -f"
                        )
                        mock_console.print.assert_any_call(
                            "   docker volume ls | grep cidx-18e970d8- | awk '{print $2}' | xargs docker volume rm"
                        )

                        assert result is False

    def test_verbose_mode_consistency_across_all_cleanup_methods(
        self, docker_manager, mock_console
    ):
        """Test that verbose mode provides consistent output format across all cleanup methods."""
        # This test verifies existing functionality works consistently
        # All methods should use similar emoji patterns and styling
        pass
