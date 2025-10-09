"""Unit tests for hint formatting in ErrorMessageFormatter.

Tests cover:
- Hint formatting with all fields
- Hint formatting without explanation
- Integration with ActionableHint
- Visual structure of formatted hints
"""

from code_indexer.proxy.error_formatter import ErrorMessage, ErrorMessageFormatter
from code_indexer.proxy.hint_generator import ActionableHint


class TestErrorFormatterHintDisplay:
    """Test hint display in error messages."""

    def setup_method(self):
        """Initialize formatter for each test."""
        self.formatter = ErrorMessageFormatter()

    def test_format_error_with_actionable_hint(self):
        """Test formatting error with ActionableHint object."""
        hint = ActionableHint(
            message="Use grep to search manually",
            suggested_commands=[
                "grep -r 'term' repo",
                "rg 'term' repo",
            ],
            explanation="Service unavailable"
        )

        error = ErrorMessage(
            repository="backend/auth",
            command="query",
            error_text="Cannot connect to Qdrant",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Should contain hint message
        assert "Use grep to search manually" in formatted

        # Should contain suggested commands
        assert "grep -r 'term' repo" in formatted
        assert "rg 'term' repo" in formatted

        # Should contain explanation
        assert "Service unavailable" in formatted

    def test_format_error_with_hint_has_proper_structure(self):
        """Test that hint section has clear visual structure."""
        hint = ActionableHint(
            message="Test hint message",
            suggested_commands=["cmd1", "cmd2"],
            explanation="Test explanation"
        )

        error = ErrorMessage(
            repository="test-repo",
            command="query",
            error_text="Test error",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Should have "Hint:" prefix
        assert "Hint:" in formatted

        # Should have "Try these commands:" section
        assert "Try these commands:" in formatted

        # Should have "Explanation:" section
        assert "Explanation:" in formatted

        # Commands should be bulleted
        assert "•" in formatted or "*" in formatted or "-" in formatted

    def test_format_error_with_hint_without_explanation(self):
        """Test formatting hint without explanation."""
        hint = ActionableHint(
            message="Test hint",
            suggested_commands=["cmd1"],
            explanation=None
        )

        error = ErrorMessage(
            repository="test-repo",
            command="query",
            error_text="Test error",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Should contain hint message and commands
        assert "Test hint" in formatted
        assert "cmd1" in formatted

        # Should not have "Explanation:" when explanation is None
        # (or if it does, it should not show "None")
        assert "Explanation: None" not in formatted

    def test_format_error_without_hint(self):
        """Test formatting error without hint (existing behavior)."""
        error = ErrorMessage(
            repository="test-repo",
            command="query",
            error_text="Test error",
            exit_code=1,
            hint=None
        )

        formatted = self.formatter.format_error(error)

        # Should not have hint section
        assert "Hint:" not in formatted
        assert "Try these commands:" not in formatted

        # Should still have basic error information
        assert "test-repo" in formatted
        assert "Test error" in formatted

    def test_format_error_with_string_hint_backward_compatibility(self):
        """Test backward compatibility with string hints."""
        error = ErrorMessage(
            repository="test-repo",
            command="query",
            error_text="Test error",
            exit_code=1,
            hint="Simple string hint"
        )

        formatted = self.formatter.format_error(error)

        # Should still display string hints
        assert "Hint:" in formatted
        assert "Simple string hint" in formatted


class TestErrorFormatterHintVisualStructure:
    """Test visual structure of hint formatting."""

    def setup_method(self):
        """Initialize formatter for each test."""
        self.formatter = ErrorMessageFormatter()

    def test_hint_section_is_visually_separated(self):
        """Test that hint section is visually separated from error."""
        hint = ActionableHint(
            message="Test message",
            suggested_commands=["cmd1"],
            explanation="Test explanation"
        )

        error = ErrorMessage(
            repository="repo",
            command="query",
            error_text="Error text",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Should have blank line before hint
        lines = formatted.split('\n')
        hint_index = next(i for i, line in enumerate(lines) if 'Hint:' in line)
        assert lines[hint_index - 1].strip() == ""  # Blank line before hint

    def test_commands_are_indented(self):
        """Test that suggested commands are properly indented."""
        hint = ActionableHint(
            message="Test message",
            suggested_commands=["cmd1", "cmd2"],
        )

        error = ErrorMessage(
            repository="repo",
            command="query",
            error_text="Error",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Commands should be indented with bullet points
        assert "  • cmd1" in formatted or "  - cmd1" in formatted or "  * cmd1" in formatted
        assert "  • cmd2" in formatted or "  - cmd2" in formatted or "  * cmd2" in formatted

    def test_complete_hint_format_matches_expected_structure(self):
        """Test complete hint format matches expected structure."""
        hint = ActionableHint(
            message="Use grep to search manually",
            suggested_commands=[
                "grep -r 'term' backend/auth",
                "rg 'term' backend/auth",
            ],
            explanation="Qdrant service not available"
        )

        error = ErrorMessage(
            repository="backend/auth",
            command="query",
            error_text="Cannot connect to Qdrant",
            exit_code=1,
            hint=hint
        )

        formatted = self.formatter.format_error(error)

        # Expected structure:
        # ============================================================
        # ✗ FAILED: backend/auth
        # ============================================================
        # Command: cidx query
        # Error: Cannot connect to Qdrant
        # Exit code: 1
        #
        # Hint: Use grep to search manually
        #
        # Try these commands:
        #   • grep -r 'term' backend/auth
        #   • rg 'term' backend/auth
        #
        # Explanation: Qdrant service not available
        # ============================================================

        lines = formatted.split('\n')

        # Verify key sections exist
        assert any("FAILED: backend/auth" in line for line in lines)
        assert any("Command: cidx query" in line for line in lines)
        assert any("Error: Cannot connect to Qdrant" in line for line in lines)
        assert any("Exit code: 1" in line for line in lines)
        assert any("Hint: Use grep to search manually" in line for line in lines)
        assert any("Try these commands:" in line for line in lines)
        assert any("grep -r 'term' backend/auth" in line for line in lines)
        assert any("Explanation: Qdrant service not available" in line for line in lines)
