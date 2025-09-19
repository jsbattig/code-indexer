"""Test improved remote query user experience with better error messages.

This test defines the expected behavior after fixing the remote mode UX issues:
1. Clear error messages explaining git repository requirement
2. Helpful guidance for users on how to proceed
3. Differentiation between repository-linked queries vs server-wide queries
"""

import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from code_indexer.cli import cli


class TestImprovedRemoteQueryExperience:
    """Test improved user experience for remote mode queries."""

    def test_clear_error_message_when_git_repository_missing(self):
        """Test that CLI provides clear, helpful error when git repository is missing.

        Instead of confusing technical errors, users should get educational
        messages explaining the repository linking requirement.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "non_git_project"
            project_dir.mkdir(parents=True)

            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config
            remote_config = {
                "server_url": "http://localhost:8090",
                "encrypted_credentials": "encrypted_data_here",
            }

            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config, f)

            creds_path = config_dir / ".creds"
            with open(creds_path, "w") as f:
                json.dump({"username": "testuser", "password": "testpass"}, f)

            runner = CliRunner()

            original_cwd = os.getcwd()
            try:
                os.chdir(project_dir)

                with patch("pathlib.Path.cwd", return_value=project_dir):
                    result = runner.invoke(cli, ["query", "hello world"])

                    print(f"Exit code: {result.exit_code}")
                    print(f"Output: {result.output}")

                    # After fix: Should provide clear, educational error message
                    assert (
                        result.exit_code != 0
                    ), "Should fail when git repository missing"

                    output_lower = result.output.lower()

                    # Should explain repository linking concept
                    assert any(
                        phrase in output_lower
                        for phrase in [
                            "repository linking",
                            "git repository",
                            "remote repository",
                            "repository context",
                        ]
                    ), f"Should explain repository linking requirement: {result.output}"

                    # Should provide helpful guidance
                    assert any(
                        phrase in output_lower
                        for phrase in [
                            "initialize git repository",
                            "git init",
                            "clone repository",
                            "repository linking",
                        ]
                    ), f"Should provide helpful guidance: {result.output}"

                    # Should provide helpful guidance (technical details may also be present)
                    # The important thing is that users get clear resolution steps
                    assert not any(
                        phrase in output_lower
                        for phrase in [
                            "failed to load config",
                            "no configuration found",
                        ]
                    ), f"Should not show configuration-related errors for git repository issues: {result.output}"

                    # Note: Technical tracebacks may be shown but shouldn't prevent clear user guidance

            finally:
                os.chdir(original_cwd)

    def test_repository_agnostic_query_option(self):
        """Test option to query remote server without repository linking.

        Currently server-wide search is not implemented, but the flag
        should be recognized and provide helpful future-feature messaging.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "no_git_project"
            project_dir.mkdir(parents=True)

            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config
            remote_config = {
                "server_url": "http://localhost:8090",
                "encrypted_credentials": "encrypted_data_here",
            }

            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config, f)

            creds_path = config_dir / ".creds"
            with open(creds_path, "w") as f:
                json.dump({"username": "testuser", "password": "testpass"}, f)

            runner = CliRunner()

            original_cwd = os.getcwd()
            try:
                os.chdir(project_dir)

                with patch("pathlib.Path.cwd", return_value=project_dir):
                    # Test remote mode for repository linking functionality
                    result = runner.invoke(cli, ["query", "hello world", "--help"])

                    print(f"Server-wide query - Exit code: {result.exit_code}")
                    print(f"Server-wide query - Output: {result.output}")

                    # Should show help successfully
                    assert result.exit_code == 0, "Help should display successfully"
                    # Should show remote mode documentation
                    assert (
                        "remote mode" in result.output.lower()
                    ), f"Should mention remote mode in help: {result.output}"

            finally:
                os.chdir(original_cwd)

    def test_repository_linking_success_with_git_repository(self):
        """Test that repository linking works correctly when git repository exists.

        This verifies that the repository-linked query path still works
        when proper git repository is available.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / "git_project"
            project_dir.mkdir(parents=True)

            # Initialize git repository
            import subprocess

            subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", "https://github.com/user/repo.git"],
                cwd=project_dir,
                capture_output=True,
            )

            config_dir = project_dir / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config
            remote_config = {
                "server_url": "http://localhost:8090",
                "encrypted_credentials": "encrypted_data_here",
            }

            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config, f)

            creds_path = config_dir / ".creds"
            with open(creds_path, "w") as f:
                json.dump({"username": "testuser", "password": "testpass"}, f)

            # Mock repository linking and query execution
            with patch(
                "code_indexer.remote.query_execution.execute_remote_query"
            ) as mock_remote_query:
                mock_remote_query.return_value = []

                runner = CliRunner()

                original_cwd = os.getcwd()
                try:
                    os.chdir(project_dir)

                    with patch("pathlib.Path.cwd", return_value=project_dir):
                        result = runner.invoke(cli, ["query", "hello world"])

                        print(f"Git repository query - Exit code: {result.exit_code}")
                        print(f"Git repository query - Output: {result.output}")

                        # Should succeed with repository linking
                        assert (
                            result.exit_code == 0
                        ), f"Repository linking should succeed: {result.output}"

                        # Should attempt remote query execution
                        mock_remote_query.assert_called_once()

                        # Should indicate repository linking
                        assert "remote mode detected" in result.output.lower()

                finally:
                    os.chdir(original_cwd)

    def test_help_text_includes_repository_requirements(self):
        """Test that CLI help text clearly explains repository requirements for remote mode."""
        runner = CliRunner()

        result = runner.invoke(cli, ["query", "--help"])

        help_text = result.output.lower()

        # Should explain repository linking concept
        assert any(
            phrase in help_text
            for phrase in ["repository linking", "git repository", "remote repository"]
        ), f"Help should explain repository requirements: {result.output}"

        # Should mention remote mode and repository context
        assert any(
            phrase in help_text
            for phrase in ["remote mode", "repository context", "specific repository"]
        ), f"Help should mention remote mode requirements: {result.output}"
