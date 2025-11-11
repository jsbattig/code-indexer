"""Integration tests for ExceptionLogger in daemon mode.

Tests that ExceptionLogger is properly initialized when daemon service starts
and that exceptions are logged to .code-indexer/error_*.log files.
"""

import pytest
from pathlib import Path


class TestDaemonExceptionLoggerIntegration:
    """Test ExceptionLogger integration with daemon service."""

    def test_daemon_service_initializes_exception_logger(self, tmp_path):
        """Test that DaemonService.__init__ initializes ExceptionLogger."""
        from code_indexer.daemon.service import CIDXDaemonService
        from code_indexer.utils.exception_logger import ExceptionLogger
        import os

        # Change to temp directory so daemon uses it as project root
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Reset singleton if it exists from previous tests
            ExceptionLogger._instance = None

            # Create daemon service instance
            service = CIDXDaemonService()

            # Verify ExceptionLogger was initialized
            # ExceptionLogger uses singleton pattern, so we can check if it's initialized
            assert (
                ExceptionLogger._instance is not None
            ), "ExceptionLogger should be initialized"

            # Verify log file path is in .code-indexer/ (daemon/CLI mode location)
            assert ExceptionLogger._instance.log_file_path is not None
            assert ".code-indexer" in str(
                ExceptionLogger._instance.log_file_path
            ), "Log file should be in .code-indexer/ directory for daemon mode"
        finally:
            os.chdir(original_cwd)
