"""Error message formatting for proxy mode.

This module provides structured error reporting with clear visual formatting
for failed repository operations. Error messages are designed to be immediately
visible and actionable.
"""

from dataclasses import dataclass
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from .hint_generator import ActionableHint


@dataclass
class ErrorMessage:
    """Structured error message for repository failures.

    Attributes:
        repository: Repository path (relative or absolute)
        command: Command that failed (without 'cidx' prefix)
        error_text: Error message text from stderr
        exit_code: Process exit code (non-zero indicates failure)
        hint: Optional hint for troubleshooting (string or ActionableHint)
    """

    repository: str
    command: str
    error_text: str
    exit_code: int
    hint: Optional[Union[str, 'ActionableHint']] = None


class ErrorMessageFormatter:
    """Format error messages for clear display.

    Provides consistent, visually distinct formatting for error messages
    and success indicators. All error output goes to stdout (not stderr)
    as specified in conversation requirements.
    """

    ERROR_SEPARATOR = "=" * 60
    ERROR_PREFIX = "✗"
    SUCCESS_PREFIX = "✓"

    def format_error(self, error: ErrorMessage) -> str:
        """Format single error message with clear visual structure.

        Output format:
        ============================================================
        ✗ FAILED: repository/path
        ============================================================
        Command: cidx <command>
        Error: <error_text>
        Exit code: <exit_code>

        Hint: <hint message> (if provided)

        Try these commands:
          • <command1>
          • <command2>

        Explanation: <explanation> (if provided)
        ============================================================

        Args:
            error: ErrorMessage with failure details

        Returns:
            Formatted multiline error message string
        """
        lines = [
            self.ERROR_SEPARATOR,
            f"{self.ERROR_PREFIX} FAILED: {error.repository}",
            self.ERROR_SEPARATOR,
            f"Command: cidx {error.command}",
            f"Error: {error.error_text}",
            f"Exit code: {error.exit_code}",
        ]

        # Add hint if provided
        if error.hint:
            lines.append("")  # Blank line before hint

            # Check if hint is ActionableHint or simple string
            if isinstance(error.hint, str):
                # Backward compatibility: simple string hint
                lines.append(f"Hint: {error.hint}")
            else:
                # ActionableHint with structured guidance
                lines.extend(self._format_actionable_hint(error.hint))

        # Add bottom separator
        lines.append(self.ERROR_SEPARATOR)

        return '\n'.join(lines)

    def _format_actionable_hint(self, hint: 'ActionableHint') -> list:
        """Format ActionableHint with commands and explanation.

        Args:
            hint: ActionableHint object with structured guidance

        Returns:
            List of formatted lines for the hint section
        """
        lines = [f"Hint: {hint.message}"]

        # Add suggested commands if present
        if hint.suggested_commands:
            lines.append("")  # Blank line before commands
            lines.append("Try these commands:")
            for cmd in hint.suggested_commands:
                lines.append(f"  • {cmd}")

        # Add explanation if present
        if hint.explanation:
            lines.append("")  # Blank line before explanation
            lines.append(f"Explanation: {hint.explanation}")

        return lines

    def format_inline_error(self, repository: str, error_text: str) -> str:
        """Format compact error for inline display.

        Output format:
        ✗ repository/path: Error message

        Args:
            repository: Repository path
            error_text: Error message text

        Returns:
            Single-line formatted error message
        """
        return f"{self.ERROR_PREFIX} {repository}: {error_text}"

    def format_success(self, repository: str, message: str = "") -> str:
        """Format success message.

        Output format:
        ✓ repository/path: Success message (if message provided)
        ✓ repository/path (if no message)

        Args:
            repository: Repository path
            message: Optional success message

        Returns:
            Single-line formatted success message
        """
        suffix = f": {message}" if message else ""
        return f"{self.SUCCESS_PREFIX} {repository}{suffix}"
