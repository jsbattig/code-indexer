"""Unit tests for centralized exception logger.

Tests exception logging functionality including:
- Log file creation with timestamp and PID
- Exception logging with full context
- Mode-specific log file paths (CLI/Daemon vs Server)
- Thread exception handling
"""

import json
import os
import threading
import time
from datetime import datetime
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_exception_logger_singleton():
    """Reset ExceptionLogger singleton before each test."""
    from src.code_indexer.utils.exception_logger import ExceptionLogger

    ExceptionLogger._instance = None
    yield
    ExceptionLogger._instance = None


class TestExceptionLoggerInitialization:
    """Test exception logger initialization and log file creation."""

    def test_cli_mode_creates_log_file_in_project_directory(self, tmp_path):
        """Test that CLI mode creates error log in .code-indexer/ directory."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Verify log file created in project's .code-indexer directory
        assert logger.log_file_path.parent == project_root / ".code-indexer"
        assert logger.log_file_path.exists()

        # Verify filename format: error_<timestamp>_<pid>.log
        filename = logger.log_file_path.name
        assert filename.startswith("error_")
        assert filename.endswith(".log")

        # Verify filename contains PID
        pid = os.getpid()
        assert str(pid) in filename

    def test_daemon_mode_creates_log_file_in_project_directory(self, tmp_path):
        """Test that Daemon mode creates error log in .code-indexer/ directory."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="daemon")

        # Daemon mode uses same location as CLI
        assert logger.log_file_path.parent == project_root / ".code-indexer"
        assert logger.log_file_path.exists()

    def test_server_mode_creates_log_file_in_home_directory(self, tmp_path):
        """Test that Server mode creates error log in ~/.cidx-server/logs/."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        with patch("pathlib.Path.home") as mock_home:
            mock_home.return_value = tmp_path
            project_root = tmp_path / "test_project"
            project_root.mkdir()

            logger = ExceptionLogger.initialize(project_root, mode="server")

            # Server mode uses ~/.cidx-server/logs/
            expected_log_dir = tmp_path / ".cidx-server" / "logs"
            assert logger.log_file_path.parent == expected_log_dir
            assert logger.log_file_path.exists()

    def test_log_directory_created_if_not_exists(self, tmp_path):
        """Test that log directory is created if it doesn't exist."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        # .code-indexer doesn't exist yet
        code_indexer_dir = project_root / ".code-indexer"
        assert not code_indexer_dir.exists()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Directory should now exist
        assert code_indexer_dir.exists()
        assert logger.log_file_path.exists()

    def test_filename_contains_timestamp_and_pid(self, tmp_path):
        """Test that log filename contains timestamp and PID for uniqueness."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        datetime.now()
        logger = ExceptionLogger.initialize(project_root, mode="cli")
        datetime.now()

        filename = logger.log_file_path.name
        pid = os.getpid()

        # Filename format: error_YYYYMMDD_HHMMSS_<pid>.log
        assert filename.startswith("error_")
        assert str(pid) in filename
        assert filename.endswith(".log")

        # Extract timestamp from filename
        # Format: error_20251109_143022_12345.log
        parts = filename.split("_")
        assert len(parts) >= 4
        date_part = parts[1]  # YYYYMMDD
        time_part = parts[2]  # HHMMSS

        # Basic validation that timestamp is reasonable
        assert len(date_part) == 8
        assert len(time_part) == 6
        current_year = str(datetime.now().year)
        assert date_part.startswith(current_year)  # Current year


class TestExceptionLogging:
    """Test exception logging functionality."""

    def test_log_exception_writes_json_to_file(self, tmp_path):
        """Test that logging an exception writes JSON data to the log file."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Create and log an exception
        try:
            raise ValueError("Test error message")
        except ValueError as e:
            logger.log_exception(e, context={"test": "data"})

        # Read and verify log file contents
        with open(logger.log_file_path) as f:
            content = f.read()

        # Should contain JSON
        assert "ValueError" in content
        assert "Test error message" in content
        assert "test" in content
        assert "data" in content

        # Verify it's valid JSON (between separators)
        log_entries = content.split("\n---\n")
        first_entry = log_entries[0]
        log_data = json.loads(first_entry)

        assert log_data["exception_type"] == "ValueError"
        assert log_data["exception_message"] == "Test error message"
        assert "stack_trace" in log_data
        assert log_data["context"]["test"] == "data"

    def test_log_exception_includes_timestamp(self, tmp_path):
        """Test that logged exception includes ISO timestamp."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        before = datetime.now()

        try:
            raise RuntimeError("Timestamp test")
        except RuntimeError as e:
            logger.log_exception(e)

        after = datetime.now()

        with open(logger.log_file_path) as f:
            content = f.read()

        log_data = json.loads(content.split("\n---\n")[0])

        # Verify timestamp exists and is ISO format
        assert "timestamp" in log_data
        timestamp = datetime.fromisoformat(log_data["timestamp"])

        # Timestamp should be between before and after
        assert before <= timestamp <= after

    def test_log_exception_includes_thread_info(self, tmp_path):
        """Test that logged exception includes thread name and ID."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        try:
            raise KeyError("Thread test")
        except KeyError as e:
            logger.log_exception(e, thread_name="TestThread")

        with open(logger.log_file_path) as f:
            content = f.read()

        log_data = json.loads(content.split("\n---\n")[0])

        assert "thread" in log_data
        assert log_data["thread"] == "TestThread"

    def test_log_exception_includes_stack_trace(self, tmp_path):
        """Test that logged exception includes complete stack trace."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        def inner_function():
            raise ZeroDivisionError("Division by zero")

        def outer_function():
            inner_function()

        try:
            outer_function()
        except ZeroDivisionError as e:
            logger.log_exception(e)

        with open(logger.log_file_path) as f:
            content = f.read()

        log_data = json.loads(content.split("\n---\n")[0])

        # Verify stack trace includes function names
        assert "stack_trace" in log_data
        assert "inner_function" in log_data["stack_trace"]
        assert "outer_function" in log_data["stack_trace"]
        assert "Division by zero" in log_data["stack_trace"]

    def test_multiple_exceptions_appended_to_same_file(self, tmp_path):
        """Test that multiple exceptions are appended with separators."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Log multiple exceptions
        try:
            raise ValueError("First exception")
        except ValueError as e:
            logger.log_exception(e)

        try:
            raise TypeError("Second exception")
        except TypeError as e:
            logger.log_exception(e)

        try:
            raise RuntimeError("Third exception")
        except RuntimeError as e:
            logger.log_exception(e)

        with open(logger.log_file_path) as f:
            content = f.read()

        # Split by separator
        entries = content.split("\n---\n")

        # Should have 3 entries (last one may be empty after final separator)
        assert len([e for e in entries if e.strip()]) == 3

        # Verify each entry
        entry1 = json.loads(entries[0])
        assert entry1["exception_type"] == "ValueError"
        assert entry1["exception_message"] == "First exception"

        entry2 = json.loads(entries[1])
        assert entry2["exception_type"] == "TypeError"
        assert entry2["exception_message"] == "Second exception"

        entry3 = json.loads(entries[2])
        assert entry3["exception_type"] == "RuntimeError"
        assert entry3["exception_message"] == "Third exception"


class TestThreadExceptionHook:
    """Test global thread exception handler."""

    def test_install_thread_exception_hook(self, tmp_path):
        """Test that threading.excepthook can be installed globally."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")

        # Install the hook
        original_excepthook = threading.excepthook
        logger.install_thread_exception_hook()

        # Verify hook was installed
        assert threading.excepthook != original_excepthook

        # Restore original
        threading.excepthook = original_excepthook

    def test_thread_exception_captured_and_logged(self, tmp_path):
        """Test that uncaught thread exceptions are captured and logged."""
        from src.code_indexer.utils.exception_logger import ExceptionLogger

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        logger = ExceptionLogger.initialize(project_root, mode="cli")
        logger.install_thread_exception_hook()

        exception_raised = threading.Event()

        def failing_thread_function():
            try:
                raise ValueError("Uncaught thread exception")
            finally:
                exception_raised.set()

        # Start thread that will raise exception
        thread = threading.Thread(target=failing_thread_function, name="FailingThread")
        thread.start()
        thread.join(timeout=2)

        # Wait for exception to be logged
        assert exception_raised.wait(timeout=2)
        time.sleep(0.1)  # Brief delay for log write

        # Verify exception was logged
        with open(logger.log_file_path) as f:
            content = f.read()

        assert "ValueError" in content
        assert "Uncaught thread exception" in content
        assert "FailingThread" in content
