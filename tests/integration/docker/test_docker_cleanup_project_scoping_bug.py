#!/usr/bin/env python3
"""
TDD Tests for Docker cleanup project scoping bug - CRITICAL BUG FIX

These tests demonstrate the critical bug where `_force_cleanup_containers()`
removes containers from OTHER projects instead of being scoped to the current project.

EVIDENCE FROM MANUAL TESTING:
The uninstall command removed containers from multiple projects:
  - cidx-2ec48a67-qdrant (state: running)     ← Different project!
  - cidx-2ec48a67-data-cleaner (state: running) ← Different project!
  - cidx-18e970d8-data-cleaner (state: running) ← Different project!
  - cidx-18e970d8-qdrant (state: running)     ← Different project!

ROOT CAUSE: _force_cleanup_containers() uses --filter "name=cidx-" which finds
ALL cidx containers system-wide, not just the current project's containers.

REQUIRED FIX: Only target containers for the current project using project-specific
container names from the current project configuration.
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from rich.console import Console

from ...conftest import get_local_tmp_dir
from code_indexer.services.docker_manager import DockerManager


class TestDockerCleanupProjectScoping:
    """Test that Docker cleanup only affects the current project's containers"""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing"""
        return Mock(spec=Console)

    @pytest.fixture
    def project_config_dict(self):
        """Mock project configuration dictionary"""
        return {
            "qdrant_name": "cidx-current123-qdrant",
            "ollama_name": "cidx-current123-ollama",
            "data_cleaner_name": "cidx-current123-data-cleaner",
        }

    @pytest.fixture
    def other_project_config_dict(self):
        """Mock configuration for other projects that should NOT be affected"""
        return {
            "qdrant_name": "cidx-other456-qdrant",
            "ollama_name": "cidx-other456-ollama",
            "data_cleaner_name": "cidx-other456-data-cleaner",
        }

    @pytest.fixture
    def docker_manager(self, mock_console):
        """Create a DockerManager instance for testing"""
        with patch("code_indexer.services.docker_manager.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path(str(get_local_tmp_dir() / "test"))
            manager = DockerManager(
                console=mock_console,
                project_name="test_project_scoping",
                force_docker=False,
            )
            return manager

    def test_force_cleanup_should_only_target_current_project_containers(
        self, docker_manager, mock_console, project_config_dict
    ):
        """
        FAILING TEST: _force_cleanup_containers should only target current project's containers

        This test demonstrates that the current implementation incorrectly targets
        ALL cidx containers system-wide instead of only the current project's containers.
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch.object(docker_manager, "get_container_name") as mock_get_name,
        ):
            # Setup
            mock_runtime.return_value = "podman"

            # Mock the current project's container names
            mock_get_name.side_effect = lambda service, config: {
                "qdrant": "cidx-current123-qdrant",
                "ollama": "cidx-current123-ollama",
                "data-cleaner": "cidx-current123-data-cleaner",
            }[service]

            # Mock subprocess.run to simulate finding containers from multiple projects
            # This is what currently happens - it finds ALL cidx containers
            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]
                if (
                    "ps" in cmd
                    and "-a" in cmd
                    and "--filter" in cmd
                    and "name=cidx-" in cmd
                ):
                    # CURRENT BUGGY BEHAVIOR: Returns containers from ALL projects
                    return Mock(
                        returncode=0,
                        stdout="cidx-current123-qdrant\tcidx-current123-ollama\tcidx-other456-qdrant\tcidx-other456-ollama\tcidx-different789-qdrant\n",
                        stderr="",
                    )
                elif "kill" in cmd or "rm" in cmd:
                    # Container operations
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act: Call _force_cleanup_containers with project configuration
            _ = docker_manager._force_cleanup_containers(verbose=True)

            # Current implementation behavior - this will FAIL because it targets other projects
            # Get all the kill/rm calls made (check actual command, not string representation)
            kill_calls = [
                call
                for call in mock_run.call_args_list
                if call.args
                and len(call.args) > 0
                and len(call.args[0]) > 1
                and call.args[0][1] == "kill"
            ]
            rm_calls = [
                call
                for call in mock_run.call_args_list
                if call.args
                and len(call.args) > 0
                and len(call.args[0]) > 1
                and call.args[0][1] == "rm"
            ]

            # ASSERTION THAT DEMONSTRATES THE BUG:
            # Currently, the implementation will try to remove containers from other projects
            all_container_operations = kill_calls + rm_calls
            other_project_operations = [
                call
                for call in all_container_operations
                if ("other456" in str(call) or "different789" in str(call))
            ]

            # THIS ASSERTION WILL FAIL with current buggy implementation
            # because it DOES target other project containers
            assert len(other_project_operations) == 0, (
                f"BUG DETECTED: _force_cleanup_containers targeted other project containers. "
                f"Operations on other projects: {other_project_operations}. "
                f"This should NEVER happen - cleanup should only target current project containers."
            )

    def test_force_cleanup_with_project_config_should_be_scoped(
        self, docker_manager, mock_console, project_config_dict
    ):
        """
        PASSING TEST: When project config is available, force cleanup should use it for scoping

        This test verifies the FIXED behavior - force cleanup only targets
        containers that belong to the current project as defined by project_config.
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup project config mock
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "current123"
            mock_config.project_containers.qdrant_name = "cidx-current123-qdrant"
            mock_config.project_containers.ollama_name = "cidx-current123-ollama"
            mock_config.project_containers.data_cleaner_name = (
                "cidx-current123-data-cleaner"
            )
            mock_config_mgr.return_value.load.return_value = mock_config

            mock_runtime.return_value = "podman"

            # Mock get_container_name to return expected names
            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-current123-qdrant",
                    "ollama": "cidx-current123-ollama",
                    "data-cleaner": "cidx-current123-data-cleaner",
                }[service]

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]

                    # FIXED BEHAVIOR: Uses project hash pattern matching for discovery
                    if (
                        "ps" in cmd
                        and "-a" in cmd
                        and "name=cidx-current123-" in str(cmd)
                    ):
                        # Return all containers for this project in a single discovery call
                        return Mock(
                            returncode=0,
                            stdout="cidx-current123-qdrant\tRunning\ncidx-current123-ollama\tRunning\ncidx-current123-data-cleaner\tRunning\n",
                            stderr="",
                        )
                    elif "kill" in cmd or "rm" in cmd:
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act: Call force cleanup
                _ = docker_manager._force_cleanup_containers(verbose=True)

                # Assert: Should only have operations on current project containers
                all_calls = mock_run.call_args_list
                container_operations = [
                    call
                    for call in all_calls
                    if call.args
                    and len(call.args) > 0
                    and len(call.args[0]) > 1
                    and call.args[0][1]
                    in [
                        "kill",
                        "rm",
                    ]  # Check the actual command, not string representation
                ]

                # Verify project-scoped discovery is used
                discovery_calls = [
                    call
                    for call in all_calls
                    if "ps" in str(call) and "name=cidx-current123-" in str(call)
                ]
                assert (
                    len(discovery_calls) == 1
                ), "Should use single discovery call for all project containers"

                # Check operations only target current project containers (kill/rm only)
                current_project_operations = [
                    call
                    for call in container_operations
                    if "cidx-current123" in str(call)
                ]
                other_project_operations = [
                    call
                    for call in container_operations
                    if (
                        "cidx-other456" in str(call) or "cidx-different789" in str(call)
                    )
                ]

                # This should pass with the fix
                assert (
                    len(other_project_operations) == 0
                ), f"Force cleanup targeted other project containers: {other_project_operations}"
                # Should have kill and rm operations for each of the 3 containers
                assert (
                    len(current_project_operations) == 6
                ), f"Force cleanup should have targeted current project containers (expected 6, got {len(current_project_operations)}): {current_project_operations}"  # 3 containers * 2 operations (kill + rm)

    def test_cleanup_uninstall_should_not_affect_other_projects(
        self,
        docker_manager,
        mock_console,
        project_config_dict,
        other_project_config_dict,
    ):
        """
        FAILING TEST: Full uninstall cleanup should not affect containers from other projects

        This is the integration test that demonstrates the real-world bug scenario
        where running `cidx uninstall` in one project removes containers from other projects.
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
            # Mock the config loading to return our project config
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
            patch("code_indexer.config.ConfigManager.load") as mock_load_config,
        ):
            # Setup: Configure mocks for project config loading
            mock_config = MagicMock()
            mock_config.project_containers = MagicMock()
            mock_config.project_containers.qdrant_name = "cidx-current123-qdrant"
            mock_config.project_containers.ollama_name = "cidx-current123-ollama"
            mock_config.project_containers.data_cleaner_name = (
                "cidx-current123-data-cleaner"
            )
            mock_config.project_containers.project_hash = "current123"

            mock_config_mgr.return_value.load.return_value = mock_config
            mock_load_config.return_value = mock_config

            # Setup other mocks
            mock_compose_cmd.return_value = ["podman-compose"]
            mock_compose_file.exists.return_value = True
            mock_cleanup_data.return_value = True
            mock_stop_main.return_value = True
            mock_clean_data.return_value = True
            mock_stop_cleaner.return_value = True
            mock_runtime.return_value = "podman"

            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]

                if "down" in cmd:
                    # Compose down fails (triggering force cleanup)
                    return Mock(returncode=1, stderr="Compose down failed")
                elif (
                    "ps" in cmd
                    and "-a" in cmd
                    and "--filter" in cmd
                    and "name=cidx-" in cmd
                ):
                    # CURRENT BUGGY BEHAVIOR: Returns ALL cidx containers from system
                    return Mock(
                        returncode=0,
                        stdout=(
                            "cidx-current123-qdrant\tRunning\n"
                            "cidx-current123-ollama\tRunning\n"
                            "cidx-other456-qdrant\tRunning\n"  # Other project!
                            "cidx-other456-ollama\tRunning\n"  # Other project!
                            "cidx-different789-qdrant\tRunning\n"  # Other project!
                        ),
                        stderr="",
                    )
                elif "kill" in cmd or "rm" in cmd:
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act: Run uninstall (remove_data=True) which triggers the bug
            docker_manager.cleanup(remove_data=True, force=False, verbose=True)

            # Assert: Should NOT have affected other project containers
            all_calls = mock_run.call_args_list
            container_operations = [
                call
                for call in all_calls
                if call.args
                and len(call.args) > 0
                and len(call.args[0]) > 1
                and call.args[0][1] in ["kill", "rm"]  # Check the actual command
            ]

            # Find operations on other projects (this is the bug!)
            other_project_operations = [
                call
                for call in container_operations
                if ("other456" in str(call) or "different789" in str(call))
            ]

            # THIS ASSERTION WILL FAIL with current implementation
            # demonstrating the critical bug
            assert len(other_project_operations) == 0, (
                f"CRITICAL BUG: Uninstall operation affected other project containers! "
                f"Operations on other projects: {other_project_operations}. "
                f"This makes uninstall DANGEROUS to other projects on the same system."
            )

    def test_fixed_implementation_uses_exact_matching_not_wildcard(
        self, docker_manager, mock_console
    ):
        """
        PASSING TEST: Fixed implementation uses exact container matching, not dangerous wildcards

        This test verifies that the fix eliminates the wildcard filter that affected all projects.
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup project config
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "proj123"
            mock_config.project_containers.qdrant_name = "cidx-proj123-qdrant"
            mock_config.project_containers.ollama_name = "cidx-proj123-ollama"
            mock_config.project_containers.data_cleaner_name = (
                "cidx-proj123-data-cleaner"
            )
            mock_config_mgr.return_value.load.return_value = mock_config

            mock_runtime.return_value = "podman"

            # Track what commands are actually used for container discovery
            actual_commands = []

            # Mock get_container_name to return expected names
            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-proj123-qdrant",
                    "ollama": "cidx-proj123-ollama",
                    "data-cleaner": "cidx-proj123-data-cleaner",
                }[service]

                def mock_subprocess_calls(*args, **kwargs):
                    actual_commands.append(args[0])
                    cmd = args[0]

                    if "ps" in cmd and "-a" in cmd:
                        # Fixed implementation checks specific containers
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act
                docker_manager._force_cleanup_containers(verbose=True)

                # Assert: Fixed implementation uses exact matching, not wildcards
                container_list_commands = [
                    cmd for cmd in actual_commands if "ps" in cmd and "--filter" in cmd
                ]

                # Verify project-scoped filters are used (with project hash)
                project_scoped_commands = [
                    cmd
                    for cmd in container_list_commands
                    if "name=cidx-proj123-" in cmd  # Project-scoped pattern
                ]

                # Fixed implementation should use project-scoped discovery
                assert len(project_scoped_commands) == 1, (
                    f"Expected project-scoped discovery command. "
                    f"Found commands: {container_list_commands}"
                )

                # The implementation should attempt to check for each container
                assert (
                    len(actual_commands) > 0
                ), f"Implementation should have executed some commands, but got: {actual_commands}"

                # Verify no system-wide wildcard patterns are used
                # Project-scoped patterns like "cidx-proj123-" are safe
                dangerous_wildcards = [
                    cmd
                    for cmd in actual_commands
                    if "name=cidx-" in str(cmd)
                    and not any(
                        f"name=cidx-{h}-" in str(cmd) for h in ["proj123"]
                    )  # Not project-scoped
                ]

                assert (
                    len(dangerous_wildcards) == 0
                ), f"No system-wide wildcard patterns should be used. Found: {dangerous_wildcards}"


if __name__ == "__main__":
    pytest.main([__file__])
