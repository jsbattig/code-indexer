"""
Unit tests for sensitive data sanitization in GlobalErrorHandler.

Tests comprehensive security compliance following CLAUDE.md Foundation #1: No mocks.
Validates that sensitive information is never leaked in error responses.
"""

import pytest
from fastapi import Request

from code_indexer.server.middleware.error_handler import (
    GlobalErrorHandler,
    SensitiveDataSanitizer,
)


class TestSensitiveDataSanitization:
    """Test sensitive data sanitization across all error types."""

    @pytest.fixture
    def error_handler(self) -> GlobalErrorHandler:
        """Create GlobalErrorHandler instance."""
        return GlobalErrorHandler()

    @pytest.fixture
    def sanitizer(self) -> SensitiveDataSanitizer:
        """Create SensitiveDataSanitizer instance."""
        return SensitiveDataSanitizer()

    @pytest.fixture
    def mock_request(self) -> Request:
        """Create request with potentially sensitive headers."""
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/auth/login",
                "headers": [
                    (b"host", b"api.company.com"),
                    (b"authorization", b"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"),
                    (b"x-api-key", b"sk-1234567890abcdef"),
                    (b"cookie", b"session=abc123def456; csrf=token789"),
                ],
                "query_string": b"api_key=secret123&token=xyz789",
                "root_path": "",
            }
        )
        return request

    def test_password_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of various password patterns."""
        sensitive_strings = [
            "password=secret123",
            "pwd:admin123",
            "pass = 'mypassword'",
            "PASSWORD: 'SuperSecret!'",
            '"password": "complex_pass_123"',
            "user_password='hidden'",
            "db_password=p@ssw0rd",
            "password123=value",  # Should NOT be sanitized (not a password field)
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            if "password123=" in original:
                # This should not be sanitized as it's not a password field
                assert original == sanitized
            else:
                # These should be sanitized
                assert sanitized != original
                assert "[REDACTED]" in sanitized
                assert "secret123" not in sanitized
                assert "admin123" not in sanitized
                assert "mypassword" not in sanitized
                assert "SuperSecret!" not in sanitized
                assert "complex_pass_123" not in sanitized
                assert "hidden" not in sanitized
                assert "p@ssw0rd" not in sanitized

    def test_api_key_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of API keys and tokens."""
        sensitive_strings = [
            "api_key=sk-1234567890abcdef",
            "API_KEY: 'key_live_abc123'",
            "apikey=pk_test_xyz789",
            "x-api-key: bearer_token_here",
            "access_token=jwt.token.here",
            "bearer_token='long_token_string'",
            "auth_token: secret_auth",
            "client_secret=oauth_secret_123",
            "refresh_token='refresh_abc'",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            assert sanitized != original
            assert "[REDACTED]" in sanitized

            # Should not contain any of the sensitive values
            assert "sk-1234567890abcdef" not in sanitized
            assert "key_live_abc123" not in sanitized
            assert "pk_test_xyz789" not in sanitized
            assert "bearer_token_here" not in sanitized
            assert "jwt.token.here" not in sanitized
            assert "long_token_string" not in sanitized
            assert "secret_auth" not in sanitized
            assert "oauth_secret_123" not in sanitized
            assert "refresh_abc" not in sanitized

    def test_database_credential_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of database connection strings and credentials."""
        sensitive_strings = [
            "postgres://admin:secret@localhost:5432/db",
            "mysql://user:password123@db.example.com/app",
            "mongodb://dbuser:dbpass@mongo:27017/database",
            "redis://auth:redispass@redis-server:6379",
            "database_url=postgres://app:secret@prod-db/main",
            "DB_PASSWORD=database_secret_123",
            "db_host=internal-db.company.com",
            "connection_string='Server=db;Password=secret;'",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            assert sanitized != original
            assert "[REDACTED]" in sanitized

            # Should not contain credentials
            assert "admin:secret" not in sanitized
            assert "user:password123" not in sanitized
            assert "dbuser:dbpass" not in sanitized
            assert "auth:redispass" not in sanitized
            assert "app:secret" not in sanitized
            assert "database_secret_123" not in sanitized
            assert "Password=secret" not in sanitized

            # Should not contain internal hostnames
            assert "internal-db.company.com" not in sanitized

    def test_file_path_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of sensitive file paths and directories."""
        sensitive_strings = [
            "/home/user/.ssh/id_rsa",
            "/etc/passwd",
            "/var/secrets/app.key",
            "C:\\Users\\admin\\Documents\\secret.txt",
            "/root/.env",
            "/app/config/production.yml",
            "/var/lib/app/secrets/",
            "~/.aws/credentials",
            "/etc/ssl/private/server.key",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            # Should either be completely redacted or have paths sanitized
            if "[REDACTED]" in sanitized:
                # Completely redacted
                assert original not in sanitized
            else:
                # Path components should be sanitized
                assert "/home/user" not in sanitized
                assert "\\Users\\admin" not in sanitized
                assert "/root" not in sanitized
                assert "/var/secrets" not in sanitized
                assert "/.ssh/" not in sanitized or "[PATH]" in sanitized

    def test_ip_address_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of internal IP addresses."""
        sensitive_strings = [
            "Database at 10.0.0.15:5432 failed",
            "Connection to 192.168.1.100 timed out",
            "Internal server 172.16.0.50 unavailable",
            "Connecting to 10.10.10.10:3306",
            "Error from 127.0.0.1:8080",  # Should NOT be sanitized (localhost)
            "Public IP 8.8.8.8 accessible",  # Should NOT be sanitized (public)
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            if "127.0.0.1" in original or "8.8.8.8" in original:
                # Localhost and public IPs should not be sanitized
                assert original == sanitized
            else:
                # Internal IPs should be sanitized
                assert "[IP_ADDRESS]" in sanitized or "[REDACTED]" in sanitized
                assert "10.0.0.15" not in sanitized
                assert "192.168.1.100" not in sanitized
                assert "172.16.0.50" not in sanitized
                assert "10.10.10.10" not in sanitized

    def test_email_address_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of email addresses."""
        sensitive_strings = [
            "User admin@company.com failed login",
            "Contact support@internal.corp for help",
            "Email sent to john.doe@example.org",
            "From: security@company.com",
            "Error in user.email@domain.co.uk validation",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            assert "[EMAIL]" in sanitized or "[REDACTED]" in sanitized
            assert "admin@company.com" not in sanitized
            assert "support@internal.corp" not in sanitized
            assert "john.doe@example.org" not in sanitized
            assert "security@company.com" not in sanitized
            assert "user.email@domain.co.uk" not in sanitized

    def test_jwt_token_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of JWT tokens."""
        jwt_tokens = [
            "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMTIzIiwiZXhwIjoxNjM5NTg0MDAwfQ.signature",
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature",
            "JWT: eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.data.sign",
        ]

        for original in jwt_tokens:
            sanitized = sanitizer.sanitize_string(original)

            assert "[JWT_TOKEN]" in sanitized or "[REDACTED]" in sanitized
            assert "eyJ0eXAiOiJKV1QiOiJhbGciOiJIUzI1NiJ9" not in sanitized
            assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in sanitized
            assert "eyJ0eXAiOiJKV1QiOiJhbGciOiJSUzI1NiJ9" not in sanitized

    def test_credit_card_sanitization(self, sanitizer: SensitiveDataSanitizer):
        """Test sanitization of credit card numbers."""
        sensitive_strings = [
            "Card number: 4532015112830366",
            "CC: 5555555555554444",
            "Credit card 371449635398431 expired",
            "Payment with 6011111111111117",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            assert "[CREDIT_CARD]" in sanitized or "[REDACTED]" in sanitized
            assert "4532015112830366" not in sanitized
            assert "5555555555554444" not in sanitized
            assert "371449635398431" not in sanitized
            assert "6011111111111117" not in sanitized

    def test_social_security_number_sanitization(
        self, sanitizer: SensitiveDataSanitizer
    ):
        """Test sanitization of SSN and similar identifiers."""
        sensitive_strings = [
            "SSN: 123-45-6789",
            "Social Security Number 987654321",
            "SSN 555-55-5555 not found",
            "Tax ID: 12-3456789",
        ]

        for original in sensitive_strings:
            sanitized = sanitizer.sanitize_string(original)

            assert "[SSN]" in sanitized or "[REDACTED]" in sanitized
            assert "123-45-6789" not in sanitized
            assert "987654321" not in sanitized
            assert "555-55-5555" not in sanitized
            assert "12-3456789" not in sanitized

    def test_complex_data_structure_sanitization(
        self, sanitizer: SensitiveDataSanitizer
    ):
        """Test sanitization of complex nested data structures."""
        complex_data = {
            "user": {
                "id": 123,
                "email": "user@company.com",
                "password": "secret123",
                "api_key": "sk-1234567890",
            },
            "config": {
                "database_url": "postgres://admin:secret@db:5432/app",
                "jwt_secret": "super_secret_key",
                "debug": True,
            },
            "safe_data": {
                "name": "John Doe",
                "age": 30,
                "city": "New York",
            },
        }

        sanitized = sanitizer.sanitize_data_structure(complex_data)

        # Sensitive data should be redacted
        assert sanitized["user"]["password"] == "[REDACTED]"
        assert sanitized["user"]["api_key"] == "[REDACTED]"
        assert "[REDACTED]" in str(sanitized["user"]["email"])
        assert "[REDACTED]" in str(sanitized["config"]["database_url"])
        assert sanitized["config"]["jwt_secret"] == "[REDACTED]"

        # Safe data should remain
        assert sanitized["safe_data"]["name"] == "John Doe"
        assert sanitized["safe_data"]["age"] == 30
        assert sanitized["safe_data"]["city"] == "New York"
        assert sanitized["user"]["id"] == 123
        assert sanitized["config"]["debug"] is True

    def test_error_response_sanitization_integration(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that all error responses are sanitized when they contain sensitive data."""

        # Create exception with sensitive information
        class SensitiveException(Exception):
            def __init__(self):
                self.database_url = "postgres://admin:password123@internal-db:5432/app"
                self.api_keys = ["sk-live_123", "pk_test_456"]
                super().__init__(f"Database connection failed: {self.database_url}")

        sensitive_exc = SensitiveException()

        response_data = error_handler.handle_unhandled_exception(
            sensitive_exc, mock_request
        )

        # Convert entire response to string for comprehensive checking
        response_str = str(response_data)

        # Should not contain any sensitive information
        assert "password123" not in response_str
        assert "admin:password123" not in response_str
        assert "internal-db" not in response_str
        assert "sk-live_123" not in response_str
        assert "pk_test_456" not in response_str

        # Should be generic error message
        assert "internal server error" in response_data["message"].lower()

    def test_validation_error_sanitization(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that validation errors with sensitive data are sanitized."""
        from pydantic import (
            BaseModel,
            ValidationError as PydanticValidationError,
            Field,
        )

        class SensitiveModel(BaseModel):
            username: str
            password: str = Field(..., min_length=8)
            api_key: str

        # This will create validation error with sensitive data
        validation_error = None
        try:
            SensitiveModel(
                username="admin", password="weak", api_key="sk-short"  # Too short
            )
        except PydanticValidationError as e:
            validation_error = e

        response_data = error_handler.handle_validation_error(
            validation_error, mock_request
        )

        # Check field errors for sanitization
        field_errors = response_data["details"]["field_errors"]

        for field_error in field_errors:
            # Rejected values should be sanitized if they're sensitive fields
            if field_error["field"] in ["password", "api_key"]:
                rejected_value = field_error["rejected_value"]
                assert rejected_value == "[REDACTED]" or "[REDACTED]" in str(
                    rejected_value
                )
            else:
                # Non-sensitive fields like username should not be redacted
                assert field_error["rejected_value"] == "admin"

    def test_request_headers_sanitization(
        self, error_handler: GlobalErrorHandler, caplog
    ):
        """Test that sensitive request headers are sanitized in logging."""
        # Create request with sensitive headers
        sensitive_request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/sensitive",
                "headers": [
                    (b"authorization", b"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9"),
                    (b"x-api-key", b"sk-live_abcdef123456"),
                    (b"cookie", b"session_id=secret_session_123"),
                    (b"x-forwarded-for", b"10.0.0.15, 192.168.1.100"),
                ],
                "query_string": b"api_key=secret&token=xyz123",
                "root_path": "",
            }
        )

        exception = ValueError("Test error")

        with caplog.at_level("ERROR"):
            error_handler.handle_unhandled_exception(exception, sensitive_request)

        # Check that logs don't contain sensitive information
        log_message = caplog.records[0].message

        assert "Bearer eyJ0eXAiOiJKV1QiOiJhbGciOiJIUzI1NiJ9" not in log_message
        assert "sk-live_abcdef123456" not in log_message
        assert "secret_session_123" not in log_message
        assert "api_key=secret" not in log_message
        assert "token=xyz123" not in log_message
        assert "10.0.0.15" not in log_message or "[IP_ADDRESS]" in log_message
        assert "192.168.1.100" not in log_message or "[IP_ADDRESS]" in log_message

    def test_sanitizer_performance_with_large_strings(
        self, sanitizer: SensitiveDataSanitizer
    ):
        """Test that sanitizer performs adequately with large strings."""
        import time

        # Create large string with scattered sensitive data
        large_parts = []
        for i in range(1000):
            if i % 100 == 0:
                large_parts.append(f"password=secret{i}")
            else:
                large_parts.append(f"safe_data_{i}=value_{i}")

        large_string = " ".join(large_parts)

        start_time = time.time()
        sanitized = sanitizer.sanitize_string(large_string)
        end_time = time.time()

        # Should complete in reasonable time (< 1 second)
        assert (end_time - start_time) < 1.0

        # Should still sanitize properly
        assert "secret0" not in sanitized
        assert "secret100" not in sanitized
        assert "secret900" not in sanitized
        assert "[REDACTED]" in sanitized

    def test_sanitizer_regex_patterns_completeness(
        self, sanitizer: SensitiveDataSanitizer
    ):
        """Test that sanitizer regex patterns are comprehensive."""
        # Test various formats and case variations
        test_cases = [
            ("Password: secret", True),
            ("PASSWORD: secret", True),
            ("password: secret", True),
            ("pwd=secret", True),
            ("PWD=secret", True),
            ("pass=secret", True),
            ("PASS=secret", True),
            ("api_key: secret", True),
            ("API_KEY: secret", True),
            ("apikey: secret", True),
            ("APIKEY: secret", True),
            ("token=secret", True),
            ("TOKEN=secret", True),
            ("bearer=secret", True),
            ("BEARER=secret", True),
            ("normal_field=value", False),
        ]

        for test_string, should_be_sanitized in test_cases:
            sanitized = sanitizer.sanitize_string(test_string)

            if should_be_sanitized:
                assert sanitized != test_string
                assert "[REDACTED]" in sanitized
                assert "secret" not in sanitized
            else:
                assert sanitized == test_string
