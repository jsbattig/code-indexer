"""Tests for admin_logs_query MCP tool."""

import json
import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from code_indexer.server.mcp.handlers import handle_admin_logs_query
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


class TestAdminLogsQueryPermissions:
    """Test permission requirements for admin_logs_query tool."""

    @pytest.mark.asyncio
    async def test_admin_can_query_logs(self, log_db_path, admin_user, monkeypatch):
        """Test admin user can query logs."""
        # Set log_db_path in app.state
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        insert_test_logs(log_db_path, 5)

        # Query logs
        response = await handle_admin_logs_query({}, admin_user)

        # Verify response structure
        assert "content" in response
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"

        # Parse and verify data
        data = json.loads(response["content"][0]["text"])
        assert "logs" in data
        assert "pagination" in data
        assert len(data["logs"]) == 5

    @pytest.mark.asyncio
    async def test_power_user_cannot_query_logs(self, log_db_path, power_user, monkeypatch):
        """Test power_user cannot query logs (requires admin role)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Attempt to query logs
        response = await handle_admin_logs_query({}, power_user)

        # Verify permission denied
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "permission" in data["error"].lower() or "admin" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_normal_user_cannot_query_logs(self, log_db_path, normal_user, monkeypatch):
        """Test normal_user cannot query logs (requires admin role)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Attempt to query logs
        response = await handle_admin_logs_query({}, normal_user)

        # Verify permission denied
        data = json.loads(response["content"][0]["text"])
        assert data["success"] is False
        assert "permission" in data["error"].lower() or "admin" in data["error"].lower()


class TestAdminLogsQueryPagination:
    """Test pagination functionality."""

    @pytest.mark.asyncio
    async def test_default_pagination(self, log_db_path, admin_user, monkeypatch):
        """Test default pagination (page 1, page_size 50)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 30)

        response = await handle_admin_logs_query({}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 30
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 50
        assert data["pagination"]["total"] == 30
        assert data["pagination"]["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_custom_page_size(self, log_db_path, admin_user, monkeypatch):
        """Test custom page_size parameter."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 30)

        response = await handle_admin_logs_query({"page_size": 10}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 10
        assert data["pagination"]["page_size"] == 10
        assert data["pagination"]["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_second_page(self, log_db_path, admin_user, monkeypatch):
        """Test requesting second page."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 30)

        response = await handle_admin_logs_query({"page": 2, "page_size": 10}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 10
        assert data["pagination"]["page"] == 2
        assert data["pagination"]["total"] == 30


class TestAdminLogsQuerySorting:
    """Test sorting functionality."""

    @pytest.mark.asyncio
    async def test_default_sort_desc(self, log_db_path, admin_user, monkeypatch):
        """Test default sort order is DESC (newest first)."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        response = await handle_admin_logs_query({}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        # Verify timestamps are in descending order (newest first)
        timestamps = [log["timestamp"] for log in data["logs"]]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_asc(self, log_db_path, admin_user, monkeypatch):
        """Test ascending sort order."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        response = await handle_admin_logs_query({"sort_order": "asc"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        # Verify timestamps are in ascending order (oldest first)
        timestamps = [log["timestamp"] for log in data["logs"]]
        assert timestamps == sorted(timestamps)


class TestAdminLogsQueryEmptyDatabase:
    """Test handling of empty database."""

    @pytest.mark.asyncio
    async def test_empty_database_returns_empty_array(self, log_db_path, admin_user, monkeypatch):
        """Test querying empty database returns empty logs array."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        response = await handle_admin_logs_query({}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert data["logs"] == []
        assert data["pagination"]["total"] == 0
        assert data["pagination"]["total_pages"] == 0


class TestAdminLogsQueryResponseFormat:
    """Test MCP response format compliance."""

    @pytest.mark.asyncio
    async def test_mcp_response_structure(self, log_db_path, admin_user, monkeypatch):
        """Test response follows MCP content array format."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 3)

        response = await handle_admin_logs_query({}, admin_user)

        # Verify MCP structure
        assert "content" in response
        assert isinstance(response["content"], list)
        assert len(response["content"]) == 1
        assert response["content"][0]["type"] == "text"
        assert isinstance(response["content"][0]["text"], str)

        # Verify JSON payload structure
        data = json.loads(response["content"][0]["text"])
        assert "success" in data
        assert "logs" in data
        assert "pagination" in data
        assert isinstance(data["logs"], list)
        assert isinstance(data["pagination"], dict)

    @pytest.mark.asyncio
    async def test_log_entry_structure(self, log_db_path, admin_user, monkeypatch):
        """Test individual log entry has all required fields."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 1)

        response = await handle_admin_logs_query({}, admin_user)
        data = json.loads(response["content"][0]["text"])

        log = data["logs"][0]
        assert "id" in log
        assert "timestamp" in log
        assert "level" in log
        assert "source" in log
        assert "message" in log
        assert "correlation_id" in log
        assert "user_id" in log
        assert "request_path" in log


class TestAdminLogsQuerySearch:
    """Test search parameter functionality (AC5 - MCP API filtering)."""

    @pytest.mark.asyncio
    async def test_search_in_message(self, log_db_path, admin_user, monkeypatch):
        """Test search parameter filters logs by message text."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data with distinctive messages
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

        # Search for "authentication"
        response = await handle_admin_logs_query({"search": "authentication"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 1
        assert "authentication" in data["logs"][0]["message"].lower()

    @pytest.mark.asyncio
    async def test_search_in_correlation_id(self, log_db_path, admin_user, monkeypatch):
        """Test search parameter filters logs by correlation_id."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data with distinctive correlation IDs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES
                (?, 'INFO', 'test', 'Request started', 'req-abc-123', 'user1', '/api'),
                (?, 'INFO', 'test', 'Request processing', 'req-xyz-456', 'user2', '/api'),
                (?, 'INFO', 'test', 'Request completed', 'req-abc-123', 'user1', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Search for correlation ID "abc"
        response = await handle_admin_logs_query({"search": "abc"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 2
        for log in data["logs"]:
            assert "abc" in log["correlation_id"]

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, log_db_path, admin_user, monkeypatch):
        """Test search is case-insensitive."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES (?, 'ERROR', 'test', 'Database ERROR occurred', 'corr-1', 'user1', '/api')
        """, (datetime.now(timezone.utc).isoformat(),))
        conn.commit()
        conn.close()

        # Search with lowercase
        response = await handle_admin_logs_query({"search": "error"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 1

    @pytest.mark.asyncio
    async def test_search_no_matches(self, log_db_path, admin_user, monkeypatch):
        """Test search with no matches returns empty results."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        # Search for non-existent term
        response = await handle_admin_logs_query({"search": "nonexistent_xyz_123"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 0
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_search_with_pagination(self, log_db_path, admin_user, monkeypatch):
        """Test search works with pagination."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert multiple matching logs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        for i in range(15):
            cursor.execute("""
                INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
                VALUES (?, 'INFO', 'test', 'Error processing request', ?, 'user1', '/api')
            """, (datetime.now(timezone.utc).isoformat(), f"corr-{i}"))
        conn.commit()
        conn.close()

        # Search with page_size=10
        response = await handle_admin_logs_query({"search": "Error", "page_size": 10}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 10
        assert data["pagination"]["total"] == 15
        assert data["pagination"]["total_pages"] == 2

    @pytest.mark.asyncio
    async def test_search_empty_string(self, log_db_path, admin_user, monkeypatch):
        """Test empty search string returns all logs."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        insert_test_logs(log_db_path, 5)

        # Empty search
        response = await handle_admin_logs_query({"search": ""}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 5


class TestAdminLogsQueryLevelFilter:
    """Test level filtering functionality (AC5 - MCP API filtering)."""

    @pytest.mark.asyncio
    async def test_single_level_filter(self, log_db_path, admin_user, monkeypatch):
        """Test filtering by single log level."""
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
                (?, 'ERROR', 'test', 'Error 2', 'corr-3', 'user1', '/api'),
                (?, 'WARNING', 'test', 'Warning 1', 'corr-4', 'user3', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Filter by ERROR
        response = await handle_admin_logs_query({"level": "ERROR"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 2
        assert all(log["level"] == "ERROR" for log in data["logs"])

    @pytest.mark.asyncio
    async def test_multiple_levels_filter(self, log_db_path, admin_user, monkeypatch):
        """Test filtering by multiple log levels (comma-separated)."""
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
                (?, 'WARNING', 'test', 'Warning 1', 'corr-3', 'user3', '/api'),
                (?, 'DEBUG', 'test', 'Debug 1', 'corr-4', 'user1', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Filter by ERROR,WARNING (comma-separated)
        response = await handle_admin_logs_query({"level": "ERROR,WARNING"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 2
        assert all(log["level"] in ["ERROR", "WARNING"] for log in data["logs"])

    @pytest.mark.asyncio
    async def test_level_filter_no_matches(self, log_db_path, admin_user, monkeypatch):
        """Test level filter with no matches returns empty results."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert only INFO logs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES (?, 'INFO', 'test', 'Info message', 'corr-1', 'user1', '/api')
        """, (datetime.now(timezone.utc).isoformat(),))
        conn.commit()
        conn.close()

        # Filter by ERROR (no matches)
        response = await handle_admin_logs_query({"level": "ERROR"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 0
        assert data["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_level_filter_with_pagination(self, log_db_path, admin_user, monkeypatch):
        """Test level filter works with pagination."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert multiple ERROR logs
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        for i in range(15):
            level = "ERROR" if i < 10 else "INFO"
            cursor.execute("""
                INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
                VALUES (?, ?, 'test', 'Test message', ?, 'user1', '/api')
            """, (datetime.now(timezone.utc).isoformat(), level, f"corr-{i}"))
        conn.commit()
        conn.close()

        # Filter by ERROR with page_size=5
        response = await handle_admin_logs_query({"level": "ERROR", "page_size": 5}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 5
        assert data["pagination"]["total"] == 10
        assert data["pagination"]["total_pages"] == 2


class TestAdminLogsQueryCombinedFilters:
    """Test combined search and level filtering (AC5 - MCP API filtering)."""

    @pytest.mark.asyncio
    async def test_search_and_level_combined(self, log_db_path, admin_user, monkeypatch):
        """Test search and level filters work together (AND logic)."""
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
                (?, 'ERROR', 'test', 'Authentication failed', 'corr-3', 'user3', '/login'),
                (?, 'WARNING', 'test', 'Database slow query', 'corr-4', 'user1', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Search for "database" AND level ERROR
        response = await handle_admin_logs_query({"search": "database", "level": "ERROR"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 1
        assert "database" in data["logs"][0]["message"].lower()
        assert data["logs"][0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_search_and_multiple_levels(self, log_db_path, admin_user, monkeypatch):
        """Test search with multiple level filters."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES
                (?, 'ERROR', 'test', 'Connection timeout', 'corr-1', 'user1', '/api'),
                (?, 'INFO', 'test', 'Connection established', 'corr-2', 'user2', '/api'),
                (?, 'WARNING', 'test', 'Connection slow', 'corr-3', 'user3', '/api'),
                (?, 'DEBUG', 'test', 'Connection details', 'corr-4', 'user1', '/api')
        """, (
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))
        conn.commit()
        conn.close()

        # Search for "connection" AND level ERROR,WARNING
        response = await handle_admin_logs_query({"search": "connection", "level": "ERROR,WARNING"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 2
        assert all("connection" in log["message"].lower() for log in data["logs"])
        assert all(log["level"] in ["ERROR", "WARNING"] for log in data["logs"])

    @pytest.mark.asyncio
    async def test_combined_filters_no_matches(self, log_db_path, admin_user, monkeypatch):
        """Test combined filters with no matches returns empty results."""
        from code_indexer.server import app as app_module
        app_module.app.state.log_db_path = str(log_db_path)

        # Insert test data
        conn = sqlite3.connect(str(log_db_path))
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path)
            VALUES (?, 'INFO', 'test', 'Normal operation', 'corr-1', 'user1', '/api')
        """, (datetime.now(timezone.utc).isoformat(),))
        conn.commit()
        conn.close()

        # Search for "error" AND level ERROR (no matches)
        response = await handle_admin_logs_query({"search": "error", "level": "ERROR"}, admin_user)
        data = json.loads(response["content"][0]["text"])

        assert data["success"] is True
        assert len(data["logs"]) == 0
        assert data["pagination"]["total"] == 0
