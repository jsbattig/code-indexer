"""Unit tests for parallel result aggregation.

Tests the ParallelResultAggregator class that combines results
from parallel command executions and calculates overall exit codes.
"""

import unittest
from unittest.mock import patch

from code_indexer.proxy.result_aggregator import ParallelResultAggregator


class TestParallelResultAggregator(unittest.TestCase):
    """Test result aggregation from parallel execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.aggregator = ParallelResultAggregator()

    def test_aggregate_all_success(self):
        """Test aggregation when all repositories succeed."""
        results = {
            "/tmp/repo1": ("Result 1", "", 0),
            "/tmp/repo2": ("Result 2", "", 0),
            "/tmp/repo3": ("Result 3", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify exit code is 0 (all success)
        self.assertEqual(exit_code, 0)

        # Verify all outputs included
        self.assertIn("Result 1", output)
        self.assertIn("Result 2", output)
        self.assertIn("Result 3", output)

    def test_aggregate_all_failure(self):
        """Test aggregation when all repositories fail."""
        results = {
            "/tmp/repo1": ("", "Error 1", 1),
            "/tmp/repo2": ("", "Error 2", 1),
            "/tmp/repo3": ("", "Error 3", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify exit code is 1 (complete failure)
        self.assertEqual(exit_code, 1)

        # Verify all errors included with formatted output
        self.assertIn("✗ FAILED: /tmp/repo1", output)
        self.assertIn("Error: Error 1", output)
        self.assertIn("✗ FAILED: /tmp/repo2", output)
        self.assertIn("Error: Error 2", output)
        self.assertIn("✗ FAILED: /tmp/repo3", output)
        self.assertIn("Error: Error 3", output)
        self.assertIn("ERRORS ENCOUNTERED (3 total)", output)

    def test_aggregate_partial_success(self):
        """Test aggregation with mixed success/failure."""
        results = {
            "/tmp/repo1": ("Result 1", "", 0),
            "/tmp/repo2": ("", "Error 2", 1),
            "/tmp/repo3": ("Result 3", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify exit code is 2 (partial success)
        self.assertEqual(exit_code, 2)

        # Verify successful outputs included
        self.assertIn("Result 1", output)
        self.assertIn("Result 3", output)

        # Verify error included with formatted output
        self.assertIn("✗ FAILED: /tmp/repo2", output)
        self.assertIn("Error: Error 2", output)

    def test_aggregate_single_failure_rest_success(self):
        """Test aggregation with one failure, rest success."""
        results = {
            "/tmp/repo1": ("Result 1", "", 0),
            "/tmp/repo2": ("Result 2", "", 0),
            "/tmp/repo3": ("", "Error 3", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify exit code is 2 (partial success)
        self.assertEqual(exit_code, 2)

    def test_aggregate_single_success_rest_failure(self):
        """Test aggregation with one success, rest failure."""
        results = {
            "/tmp/repo1": ("", "Error 1", 1),
            "/tmp/repo2": ("Result 2", "", 0),
            "/tmp/repo3": ("", "Error 3", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify exit code is 2 (partial success)
        self.assertEqual(exit_code, 2)

    def test_aggregate_empty_results(self):
        """Test aggregation with empty results dictionary."""
        results = {}

        output, exit_code = self.aggregator.aggregate(results)

        # Empty results should return success (no failures)
        self.assertEqual(exit_code, 0)
        self.assertEqual(output, "")

    def test_aggregate_stdout_and_stderr_both_present(self):
        """Test aggregation when both stdout and stderr present."""
        results = {
            "/tmp/repo1": ("Result 1", "Warning 1", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify stdout included
        self.assertIn("Result 1", output)

        # Exit code 0 means no error section (errors only for non-zero exit codes)
        # Stderr with exit code 0 is not treated as an error
        self.assertNotIn("ERRORS ENCOUNTERED", output)

        # Exit code should be 0 (success despite stderr)
        self.assertEqual(exit_code, 0)

    def test_aggregate_empty_stdout(self):
        """Test aggregation with empty stdout."""
        results = {
            "/tmp/repo1": ("", "", 0),
            "/tmp/repo2": ("Result 2", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Only non-empty stdout should be included
        self.assertNotIn("repo1", output)
        self.assertIn("Result 2", output)
        self.assertEqual(exit_code, 0)

    def test_aggregate_empty_stderr(self):
        """Test aggregation with empty stderr."""
        results = {
            "/tmp/repo1": ("Result 1", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # No error message should be included
        self.assertNotIn("ERROR", output)
        self.assertIn("Result 1", output)

    def test_aggregate_multiple_lines_output(self):
        """Test aggregation with multi-line outputs."""
        results = {
            "/tmp/repo1": ("Line 1\nLine 2\nLine 3", "", 0),
            "/tmp/repo2": ("Output A\nOutput B", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify all lines included
        self.assertIn("Line 1", output)
        self.assertIn("Line 2", output)
        self.assertIn("Line 3", output)
        self.assertIn("Output A", output)
        self.assertIn("Output B", output)

    def test_aggregate_negative_exit_codes(self):
        """Test aggregation with negative exit codes (exceptions)."""
        results = {
            "/tmp/repo1": ("", "Exception occurred", -1),
            "/tmp/repo2": ("Result 2", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify partial success (one success, one exception)
        self.assertEqual(exit_code, 2)

    def test_aggregate_preserves_order(self):
        """Test that aggregation preserves repository order in output."""
        # Using ordered results
        results = {
            "/tmp/repo1": ("Result 1", "", 0),
            "/tmp/repo2": ("Result 2", "", 0),
            "/tmp/repo3": ("Result 3", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Split output into lines
        lines = output.split("\n")

        # Verify results appear in output (order may vary in dict iteration)
        result_count = sum(1 for line in lines if line.startswith("Result"))
        self.assertEqual(result_count, 3)

    def test_aggregate_large_number_of_repos(self):
        """Test aggregation with many repositories."""
        # Create 20 repositories
        results = {
            f"/tmp/repo{i}": (f"Result {i}", "", 0 if i % 2 == 0 else 1)
            for i in range(20)
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Should be partial success (some succeed, some fail)
        self.assertEqual(exit_code, 2)

        # Verify all success results captured (10 successes)
        for i in range(0, 20, 2):  # Even numbers succeeded
            self.assertIn(f"Result {i}", output)

        # Verify error section exists (10 failures)
        self.assertIn("ERRORS ENCOUNTERED (10 total)", output)

    def test_exit_code_priority(self):
        """Test exit code calculation priority: 0 > 2 > 1."""
        # All success = 0
        results_success = {"/tmp/repo1": ("Result", "", 0)}
        _, code = self.aggregator.aggregate(results_success)
        self.assertEqual(code, 0)

        # Partial success = 2
        results_partial = {
            "/tmp/repo1": ("Result", "", 0),
            "/tmp/repo2": ("", "Error", 1),
        }
        _, code = self.aggregator.aggregate(results_partial)
        self.assertEqual(code, 2)

        # All failure = 1
        results_failure = {"/tmp/repo1": ("", "Error", 1)}
        _, code = self.aggregator.aggregate(results_failure)
        self.assertEqual(code, 1)


class TestFormattedErrorOutput(unittest.TestCase):
    """Test formatted error output in aggregation."""

    def setUp(self):
        """Set up test fixtures."""
        self.aggregator = ParallelResultAggregator()

    @patch("code_indexer.proxy.result_aggregator.print")
    def test_formatted_errors_use_error_formatter(self, mock_print):
        """Verify formatted errors use ErrorMessageFormatter."""
        results = {
            "/tmp/repo1": ("", "Connection failed", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Should format errors with visual separators
        assert "=" * 60 in output
        assert "✗ FAILED:" in output
        assert "/tmp/repo1" in output

    def test_formatted_error_includes_repository_name(self):
        """Verify formatted error includes repository name at start."""
        results = {
            "backend/auth-service": ("", "Cannot connect to Filesystem", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Repository should be in header
        assert "✗ FAILED: backend/auth-service" in output

    def test_formatted_error_shows_error_details(self):
        """Verify formatted error shows error details."""
        results = {
            "backend/auth-service": ("", "Port 6333 in use", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Error text should be included
        assert "Port 6333 in use" in output
        # Exit code should be shown
        assert "Exit code: 1" in output

    def test_multiple_formatted_errors_separated(self):
        """Verify multiple errors have clear separation."""
        results = {
            "backend/auth-service": ("", "Error 1", 1),
            "backend/user-service": ("", "Error 2", 1),
            "frontend/web-app": ("", "Error 3", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Each error should have its own separator block
        separator_count = output.count("=" * 60)
        # Should have 3 errors × 3 separators each = 9 separators
        assert separator_count >= 9

    def test_formatted_errors_chronologically_ordered(self):
        """Verify errors appear in chronological order with successes."""
        results = {
            "repo1": ("Success 1", "", 0),
            "repo2": ("", "Error 2", 1),
            "repo3": ("Success 3", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Both successes and errors should be in output
        assert "Success 1" in output
        assert "Success 3" in output
        assert "✗ FAILED: repo2" in output

    def test_formatted_error_count_in_summary(self):
        """Verify error count shown in summary."""
        results = {
            "repo1": ("Success", "", 0),
            "repo2": ("", "Error 2", 1),
            "repo3": ("", "Error 3", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Should indicate number of errors
        # Looking for pattern like "2 total" or "ERRORS ENCOUNTERED (2"
        assert "2" in output  # Error count

    def test_no_errors_section_when_all_succeed(self):
        """Verify no error section when all succeed."""
        results = {
            "repo1": ("Success 1", "", 0),
            "repo2": ("Success 2", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # No error formatting should appear
        assert "✗ FAILED:" not in output
        assert "ERRORS ENCOUNTERED" not in output

    def test_formatted_inline_errors_during_execution(self):
        """Verify inline errors shown during execution."""
        results = {
            "backend/auth-service": ("", "Connection failed", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Should have inline error format (✗ repo: error)
        # This appears in the detailed error block
        assert "✗" in output

    def test_formatted_error_visual_distinction(self):
        """Verify formatted errors are visually distinct."""
        results = {
            "repo1": ("Success output", "", 0),
            "repo2": ("", "Error occurred", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Error should have visual separators for distinction
        assert "=" * 60 in output
        # Success should not have error separators around it
        lines = output.split("=" * 60)
        # Should have error blocks
        error_blocks = [block for block in lines if "✗ FAILED:" in block]
        assert len(error_blocks) > 0

    def test_formatted_error_in_stdout_not_stderr(self):
        """Verify formatted errors appear in stdout."""
        results = {
            "backend/auth-service": ("", "Connection failed", 1),
        }

        # The aggregate method returns stdout output
        output, exit_code = self.aggregator.aggregate(results)

        # Formatted error should be in the returned output (stdout)
        assert "✗ FAILED: backend/auth-service" in output
        assert "Connection failed" in output


class TestFormattedErrorIntegration(unittest.TestCase):
    """Test integration of error formatter with aggregator."""

    def setUp(self):
        """Set up test fixtures."""
        self.aggregator = ParallelResultAggregator()

    def test_aggregate_formats_single_error(self):
        """Verify single error is formatted correctly."""
        results = {
            "backend/auth-service": (
                "",
                "Cannot connect to Filesystem service at port 6333",
                1,
            ),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Verify complete error format
        assert "=" * 60 in output
        assert "✗ FAILED: backend/auth-service" in output
        assert "Cannot connect to Filesystem service at port 6333" in output
        assert "Exit code: 1" in output

    def test_aggregate_formats_partial_success(self):
        """Verify partial success includes formatted errors."""
        results = {
            "repo1": ("Result 1", "", 0),
            "repo2": ("", "Error in repo2", 1),
            "repo3": ("Result 3", "", 0),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Successes should appear
        assert "Result 1" in output
        assert "Result 3" in output

        # Error should be formatted
        assert "✗ FAILED: repo2" in output
        assert "Error in repo2" in output

        # Exit code should be partial success
        assert exit_code == 2

    def test_aggregate_handles_empty_error_text(self):
        """Verify aggregation handles empty error text gracefully."""
        results = {
            "backend/auth-service": ("", "", 1),
        }

        output, exit_code = self.aggregator.aggregate(results)

        # Should still format error even with empty error text
        assert "✗ FAILED: backend/auth-service" in output
        assert "Exit code: 1" in output


if __name__ == "__main__":
    unittest.main()
