"""End-to-end integration test for CLI error handling fixes.

This test validates that the fixes for 'str' object has no attribute 'get' errors
work correctly in real command execution scenarios.
"""

import json
import pytest
from click.testing import CliRunner

from code_indexer.cli import cli


class TestCLIErrorHandlingE2E:
    """End-to-end tests for CLI error handling improvements."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    @pytest.fixture
    def temp_project_with_remote(self, tmp_path):
        """Create a temporary project with remote configuration."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create minimal local config to satisfy find_project_root
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps({"project_name": "test", "codebase_dir": str(project_dir)})
        )

        # Create remote configuration
        remote_file = config_dir / ".remote-config"
        remote_file.write_text(
            json.dumps(
                {
                    "mode": "remote",
                    "server_url": "http://localhost:8000",
                    "encrypted_credentials": {},
                }
            )
        )

        return project_dir

    @pytest.fixture
    def temp_project_without_remote(self, tmp_path):
        """Create a temporary project without remote configuration."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create minimal local config only
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps({"project_name": "test", "codebase_dir": str(project_dir)})
        )

        return project_dir

    def test_auth_status_without_remote_config(
        self, runner, temp_project_without_remote
    ):
        """Test auth status command handles missing remote config gracefully."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_without_remote))

            # Should not crash with attribute error
            result = runner.invoke(cli, ["auth", "status"])

            # Should show appropriate error message
            assert "'str' object has no attribute" not in result.output
            assert (
                "remote" in result.output.lower()
                or "not available" in result.output.lower()
            )
            assert result.exit_code == 1  # Should exit with error

    def test_system_health_without_remote_config(
        self, runner, temp_project_without_remote
    ):
        """Test system health command handles missing remote config gracefully."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_without_remote))

            # Should not crash with attribute error
            result = runner.invoke(cli, ["system", "health"])

            # Should show appropriate error message
            assert "'str' object has no attribute" not in result.output
            assert (
                "remote" in result.output.lower()
                or "not available" in result.output.lower()
            )
            assert result.exit_code == 1  # Should exit with error

    def test_auth_status_with_remote_config_no_credentials(
        self, runner, temp_project_with_remote
    ):
        """Test auth status with remote config but no stored credentials."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_with_remote))

            # Should handle gracefully even without credentials
            result = runner.invoke(cli, ["auth", "status"])

            # Should show not authenticated status
            assert "'str' object has no attribute" not in result.output
            assert (
                "Authenticated: No" in result.output or "Not logged in" in result.output
            )
            assert result.exit_code == 0  # Should complete successfully

    def test_auth_validate_silent_mode(self, runner, temp_project_with_remote):
        """Test auth validate command in silent mode handles errors gracefully."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_with_remote))

            # Silent mode should not output anything but should not crash
            result = runner.invoke(cli, ["auth", "validate"])

            # Should not have attribute errors even in silent mode
            assert "'str' object has no attribute" not in result.output
            # Silent mode may have no output
            assert len(result.output) == 0 or "Error" not in result.output
            # Exit code indicates validation result
            assert result.exit_code in [0, 1]

    def test_auth_validate_verbose_mode(self, runner, temp_project_with_remote):
        """Test auth validate command in verbose mode shows proper messages."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_with_remote))

            # Verbose mode should show messages
            result = runner.invoke(cli, ["auth", "validate", "--verbose"])

            # Should not have attribute errors
            assert "'str' object has no attribute" not in result.output
            # Verbose mode should show some output
            assert (
                "Validating" in result.output
                or "credentials" in result.output.lower()
                or "No stored" in result.output
            )
            assert result.exit_code in [0, 1]

    def test_system_health_detailed_mode(self, runner, temp_project_with_remote):
        """Test system health detailed mode handles missing credentials gracefully."""
        with runner.isolated_filesystem():
            import os

            os.chdir(str(temp_project_with_remote))

            # Detailed mode without valid credentials
            result = runner.invoke(cli, ["system", "health", "--detailed"])

            # Should not crash with attribute error
            assert "'str' object has no attribute" not in result.output
            # Should show some health-related output or error
            assert "health" in result.output.lower() or "error" in result.output.lower()

    def test_commands_help_always_works(self, runner):
        """Test that help commands always work regardless of configuration."""
        # Help should work without any configuration
        commands = [
            ["auth", "--help"],
            ["auth", "status", "--help"],
            ["auth", "validate", "--help"],
            ["system", "--help"],
            ["system", "health", "--help"],
        ]

        for cmd in commands:
            result = runner.invoke(cli, cmd)
            # Help should always succeed
            assert result.exit_code == 0
            assert "'str' object has no attribute" not in result.output
            assert "help" in result.output.lower() or "usage" in result.output.lower()


class TestErrorMessageClarity:
    """Test that error messages are clear and actionable."""

    @pytest.fixture
    def runner(self):
        """Create a CLI test runner."""
        return CliRunner()

    def test_missing_remote_config_message(self, runner, tmp_path):
        """Test that missing remote config shows clear message."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create minimal local config only
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps({"project_name": "test", "codebase_dir": str(project_dir)})
        )

        with runner.isolated_filesystem():
            import os

            os.chdir(str(project_dir))

            # Try auth status which requires remote mode
            result = runner.invoke(cli, ["auth", "status"])

            # Should show clear guidance
            assert "'str' object has no attribute" not in result.output
            # Should mention remote mode requirement
            assert "remote" in result.output.lower()
            assert "mode" in result.output.lower()

    def test_corrupted_remote_config_message(self, runner, tmp_path):
        """Test that corrupted remote config shows clear message."""
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()

        # Create minimal local config
        config_dir = project_dir / ".code-indexer"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text(
            json.dumps({"project_name": "test", "codebase_dir": str(project_dir)})
        )

        # Create corrupted remote config
        remote_file = config_dir / ".remote-config"
        remote_file.write_text("{ invalid json }")

        with runner.isolated_filesystem():
            import os

            os.chdir(str(project_dir))

            # Try auth status with corrupted config
            result = runner.invoke(cli, ["auth", "status"])

            # Should handle gracefully
            assert "'str' object has no attribute" not in result.output
            # Should indicate configuration issue
            assert (
                "config" in result.output.lower() or "remote" in result.output.lower()
            )
            assert result.exit_code == 1
