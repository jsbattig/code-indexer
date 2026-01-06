"""
Unit tests for SQLiteLogHandler - logging.Handler that writes to SQLite database.

TDD Red Phase: These tests will fail until SQLiteLogHandler is implemented.

Test Coverage:
- AC5: SQLite Log Storage Infrastructure
  - Handler correctly writes log records to database
  - Handler handles concurrent writes safely
  - Database schema matches requirements
  - Indexes are created properly
  - Thread-safe writes work correctly
"""

import logging
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Generator

import pytest

from code_indexer.server.services.sqlite_log_handler import SQLiteLogHandler


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Create a temporary database file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_logs.db"
        yield db_path


@pytest.fixture
def log_handler(temp_db_path: Path) -> Generator[SQLiteLogHandler, None, None]:
    """Create a SQLiteLogHandler instance for testing."""
    handler = SQLiteLogHandler(temp_db_path)
    yield handler
    handler.close()


class TestSQLiteLogHandlerBasics:
    """Test basic SQLiteLogHandler functionality."""

    def test_handler_creates_database_file(self, temp_db_path: Path):
        """Test that handler creates database file if it doesn't exist."""
        assert not temp_db_path.exists()

        handler = SQLiteLogHandler(temp_db_path)
        handler.close()

        assert temp_db_path.exists()

    def test_handler_creates_logs_table(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler creates logs table with correct schema."""
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()

        # Check table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='logs'")
        assert cursor.fetchone() is not None

        # Check schema
        cursor.execute("PRAGMA table_info(logs)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        # Required columns from AC5
        assert "id" in columns
        assert "timestamp" in columns
        assert "level" in columns
        assert "source" in columns
        assert "message" in columns
        assert "correlation_id" in columns
        assert "user_id" in columns
        assert "request_path" in columns
        assert "extra_data" in columns
        assert "created_at" in columns

        conn.close()

    def test_handler_creates_required_indexes(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler creates required indexes from AC5."""
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()

        # Get all indexes on logs table
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='logs'")
        indexes = {row[0] for row in cursor.fetchall()}

        # Required indexes from AC5
        assert "idx_logs_timestamp" in indexes
        assert "idx_logs_level" in indexes
        assert "idx_logs_correlation_id" in indexes
        assert "idx_logs_source" in indexes

        conn.close()


class TestSQLiteLogHandlerWriting:
    """Test log record writing functionality."""

    def test_handler_writes_simple_log_record(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler writes a simple log record to database."""
        # Create logger and attach handler
        logger = logging.getLogger("test.simple")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        # Log a message
        logger.info("Test message")

        # Verify record in database
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT level, source, message FROM logs")
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "INFO"
        assert row[1] == "test.simple"
        assert row[2] == "Test message"

        conn.close()

    def test_handler_writes_log_with_extra_fields(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler writes log records with extra fields (correlation_id, user_id, request_path)."""
        logger = logging.getLogger("test.extra")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        # Log with extra fields
        logger.info(
            "User action",
            extra={
                "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
                "user_id": "admin@example.com",
                "request_path": "/admin/logs"
            }
        )

        # Verify all fields in database
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT level, source, message, correlation_id, user_id, request_path FROM logs"
        )
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == "INFO"
        assert row[1] == "test.extra"
        assert row[2] == "User action"
        assert row[3] == "550e8400-e29b-41d4-a716-446655440000"
        assert row[4] == "admin@example.com"
        assert row[5] == "/admin/logs"

        conn.close()

    def test_handler_stores_timestamp_correctly(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler stores timestamp in ISO 8601 format."""
        logger = logging.getLogger("test.timestamp")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        time.time()
        logger.info("Timestamped message")
        time.time()

        # Verify timestamp is within expected range
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM logs")
        row = cursor.fetchone()

        assert row is not None
        timestamp_str = row[0]

        # Verify ISO 8601 format (basic check)
        assert "T" in timestamp_str
        assert timestamp_str.endswith("Z") or "+" in timestamp_str or "-" in timestamp_str[-6:]

        conn.close()

    def test_handler_handles_different_log_levels(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler correctly stores different log levels."""
        logger = logging.getLogger("test.levels")
        logger.addHandler(log_handler)
        logger.setLevel(logging.DEBUG)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

        # Verify all levels stored
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT level, message FROM logs ORDER BY id")
        rows = cursor.fetchall()

        assert len(rows) == 5
        assert rows[0] == ("DEBUG", "Debug message")
        assert rows[1] == ("INFO", "Info message")
        assert rows[2] == ("WARNING", "Warning message")
        assert rows[3] == ("ERROR", "Error message")
        assert rows[4] == ("CRITICAL", "Critical message")

        conn.close()


class TestSQLiteLogHandlerConcurrency:
    """Test thread-safe concurrent writes (AC5 requirement)."""

    def test_handler_handles_concurrent_writes(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler safely handles concurrent writes from multiple threads."""
        logger = logging.getLogger("test.concurrent")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        num_threads = 10
        logs_per_thread = 20

        def log_messages(thread_id: int):
            for i in range(logs_per_thread):
                logger.info(f"Thread {thread_id} message {i}")

        # Spawn threads
        threads = []
        for thread_id in range(num_threads):
            thread = threading.Thread(target=log_messages, args=(thread_id,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Verify all logs written
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM logs")
        count = cursor.fetchone()[0]

        assert count == num_threads * logs_per_thread

        conn.close()

    def test_handler_maintains_data_integrity_under_concurrency(
        self, log_handler: SQLiteLogHandler, temp_db_path: Path
    ):
        """Test that concurrent writes don't corrupt data."""
        logger = logging.getLogger("test.integrity")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        def log_with_correlation(thread_id: int):
            for i in range(10):
                logger.info(
                    f"Thread {thread_id} message {i}",
                    extra={
                        "correlation_id": f"corr-{thread_id}-{i}",
                        "user_id": f"user{thread_id}"
                    }
                )

        threads = []
        for thread_id in range(5):
            thread = threading.Thread(target=log_with_correlation, args=(thread_id,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify data integrity
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT correlation_id, user_id, message FROM logs")
        rows = cursor.fetchall()

        # Check that all correlation IDs match expected pattern
        for row in rows:
            corr_id, user_id, message = row
            # Extract thread_id from correlation_id
            if corr_id:
                assert corr_id.startswith("corr-")
                thread_id = corr_id.split("-")[1]
                # Verify user_id matches thread_id
                assert user_id == f"user{thread_id}"

        conn.close()


class TestSQLiteLogHandlerExtraData:
    """Test handling of extra_data field for arbitrary key-value pairs."""

    def test_handler_stores_extra_data_as_json(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler stores arbitrary extra data as JSON."""
        logger = logging.getLogger("test.extra_data")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        # Log with extra data
        logger.info(
            "Event with metadata",
            extra={
                "correlation_id": "test-123",
                "custom_field1": "value1",
                "custom_field2": 42,
                "custom_field3": {"nested": "data"}
            }
        )

        # Verify extra_data stored as JSON
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT extra_data FROM logs")
        row = cursor.fetchone()

        assert row is not None
        extra_data = row[0]

        # Should be JSON string
        import json
        parsed = json.loads(extra_data)
        assert parsed["custom_field1"] == "value1"
        assert parsed["custom_field2"] == 42
        assert parsed["custom_field3"] == {"nested": "data"}

        conn.close()


class TestSQLiteLogHandlerEdgeCases:
    """Test edge cases and error handling."""

    def test_handler_handles_very_long_messages(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler can store very long log messages."""
        logger = logging.getLogger("test.long")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        long_message = "A" * 10000  # 10KB message
        logger.info(long_message)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT message FROM logs")
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == long_message

        conn.close()

    def test_handler_handles_null_extra_fields(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler handles missing extra fields gracefully."""
        logger = logging.getLogger("test.nulls")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        # Log without any extra fields
        logger.info("Simple message")

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT correlation_id, user_id, request_path FROM logs")
        row = cursor.fetchone()

        assert row is not None
        # All extra fields should be NULL
        assert row[0] is None  # correlation_id
        assert row[1] is None  # user_id
        assert row[2] is None  # request_path

        conn.close()

    def test_handler_handles_unicode_messages(self, log_handler: SQLiteLogHandler, temp_db_path: Path):
        """Test that handler correctly stores Unicode messages."""
        logger = logging.getLogger("test.unicode")
        logger.addHandler(log_handler)
        logger.setLevel(logging.INFO)

        unicode_message = "Test 你好 мир 🌍"
        logger.info(unicode_message)

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT message FROM logs")
        row = cursor.fetchone()

        assert row is not None
        assert row[0] == unicode_message

        conn.close()
