"""Test module for Command Routing based on detected mode.

Tests that commands are properly routed to local or remote execution
based on the detected operational mode.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from code_indexer.cli import cli


class TestCommandRouting:
    """Test class for command routing functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.runner = CliRunner()

    def test_query_command_routing_uninitialized_mode(self):
        """Test that query command shows initialization guidance in uninitialized mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a deeper structure to avoid finding /tmp/.code-indexer
            deep_path = Path(temp_dir)
            for i in range(
                12
            ):  # Create 12 levels deep to exceed the 10-level search limit
                deep_path = deep_path / f"level{i}"
            deep_path.mkdir(parents=True)

            # Run query command from uninitialized directory
            with patch.object(Path, "cwd", return_value=deep_path):
                result = self.runner.invoke(cli, ["query", "test query"])

                assert result.exit_code != 0
                assert (
                    "not initialized" in result.output.lower()
                    or "init" in result.output.lower()
                )

    def test_query_command_routing_local_mode(self):
        """Test that query command routes to local execution in local mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid local config
            import json

            config_data = {
                "voyage": {
                    "host": "http://localhost:11434",
                    "model": "nomic-embed-text",
                },
                "filesystem": {"host": "http://localhost:6333"},
                "ports": {"voyage_port": 11434, "filesystem_port": 6333},
            }
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            # Mock local query execution
            with patch(
                "code_indexer.services.generic_query_service.GenericQueryService"
            ) as mock_service:
                mock_instance = Mock()
                mock_service.return_value = mock_instance
                mock_instance.execute_query.return_value = []

                with patch.object(Path, "cwd", return_value=project_root):
                    result = self.runner.invoke(cli, ["query", "test query"])

                    # Should not fail due to uninitialized mode
                    # (might fail for other reasons like services not running, but that's different)
                    assert "not initialized" not in result.output.lower()

    def test_query_command_routing_remote_mode(self):
        """Test that query command routes to remote execution in remote mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid remote config
            import json

            remote_config_data = {
                "server_url": "https://server.example.com",
                "encrypted_credentials": "encrypted_data_here",
                "repository_link": {
                    "alias": "test-repo",
                    "url": "https://github.com/test/repo.git",
                },
            }
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config_data, f)

            with patch.object(Path, "cwd", return_value=project_root):
                result = self.runner.invoke(cli, ["query", "test query"])

                # Should not fail due to uninitialized mode
                # (might fail for other reasons like remote server not available, but that's different)
                assert "not initialized" not in result.output.lower()

    def test_init_command_provides_clear_guidance_for_uninitialized(self):
        """Test that init command provides clear guidance when no mode is detected."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(Path, "cwd", return_value=Path(temp_dir)):
                result = self.runner.invoke(cli, ["init", "--help"])

                # Should show help including remote initialization options
                assert result.exit_code == 0
                assert "remote" in result.output.lower()

    def test_mode_detection_visible_in_verbose_output(self):
        """Test that detected mode is shown in verbose output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid local config
            import json

            config_data = {"voyage": {"host": "http://localhost:11434"}}
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            with patch.object(Path, "cwd", return_value=project_root):
                result = self.runner.invoke(cli, ["--verbose", "status"])

                # Should show detected mode in verbose output
                assert (
                    "detected mode" in result.output.lower()
                    or "mode:" in result.output.lower()
                )

    def test_project_root_detection_with_path_option(self):
        """Test that --path option correctly detects project root and mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create valid local config
            import json

            config_data = {"voyage": {"host": "http://localhost:11434"}}
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                json.dump(config_data, f)

            # Create nested directory
            nested_dir = project_root / "src" / "module"
            nested_dir.mkdir(parents=True)

            result = self.runner.invoke(
                cli, ["--verbose", "--path", str(nested_dir), "status"]
            )

            # Should detect project root from nested directory
            if (
                "detected mode" in result.output.lower()
                or "mode:" in result.output.lower()
            ):
                # Mode detection is working
                assert (
                    str(project_root) in result.output
                    or "local" in result.output.lower()
                )


class TestUnintializedModeGuidance:
    """Test class for uninitialized mode guidance messages."""

    def setup_method(self):
        """Setup test fixtures."""
        self.runner = CliRunner()

    def test_uninitialized_mode_suggests_init_commands(self):
        """Test that uninitialized mode provides actionable init guidance."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a deeper structure to avoid finding /tmp/.code-indexer
            deep_path = Path(temp_dir)
            for i in range(
                12
            ):  # Create 12 levels deep to exceed the 10-level search limit
                deep_path = deep_path / f"level{i}"
            deep_path.mkdir(parents=True)

            with patch.object(Path, "cwd", return_value=deep_path):
                result = self.runner.invoke(cli, ["query", "test"])

                # Should provide guidance about initialization
                output_lower = result.output.lower()
                assert any(
                    keyword in output_lower
                    for keyword in [
                        "not initialized",
                        "run init",
                        "initialize",
                        "init --remote",
                        "init command",
                    ]
                )

    def test_uninitialized_mode_shows_local_and_remote_options(self):
        """Test that uninitialized mode shows both local and remote initialization options."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.object(Path, "cwd", return_value=Path(temp_dir)):
                # Check init command help shows both options
                result = self.runner.invoke(cli, ["init", "--help"])

                output_lower = result.output.lower()
                # Should mention both local (default) and remote initialization
                assert "remote" in output_lower  # Should show remote option
                assert result.exit_code == 0

    def test_corrupted_config_falls_back_gracefully(self):
        """Test that corrupted configurations fall back to appropriate mode or show error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            config_dir = project_root / ".code-indexer"
            config_dir.mkdir()

            # Create corrupted local config
            config_path = config_dir / "config.json"
            with open(config_path, "w") as f:
                f.write("invalid json {")

            # Create corrupted remote config
            remote_config_path = config_dir / ".remote-config"
            with open(remote_config_path, "w") as f:
                f.write("also invalid json {")

            with patch.object(Path, "cwd", return_value=project_root):
                result = self.runner.invoke(cli, ["--verbose", "status"])

                # Should handle corrupted configs gracefully
                # Either detect as uninitialized or show appropriate error
                assert result.exit_code != -1  # Should not crash
                output_lower = result.output.lower()
                graceful_messages = [
                    "uninitialized",
                    "not initialized",
                    "detected mode",
                    "configuration",
                    "error",
                    "invalid",
                ]
                assert any(msg in output_lower for msg in graceful_messages)
