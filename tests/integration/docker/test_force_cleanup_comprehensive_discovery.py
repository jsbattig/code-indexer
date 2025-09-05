#!/usr/bin/env python3
"""
TDD Tests for comprehensive container discovery in force cleanup

UPDATED: These tests originally demonstrated the limitation where _force_cleanup_containers
only targeted 3 predefined containers but missed additional containers with the same project hash.

ISSUE FIXED: Implementation now uses comprehensive project hash-based discovery to find
             ALL containers with the current project hash pattern: cidx-{project_hash}-*

NOTE: These tests now verify that the NEW behavior works correctly (comprehensive discovery)
      instead of testing the OLD behavior (hardcoded 3-container list).
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest
from rich.console import Console

from ...conftest import get_local_tmp_dir
from code_indexer.services.docker_manager import DockerManager


class TestForceCleanupComprehensiveDiscovery:
    """Test comprehensive container discovery during force cleanup"""

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
                console=mock_console, project_name="test_discovery", force_docker=False
            )
            return manager

    def test_force_cleanup_discovers_all_project_hash_containers_not_just_three(
        self, docker_manager, mock_console
    ):
        """
        UPDATED TEST: Force cleanup now discovers ALL containers with project hash, not just 3 predefined ones

        This test verifies the fix - containers like 'cidx-abc123-extra' are now found
        by the new comprehensive project hash-based discovery approach.
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

            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-abc123-qdrant",
                    "ollama": "cidx-abc123-ollama",
                    "data-cleaner": "cidx-abc123-data-cleaner",
                }[service]

                # Track all subprocess calls for analysis
                all_subprocess_calls = []

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]
                    all_subprocess_calls.append(cmd)

                    # NEW: Simulate comprehensive discovery finding ALL project containers
                    if "ps" in cmd and "-a" in cmd and "name=cidx-abc123-" in str(cmd):
                        # Comprehensive discovery finds all containers with project hash
                        return Mock(
                            returncode=0,
                            stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\ncidx-abc123-data-cleaner\tRunning\ncidx-abc123-extra\tRunning\n",
                            stderr="",
                        )
                    elif "kill" in cmd or "rm" in cmd:
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act: Call force cleanup directly
                result = docker_manager._force_cleanup_containers(verbose=True)

                # Assert: Force cleanup should succeed
                assert result is True

                # UPDATED ASSERTION: New implementation should be using comprehensive project hash-based discovery
                project_hash_discovery_calls = [
                    call
                    for call in all_subprocess_calls
                    if "ps" in call
                    and "name=cidx-abc123-" in str(call)
                    and "--filter" in call
                ]

                # NEW BEHAVIOR: Should use comprehensive project hash-based pattern discovery
                assert len(project_hash_discovery_calls) > 0, (
                    f"New implementation should use project hash-based discovery. "
                    f"Discovery calls: {project_hash_discovery_calls}"
                )

                # VERIFY: Should NOT use individual container checks anymore
                individual_container_checks = [
                    call
                    for call in all_subprocess_calls
                    if "ps" in call
                    and any(
                        container in str(call)
                        for container in [
                            "name=^cidx-abc123-qdrant",
                            "name=^cidx-abc123-ollama",
                            "name=^cidx-abc123-data-cleaner",
                        ]
                    )
                ]

                # NEW: Should not have individual checks - uses comprehensive discovery instead
                assert len(individual_container_checks) == 0, (
                    f"New implementation should not use individual container checks. "
                    f"Found individual checks: {individual_container_checks}"
                )

    def test_force_cleanup_finds_extra_containers_with_same_project_hash(
        self, docker_manager, mock_console
    ):
        """
        UPDATED TEST: Demonstrates that extra containers with same project hash are now found

        Scenario: User manually creates 'cidx-abc123-extra' container. New cleanup finds it.
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

            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-abc123-qdrant",
                    "ollama": "cidx-abc123-ollama",
                    "data-cleaner": "cidx-abc123-data-cleaner",
                }[service]

                # Track which containers are actually targeted for cleanup
                targeted_containers = set()

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]

                    # Track container targeting
                    if ("kill" in cmd or "rm" in cmd) and "cidx-abc123" in str(cmd):
                        for part in cmd:
                            if "cidx-abc123" in str(part):
                                targeted_containers.add(str(part))

                    # NEW: Comprehensive discovery finds ALL containers including extras
                    if "ps" in cmd and "-a" in cmd and "name=cidx-abc123-" in str(cmd):
                        # Return ALL containers with project hash including the extra one
                        return Mock(
                            returncode=0,
                            stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\ncidx-abc123-data-cleaner\tRunning\ncidx-abc123-extra\tRunning\ncidx-abc123-custom\tExited\n",
                            stderr="",
                        )
                    elif "kill" in cmd or "rm" in cmd:
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act: Call force cleanup
                result = docker_manager._force_cleanup_containers(verbose=True)

                # Assert: Cleanup succeeds for all containers
                assert result is True

                # UPDATED ASSERTION: Extra containers with same project hash should now be targeted
                expected_containers = {
                    "cidx-abc123-qdrant",
                    "cidx-abc123-ollama",
                    "cidx-abc123-data-cleaner",
                    "cidx-abc123-extra",  # This should now be found!
                    "cidx-abc123-custom",  # This should now be found!
                }

                # Convert targeted containers to a comparable set
                targeted_names = {
                    container
                    for container in targeted_containers
                    if container.startswith("cidx-abc123-")
                }

                # NEW: All containers should be found, no missing containers
                missing_containers = expected_containers - targeted_names
                assert len(missing_containers) == 0, (
                    f"New implementation should find all extra containers. "
                    f"Targeted: {targeted_names}, Missing: {missing_containers}"
                )

                # Verify specifically that 'cidx-abc123-extra' is found
                assert (
                    "cidx-abc123-extra" in targeted_names
                ), "The extra container 'cidx-abc123-extra' should now be found by new implementation"

                # Verify specifically that 'cidx-abc123-custom' is found
                assert (
                    "cidx-abc123-custom" in targeted_names
                ), "The custom container 'cidx-abc123-custom' should now be found by new implementation"

    def test_comprehensive_discovery_uses_project_hash_filter(
        self, docker_manager, mock_console
    ):
        """
        UPDATED TEST: Comprehensive discovery now uses single project hash-based filter

        Verifies that instead of 3 individual container checks, uses one filter: name=cidx-{hash}-
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

            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-abc123-qdrant",
                    "ollama": "cidx-abc123-ollama",
                    "data-cleaner": "cidx-abc123-data-cleaner",
                }[service]

                all_commands = []

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]
                    all_commands.append(cmd)

                    # NEW: Return empty result for comprehensive discovery
                    if "ps" in cmd and "-a" in cmd and "name=cidx-abc123-" in str(cmd):
                        return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act
                docker_manager._force_cleanup_containers(verbose=True)

                # Analyze the discovery pattern used
                ps_commands = [
                    cmd for cmd in all_commands if "ps" in cmd and "-a" in cmd
                ]

                # OLD: individual container checks (should not exist anymore)
                individual_checks = sum(
                    1
                    for cmd in ps_commands
                    if any(
                        pattern in str(cmd)
                        for pattern in [
                            "name=^cidx-abc123-qdrant",
                            "name=^cidx-abc123-ollama",
                            "name=^cidx-abc123-data-cleaner",
                        ]
                    )
                )

                # NEW: comprehensive project hash-based discovery
                project_hash_discovery = sum(
                    1
                    for cmd in ps_commands
                    if (
                        "name=cidx-abc123-" in str(cmd)
                        and "qdrant" not in str(cmd)
                        and "ollama" not in str(cmd)
                        and "data-cleaner" not in str(cmd)
                    )
                )

                # UPDATED ASSERTIONS: New approach uses comprehensive discovery, not individual checks
                assert individual_checks == 0, (
                    f"New implementation should not use individual container checks. "
                    f"Found individual checks: {individual_checks}"
                )
                assert project_hash_discovery > 0, (
                    f"New implementation should use comprehensive project hash-based discovery. "
                    f"Individual checks: {individual_checks}, Comprehensive discovery: {project_hash_discovery}"
                )

    def test_project_scoping_should_prevent_cross_project_cleanup(
        self, docker_manager, mock_console
    ):
        """
        TEST: Verify that comprehensive discovery maintains project scoping

        Even with comprehensive discovery, should only target current project's containers
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

            with patch.object(docker_manager, "get_container_name") as mock_get_name:
                mock_get_name.side_effect = lambda service, config: {
                    "qdrant": "cidx-abc123-qdrant",
                    "ollama": "cidx-abc123-ollama",
                    "data-cleaner": "cidx-abc123-data-cleaner",
                }[service]

                cleanup_targets = []

                def mock_subprocess_calls(*args, **kwargs):
                    cmd = args[0]

                    # Track cleanup targets
                    if "kill" in cmd or "rm" in cmd:
                        cleanup_targets.extend(
                            [
                                part
                                for part in cmd
                                if isinstance(part, str) and "cidx-" in part
                            ]
                        )

                    # Simulate environment with multiple projects
                    if "ps" in cmd and "-a" in cmd:
                        # Return containers from different projects
                        if "name=^cidx-abc123" in str(cmd):
                            return Mock(
                                returncode=0,
                                stdout="cidx-abc123-qdrant\tRunning\n",
                                stderr="",
                            )
                        elif "name=cidx-abc123-" in str(cmd):
                            # Comprehensive discovery should find all abc123 containers
                            return Mock(
                                returncode=0,
                                stdout="cidx-abc123-qdrant\tRunning\ncidx-abc123-ollama\tRunning\ncidx-abc123-extra\tRunning\n",
                                stderr="",
                            )
                        else:
                            return Mock(returncode=0, stdout="", stderr="")
                    else:
                        return Mock(returncode=0, stdout="", stderr="")

                mock_run.side_effect = mock_subprocess_calls

                # Act
                docker_manager._force_cleanup_containers(verbose=True)

                # Assert: Should only target current project containers (abc123)
                # No containers from other projects (like def456, xyz789) should be targeted
                # current_project_targets = [
                #     target for target in cleanup_targets
                #     if "cidx-abc123-" in target
                # ]
                other_project_targets = [
                    target
                    for target in cleanup_targets
                    if "cidx-" in target and "cidx-abc123-" not in target
                ]

                # Project scoping should be maintained
                assert (
                    len(other_project_targets) == 0
                ), f"Should not target other projects, but found: {other_project_targets}"


if __name__ == "__main__":
    pytest.main([__file__])
