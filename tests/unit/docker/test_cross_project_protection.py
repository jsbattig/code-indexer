"""Tests to verify that DockerManager methods prevent cross-project operations."""

from pathlib import Path
from unittest.mock import Mock, patch


from code_indexer.services.docker_manager import DockerManager
from code_indexer.services.global_port_registry import GlobalPortRegistry


class TestCrossProjectProtection:
    """Test that all DockerManager cleanup methods are properly project-scoped."""

    def setup_method(self):
        """Setup test environment with mocked dependencies."""
        self.mock_console = Mock()
        self.mock_port_registry = Mock(spec=GlobalPortRegistry)

        # Mock project hash calculation to return predictable values
        self.project_hash_a = "abcd1234"
        self.project_hash_b = "efgh5678"

        self.docker_manager = DockerManager(
            console=self.mock_console, project_name="test_project", force_docker=False
        )

        # Replace the port registry with our mock
        self.docker_manager.port_registry = self.mock_port_registry

    @patch("code_indexer.services.docker_manager.subprocess.run")
    @patch("pathlib.Path.cwd")
    def test_force_cleanup_containers_with_guidance_uses_project_hash(
        self, mock_cwd, mock_subprocess
    ):
        """Test that _force_cleanup_containers_with_guidance only targets current project."""
        # Setup project path and hash
        mock_project_root = Path("/test/project/a")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_a
        )

        # Mock container engine detection
        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="podman"
        ):
            # Mock subprocess to return empty containers list
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = ""

            # Call the method
            _ = self.docker_manager._force_cleanup_containers_with_guidance(
                verbose=True
            )

            # Verify project hash was calculated for current project
            self.mock_port_registry._calculate_project_hash.assert_called_once_with(
                mock_project_root
            )

            # Verify subprocess was called with project-scoped filter
            mock_subprocess.assert_called()
            call_args = mock_subprocess.call_args[0][
                0
            ]  # First positional arg (the command list)

            # Check that the filter uses project hash
            assert "--filter" in call_args
            filter_index = call_args.index("--filter")
            filter_value = call_args[filter_index + 1]
            assert filter_value == f"name=cidx-{self.project_hash_a}-"

            # Verify it does NOT use the dangerous cross-project filter
            assert "name=cidx-" != filter_value

    @patch("code_indexer.services.docker_manager.subprocess.run")
    @patch("pathlib.Path.cwd")
    def test_validate_complete_cleanup_uses_project_hash(
        self, mock_cwd, mock_subprocess
    ):
        """Test that _validate_complete_cleanup only checks current project containers."""
        # Setup project path and hash
        mock_project_root = Path("/test/project/b")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_b
        )

        # Mock container engine detection
        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="docker"
        ):
            # Mock subprocess to return no containers
            mock_subprocess.return_value.returncode = 0
            mock_subprocess.return_value.stdout = ""

            # Call the method
            _ = self.docker_manager._validate_complete_cleanup(verbose=True)

            # Verify project hash was calculated for current project
            self.mock_port_registry._calculate_project_hash.assert_called_once_with(
                mock_project_root
            )

            # Verify subprocess was called with project-scoped filter
            mock_subprocess.assert_called()
            call_args = mock_subprocess.call_args[0][0]  # First positional arg

            # Check that the filter uses project hash
            assert "--filter" in call_args
            filter_index = call_args.index("--filter")
            filter_value = call_args[filter_index + 1]
            assert filter_value == f"name=cidx-{self.project_hash_b}-"

    @patch("code_indexer.services.docker_manager.subprocess.run")
    @patch("pathlib.Path.cwd")
    def test_force_cleanup_containers_validation_uses_project_hash(
        self, mock_cwd, mock_subprocess
    ):
        """Test that _force_cleanup_containers validation logic only checks current project."""
        # Setup project path and hash
        mock_project_root = Path("/test/project/c")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_a
        )

        # Mock container engine detection and health checker
        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="podman"
        ):
            with patch.object(
                self.docker_manager.health_checker,
                "wait_for_ports_available",
                return_value=True,
            ):
                # Mock subprocess for validation check
                mock_subprocess.return_value.returncode = 0
                mock_subprocess.return_value.stdout = ""

                # Call the method that contains the validation logic
                _ = self.docker_manager._force_cleanup_containers(verbose=True)

                # Verify project hash was calculated at some point
                assert self.mock_port_registry._calculate_project_hash.called

                # Find the call that includes our project hash filter
                found_project_scoped_call = False
                for call in mock_subprocess.call_args_list:
                    call_args = call[0][0]  # First positional arg
                    if "--filter" in call_args:
                        filter_index = call_args.index("--filter")
                        if filter_index + 1 < len(call_args):
                            filter_value = call_args[filter_index + 1]
                            if filter_value == f"name=cidx-{self.project_hash_a}-":
                                found_project_scoped_call = True
                                break

                assert (
                    found_project_scoped_call
                ), "Did not find project-scoped container filter call"

    @patch("pathlib.Path.cwd")
    def test_provide_actionable_cleanup_guidance_uses_project_hash(self, mock_cwd):
        """Test that manual cleanup guidance uses project-specific commands."""
        # Setup project path and hash
        mock_project_root = Path("/test/project/d")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_b
        )

        # Mock container engine detection
        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="docker"
        ):
            # Call the guidance method
            self.docker_manager._provide_actionable_cleanup_guidance({})

            # Verify project hash was calculated
            self.mock_port_registry._calculate_project_hash.assert_called_once_with(
                mock_project_root
            )

            # Check that the printed guidance includes project-scoped commands
            guidance_calls = [
                call
                for call in self.mock_console.print.call_args_list
                if call[0] and isinstance(call[0][0], str)
            ]

            # Find the container check command
            container_check_found = False
            volume_check_found = False

            for call in guidance_calls:
                message = call[0][0]
                if (
                    f"name=cidx-{self.project_hash_b}-" in message
                    and "ps -a --filter" in message
                ):
                    container_check_found = True
                if (
                    f"name=cidx-{self.project_hash_b}-" in message
                    and "volume ls --filter" in message
                ):
                    volume_check_found = True

            assert (
                container_check_found
            ), "Container check guidance should be project-scoped"
            assert volume_check_found, "Volume check guidance should be project-scoped"

    @patch("code_indexer.services.docker_manager.subprocess.run")
    @patch("pathlib.Path.cwd")
    def test_cleanup_with_final_guidance_validation_uses_project_hash(
        self, mock_cwd, mock_subprocess
    ):
        """Test that cleanup_with_final_guidance validation is project-scoped."""
        # Setup project path and hash
        mock_project_root = Path("/test/project/e")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_a
        )

        # Mock container engine detection
        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="podman"
        ):
            with patch.object(
                self.docker_manager,
                "get_compose_command",
                return_value=["podman-compose"],
            ):
                with patch(
                    "pathlib.Path.exists", return_value=True
                ):  # Compose file exists
                    # Mock subprocess calls
                    mock_subprocess.return_value.returncode = 0
                    mock_subprocess.return_value.stdout = ""

                    # Call the method
                    _ = self.docker_manager.cleanup_with_final_guidance(
                        validate=True, verbose=True, remove_data=False
                    )

                    # Verify project hash was calculated during validation
                    self.mock_port_registry._calculate_project_hash.assert_called_with(
                        mock_project_root
                    )

                    # Find the validation call that should use project hash
                    found_validation_call = False
                    for call in mock_subprocess.call_args_list:
                        call_args = call[0][0]  # First positional arg
                        if "--filter" in call_args and "ps" in call_args:
                            filter_index = call_args.index("--filter")
                            if filter_index + 1 < len(call_args):
                                filter_value = call_args[filter_index + 1]
                                if filter_value == f"name=cidx-{self.project_hash_a}-":
                                    found_validation_call = True
                                    break

                    assert (
                        found_validation_call
                    ), "Validation should use project-scoped container filter"

    def test_cross_project_scenarios_isolation(self):
        """Test that different project hashes result in completely isolated operations."""
        # Simulate two different projects
        project_a_root = Path("/project/a")
        project_b_root = Path("/project/b")

        with patch("pathlib.Path.cwd") as mock_cwd:
            # Test project A operations
            mock_cwd.return_value = project_a_root
            self.mock_port_registry._calculate_project_hash.return_value = (
                self.project_hash_a
            )

            with patch.object(
                self.docker_manager, "_get_available_runtime", return_value="podman"
            ):
                with patch(
                    "code_indexer.services.docker_manager.subprocess.run"
                ) as mock_subprocess:
                    mock_subprocess.return_value.returncode = 0
                    mock_subprocess.return_value.stdout = ""

                    # Call project A cleanup
                    self.docker_manager._force_cleanup_containers_with_guidance(
                        verbose=True
                    )

                    # Verify it used project A hash
                    project_a_calls = mock_subprocess.call_args_list

            # Test project B operations
            mock_cwd.return_value = project_b_root
            self.mock_port_registry._calculate_project_hash.return_value = (
                self.project_hash_b
            )

            with patch.object(
                self.docker_manager, "_get_available_runtime", return_value="podman"
            ):
                with patch(
                    "code_indexer.services.docker_manager.subprocess.run"
                ) as mock_subprocess:
                    mock_subprocess.return_value.returncode = 0
                    mock_subprocess.return_value.stdout = ""

                    # Call project B cleanup
                    self.docker_manager._force_cleanup_containers_with_guidance(
                        verbose=True
                    )

                    # Verify it used project B hash
                    project_b_calls = mock_subprocess.call_args_list

            # Verify the calls use different project hashes
            project_a_filter = None
            for call in project_a_calls:
                call_args = call[0][0]
                if "--filter" in call_args:
                    filter_index = call_args.index("--filter")
                    if filter_index + 1 < len(call_args):
                        project_a_filter = call_args[filter_index + 1]
                        break

            project_b_filter = None
            for call in project_b_calls:
                call_args = call[0][0]
                if "--filter" in call_args:
                    filter_index = call_args.index("--filter")
                    if filter_index + 1 < len(call_args):
                        project_b_filter = call_args[filter_index + 1]
                        break

            # Verify they are different and project-specific
            assert project_a_filter == f"name=cidx-{self.project_hash_a}-"
            assert project_b_filter == f"name=cidx-{self.project_hash_b}-"
            assert project_a_filter != project_b_filter

            # Verify neither uses the dangerous cross-project pattern
            assert project_a_filter != "name=cidx-"
            assert project_b_filter != "name=cidx-"

    @patch("pathlib.Path.cwd")
    def test_manual_guidance_commands_are_project_scoped(self, mock_cwd):
        """Test that all manual guidance commands include project hash."""
        mock_project_root = Path("/test/project/f")
        mock_cwd.return_value = mock_project_root
        self.mock_port_registry._calculate_project_hash.return_value = (
            self.project_hash_a
        )

        with patch.object(
            self.docker_manager, "_get_available_runtime", return_value="docker"
        ):
            with patch.object(
                self.docker_manager,
                "get_network_name",
                return_value=f"cidx-{self.project_hash_a}-network",
            ):
                # Test the actionable cleanup guidance
                self.docker_manager._provide_actionable_cleanup_guidance({})

                # Get all printed messages
                all_messages = []
                for call in self.mock_console.print.call_args_list:
                    if call[0] and isinstance(call[0][0], str):
                        all_messages.append(call[0][0])

                # Verify all container/volume commands use project hash
                for message in all_messages:
                    if "cidx-" in message and (
                        "ps -a" in message or "volume ls" in message
                    ):
                        # Should contain project hash, not generic cidx-
                        assert f"cidx-{self.project_hash_a}-" in message
                        # Should NOT contain the dangerous pattern
                        assert message.count("cidx-") == message.count(
                            f"cidx-{self.project_hash_a}-"
                        )


class TestProjectScopeDocumentation:
    """Test that the updated methods have proper documentation about project scoping."""

    def test_methods_have_critical_documentation(self):
        """Test that all fixed methods document their project-scoped behavior."""
        docker_manager = DockerManager(
            console=Mock(), project_name="test", force_docker=False
        )

        # Check that critical methods have updated docstrings mentioning project scoping
        methods_to_check = [
            "_force_cleanup_containers_with_guidance",
            "_validate_complete_cleanup",
            "_provide_actionable_cleanup_guidance",
        ]

        for method_name in methods_to_check:
            method = getattr(docker_manager, method_name)
            docstring = method.__doc__ or ""

            # Should mention project scoping or current project
            assert any(
                phrase in docstring.lower()
                for phrase in [
                    "project-scoped",
                    "current project",
                    "project hash",
                    "prevent cross-project",
                ]
            ), f"Method {method_name} should document its project-scoped behavior"

            # Should mention the critical nature
            assert (
                "critical" in docstring.lower()
            ), f"Method {method_name} should document why project scoping is critical"
