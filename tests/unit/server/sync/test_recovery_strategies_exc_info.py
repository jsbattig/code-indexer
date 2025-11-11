"""Test that recovery strategies log exceptions with full stack traces.

This test verifies that exc_info=True is used in critical exception handlers
to ensure complete debugging context is captured in error logs.
"""

import pytest
import logging
from pathlib import Path
from unittest.mock import Mock, patch


class TestRecoveryStrategiesExceptionLogging:
    """Test exception logging with exc_info=True in recovery strategies."""

    def test_checkpoint_recovery_failure_logs_with_exc_info(self, tmp_path, caplog):
        """Test that checkpoint recovery failure logs exception with stack trace."""
        from code_indexer.server.sync.recovery_strategies import (
            CheckpointRecoveryStrategy,
        )
        from code_indexer.server.sync.error_handler import (
            SyncError,
            ErrorSeverity,
            ErrorCategory,
            ErrorContext,
        )

        # Create strategy
        strategy = CheckpointRecoveryStrategy(checkpoint_dir=tmp_path)

        # Create a sync error
        error = SyncError(
            error_code="TEST_ERROR",
            message="Test error message",
            severity=ErrorSeverity.RECOVERABLE,
            category=ErrorCategory.GIT_OPERATION,
        )

        # Create error context with correct fields
        context = ErrorContext(
            phase="test_phase",
            repository="test_repo",
            user_id="test_user",
        )

        # Create a failing operation
        def failing_operation():
            raise RuntimeError("Simulated checkpoint recovery failure")

        # Execute recovery (will fail)
        with caplog.at_level(logging.ERROR):
            result = strategy.execute_recovery(error, context, failing_operation)

        # Verify error was logged
        assert any(
            "Checkpoint recovery failed" in record.message for record in caplog.records
        )

        # Verify stack trace was logged (exc_info=True)
        # When exc_info=True, the log record should have exc_info set
        error_records = [
            r for r in caplog.records if "Checkpoint recovery failed" in r.message
        ]
        assert len(error_records) > 0, "Should have logged checkpoint recovery failure"

        error_record = error_records[0]
        # exc_info should be present and not None when exc_info=True is used
        assert (
            error_record.exc_info is not None
        ), "Log record should have exc_info (stack trace) when logging exception"
        assert (
            error_record.exc_info[0] is not None
        ), "exc_info should contain exception type"
