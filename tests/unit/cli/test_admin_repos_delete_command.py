"""
Tests for CLI admin repos delete command.

Tests the CLI command for golden repository deletion including
safety features, confirmation prompts, and error handling.
Follows TDD methodology and MESSI Rule #1 (anti-mock).
"""

from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposDeleteCommand:
    """Test admin repos delete CLI command."""

    def test_admin_repos_delete_command_exists(self):
        """Test that admin repos delete command exists (will fail initially)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        # Command should exist and show help
        assert result.exit_code == 0
        assert "Delete a golden repository" in result.output
        assert "admin" in result.output.lower()

    def test_admin_repos_delete_requires_alias_argument(self):
        """Test that admin repos delete requires alias argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete"])

        # Should fail without alias
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

    def test_admin_repos_delete_has_force_flag(self):
        """Test that delete command has --force flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output
        assert "confirmation prompt" in result.output.lower()

    def test_admin_repos_delete_help_contains_safety_warnings(self):
        """Test that delete command help contains safety warnings."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "permanently delete" in result.output.lower()
        assert "cannot be undone" in result.output.lower()
        assert "admin privileges" in result.output.lower()

    def test_admin_repos_delete_help_contains_examples(self):
        """Test that delete command help contains usage examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.output
        assert "cidx admin repos delete" in result.output
        assert "--force" in result.output  # Should show force example

    def test_admin_repos_delete_mode_restriction_in_local_mode(self):
        """Test admin repos delete fails in local mode (expected)."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "delete", "test-repo"])

            # Should fail on mode restriction (expected in temp dir without remote config)
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_repos_delete_with_force_flag_mode_restriction(self):
        """Test admin repos delete with --force fails in local mode."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["admin", "repos", "delete", "test-repo", "--force"]
            )

            # Should fail on mode restriction before reaching API logic
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_repos_delete_argument_validation(self):
        """Test argument validation for delete command."""
        runner = CliRunner()

        # Test empty alias (should be handled by Click)
        result = runner.invoke(cli, ["admin", "repos", "delete", ""])

        # Should either fail with validation error or pass to mode restriction
        assert result.exit_code != 0

    def test_admin_repos_delete_listed_in_repos_help(self):
        """Test that delete command is listed in admin repos help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "--help"])

        assert result.exit_code == 0
        assert "delete" in result.output

    def test_admin_repos_delete_destructive_operation_warnings(self):
        """Test that delete command help emphasizes destructive nature."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        # Should emphasize the destructive nature
        destructive_indicators = [
            "permanently",
            "delete",
            "cannot be undone",
            "destructive",
            "irreversible",
        ]

        output_lower = result.output.lower()
        found_indicators = [
            indicator
            for indicator in destructive_indicators
            if indicator in output_lower
        ]

        # Should have at least 2 destructive operation indicators
        assert len(found_indicators) >= 2

    def test_admin_repos_delete_command_structure_consistency(self):
        """Test that delete command follows same structure as other admin repos commands."""
        runner = CliRunner()

        # Check that delete is available alongside other commands
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert "delete" in repos_result.output
        assert "add" in repos_result.output
        assert "list" in repos_result.output
        assert "show" in repos_result.output
        assert "refresh" in repos_result.output

        # Check delete command follows same help pattern
        delete_result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert delete_result.exit_code == 0
        assert "Args:" in delete_result.output
        assert "Examples:" in delete_result.output


class TestAdminReposDeleteCommandSafetyFeatures:
    """Test safety features of admin repos delete command."""

    def test_admin_repos_delete_confirmation_prompt_described(self):
        """Test that confirmation prompt behavior is described in help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "confirmation" in result.output.lower()
        assert "prompt" in result.output.lower()

    def test_admin_repos_delete_force_flag_bypasses_confirmation(self):
        """Test that force flag is described as bypassing confirmation."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "--force" in result.output
        # Should indicate that force bypasses prompts
        force_indicators = ["skip", "bypass", "without confirmation", "automation"]
        output_lower = result.output.lower()

        found_indicators = [
            indicator for indicator in force_indicators if indicator in output_lower
        ]
        assert len(found_indicators) >= 1

    def test_admin_repos_delete_alias_parameter_description(self):
        """Test that alias parameter is properly described."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "alias" in result.output.lower()
        assert "repository" in result.output.lower()

    def test_admin_repos_delete_admin_privileges_requirement(self):
        """Test that admin privileges requirement is clearly stated."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0
        assert "admin" in result.output.lower()
        assert "privileges" in result.output.lower()

    def test_admin_repos_delete_expected_user_experience(self):
        """Test that help describes expected user experience."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0

        # Should mention key aspects of user experience
        ux_elements = [
            "confirmation",  # Confirmation prompt
            "permanently",  # Permanent deletion
            "admin",  # Admin requirement
            "delete",  # Delete operation
        ]

        output_lower = result.output.lower()
        for element in ux_elements:
            assert element in output_lower

    def test_admin_repos_delete_error_handling_consistency(self):
        """Test that error handling follows same pattern as other admin commands."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            # Test delete command in environment without remote config
            result = runner.invoke(cli, ["admin", "repos", "delete", "test-repo"])

            # Should fail with similar error patterns as other admin commands
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )


class TestAdminReposDeleteCommandSignature:
    """Test the command signature and parameter validation."""

    def test_admin_repos_delete_command_signature_validation(self):
        """Test that delete command has correct signature."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0

        # Should have proper Click command structure
        assert "Usage:" in result.output
        assert "admin repos delete" in result.output
        assert "ALIAS" in result.output or "alias" in result.output

    def test_admin_repos_delete_parameter_order(self):
        """Test that parameters are in expected order."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        assert result.exit_code == 0

        # Alias should be required argument, force should be option
        assert "ALIAS" in result.output or "[alias]" in result.output
        assert "--force" in result.output

    def test_admin_repos_delete_integration_with_admin_group(self):
        """Test proper integration with admin command group."""
        runner = CliRunner()

        # Should be listed in admin group
        admin_result = runner.invoke(cli, ["admin", "--help"])
        assert "repos" in admin_result.output

        # Should be listed in repos subgroup
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert "delete" in repos_result.output

        # Should have consistent command structure
        delete_result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert delete_result.exit_code == 0
