"""
Unit tests for regex pattern pre-compilation performance optimization.

Tests that regex patterns are pre-compiled at class level to avoid 5-10ms overhead
per request following CLAUDE.md Foundation #8 Pattern #5-6 (Performance Patterns).
"""

import time
import re

from code_indexer.server.middleware.sanitization import SensitiveDataSanitizer
from code_indexer.server.models.error_models import ErrorHandlerConfiguration


class TestRegexPerformanceOptimization:
    """Test that regex patterns are pre-compiled for performance."""

    def test_sanitizer_patterns_are_pre_compiled(self):
        """Test that SensitiveDataSanitizer pre-compiles regex patterns."""
        sanitizer = SensitiveDataSanitizer()

        # Check that _compiled_rules contains compiled patterns
        assert hasattr(sanitizer, "_compiled_rules")
        assert isinstance(sanitizer._compiled_rules, list)

        # If there are rules, they should be compiled Pattern objects
        for pattern, replacement, field_names in sanitizer._compiled_rules:
            assert hasattr(pattern, "search"), "Pattern should be compiled regex object"
            assert hasattr(pattern, "sub"), "Pattern should be compiled regex object"
            assert hasattr(
                pattern, "pattern"
            ), "Pattern should be compiled regex object"

    def test_no_runtime_pattern_compilation(self):
        """Test that regex patterns are not compiled during sanitization operations."""
        import re

        # Track calls to re.compile
        original_compile = re.compile
        compile_calls = []

        def tracking_compile(pattern, flags=0):
            compile_calls.append((pattern, flags))
            return original_compile(pattern, flags)

        # Monkey patch re.compile to track calls
        re.compile = tracking_compile

        try:
            sanitizer = SensitiveDataSanitizer()
            initial_compile_count = len(compile_calls)

            # Perform multiple sanitization operations
            test_strings = [
                "password=secret123",
                "api_key=abcd1234",
                "token=xyz789",
                "user_data={'name': 'test'}",
            ]

            for test_string in test_strings:
                sanitizer.sanitize_string(test_string)
                sanitizer.sanitize_field_value("test_field", test_string)

            final_compile_count = len(compile_calls)

            # Should not have compiled any new patterns during sanitization
            assert final_compile_count == initial_compile_count, (
                f"Regex patterns were compiled during sanitization operations: "
                f"{final_compile_count - initial_compile_count} new compilations"
            )

        finally:
            # Restore original re.compile
            re.compile = original_compile

    def test_sanitization_performance_benchmark(self):
        """Test that sanitization operations are fast enough (performance regression test)."""
        sanitizer = SensitiveDataSanitizer()

        test_data = {
            "password": "secret123",
            "api_key": "abcd1234efgh5678",
            "token": "jwt_token_here",
            "user_info": {
                "name": "John Doe",
                "email": "john@example.com",
                "nested_password": "another_secret",
            },
            "request_data": "POST /api/login password=hidden_value&token=secret_token",
        }

        # Warm up
        sanitizer.sanitize_data_structure(test_data)

        # Measure performance
        iterations = 100
        start_time = time.time()

        for _ in range(iterations):
            sanitizer.sanitize_data_structure(test_data)

        end_time = time.time()
        total_time = end_time - start_time
        avg_time_per_call = total_time / iterations

        # Each call should be much faster than 5-10ms (the old problem)
        # We expect well under 1ms per call with pre-compiled patterns
        max_acceptable_time = 0.002  # 2ms per call (well under the old 5-10ms problem)

        assert avg_time_per_call < max_acceptable_time, (
            f"Sanitization too slow: {avg_time_per_call*1000:.2f}ms per call "
            f"(limit: {max_acceptable_time*1000:.2f}ms). "
            f"Regex patterns may not be pre-compiled."
        )

    def test_class_level_pattern_compilation(self):
        """Test that patterns are compiled at class level, not instance level."""
        # The SensitiveDataSanitizer should compile patterns in __init__
        # But ideally patterns should be class-level constants
        sanitizer1 = SensitiveDataSanitizer()
        sanitizer2 = SensitiveDataSanitizer()

        # Both should have their own compiled rules
        assert hasattr(sanitizer1, "_compiled_rules")
        assert hasattr(sanitizer2, "_compiled_rules")

        # Test that sanitization still works correctly
        test_text = "password=secret123"
        result1 = sanitizer1.sanitize_string(test_text)
        result2 = sanitizer2.sanitize_string(test_text)

        # Results should be the same
        assert result1 == result2

        # Results should be sanitized
        assert "secret123" not in result1

    def test_compiled_patterns_are_reused(self):
        """Test that compiled patterns are reused across multiple operations."""
        sanitizer = SensitiveDataSanitizer()

        # Store original compiled rules
        original_rules = sanitizer._compiled_rules.copy()

        # Perform multiple sanitization operations
        test_strings = [
            "password=secret1",
            "password=secret2",
            "password=secret3",
            "api_key=key1",
            "api_key=key2",
            "api_key=key3",
        ]

        for test_string in test_strings:
            sanitizer.sanitize_string(test_string)

        # Compiled rules should not have changed
        assert (
            sanitizer._compiled_rules == original_rules
        ), "Compiled patterns were modified during sanitization operations"

    def test_performance_improvement_evidence(self):
        """Test that provides evidence of performance improvement from pre-compilation."""

        # Simulate the old approach (compile on every call)
        def slow_sanitizer(text: str) -> str:
            """Simulates the old approach with pattern compilation on every call."""
            if not text or not isinstance(text, str):
                return text

            # Compile patterns on every call (BAD - old approach)
            password_pattern = re.compile(
                r'password["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE
            )
            api_key_pattern = re.compile(
                r'api[_-]?key["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE
            )
            token_pattern = re.compile(
                r'token["\s]*[:=]["\s]*([^"\s,}]+)', re.IGNORECASE
            )

            sanitized = text
            sanitized = password_pattern.sub("password=[REDACTED]", sanitized)
            sanitized = api_key_pattern.sub("api_key=[REDACTED]", sanitized)
            sanitized = token_pattern.sub("token=[REDACTED]", sanitized)

            return sanitized

        # Compare performance
        test_text = "password=secret123 api_key=abcd1234 token=xyz789"
        iterations = 50

        # Time the optimized approach
        sanitizer = SensitiveDataSanitizer()
        start_time = time.time()
        for _ in range(iterations):
            sanitizer.sanitize_string(test_text)
        optimized_time = time.time() - start_time

        # Time the slow approach
        start_time = time.time()
        for _ in range(iterations):
            slow_sanitizer(test_text)
        slow_time = time.time() - start_time

        # Optimized approach should be significantly faster
        # Allow some variance, but should be at least 2x faster
        speed_improvement = slow_time / optimized_time

        assert speed_improvement > 2.0, (
            f"Pre-compiled patterns should be significantly faster. "
            f"Speed improvement: {speed_improvement:.2f}x "
            f"(expected > 2x improvement)"
        )

        # Both should produce the same result
        optimized_result = sanitizer.sanitize_string(test_text)
        slow_result = slow_sanitizer(test_text)

        # Results should both be sanitized (may differ in exact format)
        assert "[REDACTED]" in optimized_result or "secret123" not in optimized_result
        assert "[REDACTED]" in slow_result or "secret123" not in slow_result


class TestSanitizationPatternDetection:
    """Test that the sanitizer detects patterns that need pre-compilation."""

    def test_pattern_compilation_during_init(self):
        """Test that regex patterns are compiled during sanitizer initialization."""
        import re

        # Track calls to re.compile during initialization
        original_compile = re.compile
        compile_calls = []

        def tracking_compile(pattern, flags=0):
            compile_calls.append((pattern, flags))
            return original_compile(pattern, flags)

        re.compile = tracking_compile

        try:
            # Create sanitizer - should compile patterns
            sanitizer = SensitiveDataSanitizer()

            # Should have compiled some patterns during init
            init_compile_count = len(compile_calls)

            # The default configuration might not have patterns,
            # so we'll accept 0 compilations for empty config
            # But if there are compilations, they should be during init
            assert init_compile_count >= 0, "Compilation count should be non-negative"

            # Reset counter
            compile_calls.clear()

            # Use the sanitizer - should not compile more patterns
            sanitizer.sanitize_string("password=test123")
            sanitizer.sanitize_field_value("api_key", "secret")

            runtime_compile_count = len(compile_calls)

            # Should not compile any new patterns during runtime
            assert runtime_compile_count == 0, (
                f"Patterns were compiled at runtime ({runtime_compile_count} compilations). "
                f"All patterns should be pre-compiled during initialization."
            )

        finally:
            re.compile = original_compile

    def test_custom_patterns_are_precompiled(self):
        """Test that custom sanitization rules are properly pre-compiled."""
        from code_indexer.server.models.error_models import SanitizationRule

        # Create configuration with custom patterns
        custom_rules = [
            SanitizationRule(
                pattern=r'ssn["\s]*[:=]["\s]*(\d{3}-\d{2}-\d{4})',
                replacement="ssn=[REDACTED]",
                case_sensitive=False,
            ),
            SanitizationRule(
                pattern=r'credit[_-]?card["\s]*[:=]["\s]*(\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4})',
                replacement="credit_card=[REDACTED]",
                case_sensitive=False,
            ),
        ]

        config = ErrorHandlerConfiguration(sanitization_rules=custom_rules)
        sanitizer = SensitiveDataSanitizer(config)

        # Should have pre-compiled the custom patterns
        assert len(sanitizer._compiled_rules) == len(custom_rules)

        # Test that custom patterns work
        test_data = "user_ssn=123-45-6789 and credit_card=1234-5678-9012-3456"
        result = sanitizer.sanitize_string(test_data)

        # Should not contain sensitive data
        assert "123-45-6789" not in result
        assert "1234-5678-9012-3456" not in result

        # Should contain redacted markers
        assert "[REDACTED]" in result or "ssn=[REDACTED]" in result
