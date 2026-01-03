"""
Integration tests for SQLiteLogHandler integration in app.py.

TDD Red Phase: These tests will fail until SQLiteLogHandler is integrated into server startup.

Test Coverage:
- Verifies SQLiteLogHandler is added to root logger during server startup
- Verifies logs written via logging.info() appear in SQLite database
- Verifies handler is configured with correct path and log level
"""

import logging
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Generator
from unittest.mock import patch, MagicMock
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_server_dir() -> Generator[Path, None, None]:
    """Create a temporary server directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        server_dir = Path(tmpdir) / ".cidx-server"
        server_dir.mkdir(parents=True)
        yield server_dir


@pytest.fixture
def mock_environment(temp_server_dir: Path):
    """Mock environment variables for server startup."""
    with patch.dict(os.environ, {"CIDX_SERVER_DATA_DIR": str(temp_server_dir)}):
        yield temp_server_dir


class TestSQLiteLogHandlerIntegration:
    """Test SQLiteLogHandler integration in app.py startup."""

    def test_sqlite_handler_attached_to_root_logger(self, mock_environment: Path):
        """Test that SQLiteLogHandler is attached to root logger during server startup."""
        # Import app to trigger lifespan startup
        from code_indexer.server.app import create_app

        # Clear existing handlers before test
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()

        try:
            app = create_app()

            # Use TestClient as context manager to trigger lifespan
            with TestClient(app) as client:
                # Verify SQLiteLogHandler is attached to root logger
                from code_indexer.server.services.sqlite_log_handler import SQLiteLogHandler

                root_logger = logging.getLogger()
                sqlite_handlers = [h for h in root_logger.handlers if isinstance(h, SQLiteLogHandler)]

                assert len(sqlite_handlers) > 0, "SQLiteLogHandler not attached to root logger"

                # Verify handler uses correct database path
                handler = sqlite_handlers[0]
                expected_db_path = mock_environment / "logs.db"
                assert Path(handler.db_path) == expected_db_path

                # Verify handler has correct log level
                assert handler.level <= logging.INFO

        finally:
            # Restore original handlers
            root_logger.handlers = original_handlers

    def test_logs_written_to_sqlite_database(self, mock_environment: Path):
        """Test that logs written via logging.info() appear in SQLite database."""
        from code_indexer.server.app import create_app

        # Clear existing handlers before test
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()

        try:
            app = create_app()

            # Use TestClient as context manager to trigger lifespan
            with TestClient(app) as client:
                # Set root logger to INFO level (default is WARNING)
                logging.getLogger().setLevel(logging.INFO)

                # Write test log message
                test_message = "Integration test log message - SQLiteLogHandler"
                logger = logging.getLogger("test_integration")
                logger.info(test_message)

                # Flush all handlers to ensure logs are written
                for handler in logging.getLogger().handlers:
                    handler.flush()

                # Small delay to ensure SQLite commits are visible
                time.sleep(0.1)

                # Verify message appears in database
                db_path = mock_environment / "logs.db"
                assert db_path.exists(), "Database file not created"

                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT message, level, source FROM logs WHERE message LIKE ?",
                    (f"%{test_message}%",)
                )
                row = cursor.fetchone()

                assert row is not None, "Log message not found in database"
                message, level, source = row
                assert test_message in message
                assert level == "INFO"
                assert source == "test_integration"

                conn.close()

        finally:
            # Restore original handlers
            root_logger.handlers = original_handlers

    def test_handler_configured_before_startup_logging(self, mock_environment: Path):
        """Test that SQLiteLogHandler is configured before startup logs are written."""
        from code_indexer.server.app import create_app

        # Clear existing handlers before test
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()

        try:
            app = create_app()

            # Set root logger to INFO level BEFORE TestClient starts (default is WARNING)
            logging.getLogger().setLevel(logging.INFO)

            # Use TestClient as context manager to trigger lifespan
            with TestClient(app) as client:
                # Flush all handlers to ensure logs are written
                for handler in logging.getLogger().handlers:
                    handler.flush()

                # Small delay to ensure SQLite commits are visible
                time.sleep(0.1)

                # Startup logs should be captured
                db_path = mock_environment / "logs.db"
                assert db_path.exists()

                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                # Check for startup-related log messages
                cursor.execute(
                    "SELECT COUNT(*) FROM logs WHERE message LIKE ?",
                    ("%Server startup%",)
                )
                startup_log_count = cursor.fetchone()[0]

                # Should have captured at least some startup logs
                assert startup_log_count > 0, "No startup logs captured in database"

                conn.close()

        finally:
            # Restore original handlers
            root_logger.handlers = original_handlers
