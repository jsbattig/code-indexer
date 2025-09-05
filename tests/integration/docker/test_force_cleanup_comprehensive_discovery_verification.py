#!/usr/bin/env python3
"""
TDD Tests to verify comprehensive container discovery implementation

These tests verify that the new project hash-based discovery correctly finds
ALL containers belonging to the current project, not just the 3 predefined ones.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from rich.console import Console

from ...conftest import get_local_tmp_dir
from code_indexer.services.docker_manager import DockerManager


class TestForceCleanupComprehensiveDiscoveryVerification:
    """Verify comprehensive container discovery implementation works correctly"""

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
                console=mock_console,
                project_name="test_verification",
                force_docker=False,
            )
            return manager

    def test_comprehensive_discovery_finds_all_project_containers(
        self, docker_manager, mock_console
    ):
        """
        TEST: Verify new implementation discovers all containers with project hash pattern

        Should find standard containers (qdrant, ollama, data-cleaner) plus any extras
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
            mock_config.project_containers.project_hash = "abc123"
            mock_config_mgr.return_value.load.return_value = mock_config
            mock_runtime.return_value = "podman"

            # Track cleanup targets
            cleanup_targets = set()

            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]

                # Track cleanup targets
                if ("kill" in cmd or "rm" in cmd) and len(cmd) > 2:
                    container_name = (
                        cmd[2] if "kill" in cmd else cmd[3]
                    )  # rm has -f flag
                    if container_name.startswith("cidx-abc123-"):
                        cleanup_targets.add(container_name)

                # NEW: Single comprehensive discovery call
                if (
                    "ps" in cmd
                    and "-a" in cmd
                    and "--filter" in cmd
                    and "name=cidx-abc123-" in str(cmd)
                ):
                    # Return ALL containers with project hash - standard + extras
                    discovered_output = (
                        "cidx-abc123-qdrant\tRunning\n"
                        "cidx-abc123-ollama\tRunning\n"
                        "cidx-abc123-data-cleaner\tRunning\n"
                        "cidx-abc123-extra\tRunning\n"  # This should now be found!
                        "cidx-abc123-custom\tExited\n"  # Another extra container
                    )
                    return Mock(returncode=0, stdout=discovered_output, stderr="")
                elif "kill" in cmd or "rm" in cmd:
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act: Call force cleanup
            result = docker_manager._force_cleanup_containers(verbose=True)

            # Assert: Should succeed
            assert result is True

            # Verify comprehensive discovery was used
            discovery_calls = [
                call
                for call in mock_run.call_args_list
                if ("ps" in str(call) and "name=cidx-abc123-" in str(call))
            ]

            # Should use single comprehensive discovery call
            assert (
                len(discovery_calls) >= 1
            ), f"Expected comprehensive discovery call, got: {discovery_calls}"

            # Verify all containers with project hash were targeted for cleanup
            expected_containers = {
                "cidx-abc123-qdrant",
                "cidx-abc123-ollama",
                "cidx-abc123-data-cleaner",
                "cidx-abc123-extra",  # NEW: Should now be found!
                "cidx-abc123-custom",  # NEW: Should now be found!
            }

            assert cleanup_targets == expected_containers, (
                f"Expected all project containers to be cleaned up. "
                f"Expected: {expected_containers}, Got: {cleanup_targets}"
            )

    def test_discovery_uses_project_hash_from_config(
        self, docker_manager, mock_console
    ):
        """
        TEST: Verify discovery uses project hash from configuration correctly
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup project config with specific hash
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "def456"  # Different hash
            mock_config_mgr.return_value.load.return_value = mock_config
            mock_runtime.return_value = "podman"

            used_project_hash = None

            def mock_subprocess_calls(*args, **kwargs):
                nonlocal used_project_hash
                cmd = args[0]

                # Capture the project hash used in discovery
                if "ps" in cmd and "--filter" in cmd and "name=cidx-" in str(cmd):
                    for part in cmd:
                        if isinstance(part, str) and "name=cidx-" in part:
                            # Extract hash from filter: name=cidx-{hash}-
                            used_project_hash = part.split("cidx-")[1].split("-")[0]
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act
            docker_manager._force_cleanup_containers(verbose=True)

            # Assert: Should use exact project hash from config
            assert used_project_hash == "def456", (
                f"Expected to use project hash 'def456' from config, "
                f"but used: {used_project_hash}"
            )

    def test_discovery_uses_calculated_hash_when_no_config(
        self, docker_manager, mock_console
    ):
        """
        TEST: Verify discovery calculates project hash when not in config
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
            patch.object(
                docker_manager.port_registry, "_calculate_project_hash"
            ) as mock_calc_hash,
        ):
            # Setup: No project hash in config
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = ""  # Empty hash
            mock_config_mgr.return_value.load.return_value = mock_config
            mock_runtime.return_value = "podman"
            mock_calc_hash.return_value = "xyz789"  # Calculated hash

            used_project_hash = None

            def mock_subprocess_calls(*args, **kwargs):
                nonlocal used_project_hash
                cmd = args[0]

                if "ps" in cmd and "--filter" in cmd and "name=cidx-" in str(cmd):
                    for part in cmd:
                        if isinstance(part, str) and "name=cidx-" in part:
                            used_project_hash = part.split("cidx-")[1].split("-")[0]
                    return Mock(returncode=0, stdout="", stderr="")
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act
            docker_manager._force_cleanup_containers(verbose=True)

            # Assert: Should use calculated project hash
            assert used_project_hash == "xyz789", (
                f"Expected to use calculated project hash 'xyz789', "
                f"but used: {used_project_hash}"
            )

            # Verify hash calculation was called
            mock_calc_hash.assert_called_once()

    def test_project_scoping_prevents_other_project_cleanup(
        self, docker_manager, mock_console
    ):
        """
        TEST: Verify project scoping is maintained - only current project containers targeted
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup: Current project has hash 'abc123'
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "abc123"
            mock_config_mgr.return_value.load.return_value = mock_config
            mock_runtime.return_value = "podman"

            cleanup_targets = set()

            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]

                # Track cleanup targets
                if ("kill" in cmd or "rm" in cmd) and len(cmd) > 2:
                    container_name = cmd[2] if "kill" in cmd else cmd[3]
                    cleanup_targets.add(container_name)

                # Discovery should only find current project containers
                if (
                    "ps" in cmd
                    and "--filter" in cmd
                    and "name=cidx-abc123-" in str(cmd)
                ):
                    # Return only current project containers, not others
                    return Mock(
                        returncode=0,
                        stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\n",
                        stderr="",
                    )
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act
            docker_manager._force_cleanup_containers(verbose=True)

            # Assert: Should only target current project containers
            for container in cleanup_targets:
                assert container.startswith("cidx-abc123-"), (
                    f"Container {container} should belong to current project (abc123), "
                    f"but targets were: {cleanup_targets}"
                )

            # Should not target containers from other projects
            other_project_containers = [
                container
                for container in cleanup_targets
                if not container.startswith("cidx-abc123-")
            ]
            assert (
                len(other_project_containers) == 0
            ), f"Should not target other project containers, but found: {other_project_containers}"

    def test_comprehensive_discovery_verbose_output(self, docker_manager, mock_console):
        """
        TEST: Verify verbose output shows comprehensive discovery information
        """
        with (
            patch.object(docker_manager, "_get_available_runtime") as mock_runtime,
            patch("subprocess.run") as mock_run,
            patch(
                "code_indexer.config.ConfigManager.create_with_backtrack"
            ) as mock_config_mgr,
        ):
            # Setup
            mock_config = Mock()
            mock_config.project_containers = Mock()
            mock_config.project_containers.project_hash = "abc123"
            mock_config_mgr.return_value.load.return_value = mock_config
            mock_runtime.return_value = "podman"

            def mock_subprocess_calls(*args, **kwargs):
                cmd = args[0]
                if (
                    "ps" in cmd
                    and "--filter" in cmd
                    and "name=cidx-abc123-" in str(cmd)
                ):
                    return Mock(
                        returncode=0,
                        stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-extra\tExited\n",
                        stderr="",
                    )
                else:
                    return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = mock_subprocess_calls

            # Act: Call with verbose=True
            docker_manager._force_cleanup_containers(verbose=True)

            # Assert: Should show comprehensive discovery messages
            console_calls = [call.args[0] for call in mock_console.print.call_args_list]

            # Should mention discovering ALL containers for project hash
            discovery_messages = [
                call
                for call in console_calls
                if "discovering all containers" in call.lower()
                and "project hash" in call.lower()
            ]
            assert (
                len(discovery_messages) > 0
            ), f"Expected comprehensive discovery message, but console calls were: {console_calls}"

            # Should show discovered containers
            discovered_messages = [
                call
                for call in console_calls
                if "discovered project containers" in call.lower()
            ]
            assert (
                len(discovered_messages) > 0
            ), f"Expected discovered containers message, but console calls were: {console_calls}"


if __name__ == "__main__":
    pytest.main([__file__])
