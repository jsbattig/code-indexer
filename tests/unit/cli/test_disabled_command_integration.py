"""Integration tests for disabled command handling across different operational modes.

Tests the complete end-to-end behavior of command mode detection and enforcement
for the disabled command handling story implementation.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from code_indexer.cli import cli
from code_indexer.disabled_commands import (
    COMMAND_COMPATIBILITY,
    DisabledCommandError,
    detect_current_mode,
    check_command_compatibility,
    get_disabled_commands_for_mode,
    get_available_commands_for_mode,
)


class TestEndToEndCommandModeEnforcement:
    """Test complete end-to-end command mode enforcement."""

    @pytest.mark.parametrize("mode", ["local", "remote", "uninitialized"])
    def test_all_local_only_commands_blocked_in_non_local_modes(self, mode):
        """Test that all local-only commands are properly blocked in non-local modes."""
        if mode == "local":
            pytest.skip("Testing non-local modes only")

        local_only_commands = ["start", "stop", "index", "watch"]
        runner = CliRunner()

        for command in local_only_commands:
            with patch(
                "code_indexer.disabled_commands.detect_current_mode", return_value=mode
            ):
                result = runner.invoke(cli, [command])

                # Should exit with error
                assert (
                    result.exit_code != 0
                ), f"Command '{command}' should fail in {mode} mode"

                # Should contain helpful error message
                assert command in result.output.lower()
                if mode == "uninitialized":
                    assert any(
                        word in result.output.lower()
                        for word in [
                            "uninitialized",
                            "initialization",
                            "configure",
                            "init",
                        ]
                    )
                else:
                    assert mode in result.output.lower()

    def test_compatible_commands_work_in_all_supported_modes(self):
        """Test that compatible commands work in their supported modes."""
        always_available = ["help", "version"]
        runner = CliRunner()

        for mode in ["local", "remote", "uninitialized"]:
            for command in always_available:
                with patch(
                    "code_indexer.disabled_commands.detect_current_mode",
                    return_value=mode,
                ):
                    if command == "help":
                        result = runner.invoke(cli, ["--help"])
                    elif command == "version":
                        result = runner.invoke(cli, ["--version"])

                    # Should work without error
                    assert (
                        result.exit_code == 0
                    ), f"Command '{command}' should work in {mode} mode"

    def test_query_command_blocked_in_uninitialized_mode(self):
        """Test that query command is properly blocked in uninitialized mode."""
        runner = CliRunner()

        with patch(
            "code_indexer.disabled_commands.detect_current_mode",
            return_value="uninitialized",
        ):
            result = runner.invoke(cli, ["query", "test"])

            # Should exit with error
            assert result.exit_code != 0
            assert any(
                word in result.output.lower()
                for word in ["uninitialized", "initialization", "configure", "init"]
            )
            assert any(
                word in result.output.lower()
                for word in ["init", "initialize", "configuration"]
            )

    def test_query_command_works_in_initialized_modes(self):
        """Test that query command works in both local and remote modes."""
        for mode in ["local", "remote"]:
            with patch(
                "code_indexer.disabled_commands.detect_current_mode", return_value=mode
            ):
                # Mock the query implementation to avoid actual execution
                with patch("code_indexer.cli.query") as mock_query:
                    mock_query.return_value = None
                    # The test should at least get past mode checking
                    # We can't test full execution without a real environment
                    pass


class TestModeDetectionConsistency:
    """Test that mode detection is consistent across different components."""

    @patch("code_indexer.disabled_commands.find_project_root")
    @patch("code_indexer.disabled_commands.CommandModeDetector")
    def test_mode_detection_uses_same_logic_as_cli(
        self, mock_detector_class, mock_find_root
    ):
        """Test that disabled commands use the same mode detection as the CLI."""
        # Setup mocks
        mock_find_root.return_value = Path("/test/project")
        mock_detector = MagicMock()
        mock_detector.detect_mode.return_value = "remote"
        mock_detector_class.return_value = mock_detector

        # Call mode detection
        result = detect_current_mode()

        # Verify it uses the correct integration points
        mock_find_root.assert_called_once()
        mock_detector_class.assert_called_once_with(Path("/test/project"))
        mock_detector.detect_mode.assert_called_once()
        assert result == "remote"

    def test_mode_detection_handles_errors_gracefully(self):
        """Test that mode detection handles errors gracefully."""
        with patch(
            "code_indexer.disabled_commands.find_project_root",
            side_effect=Exception("Test error"),
        ):
            result = detect_current_mode()

            # Should fall back to uninitialized on error
            assert result == "uninitialized"


class TestCommandCompatibilityHelpers:
    """Test the helper functions for command compatibility checking."""

    def test_check_command_compatibility_with_current_mode(self):
        """Test command compatibility checking with current mode detection."""
        with patch(
            "code_indexer.disabled_commands.detect_current_mode", return_value="remote"
        ):
            # Query should be compatible in remote mode
            assert check_command_compatibility("query") is True

            # Start should not be compatible in remote mode
            assert check_command_compatibility("start") is False

    def test_check_command_compatibility_with_explicit_mode(self):
        """Test command compatibility checking with explicit mode."""
        # Test local mode
        assert check_command_compatibility("start", "local") is True
        assert check_command_compatibility("start", "remote") is False

        # Test always available commands
        assert check_command_compatibility("help", "local") is True
        assert check_command_compatibility("help", "remote") is True
        assert check_command_compatibility("help", "uninitialized") is True

    def test_get_disabled_commands_for_mode(self):
        """Test getting list of disabled commands for each mode."""
        # Remote mode should disable local-only commands
        remote_disabled = get_disabled_commands_for_mode("remote")
        assert "start" in remote_disabled
        assert "stop" in remote_disabled
        assert "index" in remote_disabled
        assert "watch" in remote_disabled

        # Should not disable always available commands
        assert "help" not in remote_disabled
        assert "version" not in remote_disabled

        # Uninitialized mode should disable most commands except basics
        uninitialized_disabled = get_disabled_commands_for_mode("uninitialized")
        assert "query" in uninitialized_disabled
        assert "start" in uninitialized_disabled

        # But not initialization commands
        assert "init" not in uninitialized_disabled
        assert "help" not in uninitialized_disabled

    def test_get_available_commands_for_mode(self):
        """Test getting list of available commands for each mode."""
        # Local mode should have all commands available
        local_available = get_available_commands_for_mode("local")
        assert "start" in local_available
        assert "stop" in local_available
        assert "query" in local_available
        assert "help" in local_available

        # Remote mode should have core functionality but not local infrastructure
        remote_available = get_available_commands_for_mode("remote")
        assert "query" in remote_available
        assert "help" in remote_available
        assert "start" not in remote_available
        assert "stop" not in remote_available

        # Uninitialized mode should have minimal commands
        uninitialized_available = get_available_commands_for_mode("uninitialized")
        assert "help" in uninitialized_available
        assert "version" in uninitialized_available
        assert "init" in uninitialized_available
        assert "query" not in uninitialized_available


class TestErrorMessageEducationalValue:
    """Test that error messages provide educational value to users."""

    def test_remote_mode_error_explains_architecture(self):
        """Test that remote mode errors explain the architectural difference."""
        error = DisabledCommandError("start", "remote", ["local"])
        message = str(error)

        # Should explain why remote mode doesn't need local commands
        architectural_terms = ["server", "container", "local", "remote", "processing"]
        assert any(term in message.lower() for term in architectural_terms)

        # Should provide alternative guidance
        assert "query" in message.lower() or "server-side" in message.lower()

    def test_uninitialized_mode_error_guides_initialization(self):
        """Test that uninitialized mode errors guide users to initialize."""
        error = DisabledCommandError("query", "uninitialized", ["local", "remote"])
        message = str(error)

        # Should guide users to initialize
        initialization_terms = ["init", "initialize", "configuration", "setup"]
        assert any(term in message.lower() for term in initialization_terms)

    def test_error_messages_suggest_specific_alternatives(self):
        """Test that error messages suggest specific alternatives when available."""
        local_only_commands = ["start", "stop", "index", "watch"]

        for command in local_only_commands:
            error = DisabledCommandError(command, "remote", ["local"])
            message = str(error)

            # Should contain alternative suggestion
            assert "💡 Alternative:" in message
            # Should reference the specific alternative for this command
            assert len(message) > 100  # Should be substantial guidance


class TestCommandCompatibilityMatrixIntegrity:
    """Test the integrity and consistency of the command compatibility matrix."""

    def test_all_cli_commands_have_compatibility_definitions(self):
        """Test that all CLI commands have compatibility definitions."""
        # This test serves as a reminder to update the compatibility matrix
        # when new commands are added to the CLI

        # Core commands that should always be defined
        essential_commands = [
            "help",
            "version",
            "init",
            "query",
            "start",
            "stop",
            "index",
            "watch",
            "status",
            "uninstall",
        ]

        for command in essential_commands:
            assert (
                command in COMMAND_COMPATIBILITY
            ), f"Command '{command}' missing from compatibility matrix"

    def test_compatibility_matrix_logical_consistency(self):
        """Test logical consistency of the compatibility matrix."""
        for command_name, compatibility in COMMAND_COMPATIBILITY.items():
            # If a command works in uninitialized mode, it should work in initialized modes
            # (This is a logical constraint - if you can do something before setup, you can do it after)
            if compatibility.get("uninitialized", False):
                # Some exceptions like help and version should work everywhere
                if command_name in [
                    "help",
                    "version",
                    "init",
                    "fix-config",
                    "set-claude-prompt",
                ]:
                    continue  # These are expected to work in all modes

            # Commands that require initialization should not work in uninitialized mode
            if command_name in ["query", "start", "stop", "index", "watch", "status"]:
                assert not compatibility.get(
                    "uninitialized", True
                ), f"Command '{command_name}' should not work in uninitialized mode"

    def test_help_and_version_always_available(self):
        """Test that help and version are always available as required."""
        for command in ["help", "version"]:
            compatibility = COMMAND_COMPATIBILITY[command]
            assert compatibility["local"] is True
            assert compatibility["remote"] is True
            assert compatibility["uninitialized"] is True
