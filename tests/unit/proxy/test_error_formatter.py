"""Unit tests for error message formatting in proxy mode.

Tests the ErrorMessageFormatter class that provides clear, visually distinct
error reporting for failed repositories.
"""

from code_indexer.proxy.error_formatter import (
    ErrorMessage,
    ErrorMessageFormatter,
)


class TestErrorMessage:
    """Test the ErrorMessage dataclass."""

    def test_error_message_creation(self):
        """Verify ErrorMessage can be created with required fields."""
        error = ErrorMessage(
            repository="backend/auth-service",
            command="query 'authentication'",
            error_text="Cannot connect to Filesystem service",
            exit_code=1,
        )
        assert error.repository == "backend/auth-service"
        assert error.command == "query 'authentication'"
        assert error.error_text == "Cannot connect to Filesystem service"
        assert error.exit_code == 1
        assert error.hint is None

    def test_error_message_with_hint(self):
        """Verify ErrorMessage accepts optional hint field."""
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Port 6333 already in use",
            exit_code=1,
            hint="Check for conflicting services with 'docker ps'",
        )
        assert error.hint == "Check for conflicting services with 'docker ps'"


class TestErrorMessageFormatter:
    """Test the ErrorMessageFormatter class."""

    def setUp(self):
        """Set up test fixtures."""
        self.formatter = ErrorMessageFormatter()

    def test_formatter_has_error_separator(self):
        """Verify formatter defines error separator."""
        formatter = ErrorMessageFormatter()
        assert formatter.ERROR_SEPARATOR == "=" * 60

    def test_formatter_has_error_prefix(self):
        """Verify formatter defines error prefix."""
        formatter = ErrorMessageFormatter()
        assert formatter.ERROR_PREFIX == "✗"

    def test_formatter_has_success_prefix(self):
        """Verify formatter defines success prefix."""
        formatter = ErrorMessageFormatter()
        assert formatter.SUCCESS_PREFIX == "✓"


class TestFormatError:
    """Test the format_error method."""

    def test_format_error_basic(self):
        """Verify basic error formatting structure."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="query 'authentication'",
            error_text="Cannot connect to Filesystem service",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Verify error separator appears
        assert "=" * 60 in formatted

        # Verify repository name in header
        assert "✗ FAILED: backend/auth-service" in formatted

        # Verify command shown
        assert "Command: cidx query 'authentication'" in formatted

        # Verify error text shown
        assert "Error: Cannot connect to Filesystem service" in formatted

        # Verify exit code shown
        assert "Exit code: 1" in formatted

    def test_format_error_includes_all_separators(self):
        """Verify error formatting includes all separator lines."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Port conflict",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Count separator occurrences (should be 3: top, middle, bottom)
        separator_count = formatted.count("=" * 60)
        assert separator_count == 3

    def test_format_error_with_hint(self):
        """Verify error formatting includes hint when provided."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Port 6333 already in use",
            exit_code=1,
            hint="Check for conflicting services with 'docker ps'",
        )

        formatted = formatter.format_error(error)

        # Verify hint appears
        assert "Hint: Check for conflicting services with 'docker ps'" in formatted

    def test_format_error_without_hint(self):
        """Verify error formatting works without hint."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Service failed to start",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Verify no hint line appears
        assert "Hint:" not in formatted

    def test_format_error_repository_at_start(self):
        """Verify repository name appears at start of error block."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="frontend/web-app",
            command="query 'test'",
            error_text="Connection failed",
            exit_code=1,
        )

        formatted = formatter.format_error(error)
        lines = formatted.split("\n")

        # Second line should be the repository header (after separator)
        assert "✗ FAILED: frontend/web-app" in lines[1]

    def test_format_error_multiline_structure(self):
        """Verify error formatting creates multiline output."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Service failed",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Verify output is multiline
        assert "\n" in formatted
        lines = formatted.split("\n")
        assert len(lines) >= 6  # At least 6 lines for basic error

    def test_format_error_with_different_exit_codes(self):
        """Verify error formatting handles different exit codes."""
        formatter = ErrorMessageFormatter()

        # Test various exit codes
        for exit_code in [1, 2, 127, 255]:
            error = ErrorMessage(
                repository="test/repo",
                command="test",
                error_text="Error",
                exit_code=exit_code,
            )
            formatted = formatter.format_error(error)
            assert f"Exit code: {exit_code}" in formatted


class TestFormatInlineError:
    """Test the format_inline_error method."""

    def test_format_inline_error_basic(self):
        """Verify inline error formatting."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_inline_error(
            "backend/auth-service", "Cannot connect to Filesystem"
        )

        assert formatted == "✗ backend/auth-service: Cannot connect to Filesystem"

    def test_format_inline_error_single_line(self):
        """Verify inline error is single line."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_inline_error(
            "backend/auth-service", "Error occurred"
        )

        # Should be single line (no newlines)
        assert "\n" not in formatted

    def test_format_inline_error_includes_prefix(self):
        """Verify inline error includes error prefix."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_inline_error("backend/auth-service", "Error")

        assert formatted.startswith("✗")

    def test_format_inline_error_different_repos(self):
        """Verify inline error formatting with different repositories."""
        formatter = ErrorMessageFormatter()

        repos = [
            "backend/auth-service",
            "frontend/web-app",
            "data/analytics",
        ]

        for repo in repos:
            formatted = formatter.format_inline_error(repo, "Error")
            assert repo in formatted


class TestFormatSuccess:
    """Test the format_success method."""

    def test_format_success_basic(self):
        """Verify success formatting."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_success("backend/auth-service")

        assert formatted == "✓ backend/auth-service"

    def test_format_success_with_message(self):
        """Verify success formatting with message."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_success(
            "backend/auth-service", "Services started successfully"
        )

        assert formatted == "✓ backend/auth-service: Services started successfully"

    def test_format_success_includes_prefix(self):
        """Verify success formatting includes success prefix."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_success("backend/auth-service")

        assert formatted.startswith("✓")

    def test_format_success_single_line(self):
        """Verify success message is single line."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_success("backend/auth-service", "Complete")

        # Should be single line (no newlines)
        assert "\n" not in formatted

    def test_format_success_empty_message(self):
        """Verify success formatting handles empty message."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_success("backend/auth-service", "")

        # Empty message should not add colon
        assert formatted == "✓ backend/auth-service"


class TestVisualDistinction:
    """Test visual distinction between success and error messages."""

    def test_error_and_success_use_different_prefixes(self):
        """Verify error and success use different prefixes."""
        formatter = ErrorMessageFormatter()

        error_msg = formatter.format_inline_error("repo1", "Error")
        success_msg = formatter.format_success("repo1")

        # Different prefixes
        assert error_msg.startswith("✗")
        assert success_msg.startswith("✓")
        assert error_msg[0] != success_msg[0]

    def test_detailed_error_visually_distinct(self):
        """Verify detailed error is visually distinct."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Error",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Should have visual separators
        assert "=" * 60 in formatted
        # Should have error prefix
        assert "✗" in formatted
        # Should be multiline
        assert "\n" in formatted


class TestEdgeCases:
    """Test edge cases in error formatting."""

    def test_format_error_with_long_error_text(self):
        """Verify formatting handles very long error text."""
        formatter = ErrorMessageFormatter()
        long_error = "A" * 500  # Very long error message

        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text=long_error,
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Should still include the error text
        assert long_error in formatted

    def test_format_error_with_special_characters(self):
        """Verify formatting handles special characters."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="query 'test \"nested\" quotes'",
            error_text="Error: [CRITICAL] Connection failed @ 127.0.0.1:6333",
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Should preserve special characters
        assert "query 'test \"nested\" quotes'" in formatted
        assert "[CRITICAL]" in formatted
        assert "@" in formatted

    def test_format_error_with_newlines_in_error_text(self):
        """Verify formatting handles error text with newlines."""
        formatter = ErrorMessageFormatter()
        error_text = "Line 1\nLine 2\nLine 3"

        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text=error_text,
            exit_code=1,
        )

        formatted = formatter.format_error(error)

        # Should preserve multiline error text
        assert "Line 1" in formatted
        assert "Line 2" in formatted
        assert "Line 3" in formatted

    def test_format_inline_error_with_empty_error_text(self):
        """Verify inline formatting handles empty error text."""
        formatter = ErrorMessageFormatter()
        formatted = formatter.format_inline_error("backend/auth-service", "")

        # Should still have repository and prefix
        assert "✗" in formatted
        assert "backend/auth-service" in formatted

    def test_format_error_with_zero_exit_code(self):
        """Verify formatting handles exit code 0 (success)."""
        formatter = ErrorMessageFormatter()
        error = ErrorMessage(
            repository="backend/auth-service",
            command="start",
            error_text="Warning: deprecated feature used",
            exit_code=0,
        )

        formatted = formatter.format_error(error)

        # Should still format even with exit code 0
        assert "Exit code: 0" in formatted
        assert "✗ FAILED: backend/auth-service" in formatted
