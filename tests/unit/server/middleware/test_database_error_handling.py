"""
Unit tests for DatabaseError handling with retry logic in GlobalErrorHandler.

Tests database error handling with exponential backoff retry following CLAUDE.md Foundation #1: No mocks.
Uses real database connection simulation without mocking the actual database operations.
"""

import uuid
import time
import pytest

# Removed unittest.mock import following CLAUDE.md Foundation #1: No mocks
from fastapi import Request
from fastapi.testclient import TestClient

from code_indexer.server.middleware.error_handler import GlobalErrorHandler
from code_indexer.server.models.error_models import (
    DatabaseRetryableError,
    DatabasePermanentError,
)


class TestDatabaseErrorHandling:
    """Test DatabaseError handling with retry logic and proper categorization."""

    @pytest.fixture
    def error_handler(self) -> GlobalErrorHandler:
        """Create GlobalErrorHandler instance with retry configuration."""
        return GlobalErrorHandler(
            max_retry_attempts=3,
            base_retry_delay=0.1,  # 100ms for faster testing
            max_retry_delay=1.0,  # 1 second max delay
        )

    @pytest.fixture
    def mock_request(self) -> Request:
        """Create real FastAPI Request object for testing."""
        from fastapi import FastAPI

        app = FastAPI()
        TestClient(app)  # Creates app context

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/query",
                "headers": [(b"host", b"testserver")],
                "query_string": b"",
                "root_path": "",
            }
        )
        return request

    def test_transient_database_error_retry_success(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test successful retry of transient database errors."""
        call_count = 0

        def failing_database_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # Fail first two attempts
                raise DatabaseRetryableError("Connection timeout")
            return "success"  # Succeed on third attempt

        # Execute with retry logic
        result = error_handler.execute_with_database_retry(failing_database_operation)

        # Should succeed after retries
        assert result == "success"
        assert call_count == 3  # Two failures + one success

    def test_transient_database_error_max_retries_exceeded(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test behavior when max retries are exceeded for transient errors."""
        call_count = 0

        def always_failing_operation():
            nonlocal call_count
            call_count += 1
            raise DatabaseRetryableError("Persistent connection timeout")

        # Should raise exception after max retries
        with pytest.raises(DatabaseRetryableError):
            error_handler.execute_with_database_retry(always_failing_operation)

        # Should have called max_retry_attempts + 1 times (initial + retries)
        assert call_count == 4  # 1 initial + 3 retries

    def test_permanent_database_error_no_retry(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that permanent database errors are not retried."""
        call_count = 0

        def permanent_failure_operation():
            nonlocal call_count
            call_count += 1
            raise DatabasePermanentError("Table does not exist")

        # Should not retry permanent errors
        with pytest.raises(DatabasePermanentError):
            error_handler.execute_with_database_retry(permanent_failure_operation)

        # Should only be called once (no retries)
        assert call_count == 1

    def test_exponential_backoff_timing(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test exponential backoff timing between retries."""
        call_times = []

        def failing_operation():
            call_times.append(time.time())
            raise DatabaseRetryableError("Connection refused")

        time.time()  # Record timing start

        with pytest.raises(DatabaseRetryableError):
            error_handler.execute_with_database_retry(failing_operation)

        # Verify exponential backoff timing
        assert len(call_times) == 4  # Initial + 3 retries

        # Calculate delays between attempts
        delays = [call_times[i] - call_times[i - 1] for i in range(1, len(call_times))]

        # Should follow exponential backoff pattern (approximately)
        expected_delays = [0.1, 0.2, 0.4]  # base * 2^(attempt-1)

        for i, (actual, expected) in enumerate(zip(delays, expected_delays)):
            # Allow some variance in timing (±50ms)
            assert (
                abs(actual - expected) < 0.05
            ), f"Retry {i+1} delay {actual:.3f}s not close to expected {expected:.3f}s"

    def test_database_error_response_format_transient(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test response format for transient database errors (503 Service Unavailable)."""
        db_error = DatabaseRetryableError("Connection pool exhausted")

        response_data = error_handler.handle_database_error(db_error, mock_request)

        # Verify standardized response format
        assert "error" in response_data
        assert "message" in response_data
        assert "correlation_id" in response_data
        assert "timestamp" in response_data
        assert "retry_after" in response_data

        # Verify error type and message
        assert response_data["error"] == "service_unavailable"
        assert "temporarily unavailable" in response_data["message"].lower()

        # Verify correlation ID
        uuid.UUID(response_data["correlation_id"])

        # Verify retry-after header value
        retry_after = response_data["retry_after"]
        assert isinstance(retry_after, int)
        assert 1 <= retry_after <= 60  # Should be reasonable retry time

    def test_database_error_response_format_permanent(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test response format for permanent database errors (500 Internal Server Error)."""
        db_error = DatabasePermanentError("Invalid query syntax")

        response_data = error_handler.handle_database_error(db_error, mock_request)

        # Verify standardized response format
        assert "error" in response_data
        assert "message" in response_data
        assert "correlation_id" in response_data
        assert "timestamp" in response_data
        assert "retry_after" not in response_data  # No retry for permanent errors

        # Verify error type and message
        assert response_data["error"] == "internal_server_error"
        assert "server error" in response_data["message"].lower()

        # Correlation ID should be valid UUID
        uuid.UUID(response_data["correlation_id"])

    def test_database_error_status_codes(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that database errors return proper HTTP status codes."""
        # Transient error should return 503
        transient_status = error_handler.get_status_code_for_error_type(
            "service_unavailable"
        )
        assert transient_status == 503

        # Permanent error should return 500
        permanent_status = error_handler.get_status_code_for_error_type(
            "internal_server_error"
        )
        assert permanent_status == 500

    def test_database_error_logging(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that database errors are properly logged with full context."""
        db_error = DatabaseRetryableError("Connection timeout after 30s")

        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_database_error(db_error, mock_request)

        # Verify error was logged
        assert len(caplog.records) == 1
        log_record = caplog.records[0]

        # Verify log content
        assert log_record.levelname == "ERROR"
        assert "DatabaseError" in log_record.message
        assert "Connection timeout" in log_record.message
        assert response_data["correlation_id"] in log_record.message

        # Should include request context
        assert "POST /api/query" in log_record.message

    def test_retry_attempt_logging(
        self, error_handler: GlobalErrorHandler, mock_request: Request, caplog
    ):
        """Test that retry attempts are logged for debugging."""
        call_count = 0

        def failing_operation():
            nonlocal call_count
            call_count += 1
            raise DatabaseRetryableError(f"Attempt {call_count} failed")

        with caplog.at_level("WARNING"):
            with pytest.raises(DatabaseRetryableError):
                error_handler.execute_with_database_retry(failing_operation)

        # Should log retry attempts
        retry_logs = [
            record for record in caplog.records if record.levelname == "WARNING"
        ]
        assert len(retry_logs) == 3  # One for each retry attempt

        # Verify retry log content
        for i, log_record in enumerate(retry_logs, 1):
            assert f"attempt {i}" in log_record.message
            assert f"Attempt {i} failed" in log_record.message

    def test_database_error_correlation_with_original_request(
        self, error_handler: GlobalErrorHandler, caplog
    ):
        """Test that database errors maintain correlation with original request context."""
        # Create request with specific headers
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/repositories/123/query",
                "headers": [
                    (b"host", b"testserver"),
                    (b"user-agent", b"test-client/1.0"),
                    (b"x-request-id", b"req-12345"),
                ],
                "query_string": b"q=test&limit=10",
                "root_path": "",
            }
        )

        db_error = DatabaseRetryableError("Query timeout")

        # Use real logging capture instead of mocks
        with caplog.at_level("ERROR"):
            response_data = error_handler.handle_database_error(db_error, request)

        # Verify error was logged with request context
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        log_message = log_record.message

        # Should include request details in log
        assert "/api/repositories/123/query" in log_message
        assert "q=test&limit=10" in log_message
        assert response_data["correlation_id"] in log_message

    def test_database_connection_pool_error_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test specific handling of database connection pool errors."""
        pool_error = DatabaseRetryableError(
            "FATAL: remaining connection slots are reserved",
            error_code="53300",  # PostgreSQL connection limit error
        )

        response_data = error_handler.handle_database_error(pool_error, mock_request)

        # Should be treated as service unavailable
        assert response_data["error"] == "service_unavailable"

        # Should include appropriate retry-after time for pool exhaustion
        retry_after = response_data["retry_after"]
        assert 5 <= retry_after <= 30  # Reasonable time for pool recovery

    def test_database_deadlock_error_handling(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test specific handling of database deadlock errors."""
        deadlock_error = DatabaseRetryableError(
            "deadlock detected", error_code="40P01"  # PostgreSQL deadlock error
        )

        # Deadlocks should be retried with shorter delays
        call_count = 0

        def deadlock_operation():
            nonlocal call_count
            call_count += 1
            if call_count <= 1:  # Fail once
                raise deadlock_error
            return "recovered"

        result = error_handler.execute_with_database_retry(deadlock_operation)

        # Should recover quickly from deadlocks
        assert result == "recovered"
        assert call_count == 2

    def test_database_error_sensitive_information_sanitization(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that sensitive database information is not exposed in error responses."""
        # Error with sensitive information
        sensitive_error = DatabasePermanentError(
            "connection to server at '/var/lib/postgresql/data' failed: FATAL: password authentication failed for user 'admin'"
        )

        response_data = error_handler.handle_database_error(
            sensitive_error, mock_request
        )

        # Response should not contain sensitive details
        message = response_data["message"]
        assert "/var/lib/postgresql" not in message
        assert "admin" not in message
        assert "password" not in message

        # Should be generic error message
        assert "server error" in message.lower() or "database error" in message.lower()

    def test_database_error_retry_backoff_jitter(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test that retry backoff includes jitter to prevent thundering herd."""
        # Test jitter by examining delay calculation directly (no mocking)
        retry_handler = error_handler.retry_handler

        # Test multiple delay calculations for same attempt
        attempt = 2
        delays = []
        for _ in range(10):
            delay = retry_handler.calculate_delay(attempt)
            delays.append(delay)

        # With jitter, delays should vary
        unique_delays = set(delays)
        if retry_handler.config.jitter_factor > 0:
            # Should have some variation due to jitter
            assert len(unique_delays) > 1, "Jitter should create variation in delays"

        # All delays should be within reasonable bounds for attempt 2
        expected_base = retry_handler.config.base_delay_seconds * (
            retry_handler.config.backoff_multiplier ** (attempt - 1)
        )
        max_with_jitter = expected_base * (1 + retry_handler.config.jitter_factor)

        for delay in delays:
            assert (
                expected_base <= delay <= max_with_jitter
            ), f"Delay {delay} should be between {expected_base} and {max_with_jitter}"

    def test_retry_timing_without_mocks(
        self, error_handler: GlobalErrorHandler, mock_request: Request
    ):
        """Test actual retry timing without using mocks (CLAUDE.md Foundation #1)."""
        call_count = 0
        call_times = []

        def failing_operation():
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            # Only fail twice, succeed on third attempt
            if call_count <= 2:
                raise DatabaseRetryableError(f"Attempt {call_count} failed")
            return "success"

        start_time = time.time()
        result = error_handler.execute_with_database_retry(failing_operation)
        total_time = time.time() - start_time

        # Should succeed after retries
        assert result == "success"
        assert call_count == 3

        # Should have taken some time due to delays (but not too long for tests)
        assert total_time >= 0.1  # At least one base delay
        assert total_time < 2.0  # But not too long for tests

        # Time between calls should increase (exponential backoff)
        if len(call_times) >= 3:
            delay1 = call_times[1] - call_times[0]
            delay2 = call_times[2] - call_times[1]
            # Second delay should be longer than first (exponential backoff)
            assert delay2 > delay1
