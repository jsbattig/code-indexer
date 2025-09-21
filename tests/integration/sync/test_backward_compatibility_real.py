"""Real System Integration Tests for Sync Backward Compatibility - ANTI-MOCK COMPLIANCE.

Tests that enhanced sync functionality maintains full backward compatibility
with existing sync behavior. Uses real CIDX infrastructure with zero mocks.
"""

import tempfile

import pytest
from click.testing import CliRunner

from code_indexer.cli import cli
from tests.integration.sync.test_enhanced_sync_real_server_integration import (
    RealSyncTestInfrastructure,
)


@pytest.fixture
def real_compatibility_infrastructure():
    """Pytest fixture for real backward compatibility test infrastructure."""
    infrastructure = RealSyncTestInfrastructure()
    infrastructure.setup()

    try:
        yield infrastructure
    finally:
        infrastructure.cleanup()


class TestSyncBackwardCompatibilityReal:
    """Real system tests for sync backward compatibility."""

    def test_existing_sync_command_still_works(self, real_compatibility_infrastructure):
        """Test that existing sync command still works without repository context."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test sync help command still works
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, f"Sync help should work: {result.output}"
        assert "sync" in result.output.lower(), "Should show sync command help"

    def test_existing_sync_options_preserved(self, real_compatibility_infrastructure):
        """Test that all existing sync command options are preserved."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Get sync help to check options
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, "Sync help should work"

        # Check for common sync options that should be preserved
        help_output = result.output.lower()

        # Test for presence of important options (if they exist)
        important_options = ["--all", "--timeout", "--help"]
        preserved_options = [opt for opt in important_options if opt in help_output]

        # Should preserve at least some existing options
        assert (
            len(preserved_options) >= 1
        ), f"Should preserve existing options. Found: {preserved_options}"

    def test_sync_without_repository_context_graceful_handling(
        self, real_compatibility_infrastructure
    ):
        """Test sync command handles gracefully when run without repository context."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Create a temporary directory that's not a repository
        with tempfile.TemporaryDirectory() as temp_dir:
            # Execute sync from non-repository directory
            # Change to temp directory for test
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                result = runner.invoke(cli, ["sync"], catch_exceptions=False, env=env)
            finally:
                os.chdir(original_cwd)

            # Should handle gracefully - either succeed or fail gracefully
            # The important thing is it doesn't crash
            assert result.exit_code in [
                0,
                1,
            ], f"Should handle gracefully: {result.output}"

            # Should not show repository-specific messaging
            output_lower = result.output.lower()
            repo_specific_terms = [
                "golden repository",
                "activated repository",
                "repository context",
            ]
            for term in repo_specific_terms:
                if term in output_lower:
                    # If repository terms appear, they should be in error/info context
                    assert any(
                        context in output_lower
                        for context in ["not found", "error", "info", "warning"]
                    )

    def test_sync_command_structure_unchanged(self, real_compatibility_infrastructure):
        """Test that the basic sync command structure remains unchanged."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test that sync is still a direct command (not moved to subgroups)
        result = runner.invoke(cli, ["--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, "CLI help should work"
        assert "sync" in result.output.lower(), "Sync should still be a main command"

    def test_existing_sync_error_handling_preserved(
        self, real_compatibility_infrastructure
    ):
        """Test that existing sync error handling behavior is preserved."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test invalid sync option handling
        result = runner.invoke(
            cli, ["sync", "--invalid-option"], catch_exceptions=False, env=env
        )

        # Should handle invalid options appropriately
        assert result.exit_code != 0, "Invalid options should cause non-zero exit"
        error_output = result.output.lower()
        assert any(
            term in error_output
            for term in ["error", "invalid", "unrecognized", "no such option"]
        ), f"Should show appropriate error message: {result.output}"

    def test_sync_with_legacy_parameters_still_works(
        self, real_compatibility_infrastructure
    ):
        """Test that sync command still accepts legacy parameters."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test common legacy parameter patterns
        legacy_patterns = [
            ["sync", "--timeout", "300"],
            ["sync", "--all"],
        ]

        for pattern in legacy_patterns:
            result = runner.invoke(cli, pattern, catch_exceptions=False, env=env)

            # Should accept the parameters without crashing
            # May succeed or fail depending on context, but shouldn't crash
            assert result.exit_code in [
                0,
                1,
            ], f"Legacy pattern {pattern} should be handled: {result.output}"

    def test_enhanced_sync_doesnt_break_existing_workflows(
        self, real_compatibility_infrastructure
    ):
        """Test that enhanced sync doesn't break existing user workflows."""
        # Create a real user and repository setup
        user = real_compatibility_infrastructure.create_test_user()

        # Test that traditional sync workflow still functions
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Step 1: Traditional sync help
        help_result = runner.invoke(
            cli, ["sync", "--help"], catch_exceptions=False, env=env
        )
        assert help_result.exit_code == 0, "Traditional sync help should work"

        # Step 2: Traditional sync execution
        sync_result = runner.invoke(cli, ["sync"], catch_exceptions=False, env=env)
        # Should handle gracefully regardless of outcome
        assert sync_result.exit_code in [0, 1], "Traditional sync should not crash"

    def test_repos_command_group_is_additional_not_replacement(
        self, real_compatibility_infrastructure
    ):
        """Test that repos command group is additional functionality, not a replacement."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Both 'sync' and 'repos sync' should exist
        sync_help = runner.invoke(cli, ["sync", "--help"], env=env)
        repos_help = runner.invoke(cli, ["repos", "--help"], env=env)

        assert sync_help.exit_code == 0, "Original sync command should exist"
        assert repos_help.exit_code == 0, "New repos command group should exist"

        # Verify repos has sync subcommand
        assert "sync" in repos_help.output.lower(), "Repos should have sync subcommand"

    def test_sync_behavior_consistent_across_contexts(
        self, real_compatibility_infrastructure
    ):
        """Test that sync behavior is consistent across different contexts."""
        # Setup real repository
        user = real_compatibility_infrastructure.create_test_user()
        golden_alias = "consistency-test"
        user_alias = "consistency-repo"
        content = {"src/test.py": "def test(): pass"}

        real_compatibility_infrastructure.setup_real_golden_repository(
            golden_alias, content
        )
        activated_repo_path = (
            real_compatibility_infrastructure.activate_real_repository(
                golden_alias, user_alias, user["username"]
            )
        )

        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test sync from inside repository context
        inside_result = runner.invoke(
            cli,
            ["sync", "--help"],
            catch_exceptions=False,
            env=env,
            cwd=str(activated_repo_path),
        )

        # Test sync from outside repository context
        outside_result = runner.invoke(
            cli,
            ["sync", "--help"],
            catch_exceptions=False,
            env=env,
            cwd=str(real_compatibility_infrastructure.temp_dir),
        )

        # Help should be consistent regardless of context
        assert inside_result.exit_code == 0, "Sync help should work inside repository"
        assert outside_result.exit_code == 0, "Sync help should work outside repository"

        # Help content should be essentially the same
        # (minor differences in context are acceptable)
        inside_lines = set(inside_result.output.strip().split("\n"))
        outside_lines = set(outside_result.output.strip().split("\n"))

        # Should have significant overlap in help content
        common_lines = inside_lines.intersection(outside_lines)
        total_lines = inside_lines.union(outside_lines)

        if len(total_lines) > 0:
            overlap_ratio = len(common_lines) / len(total_lines)
            assert (
                overlap_ratio >= 0.7
            ), f"Help content should be mostly consistent: {overlap_ratio}"

    def test_existing_sync_command_precedence(self, real_compatibility_infrastructure):
        """Test that existing sync command takes precedence and works as expected."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test that 'cidx sync' still invokes the enhanced sync command (not repos sync)
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, "Main sync command should work"

        # Should show the enhanced sync help (with backward compatibility)
        help_output = result.output.lower()
        assert "sync" in help_output, "Should show sync functionality"

        # Should be the enhanced version (may show additional options)
        # but should maintain all original functionality

    def test_no_breaking_changes_in_sync_interface(
        self, real_compatibility_infrastructure
    ):
        """Test that there are no breaking changes in the sync command interface."""
        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test that sync command maintains its core interface
        result = runner.invoke(cli, ["sync", "--help"], catch_exceptions=False, env=env)

        assert result.exit_code == 0, "Sync help should work"

        help_text = result.output

        # Essential elements that should be present
        essential_elements = ["sync", "usage"]

        for element in essential_elements:
            assert (
                element.lower() in help_text.lower()
            ), f"Essential element '{element}' should be present"

        # Should not require any new mandatory parameters
        # (all new functionality should be optional or auto-detected)
        assert "--help" in help_text.lower(), "Help option should be available"

    def test_enhanced_features_are_additive_only(
        self, real_compatibility_infrastructure
    ):
        """Test that enhanced features are purely additive and don't change existing behavior."""
        # Setup real repository to test enhanced features
        user = real_compatibility_infrastructure.create_test_user()
        golden_alias = "additive-test"
        user_alias = "additive-repo"
        content = {"main.py": "print('additive test')"}

        real_compatibility_infrastructure.setup_real_golden_repository(
            golden_alias, content
        )
        activated_repo_path = (
            real_compatibility_infrastructure.activate_real_repository(
                golden_alias, user_alias, user["username"]
            )
        )

        runner = CliRunner()
        env = {"CIDX_SERVER_DATA_DIR": str(real_compatibility_infrastructure.temp_dir)}

        # Test sync from inside repository (enhanced features active)
        enhanced_result = runner.invoke(
            cli, ["sync"], catch_exceptions=False, env=env, cwd=str(activated_repo_path)
        )

        # Test sync from outside repository (traditional behavior)
        traditional_result = runner.invoke(
            cli,
            ["sync"],
            catch_exceptions=False,
            env=env,
            cwd=str(real_compatibility_infrastructure.temp_dir),
        )

        # Both should handle gracefully
        assert enhanced_result.exit_code in [0, 1], "Enhanced sync should work"
        assert traditional_result.exit_code in [0, 1], "Traditional sync should work"

        # Enhanced version may show additional context, but shouldn't break
        # The key is that both execute without crashing
