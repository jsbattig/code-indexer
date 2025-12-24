"""Tests for disabled command handling in different operational modes.

Tests the story requirement: As a CIDX user in remote mode, I want clear error messages
when I try to use commands that aren't compatible with remote mode, so that I understand
why the command isn't available and what alternatives exist.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from click import ClickException

from code_indexer.cli import cli


class TestCommandCompatibilityMatrix:
    """Test the command compatibility matrix for different operational modes."""

    def test_command_compatibility_matrix_structure(self):
        """Test that command compatibility matrix is properly structured."""
        from code_indexer.disabled_commands import COMMAND_COMPATIBILITY

        # Test required commands exist in matrix
        required_commands = [
            "help",
            "version",
            "query",
            "init",
            "start",
            "stop",
            "index",
            "watch",
            "status",
            "uninstall",
        ]

        for command in required_commands:
            assert (
                command in COMMAND_COMPATIBILITY
            ), f"Command {command} missing from compatibility matrix"

            # Each command should have mode definitions
            command_modes = COMMAND_COMPATIBILITY[command]
            assert (
                "local" in command_modes
            ), f"Command {command} missing local mode definition"
            assert (
                "remote" in command_modes
            ), f"Command {command} missing remote mode definition"
            assert (
                "uninitialized" in command_modes
            ), f"Command {command} missing uninitialized mode definition"

            # Mode values should be boolean
            assert isinstance(command_modes["local"], bool)
            assert isinstance(command_modes["remote"], bool)
            assert isinstance(command_modes["uninitialized"], bool)

    def test_always_available_commands(self):
        """Test that help and version are always available in all modes."""
        from code_indexer.disabled_commands import COMMAND_COMPATIBILITY

        always_available = ["help", "version"]

        for command in always_available:
            command_modes = COMMAND_COMPATIBILITY[command]
            assert command_modes["local"] is True
            assert command_modes["remote"] is True
            assert command_modes["uninitialized"] is True

    def test_local_only_commands(self):
        """Test that infrastructure commands are local-only."""
        from code_indexer.disabled_commands import COMMAND_COMPATIBILITY

        local_only = ["start", "stop", "index", "watch"]

        for command in local_only:
            command_modes = COMMAND_COMPATIBILITY[command]
            assert (
                command_modes["local"] is True
            ), f"Command {command} should be available in local mode"
            assert (
                command_modes["remote"] is False
            ), f"Command {command} should be disabled in remote mode"
            assert (
                command_modes["uninitialized"] is False
            ), f"Command {command} should be disabled in uninitialized mode"

    def test_core_functionality_commands(self):
        """Test that core functionality commands work in initialized modes only."""
        from code_indexer.disabled_commands import COMMAND_COMPATIBILITY

        core_commands = ["query"]

        for command in core_commands:
            command_modes = COMMAND_COMPATIBILITY[command]
            assert (
                command_modes["local"] is True
            ), f"Command {command} should work in local mode"
            assert (
                command_modes["remote"] is True
            ), f"Command {command} should work in remote mode"
            assert (
                command_modes["uninitialized"] is False
            ), f"Command {command} should be disabled in uninitialized mode"


class TestDisabledCommandError:
    """Test the custom exception for disabled commands."""

    def test_disabled_command_error_creation(self):
        """Test creation of DisabledCommandError with proper message formatting."""
        from code_indexer.disabled_commands import DisabledCommandError

        error = DisabledCommandError("start", "remote", ["local"])

        # Should be a ClickException subclass
        assert isinstance(error, ClickException)

        # Should contain command name, current mode, and allowed modes
        error_msg = str(error)
        assert "start" in error_msg
        assert "remote" in error_msg
        assert "local" in error_msg

    def test_disabled_command_error_with_alternative(self):
        """Test error message includes alternative when available."""
        from code_indexer.disabled_commands import DisabledCommandError

        error = DisabledCommandError("start", "remote", ["local"])
        error_msg = str(error)

        # Should suggest alternatives for start command in remote mode
        assert "server-side" in error_msg.lower() or "query" in error_msg.lower()

    def test_disabled_command_error_educational_content(self):
        """Test that error message provides educational context."""
        from code_indexer.disabled_commands import DisabledCommandError

        error = DisabledCommandError("index", "remote", ["local"])
        error_msg = str(error)

        # Should explain why command is disabled
        assert any(
            word in error_msg.lower()
            for word in ["remote", "server", "container", "local"]
        )


class TestModeRequirementDecorator:
    """Test the mode requirement decorator for command enforcement."""

    def test_decorator_allows_compatible_mode(self):
        """Test that decorator allows commands in compatible modes."""
        from code_indexer.disabled_commands import require_mode

        @require_mode("local", "remote")
        def mock_command():
            return "success"

        # Mock mode detection to return compatible mode
        with patch(
            "code_indexer.disabled_commands.detect_current_mode", return_value="local"
        ):
            result = mock_command()
            assert result == "success"

    def test_decorator_blocks_incompatible_mode(self):
        """Test that decorator blocks commands in incompatible modes."""
        from code_indexer.disabled_commands import require_mode, DisabledCommandError

        @require_mode("local")
        def mock_command():
            return "success"

        # Mock mode detection to return incompatible mode
        with patch(
            "code_indexer.disabled_commands.detect_current_mode", return_value="remote"
        ):
            with pytest.raises(DisabledCommandError) as exc_info:
                mock_command()

            error = exc_info.value
            assert "remote" in str(error)
            assert "local" in str(error)

    def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves original function metadata."""
        from code_indexer.disabled_commands import require_mode

        @require_mode("local")
        def test_function():
            """Test function docstring."""
            return "test"

        assert test_function.__name__ == "test_function"
        assert test_function.__doc__ == "Test function docstring."


class TestCommandAlternativesMapping:
    """Test the command alternatives mapping for helpful error messages."""

    def test_alternatives_mapping_exists(self):
        """Test that command alternatives mapping is defined."""
        from code_indexer.disabled_commands import COMMAND_ALTERNATIVES

        # Should have alternatives for local-only commands
        local_only_commands = ["start", "stop", "index", "watch"]

        for command in local_only_commands:
            assert command in COMMAND_ALTERNATIVES, f"Missing alternative for {command}"

            alternative = COMMAND_ALTERNATIVES[command]
            assert isinstance(alternative, str)
            assert len(alternative) > 0

    def test_alternatives_provide_actionable_guidance(self):
        """Test that alternatives provide actionable guidance to users."""
        from code_indexer.disabled_commands import COMMAND_ALTERNATIVES

        # Check specific alternatives for key commands
        start_alt = COMMAND_ALTERNATIVES["start"]
        assert any(word in start_alt.lower() for word in ["query", "server", "remote"])

        index_alt = COMMAND_ALTERNATIVES["index"]
        assert any(
            word in index_alt.lower() for word in ["server", "repository", "linking"]
        )


class TestModeDetectionIntegration:
    """Test integration with CommandModeDetector from Story 1."""

    def test_mode_detection_function_exists(self):
        """Test that mode detection utility function exists."""
        from code_indexer.disabled_commands import detect_current_mode

        # Should be callable
        assert callable(detect_current_mode)

    @patch("code_indexer.disabled_commands.find_project_root")
    @patch("code_indexer.disabled_commands.CommandModeDetector")
    def test_mode_detection_uses_project_root(
        self, mock_detector_class, mock_find_root
    ):
        """Test that mode detection uses proper project root discovery."""
        from code_indexer.disabled_commands import detect_current_mode

        # Mock project root discovery
        mock_find_root.return_value = Path("/test/project")

        # Mock detector instance
        mock_detector = MagicMock()
        mock_detector.detect_mode.return_value = "local"
        mock_detector_class.return_value = mock_detector

        # Call mode detection
        result = detect_current_mode()

        # Verify correct integration
        mock_find_root.assert_called_once()
        mock_detector_class.assert_called_once_with(Path("/test/project"))
        mock_detector.detect_mode.assert_called_once()
        assert result == "local"


class TestCliIntegration:
    """Test CLI integration with disabled command handling."""

    def test_local_only_command_fails_in_remote_mode(self):
        """Test that local-only commands fail properly in remote mode."""
        runner = CliRunner()

        # Mock remote mode detection
        with patch(
            "code_indexer.disabled_commands.detect_current_mode", return_value="remote"
        ):
            result = runner.invoke(cli, ["start"])

            # Should exit with error
            assert result.exit_code != 0

            # Should contain helpful error message
            assert "remote" in result.output.lower()
            assert "start" in result.output.lower()

    def test_compatible_command_works_in_remote_mode(self):
        """Test that compatible commands work in remote mode."""
        runner = CliRunner()

        # Mock remote mode detection
        with patch(
            "code_indexer.disabled_commands.detect_current_mode", return_value="remote"
        ):
            # Help should always work
            result = runner.invoke(cli, ["--help"])

            # Should work without error
            assert result.exit_code == 0

    def test_uninitialized_mode_blocks_most_commands(self):
        """Test that uninitialized mode blocks most commands except init and help."""
        runner = CliRunner()

        # Mock uninitialized mode detection
        with patch(
            "code_indexer.disabled_commands.detect_current_mode",
            return_value="uninitialized",
        ):
            # Query should fail in uninitialized mode
            result = runner.invoke(cli, ["query", "test"])

            # Should exit with error
            assert result.exit_code != 0

            # Should suggest initialization
            assert any(
                word in result.output.lower()
                for word in ["init", "uninitialized", "configure"]
            )


class TestErrorMessageQuality:
    """Test the quality and helpfulness of error messages."""

    def test_error_message_contains_mode_context(self):
        """Test that error messages explain architectural context."""
        from code_indexer.disabled_commands import DisabledCommandError

        error = DisabledCommandError("start", "remote", ["local"])
        error_msg = str(error)

        # Should explain why remote mode can't use start
        context_words = ["container", "server", "local", "remote"]
        assert any(word in error_msg.lower() for word in context_words)

    def test_error_message_provides_specific_alternatives(self):
        """Test that error messages provide specific alternatives."""
        from code_indexer.disabled_commands import DisabledCommandError

        error = DisabledCommandError("index", "remote", ["local"])
        error_msg = str(error)

        # Should suggest what to do instead
        alternative_words = ["query", "server", "repository", "linking"]
        assert any(word in error_msg.lower() for word in alternative_words)

    def test_error_message_consistent_formatting(self):
        """Test that error messages have consistent formatting."""
        from code_indexer.disabled_commands import DisabledCommandError

        commands = ["start", "stop", "index", "watch"]

        for command in commands:
            error = DisabledCommandError(command, "remote", ["local"])
            error_msg = str(error)

            # Should have consistent structure
            assert command in error_msg
            assert "remote" in error_msg
            assert len(error_msg) > 50  # Should be substantial and helpful


class TestHelpSystemIntegration:
    """Test integration with Click help system for mode awareness."""

    def test_help_shows_command_availability(self):
        """Test that help system shows command availability by mode."""
        # This test will verify the help system integration once implemented
        # For now, it serves as a placeholder for the requirement
        pass

    def test_disabled_commands_marked_in_help(self):
        """Test that disabled commands are clearly marked in help output."""
        # This test will verify help system shows disabled commands
        # For now, it serves as a placeholder for the requirement
        pass

    def test_mode_specific_help_content(self):
        """Test that help content adapts to current mode."""
        # This test will verify mode-specific help content
        # For now, it serves as a placeholder for the requirement
        pass
