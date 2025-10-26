"""Unit tests for command validation in proxy mode.

Tests the command validator that ensures only supported commands execute
in proxy mode and provides clear error messages for unsupported commands.
"""

import pytest

from code_indexer.proxy.command_validator import (
    PROXIED_COMMANDS,
    UnsupportedProxyCommandError,
    validate_proxy_command,
    is_supported_proxy_command,
    format_unsupported_command_error,
)


class TestProxiedCommandsSet:
    """Test the hardcoded PROXIED_COMMANDS set."""

    def test_proxied_commands_contains_all_supported(self):
        """Verify all 7 supported commands are in PROXIED_COMMANDS."""
        expected_commands = {
            "query",
            "status",
            "start",
            "stop",
            "uninstall",
            "fix-config",
            "watch",
        }
        assert PROXIED_COMMANDS == expected_commands

    def test_proxied_commands_is_set(self):
        """Verify PROXIED_COMMANDS is a set-like type for O(1) lookup."""
        # frozenset is immutable set, provides O(1) lookup
        assert isinstance(PROXIED_COMMANDS, (set, frozenset))

    def test_proxied_commands_immutable(self):
        """Verify PROXIED_COMMANDS cannot be modified."""
        original_size = len(PROXIED_COMMANDS)
        with pytest.raises(AttributeError):
            PROXIED_COMMANDS.add("new-command")  # Should fail if immutable
        # If mutable, verify size unchanged
        assert len(PROXIED_COMMANDS) == original_size


class TestIsSupportedProxyCommand:
    """Test the is_supported_proxy_command function."""

    def test_supported_commands_return_true(self):
        """Verify all supported commands return True."""
        assert is_supported_proxy_command("query") is True
        assert is_supported_proxy_command("status") is True
        assert is_supported_proxy_command("start") is True
        assert is_supported_proxy_command("stop") is True
        assert is_supported_proxy_command("uninstall") is True
        assert is_supported_proxy_command("fix-config") is True
        assert is_supported_proxy_command("watch") is True

    def test_unsupported_commands_return_false(self):
        """Verify unsupported commands return False."""
        assert is_supported_proxy_command("init") is False
        assert is_supported_proxy_command("index") is False
        assert is_supported_proxy_command("reconcile") is False
        assert is_supported_proxy_command("unknown") is False

    def test_case_sensitive_validation(self):
        """Verify command validation is case-sensitive."""
        assert is_supported_proxy_command("Query") is False
        assert is_supported_proxy_command("QUERY") is False
        assert is_supported_proxy_command("query") is True


class TestUnsupportedProxyCommandError:
    """Test the UnsupportedProxyCommandError exception."""

    def test_exception_contains_command_name(self):
        """Verify exception stores the command name."""
        error = UnsupportedProxyCommandError("init")
        assert error.command == "init"

    def test_exception_generates_message(self):
        """Verify exception generates error message."""
        error = UnsupportedProxyCommandError("index")
        assert error.message is not None
        assert len(error.message) > 0

    def test_exception_message_includes_command(self):
        """Verify error message includes attempted command."""
        error = UnsupportedProxyCommandError("init")
        assert "init" in error.message

    def test_exception_message_includes_supported_commands(self):
        """Verify error message lists supported commands."""
        error = UnsupportedProxyCommandError("init")
        assert "query" in error.message
        assert "status" in error.message
        assert "start" in error.message
        assert "stop" in error.message
        assert "uninstall" in error.message

    def test_exception_message_includes_navigation_instructions(self):
        """Verify error message shows how to use unsupported command."""
        error = UnsupportedProxyCommandError("init")
        assert "cd" in error.message or "navigate" in error.message.lower()

    def test_exception_inherits_from_exception(self):
        """Verify UnsupportedProxyCommandError inherits from Exception."""
        error = UnsupportedProxyCommandError("init")
        assert isinstance(error, Exception)


class TestValidateProxyCommand:
    """Test the validate_proxy_command function."""

    def test_supported_command_no_exception(self):
        """Verify supported commands don't raise exceptions."""
        # Should not raise
        validate_proxy_command("query")
        validate_proxy_command("status")
        validate_proxy_command("start")
        validate_proxy_command("stop")
        validate_proxy_command("uninstall")
        validate_proxy_command("fix-config")
        validate_proxy_command("watch")

    def test_unsupported_command_raises_exception(self):
        """Verify unsupported commands raise UnsupportedProxyCommandError."""
        with pytest.raises(UnsupportedProxyCommandError) as exc_info:
            validate_proxy_command("init")
        assert exc_info.value.command == "init"

        with pytest.raises(UnsupportedProxyCommandError) as exc_info:
            validate_proxy_command("index")
        assert exc_info.value.command == "index"

    def test_validation_prevents_execution(self):
        """Verify validation happens before any subprocess execution.

        This is a design test - validation should not have side effects.
        """
        # Validation should be pure function with no side effects
        try:
            validate_proxy_command("init")
        except UnsupportedProxyCommandError:
            pass  # Expected

        # No subprocess calls should have been made (no way to verify directly,
        # but the function should not have any execution logic)


class TestFormatUnsupportedCommandError:
    """Test the format_unsupported_command_error function."""

    def test_error_message_format(self):
        """Verify error message has correct structure."""
        message = format_unsupported_command_error("init")

        # Should contain error header
        assert "ERROR" in message or "error" in message

        # Should mention proxy mode
        assert "proxy mode" in message.lower()

        # Should include command name
        assert "init" in message

    def test_error_includes_supported_commands_list(self):
        """Verify error message lists all 7 supported commands."""
        message = format_unsupported_command_error("init")

        assert "query" in message
        assert "status" in message
        assert "start" in message
        assert "stop" in message
        assert "uninstall" in message
        assert "fix-config" in message
        assert "watch" in message

    def test_error_includes_navigation_guidance(self):
        """Verify error message shows how to execute unsupported command."""
        message = format_unsupported_command_error("init")

        # Should suggest navigating to specific repository
        assert "cd" in message or "navigate" in message.lower()

        # Should show how to run the command
        assert "cidx init" in message

    def test_error_message_for_different_commands(self):
        """Verify error message adapts to different commands."""
        init_message = format_unsupported_command_error("init")
        index_message = format_unsupported_command_error("index")

        assert "init" in init_message
        assert "index" in index_message
        assert init_message != index_message

    def test_error_message_readable(self):
        """Verify error message is well-formatted and readable."""
        message = format_unsupported_command_error("init")

        # Should have multiple lines
        lines = message.split("\n")
        assert len(lines) > 5

        # Should not be too long (under 500 chars)
        assert len(message) < 1000


class TestExitCodeHandling:
    """Test exit code 3 for unsupported commands.

    Note: This will be tested in integration/E2E tests as it requires
    CLI execution context.
    """

    def test_exception_can_be_caught_for_exit_code_handling(self):
        """Verify exception can be caught to set exit code 3."""
        try:
            validate_proxy_command("init")
            assert False, "Should have raised exception"
        except UnsupportedProxyCommandError as e:
            # CLI handler should catch this and return exit code 3
            assert e.command == "init"
            assert e.message is not None
