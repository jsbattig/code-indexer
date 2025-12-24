"""
Test CLI admin repository maintenance commands functionality verification.

Simple integration tests to verify the commands exist and have the correct
structure without requiring actual server connectivity.
"""

import pytest
from click.testing import CliRunner

from src.code_indexer.cli import cli


class TestAdminReposFunctionalityVerification:
    """Test admin repos functionality verification."""

    @pytest.fixture
    def runner(self):
        """Create CLI runner for testing."""
        return CliRunner()

    def test_admin_repos_commands_complete_structure(self, runner):
        """Test that all expected admin repos commands exist."""
        # Test main admin group
        result = runner.invoke(cli, ["admin", "--help"])
        assert result.exit_code == 0
        assert "repos" in result.output

        # Test repos subgroup
        result = runner.invoke(cli, ["admin", "repos", "--help"])
        assert result.exit_code == 0
        assert "add" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "refresh" in result.output

    def test_admin_repos_list_help_complete(self, runner):
        """Test that list command help is complete."""
        result = runner.invoke(cli, ["admin", "repos", "list", "--help"])
        assert result.exit_code == 0
        assert "List all golden repositories" in result.output
        assert "formatted table" in result.output
        assert "admin privileges" in result.output

    def test_admin_repos_show_help_complete(self, runner):
        """Test that show command help is complete."""
        result = runner.invoke(cli, ["admin", "repos", "show", "--help"])
        assert result.exit_code == 0
        assert "Show detailed information" in result.output
        assert "ALIAS" in result.output
        assert "Examples:" in result.output
        assert "cidx admin repos show" in result.output

    def test_admin_repos_refresh_help_complete(self, runner):
        """Test that refresh command help is complete."""
        result = runner.invoke(cli, ["admin", "repos", "refresh", "--help"])
        assert result.exit_code == 0
        assert "Refresh a golden repository" in result.output
        assert "ALIAS" in result.output
        assert "re-indexing" in result.output
        assert "asynchronously" in result.output
        assert "Examples:" in result.output

    def test_admin_repos_show_missing_alias_error(self, runner):
        """Test that show command requires alias argument."""
        result = runner.invoke(cli, ["admin", "repos", "show"])
        assert result.exit_code != 0
        # Should show usage or missing argument error
        assert "Usage:" in result.output or "Missing argument" in result.output

    def test_admin_repos_refresh_missing_alias_error(self, runner):
        """Test that refresh command requires alias argument."""
        result = runner.invoke(cli, ["admin", "repos", "refresh"])
        assert result.exit_code != 0
        # Should show usage or missing argument error
        assert "Usage:" in result.output or "Missing argument" in result.output

    def test_admin_repos_list_connection_error_expected(self, runner):
        """Test that list command fails gracefully when no server is available."""
        # This test verifies that the command structure is correct even when it fails
        result = runner.invoke(cli, ["admin", "repos", "list"])

        # We expect this to fail because there's no server running
        assert result.exit_code == 1

        # But it should fail with a recognizable error, not a crash
        error_output = result.output.lower()
        expected_errors = [
            "no project root found",
            "no remote configuration found",
            "no credentials found",
            "connection",
            "network",
            "failed to list golden repositories",
        ]

        # Should fail with one of the expected error types
        assert any(expected_error in error_output for expected_error in expected_errors)

    def test_admin_repos_show_connection_error_expected(self, runner):
        """Test that show command fails gracefully when no server is available."""
        result = runner.invoke(cli, ["admin", "repos", "show", "test-repo"])

        # We expect this to fail because there's no server running
        assert result.exit_code == 1

        # But it should fail with a recognizable error, not a crash
        error_output = result.output.lower()
        expected_errors = [
            "no project root found",
            "no remote configuration found",
            "no credentials found",
            "connection",
            "network",
            "failed to show repository details",
        ]

        # Should fail with one of the expected error types
        assert any(expected_error in error_output for expected_error in expected_errors)

    def test_admin_repos_refresh_connection_error_expected(self, runner):
        """Test that refresh command fails gracefully when no server is available."""
        result = runner.invoke(cli, ["admin", "repos", "refresh", "test-repo"])

        # We expect this to fail because there's no server running
        assert result.exit_code == 1

        # But it should fail with a recognizable error, not a crash
        error_output = result.output.lower()
        expected_errors = [
            "no project root found",
            "no remote configuration found",
            "no credentials found",
            "connection",
            "network",
            "failed to refresh repository",
        ]

        # Should fail with one of the expected error types
        assert any(expected_error in error_output for expected_error in expected_errors)
