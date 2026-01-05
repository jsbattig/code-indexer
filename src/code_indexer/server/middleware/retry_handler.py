from code_indexer.server.middleware.correlation import get_correlation_id
"""
Database retry handler middleware for CIDX Server.

Handles database operation retries with exponential backoff following
CLAUDE.md Foundation #1: No mocks - real retry logic with actual timing.
"""

import time
import random
import logging
from typing import Callable, TypeVar

from ..models.error_models import (
    RetryConfiguration,
    DatabaseRetryableError,
    DatabasePermanentError,
)

# Configure logger for this module
logger = logging.getLogger(__name__)

# Type variable for retry functions
T = TypeVar("T")


class DatabaseRetryHandler:
    """
    Handles database operation retries with exponential backoff.

    Follows CLAUDE.md Foundation #1: No mocks - real retry logic with actual timing.
    Implements sophisticated retry patterns for different error types.
    """

    def __init__(self, config: RetryConfiguration):
        """Initialize retry handler with configuration."""
        self.config = config

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        Determine if an error should be retried.

        Args:
            error: The exception that occurred
            attempt: Current attempt number (1-indexed)

        Returns:
            True if the error should be retried, False otherwise
        """
        if attempt > self.config.max_attempts:
            return False

        # DatabaseRetryableError should be retried
        if isinstance(error, DatabaseRetryableError):
            return True

        # DatabasePermanentError should NOT be retried
        if isinstance(error, DatabasePermanentError):
            return False

        # Check for known transient database errors by message patterns
        error_message = str(error).lower()
        transient_patterns = [
            "connection timeout",
            "connection refused",
            "connection reset",
            "connection pool exhausted",
            "temporary failure",
            "deadlock detected",
            "lock wait timeout",
            "server shutdown",
            "too many connections",
            "connection lost",
        ]

        return any(pattern in error_message for pattern in transient_patterns)

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for retry attempt using exponential backoff with jitter.

        Args:
            attempt: Attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: base_delay * (multiplier ^ (attempt - 1))
        base_delay = self.config.base_delay_seconds * (
            self.config.backoff_multiplier ** (attempt - 1)
        )

        # Apply maximum delay limit
        delay = min(base_delay, self.config.max_delay_seconds)

        # Add jitter to prevent thundering herd
        if self.config.jitter_factor > 0:
            jitter = delay * self.config.jitter_factor * random.random()
            delay += jitter

        return delay

    def execute_with_retry(self, operation: Callable[[], T]) -> T:
        """
        Execute database operation with retry logic.

        Args:
            operation: Function to execute that may raise database errors

        Returns:
            Result of the operation

        Raises:
            The final exception if all retries are exhausted
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 2):  # +1 for initial attempt
            try:
                return operation()
            except Exception as e:
                last_exception = e

                if not self.should_retry(e, attempt):
                    # Don't retry permanent errors or if max attempts exceeded
                    raise e

                if (
                    attempt <= self.config.max_attempts
                ):  # Don't delay after final attempt
                    delay = self.calculate_delay(attempt)
                    logger.warning(
                        f"Database operation failed on attempt {attempt}, retrying in {delay:.2f}s: {e}"
                    , extra={"correlation_id": get_correlation_id()})
                    time.sleep(delay)

        # This should not be reached, but provide fallback
        raise last_exception or Exception("Retry logic error")
