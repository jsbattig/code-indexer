"""Result aggregation for parallel command execution.

This module provides the ParallelResultAggregator class that combines
results from parallel command executions and calculates overall exit codes.
"""

from typing import Dict, Tuple, List

from .error_formatter import ErrorMessage, ErrorMessageFormatter
from .hint_generator import HintGenerator


class ParallelResultAggregator:
    """Aggregate results from parallel command execution.

    This class combines stdout/stderr outputs from multiple repository
    executions and calculates an overall exit code based on success/failure
    patterns. Uses ErrorMessageFormatter for clear, visually distinct error
    reporting.
    """

    def __init__(self):
        """Initialize aggregator with error formatter and hint generator."""
        self.formatter = ErrorMessageFormatter()
        self.hint_generator = HintGenerator()

    def aggregate(
        self,
        results: Dict[str, Tuple[str, str, int]],
        command: str = "query"
    ) -> Tuple[str, int]:
        """Aggregate parallel results into final output with formatted errors.

        Args:
            results: Dictionary mapping repo_path -> (stdout, stderr, exit_code)
            command: Command that was executed (for error formatting)

        Returns:
            Tuple of (combined_output, overall_exit_code)
            Exit codes:
                0 = all success
                1 = all failed
                2 = partial success
        """
        # Handle empty results
        if not results:
            return "", 0

        all_outputs = []
        exit_codes = []
        errors: List[ErrorMessage] = []

        # Process each repository result
        for repo, (stdout, stderr, code) in results.items():
            # Include non-empty stdout
            if stdout:
                all_outputs.append(stdout)

            # Collect errors for detailed formatting at end
            if code != 0:
                # Generate actionable hint for this error
                hint = self.hint_generator.generate_hint(
                    command=command,
                    error_text=stderr if stderr else "",
                    repository=repo
                )

                error = ErrorMessage(
                    repository=repo,
                    command=command,
                    error_text=stderr if stderr else "",
                    exit_code=code,
                    hint=hint,
                )
                errors.append(error)

            exit_codes.append(code)

        # Add detailed error section if there were failures
        if errors:
            error_section = self._format_error_section(errors)
            all_outputs.append(error_section)

        # Calculate overall exit code
        if all(code == 0 for code in exit_codes):
            overall_code = 0  # All success
        elif any(code == 0 for code in exit_codes):
            overall_code = 2  # Partial success
        else:
            overall_code = 1  # Complete failure

        # Combine all outputs with newlines
        combined_output = '\n'.join(all_outputs) if all_outputs else ""

        return combined_output, overall_code

    def _format_error_section(self, errors: List[ErrorMessage]) -> str:
        """Format error section with all detailed errors.

        Args:
            errors: List of ErrorMessage objects

        Returns:
            Formatted error section string
        """
        lines = [
            "",  # Blank line before error section
            "=" * 60,
            f"ERRORS ENCOUNTERED ({len(errors)} total)",
            "=" * 60,
            "",
        ]

        # Add each formatted error
        for i, error in enumerate(errors, 1):
            if i > 1:
                lines.append("")  # Blank line between errors

            lines.append(f"Error {i} of {len(errors)}:")
            lines.append(self.formatter.format_error(error))

        return '\n'.join(lines)
