"""
Tests for /admin/api/logs REST API endpoint.

TDD tests written FIRST before implementation.

Verifies:
- Admin authentication requirement
- Query parameters: page, page_size, sort_order
- JSON response format with logs array + pagination
- Integration with LogAggregatorService
"""

import pytest
import tempfile
import os
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.auth.dependencies import get_current_user
from code_indexer.server.services.sqlite_log_handler import SQLiteLogHandler


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
def log_handler(temp_db):
    """Create SQLiteLogHandler with temp database."""
    return SQLiteLogHandler(temp_db)


@pytest.fixture
def populated_log_handler(log_handler, temp_db):
    """SQLiteLogHandler with sample logs."""
    import sqlite3
    import json

    test_logs = [
        {
            "timestamp": datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
            "level": "INFO",
            "message": "Server started",
            "source": "server",
            "correlation_id": "corr-001",
            "extra_data": json.dumps({"version": "1.0"}),
        },
        {
            "timestamp": datetime(2025, 1, 1, 10, 5, 0, tzinfo=timezone.utc).isoformat(),
            "level": "WARNING",
            "message": "High memory usage",
            "source": "monitor",
            "correlation_id": "corr-002",
            "extra_data": json.dumps({"memory_mb": 512}),
        },
        {
            "timestamp": datetime(2025, 1, 1, 10, 10, 0, tzinfo=timezone.utc).isoformat(),
            "level": "ERROR",
            "message": "Connection failed",
            "source": "network",
            "correlation_id": "corr-003",
            "extra_data": json.dumps({"host": "example.com"}),
        },
    ]

    # Write logs directly to database
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    for log in test_logs:
        cursor.execute(
            """
            INSERT INTO logs (timestamp, level, source, message, correlation_id, extra_data)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                log["timestamp"],
                log["level"],
                log["source"],
                log["message"],
                log["correlation_id"],
                log["extra_data"],
            ),
        )

    conn.commit()
    conn.close()

    return log_handler


@pytest.fixture
def test_app_admin(temp_db, populated_log_handler):
    """Create test app with admin user authentication."""
    # Import admin API router (to be created)
    from code_indexer.server.routes.admin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")

    # Store log DB path in app state for route to access
    app.state.log_db_path = temp_db

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
def test_app_user(temp_db, populated_log_handler):
    """Create test app with regular user authentication."""
    from code_indexer.server.routes.admin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.log_db_path = temp_db

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


@pytest.fixture
def test_app_unauthenticated(temp_db, populated_log_handler):
    """Create test app without authentication."""
    from code_indexer.server.routes.admin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/admin/api")
    app.state.log_db_path = temp_db

    # No auth override - endpoint should reject

    return TestClient(app)


class TestAdminApiLogsAuthentication:
    """Test admin authentication for /admin/api/logs endpoint."""

    def test_requires_authentication(self, test_app_unauthenticated):
        """Endpoint requires authentication."""
        response = test_app_unauthenticated.get("/admin/api/logs")
        assert response.status_code == 401

    def test_requires_admin_role(self, test_app_user):
        """Endpoint requires admin role, rejects regular users."""
        response = test_app_user.get("/admin/api/logs")
        assert response.status_code == 403

    def test_allows_admin_access(self, test_app_admin):
        """Endpoint allows admin users."""
        response = test_app_admin.get("/admin/api/logs")
        assert response.status_code == 200


class TestAdminApiLogsBasicQuery:
    """Test basic query functionality."""

    def test_returns_json_response(self, test_app_admin):
        """Returns JSON response."""
        response = test_app_admin.get("/admin/api/logs")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

    def test_response_structure(self, test_app_admin):
        """Response has correct structure: logs array + pagination."""
        response = test_app_admin.get("/admin/api/logs")
        data = response.json()

        assert "logs" in data
        assert isinstance(data["logs"], list)
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "page_size" in data["pagination"]
        assert "total_count" in data["pagination"]
        assert "total_pages" in data["pagination"]

    def test_returns_all_logs_default(self, test_app_admin):
        """Returns all logs with default parameters."""
        response = test_app_admin.get("/admin/api/logs")
        data = response.json()

        # Should have 3 sample logs
        assert len(data["logs"]) == 3
        assert data["pagination"]["total_count"] == 3

    def test_log_entry_structure(self, test_app_admin):
        """Log entries have correct structure."""
        response = test_app_admin.get("/admin/api/logs")
        data = response.json()

        log = data["logs"][0]
        assert "timestamp" in log
        assert "level" in log
        assert "message" in log
        assert "source" in log
        assert "correlation_id" in log
        assert "metadata" in log


class TestAdminApiLogsPagination:
    """Test pagination parameters."""

    def test_page_parameter(self, test_app_admin):
        """Page parameter controls which page of results."""
        # Get first page
        response1 = test_app_admin.get("/admin/api/logs?page=1&page_size=2")
        data1 = response1.json()

        # Get second page
        response2 = test_app_admin.get("/admin/api/logs?page=2&page_size=2")
        data2 = response2.json()

        # Different logs on each page
        assert len(data1["logs"]) == 2
        assert len(data2["logs"]) == 1
        assert data1["logs"][0]["correlation_id"] != data2["logs"][0]["correlation_id"]

    def test_page_size_parameter(self, test_app_admin):
        """Page size parameter controls results per page."""
        response = test_app_admin.get("/admin/api/logs?page_size=2")
        data = response.json()

        assert len(data["logs"]) == 2
        assert data["pagination"]["page_size"] == 2

    def test_pagination_metadata(self, test_app_admin):
        """Pagination metadata is correct."""
        response = test_app_admin.get("/admin/api/logs?page=1&page_size=2")
        data = response.json()

        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2
        assert data["pagination"]["total_count"] == 3
        assert data["pagination"]["total_pages"] == 2


class TestAdminApiLogsSorting:
    """Test sort_order parameter."""

    def test_desc_sort_order_default(self, test_app_admin):
        """Default sort order is DESC (newest first)."""
        response = test_app_admin.get("/admin/api/logs")
        data = response.json()

        # Newest log should be first
        assert data["logs"][0]["message"] == "Connection failed"
        assert data["logs"][-1]["message"] == "Server started"

    def test_asc_sort_order(self, test_app_admin):
        """ASC sort order returns oldest first."""
        response = test_app_admin.get("/admin/api/logs?sort_order=asc")
        data = response.json()

        # Oldest log should be first
        assert data["logs"][0]["message"] == "Server started"
        assert data["logs"][-1]["message"] == "Connection failed"

    def test_invalid_sort_order(self, test_app_admin):
        """Invalid sort_order returns error."""
        response = test_app_admin.get("/admin/api/logs?sort_order=invalid")
        assert response.status_code == 422  # Validation error


class TestAdminApiLogsEmptyDatabase:
    """Test behavior with empty database."""

    def test_empty_database_returns_empty_list(self, temp_db):
        """Empty database returns empty logs array."""
        from code_indexer.server.routes.admin_api import router

        app = FastAPI()
        app.include_router(router, prefix="/admin/api")
        app.state.log_db_path = temp_db

        # Override auth for admin
        def override_get_current_user():
            return User(
                username="admin",
                password_hash="dummy_hash",
                role=UserRole.ADMIN,
                created_at=datetime.now(timezone.utc),
            )

        app.dependency_overrides[get_current_user] = override_get_current_user

        client = TestClient(app)
        response = client.get("/admin/api/logs")
        data = response.json()

        assert len(data["logs"]) == 0
        assert data["pagination"]["total_count"] == 0
        assert data["pagination"]["total_pages"] == 0


class TestAdminApiLogsSearch:
    """Test search query parameter (Story #665 AC4)."""

    def test_search_by_message_content(self, test_app_admin):
        """Search parameter filters logs by message content."""
        response = test_app_admin.get("/admin/api/logs?search=Connection")
        data = response.json()

        # Should find only the "Connection failed" log
        assert len(data["logs"]) == 1
        assert "Connection" in data["logs"][0]["message"]

    def test_search_by_correlation_id(self, test_app_admin):
        """Search parameter filters logs by correlation_id."""
        response = test_app_admin.get("/admin/api/logs?search=corr-002")
        data = response.json()

        # Should find the log with correlation_id="corr-002"
        assert len(data["logs"]) == 1
        assert data["logs"][0]["correlation_id"] == "corr-002"

    def test_search_is_case_insensitive(self, test_app_admin):
        """Search is case-insensitive."""
        # Search with uppercase
        response_upper = test_app_admin.get("/admin/api/logs?search=CONNECTION")
        data_upper = response_upper.json()

        # Search with lowercase
        response_lower = test_app_admin.get("/admin/api/logs?search=connection")
        data_lower = response_lower.json()

        # Should return same results
        assert len(data_upper["logs"]) == len(data_lower["logs"])
        assert len(data_upper["logs"]) == 1

    def test_search_partial_match(self, test_app_admin):
        """Search matches partial strings."""
        response = test_app_admin.get("/admin/api/logs?search=memory")
        data = response.json()

        # Should find "High memory usage" log
        assert len(data["logs"]) == 1
        assert "memory" in data["logs"][0]["message"].lower()

    def test_search_no_matches_returns_empty(self, test_app_admin):
        """Search with no matches returns empty results."""
        response = test_app_admin.get("/admin/api/logs?search=nonexistent")
        data = response.json()

        assert len(data["logs"]) == 0
        assert data["pagination"]["total_count"] == 0

    def test_search_combines_with_pagination(self, test_app_admin):
        """Search works with pagination parameters."""
        response = test_app_admin.get("/admin/api/logs?search=corr&page=1&page_size=2")
        data = response.json()

        # Should have pagination metadata
        assert "pagination" in data
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2


class TestAdminApiLogsLevelFiltering:
    """Test level query parameter for filtering (Story #665 AC4)."""

    def test_filter_by_single_level(self, test_app_admin):
        """Level parameter filters by single log level."""
        response = test_app_admin.get("/admin/api/logs?level=ERROR")
        data = response.json()

        # Should find only ERROR log
        assert len(data["logs"]) == 1
        assert data["logs"][0]["level"] == "ERROR"

    def test_filter_by_multiple_levels_comma_separated(self, test_app_admin):
        """Level parameter supports comma-separated multiple levels."""
        response = test_app_admin.get("/admin/api/logs?level=WARNING,ERROR")
        data = response.json()

        # Should find WARNING and ERROR logs
        assert len(data["logs"]) == 2
        levels = {log["level"] for log in data["logs"]}
        assert levels == {"WARNING", "ERROR"}

    def test_filter_by_level_case_sensitive(self, test_app_admin):
        """Level filtering is case-sensitive."""
        response = test_app_admin.get("/admin/api/logs?level=error")
        data = response.json()

        # Should not match (levels are uppercase in DB)
        assert len(data["logs"]) == 0

    def test_filter_by_info_level(self, test_app_admin):
        """Can filter by INFO level."""
        response = test_app_admin.get("/admin/api/logs?level=INFO")
        data = response.json()

        assert len(data["logs"]) == 1
        assert data["logs"][0]["level"] == "INFO"


class TestAdminApiLogsCombinedFilters:
    """Test combining search and level filters (Story #665 AC3, AC4)."""

    def test_search_and_level_combined(self, test_app_admin):
        """Search and level filters combine with AND logic."""
        # Search for "failed" AND level=ERROR
        response = test_app_admin.get("/admin/api/logs?search=failed&level=ERROR")
        data = response.json()

        # Should find only ERROR logs containing "failed"
        assert len(data["logs"]) == 1
        assert data["logs"][0]["level"] == "ERROR"
        assert "failed" in data["logs"][0]["message"].lower()

    def test_search_and_multiple_levels(self, test_app_admin):
        """Search combines with multiple level filter."""
        # Search for "usage" AND level in (INFO, WARNING)
        response = test_app_admin.get("/admin/api/logs?search=usage&level=INFO,WARNING")
        data = response.json()

        # Should find WARNING log with "usage"
        assert len(data["logs"]) == 1
        assert data["logs"][0]["level"] == "WARNING"
        assert "usage" in data["logs"][0]["message"].lower()

    def test_filters_with_pagination(self, test_app_admin):
        """Filters work correctly with pagination."""
        response = test_app_admin.get(
            "/admin/api/logs?search=corr&level=INFO,WARNING&page=1&page_size=5"
        )
        data = response.json()

        # Should have proper pagination with filtered results
        assert "pagination" in data
        assert data["pagination"]["total_count"] <= 2  # At most 2 matching logs
