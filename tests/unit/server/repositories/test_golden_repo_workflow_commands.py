"""
Test suite for golden repository post-clone workflow command generation.

This test verifies that the workflow commands generated for post-clone operations
are correct and don't include obsolete container management flags.

Bug #2: Obsolete Workflow Commands (BLOCKING)
- Location: src/code_indexer/server/repositories/golden_repo_manager.py:792-798
- Issue: Workflow uses obsolete --force-docker flags that don't exist anymore
- Impact: ALL golden repo registrations fail (100% failure rate) at workflow step 2
- Root Cause: Code not updated for FilesystemVectorStore (container-free architecture)
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from code_indexer.server.repositories.golden_repo_manager import GoldenRepoManager


class TestGoldenRepoWorkflowCommands:
    """Test suite for post-clone workflow command generation."""

    @pytest.fixture
    def mock_repo_manager(self, tmp_path):
        """Create a GoldenRepoManager with mocked dependencies."""
        manager = GoldenRepoManager(data_dir=str(tmp_path))
        return manager

    @pytest.fixture
    def mock_clone_path(self, tmp_path):
        """Create a mock clone path."""
        clone_path = tmp_path / "test-repo"
        clone_path.mkdir()
        return clone_path

    def test_workflow_commands_no_obsolete_force_docker_flags(
        self, mock_repo_manager, mock_clone_path
    ):
        """
        Test that workflow commands don't include obsolete --force-docker flags.

        EXPECTED TO FAIL INITIALLY (demonstrating bug exists).

        Bug: Current workflow includes:
        - ["cidx", "start", "--force-docker"]  # OBSOLETE
        - ["cidx", "status", "--force-docker"] # OBSOLETE
        - ["cidx", "stop", "--force-docker"]   # OBSOLETE

        These commands fail because:
        1. FilesystemVectorStore doesn't need containers (architecture change)
        2. --force-docker flag no longer exists in CLI
        3. start/stop/status commands are unnecessary for container-free backend

        Correct workflow should ONLY contain:
        1. cidx init --embedding-provider voyage-ai
        2. cidx index
        """
        # Arrange: Mock subprocess.run to capture commands without executing
        executed_commands = []

        def mock_subprocess_run(command, **kwargs):
            executed_commands.append(command)
            # Return successful mock result
            return Mock(returncode=0, stdout="", stderr="")

        with patch.object(subprocess, "run", side_effect=mock_subprocess_run):
            # Act: Execute post-clone workflow
            mock_repo_manager._execute_post_clone_workflow(
                clone_path=str(mock_clone_path),
                force_init=False,
                enable_temporal=False,
                temporal_options=None,
            )

        # Assert: Verify NO --force-docker flags in ANY command
        for command in executed_commands:
            assert (
                "--force-docker" not in command
            ), f"Found obsolete --force-docker flag in command: {command}"

        # Assert: Workflow should ONLY contain init and index commands
        assert len(executed_commands) == 2, (
            f"Expected 2 commands (init, index), got {len(executed_commands)}: "
            f"{executed_commands}"
        )

        # Assert: First command is 'cidx init'
        assert executed_commands[0][0] == "cidx", "First command should be cidx"
        assert executed_commands[0][1] == "init", "First command should be 'cidx init'"
        assert (
            "--embedding-provider" in executed_commands[0]
        ), "init command missing --embedding-provider"

        # Assert: Second command is 'cidx index'
        assert executed_commands[1][0] == "cidx", "Second command should be cidx"
        assert (
            executed_commands[1][1] == "index"
        ), "Second command should be 'cidx index'"

        # Assert: NO start/stop/status commands (obsolete for FilesystemVectorStore)
        command_verbs = [cmd[1] for cmd in executed_commands if len(cmd) > 1]
        assert "start" not in command_verbs, "start command is obsolete"
        assert "stop" not in command_verbs, "stop command is obsolete"
        assert "status" not in command_verbs, "status command is obsolete"
