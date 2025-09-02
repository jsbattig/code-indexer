"""
Unit tests for Golden Repository refresh workflow bug.

Tests the specific issue where refresh operations fail because cidx init
command doesn't use --force flag when configuration already exists.
"""

import tempfile
import subprocess
import os
import pytest
from unittest.mock import patch, MagicMock

from src.code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


class TestGoldenRepoRefreshWorkflow:
    """Test the specific refresh workflow issue with cidx init --force flag."""

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def test_repo_path(self, temp_data_dir):
        """Create a real test git repository."""
        repo_path = os.path.join(temp_data_dir, "test_repo")

        os.makedirs(repo_path)
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )

        # Add test files
        with open(os.path.join(repo_path, "README.md"), "w") as f:
            f.write("# Test Repository\n\nRefresh workflow test.\n")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        return repo_path

    @pytest.fixture
    def golden_repo_manager(self, temp_data_dir):
        """Create golden repository manager."""
        return GoldenRepoManager(data_dir=temp_data_dir)

    def test_refresh_would_fail_without_force_flag_simulation(
        self, golden_repo_manager, test_repo_path
    ):
        """Test simulation showing refresh would fail without --force flag."""

        # Mock subprocess.run to simulate the workflow commands
        with patch("subprocess.run") as mock_run:
            # Configure mock to return success for git operations but fail for cidx init without --force
            def mock_subprocess_run(*args, **kwargs):
                command = args[0] if args else kwargs.get("args", [])

                # Git operations succeed
                if command and command[0] == "git":
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # Simulate failure for cidx init without --force when config exists
                if (
                    command
                    and len(command) >= 4
                    and command[0] == "cidx"
                    and command[1] == "init"
                    and "--force" not in command
                ):
                    # If this is a refresh operation (directory already has config), fail
                    cwd = kwargs.get("cwd", "")
                    if cwd and os.path.exists(os.path.join(cwd, ".cidx-config.yaml")):
                        mock_result = MagicMock()
                        mock_result.returncode = 1
                        mock_result.stdout = ""
                        mock_result.stderr = "Configuration already exists in this directory. Use --force to overwrite"
                        return mock_result
                    else:
                        # Initial setup - create mock config file
                        if cwd:
                            config_path = os.path.join(cwd, ".cidx-config.yaml")
                            with open(config_path, "w") as f:
                                f.write("embedding_provider: voyage-ai\n")
                        mock_result = MagicMock()
                        mock_result.returncode = 0
                        mock_result.stdout = ""
                        mock_result.stderr = ""
                        return mock_result

                # cidx init with --force succeeds even if config exists (our fix)
                if (
                    command
                    and len(command) >= 4
                    and command[0] == "cidx"
                    and command[1] == "init"
                    and "--force" in command
                ):
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # Other cidx commands succeed
                if command and command[0] == "cidx":
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # Default success for other commands
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result

            mock_run.side_effect = mock_subprocess_run

            # Step 1: Add golden repository (should succeed)
            result = golden_repo_manager.add_golden_repo(
                repo_url=test_repo_path, alias="refresh-test", default_branch="master"
            )
            assert result["success"] is True

            # Step 2: Refresh should now succeed because our fix adds --force flag
            refresh_result = golden_repo_manager.refresh_golden_repo("refresh-test")
            assert refresh_result["success"] is True

    def test_refresh_workflow_calls_correct_commands(
        self, golden_repo_manager, test_repo_path
    ):
        """Test that refresh workflow calls the expected commands with --force flag."""

        with patch("subprocess.run") as mock_run:
            # Mock successful responses for all commands
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Add golden repository first
            golden_repo_manager.add_golden_repo(
                repo_url=test_repo_path, alias="command-test", default_branch="master"
            )

            # Clear the mock call history
            mock_run.reset_mock()

            # Now call refresh
            golden_repo_manager.refresh_golden_repo("command-test")

            # Verify that cidx init was called WITH --force flag (this is the fix!)
            init_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0]
                and len(call[0][0]) >= 2
                and call[0][0][0] == "cidx"
                and call[0][0][1] == "init"
            ]

            assert (
                len(init_calls) > 0
            ), "cidx init should have been called during refresh"

            # After the fix - init is called WITH --force during refresh
            for call in init_calls:
                command = call[0][0]
                assert "--force" in command, "Refresh should now use --force flag"

    def test_post_clone_workflow_command_sequence(
        self, golden_repo_manager, test_repo_path
    ):
        """Test the exact sequence of commands in post-clone workflow."""

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Test the workflow directly
            clone_path = os.path.join(
                golden_repo_manager.golden_repos_dir, "workflow-test"
            )
            os.makedirs(clone_path, exist_ok=True)

            # This should call the post-clone workflow
            golden_repo_manager._execute_post_clone_workflow(clone_path)

            # Verify the expected command sequence
            expected_commands = [
                ["cidx", "init", "--embedding-provider", "voyage-ai"],
                ["cidx", "start", "--force-docker"],
                ["cidx", "status", "--force-docker"],
                ["cidx", "index"],
                ["cidx", "stop", "--force-docker"],
            ]

            assert len(mock_run.call_args_list) == len(expected_commands)

            for i, (actual_call, expected_cmd) in enumerate(
                zip(mock_run.call_args_list, expected_commands)
            ):
                actual_command = actual_call[0][0]
                assert (
                    actual_command == expected_cmd
                ), f"Command {i+1} mismatch: expected {expected_cmd}, got {actual_command}"

                # Verify cwd is set correctly
                assert actual_call[1]["cwd"] == clone_path

    def test_initial_setup_uses_no_force_flag(
        self, golden_repo_manager, test_repo_path
    ):
        """Test that initial repository setup doesn't use --force flag."""

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Add golden repository (initial setup)
            golden_repo_manager.add_golden_repo(
                repo_url=test_repo_path, alias="initial-test", default_branch="master"
            )

            # Find the cidx init call
            init_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0]
                and len(call[0][0]) >= 2
                and call[0][0][0] == "cidx"
                and call[0][0][1] == "init"
            ]

            assert (
                len(init_calls) == 1
            ), "cidx init should be called once during initial setup"

            init_command = init_calls[0][0][0]
            assert (
                "--force" not in init_command
            ), "Initial setup should NOT use --force flag"
            assert (
                "--embedding-provider" in init_command
            ), "Should include embedding provider"
            assert "voyage-ai" in init_command, "Should use voyage-ai provider"

    def test_refresh_uses_force_flag_after_fix(
        self, golden_repo_manager, test_repo_path
    ):
        """Test that refresh now correctly uses --force flag (after fix)."""

        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_result.stderr = ""
            mock_run.return_value = mock_result

            # Add golden repository first
            golden_repo_manager.add_golden_repo(
                repo_url=test_repo_path, alias="force-test", default_branch="master"
            )

            # Clear the mock call history
            mock_run.reset_mock()

            # Now call refresh
            golden_repo_manager.refresh_golden_repo("force-test")

            # Find the cidx init call from refresh
            init_calls = [
                call
                for call in mock_run.call_args_list
                if call[0][0]
                and len(call[0][0]) >= 2
                and call[0][0][0] == "cidx"
                and call[0][0][1] == "init"
            ]

            assert (
                len(init_calls) == 1
            ), "cidx init should be called once during refresh"

            init_command = init_calls[0][0][0]
            assert (
                "--force" in init_command
            ), "Refresh should use --force flag after fix"
            assert (
                "--embedding-provider" in init_command
            ), "Should include embedding provider"
            assert "voyage-ai" in init_command, "Should use voyage-ai provider"

    def test_refresh_succeeds_with_force_flag(
        self, golden_repo_manager, test_repo_path
    ):
        """Test that refresh succeeds when using --force flag."""

        with patch("subprocess.run") as mock_run:

            def mock_subprocess_run(*args, **kwargs):
                command = args[0] if args else kwargs.get("args", [])

                # Git operations succeed
                if command and command[0] == "git":
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # cidx init without --force fails if config exists
                if (
                    command
                    and len(command) >= 4
                    and command[0] == "cidx"
                    and command[1] == "init"
                    and "--force" not in command
                ):
                    # Create config file for initial setup
                    cwd = kwargs.get("cwd", "")
                    if cwd:
                        config_path = os.path.join(cwd, ".cidx-config.yaml")
                        with open(config_path, "w") as f:
                            f.write("embedding_provider: voyage-ai\n")
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # cidx init with --force succeeds even if config exists
                if (
                    command
                    and len(command) >= 4
                    and command[0] == "cidx"
                    and command[1] == "init"
                    and "--force" in command
                ):
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # Other cidx commands succeed
                if command and command[0] == "cidx":
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = ""
                    mock_result.stderr = ""
                    return mock_result

                # Default success
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
                return mock_result

            mock_run.side_effect = mock_subprocess_run

            # Add golden repository
            result = golden_repo_manager.add_golden_repo(
                repo_url=test_repo_path, alias="success-test", default_branch="master"
            )
            assert result["success"] is True

            # Refresh should now succeed with --force flag
            refresh_result = golden_repo_manager.refresh_golden_repo("success-test")
            assert refresh_result["success"] is True
            assert "refreshed successfully" in refresh_result["message"]
