"""
Unit tests for magic number constants compliance in GlobalErrorHandler.

Tests that all magic numbers have been extracted into named constants following
CLAUDE.md Foundation #8: CODE REVIEWER ALERT PATTERNS - Pattern #7.
"""

import re
import ast
import inspect
import pytest

from code_indexer.server.middleware.error_handler import (
    GlobalErrorHandler,
)


class TestMagicNumberCompliance:
    """Test that all magic numbers have been extracted into named constants."""

    def test_no_magic_numbers_in_global_error_handler_init(self):
        """Test that GlobalErrorHandler.__init__ uses named constants, not magic numbers."""
        # Get the source code of the __init__ method
        source = inspect.getsource(GlobalErrorHandler.__init__)

        # Look for magic numbers in default parameter values
        magic_number_pattern = r"=\s*(\d+\.?\d*)\s*[,)]"
        matches = re.findall(magic_number_pattern, source)

        # Filter out acceptable values (0, 1, etc.)
        magic_numbers = [
            float(match) for match in matches if float(match) not in [0, 0.0, 1, 1.0]
        ]

        if magic_numbers:
            pytest.fail(
                f"Found magic numbers in GlobalErrorHandler.__init__: {magic_numbers}. "
                "Replace with named constants following CLAUDE.md Foundation #8 Pattern #7"
            )

    def test_default_constants_are_defined(self):
        """Test that default configuration constants are defined at module level."""
        from code_indexer.server.middleware import error_handler

        # Required constant names based on code-reviewer feedback
        required_constants = [
            "DEFAULT_MAX_RETRY_ATTEMPTS",
            "DEFAULT_BASE_RETRY_DELAY_SECONDS",
            "DEFAULT_MAX_RETRY_DELAY_SECONDS",
        ]

        missing_constants = []
        for constant_name in required_constants:
            if not hasattr(error_handler, constant_name):
                missing_constants.append(constant_name)

        if missing_constants:
            pytest.fail(
                f"Missing required constants: {missing_constants}. "
                "Add module-level constants following CLAUDE.md Foundation #8 Pattern #7"
            )

    def test_retry_calculation_constants_defined(self):
        """Test that retry calculation constants are defined to fix security vulnerability."""
        from code_indexer.server.middleware import error_handler

        # Required constants for retry calculation security fix
        required_constants = [
            "MINIMUM_RETRY_SECONDS",
            "MAXIMUM_RETRY_SECONDS",
            "RETRY_MULTIPLIER",
        ]

        missing_constants = []
        for constant_name in required_constants:
            if not hasattr(error_handler, constant_name):
                missing_constants.append(constant_name)

        if missing_constants:
            pytest.fail(
                f"Missing retry calculation constants: {missing_constants}. "
                "Add these constants to fix security vulnerability in retry timing"
            )

    def test_no_hardcoded_retry_calculation(self):
        """Test that handle_database_error uses constants for retry calculation."""
        # Get the source code of handle_database_error
        source = inspect.getsource(GlobalErrorHandler.handle_database_error)

        # Look for hardcoded values in retry calculation
        # This should fail if we still have: min(60, max(5, int(...)))
        hardcoded_pattern = r"min\s*\(\s*\d+\s*,\s*max\s*\(\s*\d+\s*,\s*int\s*\("

        if re.search(hardcoded_pattern, source):
            pytest.fail(
                "Found hardcoded retry calculation values. "
                "Replace with MINIMUM_RETRY_SECONDS and MAXIMUM_RETRY_SECONDS constants"
            )

    def test_constant_values_are_reasonable(self):
        """Test that constant values are within reasonable ranges."""
        from code_indexer.server.middleware import error_handler

        # Test default retry attempts
        if hasattr(error_handler, "DEFAULT_MAX_RETRY_ATTEMPTS"):
            attempts = error_handler.DEFAULT_MAX_RETRY_ATTEMPTS
            assert isinstance(
                attempts, int
            ), "DEFAULT_MAX_RETRY_ATTEMPTS must be integer"
            assert (
                1 <= attempts <= 10
            ), "DEFAULT_MAX_RETRY_ATTEMPTS must be between 1-10"

        # Test base retry delay
        if hasattr(error_handler, "DEFAULT_BASE_RETRY_DELAY_SECONDS"):
            delay = error_handler.DEFAULT_BASE_RETRY_DELAY_SECONDS
            assert isinstance(
                delay, (int, float)
            ), "DEFAULT_BASE_RETRY_DELAY_SECONDS must be numeric"
            assert (
                0.01 <= delay <= 5.0
            ), "DEFAULT_BASE_RETRY_DELAY_SECONDS must be between 0.01-5.0"

        # Test max retry delay
        if hasattr(error_handler, "DEFAULT_MAX_RETRY_DELAY_SECONDS"):
            max_delay = error_handler.DEFAULT_MAX_RETRY_DELAY_SECONDS
            assert isinstance(
                max_delay, (int, float)
            ), "DEFAULT_MAX_RETRY_DELAY_SECONDS must be numeric"
            assert (
                10 <= max_delay <= 300
            ), "DEFAULT_MAX_RETRY_DELAY_SECONDS must be between 10-300"

        # Test retry bounds
        if hasattr(error_handler, "MINIMUM_RETRY_SECONDS"):
            min_retry = error_handler.MINIMUM_RETRY_SECONDS
            assert isinstance(min_retry, int), "MINIMUM_RETRY_SECONDS must be integer"
            assert 1 <= min_retry <= 10, "MINIMUM_RETRY_SECONDS must be between 1-10"

        if hasattr(error_handler, "MAXIMUM_RETRY_SECONDS"):
            max_retry = error_handler.MAXIMUM_RETRY_SECONDS
            assert isinstance(max_retry, int), "MAXIMUM_RETRY_SECONDS must be integer"
            assert (
                30 <= max_retry <= 300
            ), "MAXIMUM_RETRY_SECONDS must be between 30-300"

        if hasattr(error_handler, "RETRY_MULTIPLIER"):
            multiplier = error_handler.RETRY_MULTIPLIER
            assert isinstance(multiplier, int), "RETRY_MULTIPLIER must be integer"
            assert 2 <= multiplier <= 20, "RETRY_MULTIPLIER must be between 2-20"


class TestCodePatternCompliance:
    """Test compliance with CLAUDE.md Foundation #8 correct coding patterns."""

    def test_no_magic_numbers_in_source_code(self):
        """Test that source code uses named constants instead of magic numbers."""
        # Get all source files in middleware
        import os

        middleware_dir = os.path.dirname(inspect.getfile(GlobalErrorHandler))

        for filename in os.listdir(middleware_dir):
            if filename.endswith(".py") and not filename.startswith("test_"):
                filepath = os.path.join(middleware_dir, filename)

                with open(filepath, "r") as f:
                    content = f.read()

                # Parse AST to find numeric literals in problematic contexts
                tree = ast.parse(content)

                for node in ast.walk(tree):
                    # Check for numeric literals in function calls, assignments, comparisons
                    if isinstance(node, ast.Num) and isinstance(node.n, (int, float)):
                        # Allow common acceptable values
                        if node.n in [0, 0.0, 1, 1.0, -1, 2, 100, 1000]:
                            continue

                        # Allow standard HTTP status codes (well-known constants)
                        http_status_codes = {
                            200,
                            201,
                            204,
                            400,
                            401,
                            403,
                            404,
                            409,
                            422,
                            429,
                            500,
                            503,
                        }
                        if node.n in http_status_codes:
                            continue

                        # Skip constant definitions (assignments to uppercase variables)
                        parent = getattr(node, "parent", None)
                        if isinstance(parent, ast.Assign):
                            for target in parent.targets:
                                if isinstance(target, ast.Name) and target.id.isupper():
                                    continue  # This is a constant definition, skip it

                        # Find line number and context
                        line_num = getattr(node, "lineno", "unknown")

                        # Check if this is part of a constant assignment line
                        lines = content.split("\n")
                        if line_num != "unknown" and line_num <= len(lines):
                            line_content = lines[line_num - 1].strip()
                            # If line contains an uppercase assignment, it's likely a constant
                            if "=" in line_content and any(
                                part.strip().isupper()
                                for part in line_content.split("=")[0].split()
                            ):
                                continue

                        # This test should fail initially to drive TDD implementation
                        pytest.fail(
                            f"Found magic number {node.n} at line {line_num} in {filename}. "
                            "Replace with named constant following CLAUDE.md Foundation #8 Pattern #7"
                        )


class TestConstantsUsageInProduction:
    """Test that production code uses the defined constants correctly."""

    def test_global_error_handler_uses_constants(self):
        """Test that GlobalErrorHandler uses constants in initialization."""
        from code_indexer.server.middleware import error_handler

        # Create handler with default parameters
        handler = GlobalErrorHandler()

        # Verify that configuration uses constants (this will fail initially)
        if hasattr(error_handler, "DEFAULT_MAX_RETRY_ATTEMPTS"):
            expected_attempts = error_handler.DEFAULT_MAX_RETRY_ATTEMPTS
            actual_attempts = handler.config.retry_config.max_attempts
            assert (
                actual_attempts == expected_attempts
            ), f"Handler should use DEFAULT_MAX_RETRY_ATTEMPTS constant ({expected_attempts}), got {actual_attempts}"

    def test_retry_calculation_uses_constants(self):
        """Test that retry calculation in handle_database_error uses constants."""
        from code_indexer.server.middleware import error_handler

        if not all(
            hasattr(error_handler, const)
            for const in [
                "MINIMUM_RETRY_SECONDS",
                "MAXIMUM_RETRY_SECONDS",
                "RETRY_MULTIPLIER",
            ]
        ):
            pytest.fail("Retry calculation constants not defined")

        handler = GlobalErrorHandler()

        # Create a mock request
        from fastapi import Request

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/test",
                "headers": [(b"host", b"testserver")],
            }
        )

        from code_indexer.server.middleware.error_handler import DatabaseRetryableError

        error = DatabaseRetryableError("Test error")

        response = handler.handle_database_error(error, request)

        # Verify retry_after value uses constants
        retry_after = response.get("retry_after")
        if retry_after is not None:
            min_retry = error_handler.MINIMUM_RETRY_SECONDS
            max_retry = error_handler.MAXIMUM_RETRY_SECONDS

            assert (
                min_retry <= retry_after <= max_retry
            ), f"Retry after ({retry_after}) should be between {min_retry} and {max_retry}"
