#!/usr/bin/env python3
"""
Unit tests for Docker container name resolution bug in stop_main_services.

This test demonstrates and verifies the fix for the bug where stop_main_services()
uses incorrect container naming pattern f"{self.project_name}-{service}-1" instead
of the project-specific names like cidx-{project_hash}-{service}.

Bug: Line ~4290 in docker_manager.py stop_main_services() method uses wrong container names
Fix: Use self.get_container_name(service, project_config_dict) for accurate naming
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from code_indexer.services.docker_manager import DockerManager


class TestContainerNameResolutionBug:
    """Test the container name resolution bug in stop_main_services"""

    @pytest.fixture
    def mock_console(self):
        """Create a mock console for testing"""
        return Mock()

    @pytest.fixture
    def docker_manager(self, mock_console):
        """Create a DockerManager instance for testing"""
        with patch("code_indexer.services.docker_manager.Path.cwd") as mock_cwd:
            mock_cwd.return_value = Path("/tmp/test")
            manager = DockerManager(
                console=mock_console, project_name="test_project", force_docker=False
            )
            return manager

    @pytest.fixture
    def mock_project_config(self):
        """Mock project configuration with proper container names"""
        return {
            "qdrant_name": "cidx-abc123-qdrant",
            "ollama_name": "cidx-abc123-ollama",
            "data_cleaner_name": "cidx-abc123-data-cleaner",
        }

    def test_stop_main_services_uses_incorrect_container_names_currently(
        self, docker_manager, mock_console, mock_project_config
    ):
        """
        FAILING TEST: Demonstrates the current bug where stop_main_services
        uses f"{self.project_name}-{service}-1" instead of get_container_name()

        This test will FAIL initially, proving the bug exists.
        After the fix, it should PASS.
        """
        # Mock compose file exists
        with patch.object(docker_manager, "compose_file") as mock_compose_file:
            mock_compose_file.exists.return_value = True

            # Mock compose command
            with patch.object(
                docker_manager, "get_compose_command"
            ) as mock_compose_cmd:
                mock_compose_cmd.return_value = ["podman-compose"]

                # Mock runtime detection
                with patch.object(
                    docker_manager, "_get_available_runtime"
                ) as mock_runtime:
                    mock_runtime.return_value = "podman"

                    # Mock subprocess.run for compose stop commands
                    with patch("subprocess.run") as mock_run:
                        # Configure mock to return successful compose stop
                        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                        # Mock ConfigManager to return proper project config
                        with patch(
                            "code_indexer.config.ConfigManager"
                        ) as mock_config_mgr:
                            mock_config_instance = Mock()
                            mock_config_instance.load.return_value = Mock(
                                project_containers=mock_project_config
                            )
                            mock_config_mgr.create_with_backtrack.return_value = (
                                mock_config_instance
                            )

                            # Call the method under test
                            result = docker_manager.stop_main_services()

                            # Verify the method was called successfully
                            assert result is True

                            # Verify subprocess.run was called
                            assert (
                                mock_run.call_count >= 2
                            )  # At least 2 calls for ollama and qdrant stop

                            # Find verification calls - these should use correct container names
                            verification_calls = [
                                call
                                for call in mock_run.call_args_list
                                if len(call[0]) > 0
                                and call[0][0][1] == "ps"  # podman ps calls
                            ]

                            # The bug: verification should look for cidx-abc123-ollama, cidx-abc123-qdrant
                            # But currently it looks for test_project-ollama-1, test_project-qdrant-1
                            expected_correct_names = [
                                "cidx-abc123-ollama",
                                "cidx-abc123-qdrant",
                            ]
                            # These would be the incorrect names that would be generated:
                            # actual_buggy_names = ["test_project-ollama-1", "test_project-qdrant-1"]

                            # Check what names are actually being used in ps commands
                            used_names = []
                            for call in verification_calls:
                                args = call[0][
                                    0
                                ]  # First positional arg is the command list
                                for i, arg in enumerate(args):
                                    if arg.startswith("name="):
                                        used_names.append(
                                            arg[5:]
                                        )  # Remove "name=" prefix

                            # THIS IS THE BUG - currently it uses wrong names
                            # This assertion will FAIL initially, demonstrating the bug
                            for expected_name in expected_correct_names:
                                assert expected_name in used_names, (
                                    f"Expected container name {expected_name} not found in verification calls. "
                                    f"Found names: {used_names}. This demonstrates the bug where wrong container "
                                    f"names are used for verification."
                                )

    def test_get_container_name_works_correctly_with_project_config(
        self, docker_manager, mock_project_config
    ):
        """
        PASSING TEST: Verify get_container_name() method works correctly

        This proves the correct method exists and works properly.
        """
        # Test that get_container_name returns correct names
        ollama_name = docker_manager.get_container_name("ollama", mock_project_config)
        assert ollama_name == "cidx-abc123-ollama"

        qdrant_name = docker_manager.get_container_name("qdrant", mock_project_config)
        assert qdrant_name == "cidx-abc123-qdrant"

        data_cleaner_name = docker_manager.get_container_name(
            "data-cleaner", mock_project_config
        )
        assert data_cleaner_name == "cidx-abc123-data-cleaner"

    def test_stop_main_services_should_use_get_container_name_method(
        self, docker_manager, mock_console, mock_project_config
    ):
        """
        DESIGN TEST: This test defines the expected behavior after the fix

        This test will FAIL initially because the bug exists.
        After implementing the fix, this test should PASS.
        """
        # Mock compose file exists
        with patch.object(docker_manager, "compose_file") as mock_compose_file:
            mock_compose_file.exists.return_value = True

            # Mock compose command
            with patch.object(
                docker_manager, "get_compose_command"
            ) as mock_compose_cmd:
                mock_compose_cmd.return_value = ["podman-compose"]

                # Mock runtime detection
                with patch.object(
                    docker_manager, "_get_available_runtime"
                ) as mock_runtime:
                    mock_runtime.return_value = "podman"

                    # Mock get_container_name method to track its usage
                    with patch.object(
                        docker_manager, "get_container_name"
                    ) as mock_get_container_name:
                        mock_get_container_name.side_effect = [
                            "cidx-abc123-ollama",  # First call for ollama
                            "cidx-abc123-qdrant",  # Second call for qdrant
                        ]

                        # Mock subprocess.run for compose stop and verification commands
                        with patch("subprocess.run") as mock_run:
                            # Configure mock to simulate successful operations
                            mock_run.return_value = Mock(
                                returncode=0, stdout="", stderr=""
                            )

                            # Mock ConfigManager to return proper project config
                            with patch(
                                "code_indexer.config.ConfigManager"
                            ) as mock_config_mgr:
                                mock_config_instance = Mock()
                                mock_config_instance.load.return_value = Mock(
                                    project_containers=mock_project_config
                                )
                                mock_config_mgr.create_with_backtrack.return_value = (
                                    mock_config_instance
                                )

                                # Call the method under test
                                result = docker_manager.stop_main_services()

                                # Verify the method succeeded
                                assert result is True

                                # THE FIX VERIFICATION: get_container_name should be called for each service
                                # This will FAIL initially because the current implementation doesn't call it
                                assert mock_get_container_name.call_count == 2, (
                                    "get_container_name should be called twice (once for ollama, once for qdrant) "
                                    "for proper container name resolution during verification"
                                )

                                # Verify it was called with correct arguments
                                expected_calls: list[str] = [
                                    (("ollama", mock_project_config), {}),
                                    (("qdrant", mock_project_config), {}),
                                ]
                                actual_calls = mock_get_container_name.call_args_list

                                for i, expected_call in enumerate(expected_calls):
                                    assert (
                                        actual_calls[i][0][0] == expected_call[0][0]
                                    ), (
                                        f"Call {i+1}: Expected service '{expected_call[0][0]}', "
                                        f"got '{actual_calls[i][0][0]}'"
                                    )

    def test_stop_main_services_fix_verification_with_config_manager(
        self, docker_manager, mock_console, mock_project_config
    ):
        """
        VERIFICATION TEST: Test the specific fix implementation

        This test validates that:
        1. ConfigManager is used to load project configuration
        2. get_container_name is called with the loaded config
        3. Correct container names are used in verification commands
        """
        with patch.object(docker_manager, "compose_file") as mock_compose_file:
            mock_compose_file.exists.return_value = True

            with patch.object(
                docker_manager, "get_compose_command"
            ) as mock_compose_cmd:
                mock_compose_cmd.return_value = ["podman-compose"]

                with patch.object(
                    docker_manager, "_get_available_runtime"
                ) as mock_runtime:
                    mock_runtime.return_value = "podman"

                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

                        # Mock ConfigManager to return proper project config
                        with patch(
                            "code_indexer.config.ConfigManager"
                        ) as mock_config_mgr:
                            mock_config_instance = Mock()
                            mock_config_instance.load.return_value = Mock(
                                project_containers=mock_project_config
                            )
                            mock_config_mgr.create_with_backtrack.return_value = (
                                mock_config_instance
                            )

                            # Call the method under test
                            result = docker_manager.stop_main_services()

                            # Verify the method succeeded
                            assert result is True

                            # Verify ConfigManager was used to load configuration
                            mock_config_mgr.create_with_backtrack.assert_called_once()
                            mock_config_instance.load.assert_called_once()

                            # Check subprocess calls for correct container names in verification
                            verification_calls = [
                                call
                                for call in mock_run.call_args_list
                                if len(call[0]) > 0
                                and len(call[0][0]) > 1
                                and call[0][0][1] == "ps"
                            ]

                            # Should have verification calls that use correct container names
                            assert (
                                len(verification_calls) >= 2
                            ), "Should have verification calls for ollama and qdrant"

                            # Extract the container names being checked
                            verified_names = []
                            for call in verification_calls:
                                args = call[0][0]  # Command arguments
                                for i, arg in enumerate(args):
                                    if arg.startswith("name="):
                                        verified_names.append(
                                            arg[5:]
                                        )  # Remove "name=" prefix

                            # Should verify the correct project-specific container names
                            assert (
                                "cidx-abc123-ollama" in verified_names
                                or "cidx-abc123-qdrant" in verified_names
                            ), (
                                f"Expected project-specific container names to be verified. "
                                f"Actual names verified: {verified_names}"
                            )


if __name__ == "__main__":
    pytest.main([__file__])
