"""
Tests for /admin/api/logs/export REST API endpoint (Story #667 AC4).

TDD tests written FIRST before implementation.

Verifies:
- Admin authentication requirement
- Format parameter (json/csv)
- Filter parameters (search, level, correlation_id)
- Content-Type and Content-Disposition headers
- File download functionality
- Filter accuracy
"""

import pytest
import tempfile
import os
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.auth.dependencies import get_current_user


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def populated_db(temp_db):
    """Populate database with test logs."""
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Create logs table first
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level TEXT,
            source TEXT,
            message TEXT,
            correlation_id TEXT,
            user_id TEXT,
            request_path TEXT,
            extra_data TEXT
        )
    """)

    test_logs = [
        {
            "timestamp": datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
            "level": "INFO",
            "message": "Server started",
            "source": "server",
            "correlation_id": "corr-001",
            "user_id": "admin",
            "request_path": "/",
            "extra_data": "{}",
        },
        {
            "timestamp": datetime(2025, 1, 1, 10, 5, 0, tzinfo=timezone.utc).isoformat(),
            "level": "WARNING",
            "message": "High memory usage",
            "source": "monitor",
            "correlation_id": "corr-002",
            "user_id": None,
            "request_path": None,
            "extra_data": "{}",
        },
        {
            "timestamp": datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc).isoformat(),
            "level": "ERROR",
            "message": "Connection failed",
            "source": "network",
            "correlation_id": "corr-003",
            "user_id": "admin",
            "request_path": "/api",
            "extra_data": "{}",
        },
        {
            "timestamp": datetime(2025, 1, 1, 10, 15, 0, tzinfo=timezone.utc).isoformat(),
            "level": "ERROR",
            "message": "Database error",
            "source": "database",
            "correlation_id": "corr-004",
            "user_id": None,
            "request_path": None,
            "extra_data": "{}",
        },
    ]

    # Insert test logs
    for log in test_logs:
        cursor.execute(
            """
            INSERT INTO logs (timestamp, level, source, message, correlation_id, user_id, request_path, extra_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log["timestamp"],
                log["level"],
                log["source"],
                log["message"],
                log["correlation_id"],
                log["user_id"],
                log["request_path"],
                log["extra_data"],
            ),
        )

    conn.commit()
    conn.close()

    return temp_db


@pytest.fixture
def test_app_admin(populated_db):
    """Create test app with admin user authentication."""
    from code_indexer.server.routes.admin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.log_db_path = populated_db

    # Override auth dependency to return admin user
    def override_get_current_user():
        return User(
            username="admin",
            password_hash="dummy_hash",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    return TestClient(app)


@pytest.fixture
def test_app_user(populated_db):
    """Create test app with regular user authentication."""
    from code_indexer.server.routes.admin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.log_db_path = populated_db

    # Override auth dependency to return regular user
    def override_get_current_user():
        return User(
            username="user",
            password_hash="dummy_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    app.dependency_overrides[get_current_user] = override_get_current_user

    return TestClient(app)


class TestAdminApiLogsExportAuthentication:
    """Test authentication for export endpoint."""

    def test_requires_admin_role(self, test_app_user):
        """Export endpoint requires admin role."""
        response = test_app_user.get("/admin/api/logs/export")
        assert response.status_code == 403

    def test_allows_admin_access(self, test_app_admin):
        """Export endpoint allows admin users."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")
        assert response.status_code == 200


class TestAdminApiLogsExportJSON:
    """Test JSON export format."""

    def test_json_export_returns_json_content_type(self, test_app_admin):
        """JSON export returns application/json content type."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")

        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_json_export_returns_content_disposition_header(self, test_app_admin):
        """JSON export returns Content-Disposition header for file download."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")

        assert "content-disposition" in response.headers
        assert "attachment" in response.headers["content-disposition"]
        assert ".json" in response.headers["content-disposition"]

    def test_json_export_returns_valid_json(self, test_app_admin):
        """JSON export returns valid parseable JSON."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")

        # Should be valid JSON
        data = response.json()
        assert isinstance(data, dict)

    def test_json_export_includes_metadata(self, test_app_admin):
        """JSON export includes metadata header."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")
        data = response.json()

        assert "metadata" in data
        assert "exported_at" in data["metadata"]
        assert "filters" in data["metadata"]
        assert "count" in data["metadata"]

    def test_json_export_includes_logs_array(self, test_app_admin):
        """JSON export includes logs array."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")
        data = response.json()

        assert "logs" in data
        assert isinstance(data["logs"], list)
        assert len(data["logs"]) == 4  # All 4 test logs

    def test_json_export_log_entries_have_all_fields(self, test_app_admin):
        """JSON export log entries have all required fields."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")
        data = response.json()

        log_entry = data["logs"][0]
        assert "timestamp" in log_entry
        assert "level" in log_entry
        assert "source" in log_entry
        assert "message" in log_entry
        assert "correlation_id" in log_entry
        assert "user_id" in log_entry
        assert "request_path" in log_entry


class TestAdminApiLogsExportCSV:
    """Test CSV export format."""

    def test_csv_export_returns_csv_content_type(self, test_app_admin):
        """CSV export returns text/csv content type."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

    def test_csv_export_returns_content_disposition_header(self, test_app_admin):
        """CSV export returns Content-Disposition header for file download."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv")

        assert "content-disposition" in response.headers
        assert "attachment" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

    def test_csv_export_has_header_row(self, test_app_admin):
        """CSV export has header row with column names."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv")
        content = response.text

        lines = content.strip().split("\n")
        header = lines[0]

        # Remove BOM if present
        if header.startswith("\ufeff"):
            header = header[1:]

        assert "timestamp" in header
        assert "level" in header
        assert "source" in header
        assert "message" in header

    def test_csv_export_includes_utf8_bom(self, test_app_admin):
        """CSV export includes UTF-8 BOM for Excel compatibility."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv")
        content = response.text

        # Should start with UTF-8 BOM
        assert content.startswith("\ufeff")

    def test_csv_export_has_data_rows(self, test_app_admin):
        """CSV export has data rows for all logs."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv")
        content = response.text

        lines = content.strip().split("\n")
        # Should have header + 4 data rows
        assert len(lines) == 5


class TestAdminApiLogsExportFilters:
    """Test filter parameters."""

    def test_export_respects_search_filter(self, test_app_admin):
        """Export respects search parameter."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&search=Connection")
        data = response.json()

        # Should only return logs matching "Connection"
        assert data["metadata"]["count"] == 1
        assert len(data["logs"]) == 1
        assert "Connection" in data["logs"][0]["message"]

    def test_export_respects_level_filter(self, test_app_admin):
        """Export respects level parameter."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&level=ERROR")
        data = response.json()

        # Should only return ERROR logs (2 in fixture)
        assert data["metadata"]["count"] == 2
        assert len(data["logs"]) == 2
        for log in data["logs"]:
            assert log["level"] == "ERROR"

    def test_export_respects_correlation_id_filter(self, test_app_admin):
        """Export respects correlation_id parameter."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&correlation_id=corr-001")
        data = response.json()

        # Should only return log with correlation_id="corr-001"
        assert data["metadata"]["count"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["correlation_id"] == "corr-001"

    def test_export_combines_multiple_filters(self, test_app_admin):
        """Export combines multiple filters with AND logic."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&level=ERROR&search=Database")
        data = response.json()

        # Should return ERROR logs containing "Database" (1 log)
        assert data["metadata"]["count"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["level"] == "ERROR"
        assert "Database" in data["logs"][0]["message"]

    def test_export_includes_filter_metadata(self, test_app_admin):
        """Export includes applied filters in metadata."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&level=ERROR&search=Database")
        data = response.json()

        # Metadata should include filters
        assert "filters" in data["metadata"]
        assert data["metadata"]["filters"]["level"] == "ERROR"
        assert data["metadata"]["filters"]["search"] == "Database"


class TestAdminApiLogsExportFilename:
    """Test filename generation."""

    def test_filename_includes_timestamp(self, test_app_admin):
        """Filename includes timestamp in YYYYMMDD_HHMMSS format."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")

        filename = response.headers["content-disposition"]
        # Should match pattern: logs_YYYYMMDD_HHMMSS.json
        assert "logs_" in filename
        assert ".json" in filename

    def test_filename_matches_format(self, test_app_admin):
        """Filename extension matches requested format."""
        # JSON format
        response_json = test_app_admin.get("/admin/api/logs/export?format=json")
        assert ".json" in response_json.headers["content-disposition"]

        # CSV format
        response_csv = test_app_admin.get("/admin/api/logs/export?format=csv")
        assert ".csv" in response_csv.headers["content-disposition"]


class TestAdminApiLogsExportDefaults:
    """Test default parameters."""

    def test_default_format_is_json(self, test_app_admin):
        """Default export format is JSON."""
        response = test_app_admin.get("/admin/api/logs/export")

        assert "application/json" in response.headers["content-type"]

    def test_export_without_filters_returns_all_logs(self, test_app_admin):
        """Export without filters returns all logs."""
        response = test_app_admin.get("/admin/api/logs/export?format=json")
        data = response.json()

        # Should return all 4 test logs
        assert data["metadata"]["count"] == 4
        assert len(data["logs"]) == 4


class TestAdminApiLogsExportEmptyResults:
    """Test empty result handling."""

    def test_export_with_no_matches_returns_empty(self, test_app_admin):
        """Export with no matching logs returns empty results."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&search=nonexistent")
        data = response.json()

        assert data["metadata"]["count"] == 0
        assert len(data["logs"]) == 0

    def test_empty_json_export_is_valid_json(self, test_app_admin):
        """Empty JSON export is still valid JSON."""
        response = test_app_admin.get("/admin/api/logs/export?format=json&search=nonexistent")

        # Should be valid JSON with empty logs array
        data = response.json()
        assert isinstance(data, dict)
        assert data["logs"] == []

    def test_empty_csv_export_has_header(self, test_app_admin):
        """Empty CSV export still has header row."""
        response = test_app_admin.get("/admin/api/logs/export?format=csv&search=nonexistent")
        content = response.text

        lines = content.strip().split("\n")
        # Should have only header row (no data rows)
        assert len(lines) == 1
        header = lines[0]
        if header.startswith("\ufeff"):
            header = header[1:]
        assert "timestamp" in header
