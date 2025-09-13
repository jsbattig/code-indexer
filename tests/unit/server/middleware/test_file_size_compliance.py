"""
Unit tests for file size compliance following CLAUDE.md Foundation #5/6: File organization and size limits.

Tests that error handler modules are properly split and under size limits.
"""

import os
import inspect
import pytest

from code_indexer.server.middleware.error_handler import (
    GlobalErrorHandler,
    SensitiveDataSanitizer,
    DatabaseRetryHandler,
)


class TestFileSizeCompliance:
    """Test that middleware files comply with CLAUDE.md Foundation #5/6 size limits."""

    def test_main_error_handler_file_size_limit(self):
        """Test that error_handler.py is under 500 lines (CLAUDE.md Foundation #6)."""
        error_handler_file = inspect.getfile(GlobalErrorHandler)

        with open(error_handler_file, "r") as f:
            lines = f.readlines()

        line_count = len(lines)
        max_lines = 500

        if line_count > max_lines:
            pytest.fail(
                f"error_handler.py has {line_count} lines, exceeds limit of {max_lines} lines. "
                f"Split into focused modules following CLAUDE.md Foundation #5/6"
            )

    def test_all_middleware_files_under_size_limit(self):
        """Test that all middleware files are under appropriate size limits."""
        middleware_dir = os.path.dirname(inspect.getfile(GlobalErrorHandler))
        file_size_limits = {
            "error_handler.py": 400,  # Main middleware (reduced from 738 to 361)
            "sanitization.py": 200,  # Sanitization logic
            "retry_handler.py": 150,  # Retry logic
            "error_formatters.py": 300,  # Response formatting
        }

        violations = []

        for filename in os.listdir(middleware_dir):
            if filename.endswith(".py") and not filename.startswith("test_"):
                filepath = os.path.join(middleware_dir, filename)

                with open(filepath, "r") as f:
                    lines = f.readlines()

                line_count = len(lines)
                expected_limit = file_size_limits.get(filename, 500)  # Default limit

                if line_count > expected_limit:
                    violations.append(
                        f"{filename}: {line_count} lines > {expected_limit} limit"
                    )

        if violations:
            pytest.fail(
                "File size violations found:\n"
                + "\n".join(violations)
                + "\nSplit files following CLAUDE.md Foundation #5/6"
            )

    def test_expected_module_structure_exists(self):
        """Test that the expected modular structure exists after splitting."""
        middleware_dir = os.path.dirname(inspect.getfile(GlobalErrorHandler))

        expected_modules = [
            "error_handler.py",  # Main middleware (~200 lines)
            "sanitization.py",  # SensitiveDataSanitizer (~200 lines)
            "retry_handler.py",  # DatabaseRetryHandler (~100 lines)
            "error_formatters.py",  # Response formatting (~150 lines)
        ]

        missing_modules = []
        for module in expected_modules:
            module_path = os.path.join(middleware_dir, module)
            if not os.path.exists(module_path):
                missing_modules.append(module)

        if missing_modules:
            pytest.fail(
                f"Missing expected modules: {missing_modules}. "
                "Create modular structure following CLAUDE.md Foundation #5/6"
            )

    def test_functionality_imports_correctly_after_split(self):
        """Test that main classes can still be imported after module split."""
        # These imports should work regardless of internal module organization
        from code_indexer.server.middleware.error_handler import GlobalErrorHandler

        # Test that we can instantiate classes
        handler = GlobalErrorHandler()
        assert handler is not None

        sanitizer = SensitiveDataSanitizer()
        assert sanitizer is not None

        from code_indexer.server.models.error_models import RetryConfiguration

        retry_config = RetryConfiguration()
        retry_handler = DatabaseRetryHandler(retry_config)
        assert retry_handler is not None


class TestModularArchitecture:
    """Test that the modular architecture is properly implemented."""

    def test_sanitization_module_single_responsibility(self):
        """Test that sanitization module only contains sanitization logic."""
        # This test will fail initially until we create sanitization.py
        try:
            from code_indexer.server.middleware.sanitization import (
                SensitiveDataSanitizer,
            )

            # If import succeeds, verify it's focused on sanitization
            import inspect

            sanitization_module = inspect.getmodule(SensitiveDataSanitizer)

            # Module should primarily contain sanitization-related classes/functions
            module_members = inspect.getmembers(sanitization_module)
            class_names = [name for name, obj in module_members if inspect.isclass(obj)]

            # Should not contain retry or formatting classes
            invalid_classes = [
                name
                for name in class_names
                if "retry" in name.lower() or "format" in name.lower()
            ]

            if invalid_classes:
                pytest.fail(
                    f"Sanitization module contains non-sanitization classes: {invalid_classes}"
                )

        except ImportError:
            pytest.fail(
                "SensitiveDataSanitizer should be moved to sanitization.py module"
            )

    def test_retry_handler_module_single_responsibility(self):
        """Test that retry handler module only contains retry logic."""
        # This test will fail initially until we create retry_handler.py
        try:
            from code_indexer.server.middleware.retry_handler import (
                DatabaseRetryHandler,
            )
            import inspect

            retry_module = inspect.getmodule(DatabaseRetryHandler)

            # Module should primarily contain retry-related classes/functions
            module_members = inspect.getmembers(retry_module)
            class_names = [name for name, obj in module_members if inspect.isclass(obj)]

            # Should not contain sanitization or formatting classes
            invalid_classes = [
                name
                for name in class_names
                if "sanitiz" in name.lower() or "format" in name.lower()
            ]

            if invalid_classes:
                pytest.fail(
                    f"Retry handler module contains non-retry classes: {invalid_classes}"
                )

        except ImportError:
            pytest.fail(
                "DatabaseRetryHandler should be moved to retry_handler.py module"
            )

    def test_error_formatters_module_single_responsibility(self):
        """Test that error formatters module only contains formatting logic."""
        # This test will fail initially until we create error_formatters.py
        try:
            # Look for response formatting functions in error_formatters module
            from code_indexer.server.middleware import error_formatters
            import inspect

            # Should contain formatting-related functions/classes
            module_members = inspect.getmembers(error_formatters)
            function_names = [
                name for name, obj in module_members if inspect.isfunction(obj)
            ]

            # Should contain response formatting functions
            formatting_functions = [
                name
                for name in function_names
                if "response" in name.lower() or "format" in name.lower()
            ]

            if not formatting_functions:
                pytest.fail(
                    "Error formatters module should contain response formatting functions"
                )

        except ImportError:
            pytest.fail(
                "Response formatting should be moved to error_formatters.py module"
            )


class TestModuleIntegration:
    """Test that split modules integrate correctly."""

    def test_main_error_handler_imports_from_submodules(self):
        """Test that main error handler imports classes from split modules."""
        # After splitting, error_handler.py should import from other modules
        error_handler_file = inspect.getfile(GlobalErrorHandler)

        with open(error_handler_file, "r") as f:
            content = f.read()

        expected_imports = [
            "from .sanitization import SensitiveDataSanitizer",
            "from .retry_handler import DatabaseRetryHandler",
            "from .error_formatters import",
        ]

        missing_imports = []
        for expected_import in expected_imports:
            if expected_import not in content:
                missing_imports.append(expected_import)

        if missing_imports:
            pytest.fail(
                f"Missing expected imports in error_handler.py: {missing_imports}. "
                "Main module should import from split modules"
            )

    def test_no_circular_imports(self):
        """Test that split modules don't create circular import dependencies."""
        # Test that we can import each module independently
        modules_to_test = [
            "code_indexer.server.middleware.error_handler",
            "code_indexer.server.middleware.sanitization",
            "code_indexer.server.middleware.retry_handler",
            "code_indexer.server.middleware.error_formatters",
        ]

        import importlib

        for module_name in modules_to_test:
            try:
                importlib.import_module(module_name)
            except ImportError as e:
                if "circular import" in str(e).lower():
                    pytest.fail(f"Circular import detected in {module_name}: {e}")
                # Other import errors are expected until modules are created

    def test_functionality_preserved_after_split(self):
        """Test that all functionality is preserved after module split."""
        # Test that we can still create and use the error handler
        handler = GlobalErrorHandler()

        # Test that sanitizer is accessible
        assert handler.sanitizer is not None

        # Test that retry handler is accessible
        assert handler.retry_handler is not None

        # Test basic sanitization functionality
        sensitive_text = "password=secret123"
        sanitized = handler.sanitizer.sanitize_string(sensitive_text)
        assert "secret123" not in sanitized

        # Test that status code mapping still works
        status_code = handler.get_status_code_for_error_type("validation_error")
        assert status_code == 400
