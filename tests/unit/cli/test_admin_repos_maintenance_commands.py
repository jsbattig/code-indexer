"""
Test CLI admin repository maintenance commands.

Tests the CLI commands for golden repository maintenance including
list, show, and refresh operations. Follows Foundation #1 compliance
with minimal mocking and real CLI integration testing.
"""

from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposMaintenanceCommands:
    """Test admin repos maintenance CLI commands."""

    def test_admin_repos_list_command_exists(self):
        """Test that admin repos list command exists."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "list", "--help"])

        # Command should exist and show help
        assert result.exit_code == 0
        assert "List all golden repositories" in result.output
        assert "admin privileges" in result.output

    def test_admin_repos_show_command_exists(self):
        """Test that admin repos show command exists."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "show", "--help"])

        # Command should exist and show help
        assert result.exit_code == 0
        assert "Show detailed information" in result.output
        assert "alias" in result.output
        assert "admin" in result.output

    def test_admin_repos_refresh_command_exists(self):
        """Test that admin repos refresh command exists."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "refresh", "--help"])

        # Command should exist and show help
        assert result.exit_code == 0
        assert "Refresh a golden repository" in result.output
        assert "alias" in result.output
        assert "admin" in result.output

    def test_admin_repos_show_requires_alias_argument(self):
        """Test that admin repos show requires alias argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "show"])

        # Should fail without alias
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_admin_repos_refresh_requires_alias_argument(self):
        """Test that admin repos refresh requires alias argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "refresh"])

        # Should fail without alias
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_admin_repos_list_mode_restriction_in_local_mode(self):
        """Test admin repos list fails in local mode (expected)."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "list"])

            # Should fail on mode restriction (expected in temp dir without remote config)
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_repos_show_mode_restriction_in_local_mode(self):
        """Test admin repos show fails in local mode (expected)."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "show", "test-repo"])

            # Should fail on mode restriction before reaching API logic
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_repos_refresh_mode_restriction_in_local_mode(self):
        """Test admin repos refresh fails in local mode (expected)."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "refresh", "test-repo"])

            # Should fail on mode restriction before reaching API logic
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_repos_list_help_contains_examples(self):
        """Test that list command help contains usage examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "list", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.output
        assert "cidx admin repos list" in result.output

    def test_admin_repos_show_help_contains_examples(self):
        """Test that show command help contains usage examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "show", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.output
        assert "cidx admin repos show" in result.output

    def test_admin_repos_refresh_help_contains_examples(self):
        """Test that refresh command help contains usage examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "refresh", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.output
        assert "cidx admin repos refresh" in result.output

    def test_admin_repos_commands_follow_error_message_patterns(self):
        """Test that error messages follow consistent patterns."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            # Test list command error message structure
            list_result = runner.invoke(cli, ["admin", "repos", "list"])
            assert list_result.exit_code == 1

            # Test show command error message structure
            show_result = runner.invoke(cli, ["admin", "repos", "show", "test"])
            assert show_result.exit_code == 1

            # Test refresh command error message structure
            refresh_result = runner.invoke(cli, ["admin", "repos", "refresh", "test"])
            assert refresh_result.exit_code == 1

            # All should have similar error patterns for mode restrictions
            for result in [list_result, show_result, refresh_result]:
                assert (
                    "not available in local mode" in result.output
                    or "requires: 'remote' mode" in result.output
                    or "No project configuration found" in result.output
                    or "No remote configuration found" in result.output
                )


class TestAdminReposCommandIntegration:
    """Test admin repos command integration and structure."""

    def test_admin_repos_commands_are_under_admin_group(self):
        """Test that repos commands are properly grouped under admin."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "--help"])

        assert result.exit_code == 0
        assert "repos" in result.output

    def test_admin_repos_group_help(self):
        """Test admin repos group help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "--help"])

        assert result.exit_code == 0
        assert "Repository management commands" in result.output
        assert "add" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "refresh" in result.output

    def test_admin_repos_list_help_details(self):
        """Test admin repos list command help details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "list", "--help"])

        assert result.exit_code == 0
        assert "List all golden repositories" in result.output
        assert "formatted table" in result.output
        assert "status" in result.output
        assert "admin privileges" in result.output

    def test_admin_repos_show_help_details(self):
        """Test admin repos show command help details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "show", "--help"])

        assert result.exit_code == 0
        assert "Show detailed information" in result.output
        assert "Args:" in result.output
        assert "alias" in result.output
        assert "Examples:" in result.output

    def test_admin_repos_refresh_help_details(self):
        """Test admin repos refresh command help details."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "refresh", "--help"])

        assert result.exit_code == 0
        assert "Refresh a golden repository" in result.output
        assert "re-indexing" in result.output
        assert "asynchronously" in result.output
        assert "Args:" in result.output
        assert "alias" in result.output

    def test_admin_repos_command_structure_matches_other_admin_commands(self):
        """Test that command structure is consistent with other admin commands."""
        runner = CliRunner()

        # Test admin group commands all exist
        admin_result = runner.invoke(cli, ["admin", "--help"])
        assert "repos" in admin_result.output
        assert "users" in admin_result.output

        # Test repos subcommands exist
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert "add" in repos_result.output
        assert "list" in repos_result.output
        assert "show" in repos_result.output
        assert "refresh" in repos_result.output

        # All should be available and follow same pattern
        for cmd in ["add", "list", "show", "refresh"]:
            cmd_result = runner.invoke(cli, ["admin", "repos", cmd, "--help"])
            assert (
                cmd_result.exit_code == 0
            ), f"Command {cmd} should exist and show help"

    def test_admin_repos_input_validation_patterns(self):
        """Test that input validation follows consistent patterns."""
        runner = CliRunner()

        # Test that commands requiring arguments fail appropriately
        show_result = runner.invoke(cli, ["admin", "repos", "show"])
        refresh_result = runner.invoke(cli, ["admin", "repos", "refresh"])

        # Both should fail with missing argument errors
        assert show_result.exit_code != 0
        assert refresh_result.exit_code != 0

        # Error messages should indicate missing arguments
        for result in [show_result, refresh_result]:
            assert (
                "Missing argument" in result.output
                or "Usage:" in result.output
                or "Error:" in result.output
            )

    def test_admin_repos_error_handling_consistency(self):
        """Test that error handling is consistent across commands."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            # Test all commands in an environment without remote config
            commands = [
                ["admin", "repos", "list"],
                ["admin", "repos", "show", "test"],
                ["admin", "repos", "refresh", "test"],
            ]

            for cmd in commands:
                result = runner.invoke(cli, cmd)

                # All should fail with similar error patterns
                assert result.exit_code == 1
                assert (
                    "not available in local mode" in result.output
                    or "requires: 'remote' mode" in result.output
                    or "No project configuration found" in result.output
                    or "No remote configuration found" in result.output
                )
