"""
Validation exceptions for CIDX Server - Story 9 Implementation.

Custom exception classes for index validation failures and recovery operations.
Following CLAUDE.md Foundation #1: Real exceptions, not mocked failures.
"""


class ValidationFailedError(Exception):
    """Exception raised when index validation fails with actionable errors."""

    def __init__(self, message: str, validation_errors=None, health_score: float = 0.0):
        """
        Initialize ValidationFailedError.

        Args:
            message: Human-readable error message
            validation_errors: List of specific validation errors
            health_score: Overall health score (0.0 - 1.0)
        """
        super().__init__(message)
        self.validation_errors = validation_errors or []
        self.health_score = health_score


class IndexCorruptionError(ValidationFailedError):
    """Exception raised when severe index corruption is detected."""

    def __init__(
        self, message: str, corrupt_files=None, corruption_type: str = "unknown"
    ):
        """
        Initialize IndexCorruptionError.

        Args:
            message: Human-readable error message
            corrupt_files: List of files with corrupted data
            corruption_type: Type of corruption detected
        """
        super().__init__(message, health_score=0.0)
        self.corrupt_files = corrupt_files or []
        self.corruption_type = corruption_type


class RecoveryFailedError(Exception):
    """Exception raised when auto-recovery operations fail."""

    def __init__(
        self, message: str, recovery_type: str = "unknown", original_error=None
    ):
        """
        Initialize RecoveryFailedError.

        Args:
            message: Human-readable error message
            recovery_type: Type of recovery that failed
            original_error: Original exception that caused recovery to fail
        """
        super().__init__(message)
        self.recovery_type = recovery_type
        self.original_error = original_error
