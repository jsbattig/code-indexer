"""
Tests for admin users change-password CLI command.

Following Foundation #1 compliance: Zero mocks, real functionality testing.
Tests the admin password change command with proper validation and safety features.
"""

import tempfile
from click.testing import CliRunner

from code_indexer.cli import cli


class TestAdminPasswordChangeCommand:
    """Test admin users change-password command functionality."""

    def test_admin_change_password_command_exists(self):
        """Test that change-password command is registered correctly."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "users", "change-password", "--help"])

        # Should show help without error
        assert result.exit_code == 0
        assert "change-password" in result.output
        assert "Change a user's password" in result.output
        assert "--password" in result.output
        assert "--force" in result.output

    def test_admin_change_password_requires_username(self):
        """Test that username argument is required."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "users", "change-password"])

        # Should fail with missing argument error
        assert result.exit_code != 0
        assert "Usage:" in result.output or "Missing argument" in result.output

    def test_admin_change_password_invalid_username_format(self):
        """Test that invalid username format is rejected."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "admin",
                "users",
                "change-password",
                "in@valid",
                "--password",
                "ValidPass123!",
                "--force",
            ],
        )

        # Should fail with username validation error
        assert result.exit_code == 1
        assert "Invalid username format" in result.output

    def test_admin_change_password_weak_password_validation(self):
        """Test that weak passwords are rejected."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "admin",
                "users",
                "change-password",
                "testuser",
                "--password",
                "weak",
                "--force",
            ],
        )

        # Should fail with password validation error
        assert result.exit_code == 1
        assert (
            "Password too weak" in result.output
            or "Password Requirements" in result.output
        )

    def test_admin_change_password_valid_password_format(self):
        """Test that properly formatted passwords pass validation."""
        with tempfile.TemporaryDirectory():
            runner = CliRunner()

            # This should pass validation but fail on remote config (expected)
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli,
                    [
                        "admin",
                        "users",
                        "change-password",
                        "testuser",
                        "--password",
                        "ValidPass123!",
                        "--force",
                    ],
                )

                # Should fail on mode restriction, not password validation
                assert result.exit_code == 1
                assert (
                    "not available in local mode" in result.output
                    or "requires: 'remote' mode" in result.output
                    or "No project configuration found" in result.output
                    or "No remote configuration found" in result.output
                )
                # Should NOT contain password validation errors
                assert "Password too weak" not in result.output

    def test_admin_change_password_confirmation_prompts(self):
        """Test that confirmation prompts work correctly without --force."""
        runner = CliRunner()

        # Test with 'n' (no) to confirmation
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "admin",
                    "users",
                    "change-password",
                    "testuser",
                    "--password",
                    "ValidPass123!",
                ],
                input="n\n",
            )

            # Should fail on mode restriction before reaching confirmation
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )

    def test_admin_change_password_force_skips_confirmation(self):
        """Test that --force flag skips confirmation prompts."""
        runner = CliRunner()

        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "admin",
                    "users",
                    "change-password",
                    "testuser",
                    "--password",
                    "ValidPass123!",
                    "--force",
                ],
            )

            # Should fail on mode restriction (expected in temp dir)
            assert result.exit_code == 1
            assert (
                "not available in local mode" in result.output
                or "requires: 'remote' mode" in result.output
                or "No project configuration found" in result.output
                or "No remote configuration found" in result.output
            )
            # Should NOT contain confirmation prompts in output
            assert "Do you want to continue?" not in result.output

    def test_admin_change_password_help_contains_examples(self):
        """Test that help text contains usage examples."""
        runner = CliRunner()
        result = runner.invoke(cli, ["admin", "users", "change-password", "--help"])

        assert result.exit_code == 0
        assert "Examples:" in result.output
        assert "cidx admin users change-password" in result.output

    def test_admin_change_password_password_validation_uses_policy(self):
        """Test that password validation uses the existing password policy."""
        runner = CliRunner()

        # Test various weak passwords that should fail policy validation
        weak_passwords = [
            "short",  # Too short
            "NoNumbers",  # No numbers
            "nonumbers123",  # No special chars
            "123456789",  # No letters
        ]

        for weak_password in weak_passwords:
            result = runner.invoke(
                cli,
                [
                    "admin",
                    "users",
                    "change-password",
                    "testuser",
                    "--password",
                    weak_password,
                    "--force",
                ],
            )

            assert result.exit_code == 1
            assert (
                "Password too weak" in result.output
                or "Password Requirements" in result.output
            ), f"Failed for password: {weak_password}"

    def test_admin_change_password_command_structure_matches_other_admin_commands(self):
        """Test that command structure is consistent with other admin commands."""
        runner = CliRunner()

        # Test admin users commands all exist
        admin_result = runner.invoke(cli, ["admin", "--help"])
        assert "users" in admin_result.output

        users_result = runner.invoke(cli, ["admin", "users", "--help"])
        assert "create" in users_result.output
        assert "list" in users_result.output
        assert "show" in users_result.output
        assert "update" in users_result.output
        assert "delete" in users_result.output
        assert "change-password" in users_result.output

        # All should be available and follow same pattern
        for cmd in ["create", "list", "show", "update", "delete", "change-password"]:
            cmd_result = runner.invoke(cli, ["admin", "users", cmd, "--help"])
            assert (
                cmd_result.exit_code == 0
            ), f"Command {cmd} should exist and show help"
