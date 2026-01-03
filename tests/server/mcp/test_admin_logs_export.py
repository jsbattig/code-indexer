"""Tests for admin_logs_export MCP tool."""

import json
import csv
import io
import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from code_indexer.server.mcp.handlers import admin_logs_export
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def log_db_path(tmp_path):
    """Create temporary log database for testing."""
    db_path = tmp_path / "test_logs.db"

    # Create database with schema (matching SQLiteLogHandler)
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            level TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            correlation_id TEXT,
            user_id TEXT,
            request_path TEXT
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX idx_timestamp ON logs(timestamp)")
    cursor.execute("CREATE INDEX idx_level ON logs(level)")
    cursor.execute("CREATE INDEX idx_correlation_id ON logs(correlation_id)")
    cursor.execute("CREATE INDEX idx_source ON logs(source)")

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return User(
        username="admin",
        password_hash="fake_hash",
        role=UserRole.ADMIN,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def power_user():
    """Create power user for testing."""
    return User(
        username="power",
        password_hash="fake_hash",
        role=UserRole.POWER_USER,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def normal_user():
    """Create normal user for testing."""
    return User(
        username="normal",
        password_hash="fake_hash",
        role=UserRole.NORMAL_USER,
        created_at=datetime.now(timezone.utc),
    )


def insert_test_logs(db_path: Path, count: int = 10):
    """
    Insert test log entries into database.

    Args:
        db_path: Path to log database
        count: Number of log entries to insert
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    for i in range(count):
        timestamp = datetime.now(timezone.utc).isoformat()
        level = "ERROR" if i % 3 == 0 else "INFO"
        source = f"test.module{i % 3}"
        message = f"Test log message {i}"
        correlation_id = f"corr-{i // 5}"  # Group every 5 logs
        user_id = f"user{i % 2}@example.com"
        request_path = f"/api/test/{i}"

        cursor.execute(
            """
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (timestamp, level, source, message, correlation_id, user_id, request_path)
        )

    conn.commit()
    conn.close()


class TestAdminLogsExportPermissions:
    """Test permission requirements for admin_logs_export tool (AC5)."""

    @pytest.mark.asyncio
    async def test_admin_can_export_logs(self, log_db_path, admin_user, monkeypatch):
        """Test admin user can export logs."""
        # Set log_db_path in app.state
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        insert_test_logs(log_db_path, 5)

        # Export logs
        response = await admin_logs_export({"format": "json"}, admin_user)

        # Verify response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse and verify data
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is True
        assert "format" in data
        assert "count" in data
        assert "data" in data
        assert data["count"] == 5

    @pytest.mark.asyncio
    async def test_power_user_cannot_export_logs(self, log_db_path, power_user, monkeypatch):
        """Test power_user cannot export logs (requires admin role)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Attempt to export logs
        response = await admin_logs_export({"format": "json"}, power_user)

        # Verify permission denied
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "permission" in data["error"].lower() or "admin" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_normal_user_cannot_export_logs(self, log_db_path, normal_user, monkeypatch):
        """Test normal_user cannot export logs (requires admin role)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Attempt to export logs
        response = await admin_logs_export({"format": "json"}, normal_user)

        # Verify permission denied
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "permission" in data["error"].lower() or "admin" in data["error"].lower()


class TestAdminLogsExportJSONFormat:
    """Test JSON export format (AC2)."""

    @pytest.mark.asyncio
    async def test_json_export_structure(self, log_db_path, admin_user, monkeypatch):
        """Test JSON export produces valid JSON with metadata."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 3)

        response = await admin_logs_export({"format": "json"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        # Verify response structure
        assert data["success"] is True
        assert data["format"] == "json"
        assert data["count"] == 3
        assert "data" in data

        # Parse nested JSON data
        export_data = json.loads(data["data"])
        assert "metadata" in export_data
        assert "logs" in export_data
        assert isinstance(export_data["logs"], list)
        assert len(export_data["logs"]) == 3

    @pytest.mark.asyncio
    async def test_json_export_metadata(self, log_db_path, admin_user, monkeypatch):
        """Test JSON export includes metadata with filters and timestamp."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        response = await admin_logs_export({
            "format": "json",
            "search": "test",
            "level": "ERROR"
        }, admin_user)
        data = json.loads(response["content"][0]["text"])
        export_data = json.loads(data["data"])

        # Verify metadata
        assert "exported_at" in export_data["metadata"]
        assert "filters" in export_data["metadata"]
        assert "count" in export_data["metadata"]
        assert export_data["metadata"]["filters"]["search"] == "test"
        assert export_data["metadata"]["filters"]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_json_export_log_structure(self, log_db_path, admin_user, monkeypatch):
        """Test each log entry has all required fields."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 1)

        response = await admin_logs_export({"format": "json"}, admin_user)
        data = json.loads(response["content"][0]["text"])
        export_data = json.loads(data["data"])

        log = export_data["logs"][0]
        assert "id" in log
        assert "timestamp" in log
        assert "level" in log
        assert "source" in log
        assert "message" in log
        assert "correlation_id" in log
        assert "user_id" in log
        assert "request_path" in log


class TestAdminLogsExportCSVFormat:
    """Test CSV export format (AC3)."""

    @pytest.mark.asyncio
    async def test_csv_export_structure(self, log_db_path, admin_user, monkeypatch):
        """Test CSV export produces valid CSV with headers."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 3)

        response = await admin_logs_export({"format": "csv"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        # Verify response structure
        assert data["success"] is True
        assert data["format"] == "csv"
        assert data["count"] == 3
        assert "data" in data

        # Parse CSV data (strip BOM for parsing)
        csv_data = data["data"].lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)

        assert len(rows) == 3
        assert "timestamp" in reader.fieldnames
        assert "level" in reader.fieldnames
        assert "source" in reader.fieldnames
        assert "message" in reader.fieldnames

    @pytest.mark.asyncio
    async def test_csv_export_bom(self, log_db_path, admin_user, monkeypatch):
        """Test CSV export includes UTF-8 BOM for Excel compatibility."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 1)

        response = await admin_logs_export({"format": "csv"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        # Verify BOM at start of CSV
        csv_data = data["data"]
        assert csv_data.startswith('\ufeff')

    @pytest.mark.asyncio
    async def test_csv_export_special_characters(self, log_db_path, admin_user, monkeypatch):
        """Test CSV export properly escapes special characters."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert log with special characters
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES (?, 'ERROR', 'test', 'Message with "quotes" and, commas', 'corr-1', 'user@example.com', '/api')
        """, (datetime.now(timezone.utc).isoformat(),))
        conn.commit()
        conn.close()

        response = await admin_logs_export({"format": "csv"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        # Parse CSV to verify proper escaping (strip BOM for parsing)
        csv_data = data["data"].lstrip('\ufeff')
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)

        assert len(rows) == 1
        assert 'Message with "quotes" and, commas' in rows[0]["message"]


class TestAdminLogsExportFiltering:
    """Test export filtering functionality (AC5 - MCP API filtering)."""

    @pytest.mark.asyncio
    async def test_export_with_search_filter(self, log_db_path, admin_user, monkeypatch):
        """Test export respects search filter."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert mixed logs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES
                (?, 'INFO', 'test', 'User authentication successful', 'corr-1', 'user1', '/login'),
                (?, 'ERROR', 'test', 'Database connection failed', 'corr-2', 'user2', '/api'),
                (?, 'INFO', 'test', 'Password reset requested', 'corr-3', 'user3', '/reset')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Export with search filter
        response = await admin_logs_export({
            "format": "json",
            "search": "authentication"
        }, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["count"] == 1
        export_data = json.loads(data["data"])
        assert len(export_data["logs"]) == 1
        assert "authentication" in export_data["logs"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_export_with_level_filter(self, log_db_path, admin_user, monkeypatch):
        """Test export respects level filter."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert mixed level logs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES
                (?, 'ERROR', 'test', 'Error 1', 'corr-1', 'user1', '/api'),
                (?, 'INFO', 'test', 'Info 1', 'corr-2', 'user2', '/api'),
                (?, 'ERROR', 'test', 'Error 2', 'corr-3', 'user1', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Export with level filter
        response = await admin_logs_export({
            "format": "json",
            "level": "ERROR"
        }, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["count"] == 2
        export_data = json.loads(data["data"])
        assert all(log["level"] == "ERROR" for log in export_data["logs"])

    @pytest.mark.asyncio
    async def test_export_with_combined_filters(self, log_db_path, admin_user, monkeypatch):
        """Test export with multiple filters (AC6 - filtered export accuracy)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES
                (?, 'ERROR', 'test', 'Database error occurred', 'corr-1', 'user1', '/api'),
                (?, 'INFO', 'test', 'Database connection successful', 'corr-2', 'user2', '/api'),
                (?, 'ERROR', 'test', 'Authentication failed', 'corr-3', 'user3', '/login')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Export with combined filters
        response = await admin_logs_export({
            "format": "json",
            "search": "database",
            "level": "ERROR"
        }, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["count"] == 1
        export_data = json.loads(data["data"])
        assert len(export_data["logs"]) == 1
        assert "database" in export_data["logs"][0]["message"].lower()
        assert export_data["logs"][0]["level"] == "ERROR"


class TestAdminLogsExportEmptyResults:
    """Test export with empty results."""

    @pytest.mark.asyncio
    async def test_export_empty_database(self, log_db_path, admin_user, monkeypatch):
        """Test export of empty database returns valid empty export."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        response = await admin_logs_export({"format": "json"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["count"] == 0
        export_data = json.loads(data["data"])
        assert export_data["logs"] == []

    @pytest.mark.asyncio
    async def test_export_no_matches(self, log_db_path, admin_user, monkeypatch):
        """Test export with filters that match nothing."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        response = await admin_logs_export({
            "format": "json",
            "search": "nonexistent_xyz_123"
        }, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["count"] == 0


class TestAdminLogsExportMCPCompliance:
    """Test MCP response format compliance."""

    @pytest.mark.asyncio
    async def test_mcp_response_structure(self, log_db_path, admin_user, monkeypatch):
        """Test response follows MCP content array format."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 3)

        response = await admin_logs_export({"format": "json"}, admin_user)

        # Verify MCP structure
        assert "content" in response
        assert isinstance(response["content"], list)
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"
        assert isinstance(response["content"][0]["text"], str)

        # Verify JSON payload structure
        data = json.loads(response["content"][0]["text"])
        assert "success" in data
        assert "format" in data
        assert "count" in data
        assert "data" in data
        assert "filters" in data
