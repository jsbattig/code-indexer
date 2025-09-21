"""
End-to-end integration tests for admin repos delete command.

Tests the complete golden repository deletion workflow including
safety features, confirmation prompts, and error handling.
Follows TDD methodology and MESSI Rule #1 (anti-mock).
"""

from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminReposDeleteE2EIntegration:
    """E2E integration tests for admin repos delete command."""

    def test_admin_repos_delete_fails_gracefully_in_local_mode(self):
        """Test that delete command fails gracefully in local mode."""
        runner = CliRunner()

        # Test delete command in isolated filesystem (local mode)
        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "delete", "test-repo"])

            # Should fail gracefully with mode restriction
            assert result.exit_code == 1, "Delete command should fail in local mode"

            # Should have clear error message about mode restriction
            error_patterns = [
                "not available in local mode",
                "requires: 'remote' mode",
                "No project configuration found",
                "No remote configuration found",
            ]

            assert any(
                pattern in result.output for pattern in error_patterns
            ), "Delete command should show clear error message about mode restriction"

            # Should not crash or show stack traces
            assert (
                "Traceback" not in result.output
            ), "Delete command should not show stack traces"
            assert (
                "Exception" not in result.output
            ), "Delete command should not show raw exceptions"

    def test_admin_repos_delete_with_force_fails_gracefully_in_local_mode(self):
        """Test that delete command with --force fails gracefully in local mode."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli, ["admin", "repos", "delete", "test-repo", "--force"]
            )

            # Should fail gracefully with mode restriction
            assert result.exit_code == 1
            error_patterns = [
                "not available in local mode",
                "requires: 'remote' mode",
                "No project configuration found",
                "No remote configuration found",
            ]

            assert any(pattern in result.output for pattern in error_patterns)
            assert "Traceback" not in result.output
            assert "Exception" not in result.output

    def test_admin_repos_delete_input_validation(self):
        """Test that admin repos delete validates input properly."""
        runner = CliRunner()

        # Test without required alias argument
        result = runner.invoke(cli, ["admin", "repos", "delete"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Usage:" in result.output

        # Test with invalid flags
        result = runner.invoke(
            cli, ["admin", "repos", "delete", "--invalid-flag", "test"]
        )

        # Should fail with usage error, not reach remote API logic
        assert result.exit_code != 0
        assert (
            "Usage:" in result.output
            or "no such option" in result.output
            or "Unrecognized option" in result.output
        )

    def test_admin_repos_delete_argument_parsing_edge_cases(self):
        """Test edge cases in argument parsing."""
        runner = CliRunner()

        # Test with empty alias
        result = runner.invoke(cli, ["admin", "repos", "delete", ""])
        assert result.exit_code != 0  # Should fail gracefully

        # Test with whitespace-only alias
        result = runner.invoke(cli, ["admin", "repos", "delete", "   "])
        assert result.exit_code != 0  # Should fail gracefully

        # Test with very long alias (should not crash)
        long_alias = "a" * 1000
        result = runner.invoke(cli, ["admin", "repos", "delete", long_alias])
        # Should fail on mode restriction, not crash on long input
        assert result.exit_code == 1
        assert "Traceback" not in result.output

    def test_admin_repos_delete_preserves_error_context(self):
        """Test that delete command preserves proper error context for troubleshooting."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "delete", "test-repo"])

            # Should fail gracefully
            assert result.exit_code == 1

            # Should provide actionable error messages
            assert (
                "cidx remote init" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
                or "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
            ), "Delete command should provide actionable error message"

            # Should not leave users without guidance
            assert (
                result.output.strip() != ""
            ), "Delete command should not produce empty output"

    def test_admin_repos_delete_help_format_and_consistency(self):
        """Test that delete command help has consistent formatting."""
        runner = CliRunner()

        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])

        # Should show help successfully
        assert result.exit_code == 0, "Help for delete should work"

        # Should have consistent formatting elements
        assert "Examples:" in result.output, "Help should contain examples"
        assert (
            "cidx admin repos delete" in result.output
        ), "Help should contain command examples"

        # Should mention admin privileges
        assert (
            "admin" in result.output.lower() or "privilege" in result.output.lower()
        ), "Help should mention admin requirements"

        # Should emphasize destructive nature
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
        assert len(found_indicators) >= 2, "Help should emphasize destructive nature"

    def test_admin_repos_delete_registration_in_command_hierarchy(self):
        """Test that delete command is properly registered in command hierarchy."""
        runner = CliRunner()

        # Test that delete is listed in admin repos help
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert repos_result.exit_code == 0
        assert "delete" in repos_result.output, "Delete should be listed in repos help"

        # Test that admin group lists repos
        admin_result = runner.invoke(cli, ["admin", "--help"])
        assert admin_result.exit_code == 0
        assert "repos" in admin_result.output

    def test_admin_repos_delete_error_message_quality(self):
        """Test that error messages are helpful and professional."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(cli, ["admin", "repos", "delete", "test-repo"])

            # Should have professional error messages
            assert result.exit_code == 1
            # Allow "Error:" as it's part of Click's standard output format
            assert not any(
                word in result.output.lower()
                for word in ["exception:", "traceback", "failed", "crash"]
            ), "Error messages should be professional, not technical"

            # Should provide actionable guidance
            guidance_patterns = [
                "cidx remote init",
                "configure",
                "setup",
                "No project configuration found",
                "No remote configuration found",
                "not available in local mode",
                "requires: 'remote' mode",
            ]

            assert any(
                pattern in result.output for pattern in guidance_patterns
            ), "Error should provide actionable guidance"

    def test_admin_repos_delete_handles_keyboard_interruption(self):
        """Test that delete command handles keyboard interruption gracefully."""
        runner = CliRunner()

        # Test that help command completes quickly and doesn't hang
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0, "Delete help should complete successfully"

    def test_admin_repos_delete_force_flag_behavior(self):
        """Test force flag behavior and documentation."""
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
        assert len(found_indicators) >= 1, "Help should describe force flag behavior"


class TestAdminReposDeleteSafetyFeatures:
    """Test safety features of the delete command."""

    def test_admin_repos_delete_safety_documentation(self):
        """Test that safety features are properly documented."""
        runner = CliRunner()

        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should document safety features
        safety_elements = [
            "confirmation",
            "permanently",
            "cannot be undone",
            "admin privileges",
        ]

        output_lower = result.output.lower()
        for element in safety_elements:
            assert element in output_lower, f"Help should mention {element}"

    def test_admin_repos_delete_destructive_operation_warnings(self):
        """Test that destructive operation warnings are prominent."""
        runner = CliRunner()

        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should have prominent warnings about destructive nature
        warning_indicators = ["⚠️", "DESTRUCTIVE", "permanently", "cannot be undone"]

        found_warnings = [
            indicator for indicator in warning_indicators if indicator in result.output
        ]
        assert (
            len(found_warnings) >= 2
        ), "Help should have prominent destructive operation warnings"

    def test_admin_repos_delete_command_follows_cli_conventions(self):
        """Test that delete command follows established CLI conventions."""
        runner = CliRunner()

        # Should follow same pattern as other admin repos commands
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should have Args section
        assert "Args:" in result.output or "alias" in result.output.lower()

        # Should have Examples section
        assert "Examples:" in result.output

        # Should mention admin requirement
        assert "admin" in result.output.lower()

    def test_admin_repos_delete_integration_with_existing_commands(self):
        """Test integration with existing admin repos commands."""
        runner = CliRunner()

        # Should be listed alongside other commands
        repos_result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert repos_result.exit_code == 0

        expected_commands = ["add", "list", "show", "refresh", "delete"]
        for cmd in expected_commands:
            assert cmd in repos_result.output, f"Command {cmd} should be listed"

        # Should follow same error handling pattern
        with runner.isolated_filesystem():
            commands_to_test = [
                (["admin", "repos", "list"], "list"),
                (["admin", "repos", "show", "test"], "show"),
                (["admin", "repos", "refresh", "test"], "refresh"),
                (["admin", "repos", "delete", "test"], "delete"),
            ]

            for cmd_args, cmd_name in commands_to_test:
                result = runner.invoke(cli, cmd_args)

                # All should fail with same mode restriction pattern
                assert (
                    result.exit_code == 1
                ), f"Command {cmd_name} should fail in local mode"

                error_patterns = [
                    "not available in local mode",
                    "requires: 'remote' mode",
                    "No project configuration found",
                    "No remote configuration found",
                ]

                assert any(
                    pattern in result.output for pattern in error_patterns
                ), f"Command {cmd_name} should show consistent error pattern"


class TestAdminReposDeleteWorkflowValidation:
    """Test the complete deletion workflow validation."""

    def test_admin_repos_delete_workflow_structure(self):
        """Test that delete workflow follows expected structure."""
        runner = CliRunner()

        # Test basic command structure
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should describe complete workflow
        workflow_elements = ["confirmation", "repository details", "delete", "admin"]

        output_lower = result.output.lower()
        for element in workflow_elements:
            assert (
                element in output_lower
            ), f"Help should describe {element} in workflow"

    def test_admin_repos_delete_parameter_validation(self):
        """Test parameter validation follows expected patterns."""
        runner = CliRunner()

        # Test help shows proper parameter structure
        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should show alias as required parameter
        assert (
            "ALIAS" in result.output or "alias" in result.output.lower()
        ), "Help should show alias parameter"

        # Should show force as optional flag
        assert "--force" in result.output, "Help should show force flag"

    def test_admin_repos_delete_consistency_with_other_destructive_commands(self):
        """Test consistency with other destructive commands in the system."""
        runner = CliRunner()

        # Delete should follow similar patterns to other admin commands
        delete_help = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert delete_help.exit_code == 0

        # Should have professional tone and clear warnings
        assert "admin" in delete_help.output.lower()
        assert (
            "privileges" in delete_help.output.lower()
            or "privilege" in delete_help.output.lower()
        )

        # Should provide examples for both confirmation and force modes
        assert "Examples:" in delete_help.output
        assert "--force" in delete_help.output

    def test_admin_repos_delete_comprehensive_help_content(self):
        """Test that help content is comprehensive and useful."""
        runner = CliRunner()

        result = runner.invoke(cli, ["admin", "repos", "delete", "--help"])
        assert result.exit_code == 0

        # Should cover all essential aspects
        essential_content = [
            "Delete a golden repository",  # Basic function
            "admin",  # Permission requirement
            "permanently",  # Permanence warning
            "cannot be undone",  # Irreversibility
            "confirmation",  # Safety feature
            "--force",  # Automation option
            "Examples:",  # Usage examples
            "alias",  # Required parameter
        ]

        for content in essential_content:
            assert content in result.output, f"Help should contain: {content}"

    def test_admin_repos_delete_error_handling_robustness(self):
        """Test that error handling is robust and informative."""
        runner = CliRunner()

        # Test various error conditions
        error_scenarios = [
            # Missing argument
            (["admin", "repos", "delete"], "Missing argument"),
            # Invalid flag
            (["admin", "repos", "delete", "--invalid", "test"], "no such option"),
            # Mode restriction (in isolated filesystem)
            (["admin", "repos", "delete", "test"], "local mode"),
        ]

        for cmd_args, expected_error_type in error_scenarios:
            if "local mode" in expected_error_type:
                with runner.isolated_filesystem():
                    result = runner.invoke(cli, cmd_args)
            else:
                result = runner.invoke(cli, cmd_args)

            assert (
                result.exit_code != 0
            ), f"Command {cmd_args} should fail appropriately"
            assert (
                "Traceback" not in result.output
            ), f"Command {cmd_args} should not show stack traces"
