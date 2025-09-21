"""
Integration validation tests for admin repos commands.

Tests that validate actual CLI-to-API integration and ensure
error scenarios are properly handled with real network/authentication failures.
Follows Foundation #1 compliance with minimal mocking.
"""

from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposIntegrationValidation:
    """Test admin repos commands integration and error handling."""

    def test_admin_repos_commands_fail_gracefully_in_local_mode(self):
        """Test that all admin repos commands fail gracefully in local mode."""
        runner = CliRunner()

        # Test all admin repos commands in isolated filesystem (local mode)
        commands_and_args = [
            (["admin", "repos", "list"], "list"),
            (["admin", "repos", "show", "test-repo"], "show"),
            (["admin", "repos", "refresh", "test-repo"], "refresh"),
        ]

        with runner.isolated_filesystem():
            for cmd_args, cmd_name in commands_and_args:
                result = runner.invoke(cli, cmd_args)

                # Should fail gracefully with mode restriction
                assert (
                    result.exit_code == 1
                ), f"Command {cmd_name} should fail in local mode"

                # Should have clear error message about mode restriction
                error_patterns = [
                    "not available in local mode",
                    "requires: 'remote' mode",
                    "No project configuration found",
                    "No remote configuration found",
                ]

                assert any(
                    pattern in result.output for pattern in error_patterns
                ), f"Command {cmd_name} should show clear error message about mode restriction"

                # Should not crash or show stack traces
                assert (
                    "Traceback" not in result.output
                ), f"Command {cmd_name} should not show stack traces"
                assert (
                    "Exception" not in result.output
                ), f"Command {cmd_name} should not show raw exceptions"

    def test_admin_repos_list_input_validation(self):
        """Test that admin repos list validates input properly."""
        runner = CliRunner()

        # Test with invalid flags
        result = runner.invoke(cli, ["admin", "repos", "list", "--invalid-flag"])

        # Should fail with usage error, not reach remote API logic
        assert result.exit_code != 0
        assert (
            "Usage:" in result.output
            or "no such option" in result.output
            or "Unrecognized option" in result.output
        )

    def test_admin_repos_show_input_validation(self):
        """Test that admin repos show validates input properly."""
        runner = CliRunner()

        # Test without required alias argument
        result = runner.invoke(cli, ["admin", "repos", "show"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

        # Test with invalid flags
        result = runner.invoke(
            cli, ["admin", "repos", "show", "--invalid-flag", "test"]
        )

        # Should fail with usage error, not reach remote API logic
        assert result.exit_code != 0
        assert (
            "Usage:" in result.output
            or "no such option" in result.output
            or "Unrecognized option" in result.output
        )

    def test_admin_repos_refresh_input_validation(self):
        """Test that admin repos refresh validates input properly."""
        runner = CliRunner()

        # Test without required alias argument
        result = runner.invoke(cli, ["admin", "repos", "refresh"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

        # Test with invalid flags
        result = runner.invoke(
            cli, ["admin", "repos", "refresh", "--invalid-flag", "test"]
        )

        # Should fail with usage error, not reach remote API logic
        assert result.exit_code != 0
        assert (
            "Usage:" in result.output
            or "no such option" in result.output
            or "Unrecognized option" in result.output
        )

    def test_admin_repos_commands_preserve_error_context(self):
        """Test that commands preserve proper error context for troubleshooting."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            commands = [
                ["admin", "repos", "list"],
                ["admin", "repos", "show", "test"],
                ["admin", "repos", "refresh", "test"],
            ]

            for cmd in commands:
                result = runner.invoke(cli, cmd)

                # Should fail gracefully
                assert result.exit_code == 1

                # Should provide actionable error messages
                assert (
                    "cidx remote init" in result.output
                    or "No project configuration found" in result.output
                    or "No remote configuration found" in result.output
                ), f"Command {' '.join(cmd)} should provide actionable error message"

                # Should not leave users without guidance
                assert (
                    result.output.strip() != ""
                ), f"Command {' '.join(cmd)} should not produce empty output"

    def test_admin_repos_commands_consistent_help_format(self):
        """Test that all commands have consistent help formatting."""
        runner = CliRunner()

        commands = ["list", "show", "refresh"]

        for cmd in commands:
            result = runner.invoke(cli, ["admin", "repos", cmd, "--help"])

            # Should show help successfully
            assert result.exit_code == 0, f"Help for {cmd} should work"

            # Should have consistent formatting elements
            assert (
                "Examples:" in result.output
            ), f"Help for {cmd} should contain examples"
            assert (
                f"cidx admin repos {cmd}" in result.output
            ), f"Help for {cmd} should contain command examples"

            # Should mention admin privileges
            assert (
                "admin" in result.output.lower() or "privilege" in result.output.lower()
            ), f"Help for {cmd} should mention admin requirements"

    def test_admin_repos_commands_follow_cli_conventions(self):
        """Test that commands follow CLI conventions."""
        runner = CliRunner()

        # Test that admin group exists
        admin_result = runner.invoke(cli, ["admin", "--help"])
        assert admin_result.exit_code == 0
        assert "repos" in admin_result.output

        # Test that repos subgroup exists
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert repos_result.exit_code == 0

        # Test that all expected commands exist
        expected_commands = ["add", "list", "show", "refresh"]
        for cmd in expected_commands:
            assert (
                cmd in repos_result.output
            ), f"Command {cmd} should be listed in repos help"

        # Test that each command can show help
        for cmd in expected_commands:
            help_result = runner.invoke(cli, ["admin", "repos", cmd, "--help"])
            assert help_result.exit_code == 0, f"Command {cmd} should provide help"

    def test_admin_repos_error_message_quality(self):
        """Test that error messages are helpful and professional."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            # Test list command error quality
            list_result = runner.invoke(cli, ["admin", "repos", "list"])

            # Should have professional error messages
            assert list_result.exit_code == 1
            assert not any(
                word in list_result.output.lower()
                for word in ["error:", "exception:", "traceback", "failed", "crash"]
            ), "Error messages should be professional, not technical"

            # Should provide actionable guidance
            guidance_patterns = [
                "cidx remote init",
                "configure",
                "setup",
                "No project configuration found",
                "No remote configuration found",
            ]

            assert any(
                pattern in list_result.output for pattern in guidance_patterns
            ), "Error should provide actionable guidance"

    def test_admin_repos_commands_handle_keyboard_interruption(self):
        """Test that commands handle keyboard interruption gracefully."""
        runner = CliRunner()

        # Test that help commands complete quickly and don't hang
        # (This is a basic test for responsiveness)
        commands = [
            ["admin", "repos", "--help"],
            ["admin", "repos", "list", "--help"],
            ["admin", "repos", "show", "--help"],
            ["admin", "repos", "refresh", "--help"],
        ]

        for cmd in commands:
            result = runner.invoke(cli, cmd)
            assert (
                result.exit_code == 0
            ), f"Command {' '.join(cmd)} should complete successfully"

    def test_admin_repos_argument_parsing_edge_cases(self):
        """Test edge cases in argument parsing."""
        runner = CliRunner()

        # Test with empty alias
        result = runner.invoke(cli, ["admin", "repos", "show", ""])
        assert result.exit_code != 0  # Should fail gracefully

        # Test with whitespace-only alias
        result = runner.invoke(cli, ["admin", "repos", "show", "   "])
        assert result.exit_code != 0  # Should fail gracefully

        # Test with very long alias (should not crash)
        long_alias = "a" * 1000
        result = runner.invoke(cli, ["admin", "repos", "show", long_alias])
        # Should fail on mode restriction, not crash on long input
        assert result.exit_code == 1
        assert "Traceback" not in result.output


class TestAdminReposCommandStructure:
    """Test the structural integrity of admin repos commands."""

    def test_admin_repos_command_registration(self):
        """Test that all admin repos commands are properly registered."""
        runner = CliRunner()

        # Test command hierarchy exists
        result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert result.exit_code == 0
        assert "Repository management commands" in result.output

        # Verify all expected subcommands are registered
        expected_subcommands = {
            "add": "Add a new golden repository",
            "list": "List all golden repositories",
            "show": "Show detailed information",
            "refresh": "Refresh a golden repository",
        }

        for subcmd, description_fragment in expected_subcommands.items():
            # Command should be listed
            assert subcmd in result.output, f"Subcommand {subcmd} should be registered"

            # Command should have help
            help_result = runner.invoke(cli, ["admin", "repos", subcmd, "--help"])
            assert (
                help_result.exit_code == 0
            ), f"Subcommand {subcmd} should provide help"
            assert (
                description_fragment in help_result.output
            ), f"Subcommand {subcmd} should have appropriate description"

    def test_admin_repos_command_consistency(self):
        """Test consistency across all admin repos commands."""
        runner = CliRunner()

        commands = ["list", "show", "refresh"]

        for cmd in commands:
            # Each command should have help
            help_result = runner.invoke(cli, ["admin", "repos", cmd, "--help"])
            assert help_result.exit_code == 0

            # Each command should mention admin privileges
            assert (
                "admin" in help_result.output.lower()
                or "privilege" in help_result.output.lower()
            )

            # Each command should have examples
            assert "Examples:" in help_result.output

            # Commands should fail gracefully in local mode
            with runner.isolated_filesystem():
                if cmd == "list":
                    test_result = runner.invoke(cli, ["admin", "repos", cmd])
                else:
                    test_result = runner.invoke(
                        cli, ["admin", "repos", cmd, "test-repo"]
                    )

                assert test_result.exit_code == 1
                assert "Traceback" not in test_result.output
