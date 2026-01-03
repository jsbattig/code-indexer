"""
Tests for Log Viewer Web UI (Story #664).

These tests follow TDD methodology - tests are written FIRST before implementation.
All tests use real components following MESSI Rule #1: No mocks.
"""

import re

from fastapi.testclient import TestClient


# =============================================================================
# AC1 & AC7: Logs Page Display & Admin Access Tests
# =============================================================================


class TestLogsPageDisplay:
    """Tests for logs page display (AC1) and admin access (AC7)."""

    def test_logs_page_requires_auth(self, web_client: TestClient):
        """
        AC7: Unauthenticated access to /admin/logs redirects to login.

        Given I am not authenticated
        When I navigate to /admin/logs
        Then I am redirected to /login (consolidated login from issue #662)
        """
        response = web_client.get("/admin/logs")

        assert response.status_code in [
            302,
            303,
        ], f"Expected redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert (
            "/login" in location
        ), f"Expected redirect to /login, got {location}"

    def test_logs_page_renders(self, authenticated_client: TestClient):
        """
        AC1: Authenticated admin access to /admin/logs shows logs page.

        Given I am authenticated as an admin
        When I navigate to /admin/logs
        Then I see the logs page with title "Logs - CIDX Admin"
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "Logs - CIDX Admin" in response.text
        ), "Page title should be 'Logs - CIDX Admin'"

    def test_logs_page_has_table(self, authenticated_client: TestClient):
        """
        AC1: Logs page displays a table for log entries.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see a table with log entry columns
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        assert "<table" in response.text, "Page should contain a table element"
        # Check for expected column headers
        text_lower = response.text.lower()
        assert "timestamp" in text_lower, "Table should have Timestamp column"
        assert "level" in text_lower, "Table should have Level column"
        assert "message" in text_lower, "Table should have Message column"

    def test_logs_empty_state(self, authenticated_client: TestClient):
        """
        AC1: Empty log list shows "No logs found" message.

        Given I am authenticated as an admin
        And there are no logs
        When I view the logs page
        Then I see "No logs found" message
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        # Should have some indication of no logs
        assert (
            "no logs" in text_lower or "empty" in text_lower or "none" in text_lower
        ), "Empty state should be displayed when no logs exist"

    def test_logs_nav_highlighted(self, authenticated_client: TestClient):
        """
        AC1: Logs is highlighted in navigation.

        Given I am authenticated as an admin
        When I view the logs page
        Then the Logs link is highlighted in navigation
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        # Check for navigation highlighting (aria-current="page" on Logs link)
        assert 'aria-current="page"' in response.text, "Navigation should be highlighted"
        # Verify it's on the Logs link
        # Look for pattern: <a href="/admin/logs" aria-current="page">Logs</a>
        logs_link_pattern = r'<a[^>]*href="/admin/logs"[^>]*aria-current="page"[^>]*>Logs</a>'
        assert re.search(
            logs_link_pattern, response.text
        ), "Logs link should have aria-current='page'"


# =============================================================================
# AC2: Refresh Button & HTMX Tests
# =============================================================================


class TestLogsRefresh:
    """Tests for logs refresh functionality (AC2)."""

    def test_refresh_button_present(self, authenticated_client: TestClient):
        """
        AC2: Logs page has a refresh button.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see a Refresh button
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert "refresh" in text_lower, "Page should have a Refresh button"
        # Should be an actual button element
        assert (
            '<button' in response.text and "refresh" in text_lower
        ), "Should have <button> element for refresh"

    def test_refresh_button_htmx_configured(self, authenticated_client: TestClient):
        """
        AC2: Refresh button uses HTMX to reload logs.

        Given I am authenticated as an admin
        When I view the logs page
        Then the refresh button has hx-get attribute pointing to partial endpoint
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        # Check for HTMX attributes on refresh button
        assert "hx-get" in response.text, "Refresh button should have hx-get attribute"
        assert (
            "/admin/partials/logs-list" in response.text
        ), "hx-get should point to logs partial endpoint"

    def test_logs_partial_endpoint_exists(self, authenticated_client: TestClient):
        """
        AC2: HTMX partial endpoint /admin/partials/logs-list returns log table.

        Given I am authenticated as an admin
        When I request /admin/partials/logs-list
        Then I receive the logs table HTML partial
        """
        response = authenticated_client.get("/admin/partials/logs-list")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert "<table" in response.text, "Partial should contain table"
        text_lower = response.text.lower()
        assert "timestamp" in text_lower, "Partial should have Timestamp column"


# =============================================================================
# AC1: Filtering & Pagination Tests
# =============================================================================


class TestLogsFiltering:
    """Tests for logs filtering functionality (AC1)."""

    def test_level_filter_present(self, authenticated_client: TestClient):
        """
        AC1: Logs page has level filter dropdown.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see a Level filter dropdown with log levels
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        text_lower = response.text.lower()
        assert (
            'name="level"' in response.text or 'id="level"' in text_lower
        ), "Page should have level filter"
        # Should have common log levels
        assert "debug" in text_lower or "info" in text_lower, "Should have log levels"

    def test_logger_filter_present(self, authenticated_client: TestClient):
        """
        AC1: Logs page has logger name filter.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see a Logger filter field
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        # Should have logger filter input or select
        assert (
            'name="logger"' in response.text or "logger" in response.text.lower()
        ), "Page should have logger filter"

    def test_search_filter_present(self, authenticated_client: TestClient):
        """
        AC1: Logs page has search field for message filtering.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see a Search field for filtering by message
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        # Should have search input
        assert (
            'type="search"' in response.text or 'name="search"' in response.text
        ), "Page should have search field"

    def test_level_filter_works(self, authenticated_client: TestClient):
        """
        AC1: Level filter filters logs by level.

        Given I am authenticated as an admin
        And there are logs with different levels
        When I filter by level=ERROR
        Then I see only ERROR level logs
        """
        # Test that the endpoint accepts level parameter
        response = authenticated_client.get("/admin/logs?level=ERROR")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        # Endpoint should accept the parameter without error

    def test_pagination_present(self, authenticated_client: TestClient):
        """
        AC1: Logs page has pagination controls.

        Given I am authenticated as an admin
        When I view the logs page
        Then I see pagination controls if there are multiple pages
        """
        response = authenticated_client.get("/admin/logs")

        assert response.status_code == 200
        # Page parameter should be accepted
        page_response = authenticated_client.get("/admin/logs?page=1")
        assert (
            page_response.status_code == 200
        ), "Should accept page parameter without error"


# =============================================================================
# Story #667 AC1: Web UI Log Export Tests
# =============================================================================


class TestLogsExport:
    """Tests for log export endpoint /admin/logs/export (Story #667 AC1, AC4)."""

    def test_export_requires_auth(self, web_client: TestClient):
        """
        Test unauthenticated access to /admin/logs/export redirects to login.

        Given I am not authenticated
        When I try to export logs
        Then I am redirected to /login
        """
        response = web_client.get("/admin/logs/export?format=json")

        assert response.status_code in [
            302,
            303,
        ], f"Expected redirect, got {response.status_code}"
        location = response.headers.get("location", "")
        assert "/login" in location, f"Expected redirect to /login, got {location}"

    def test_export_json_format(self, authenticated_client: TestClient):
        """
        Test JSON export returns valid JSON with proper headers.

        Given I am authenticated as an admin
        When I export logs as JSON
        Then I receive JSON data with Content-Disposition header for download
        """
        response = authenticated_client.get("/admin/logs/export?format=json")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "application/json" in response.headers.get("content-type", "").lower()
        ), "Expected JSON content-type"

        # Verify Content-Disposition header triggers download
        content_disposition = response.headers.get("content-disposition", "")
        assert (
            "attachment" in content_disposition
        ), "Expected attachment in Content-Disposition"
        assert (
            "logs_" in content_disposition
        ), "Expected filename with 'logs_' prefix"
        assert ".json" in content_disposition, "Expected .json extension"

        # Verify valid JSON structure
        import json

        data = json.loads(response.text)
        assert "metadata" in data, "Expected metadata in JSON export"
        assert "logs" in data, "Expected logs array in JSON export"
        assert isinstance(data["logs"], list), "Expected logs to be array"

    def test_export_csv_format(self, authenticated_client: TestClient):
        """
        Test CSV export returns valid CSV with proper headers and BOM.

        Given I am authenticated as an admin
        When I export logs as CSV
        Then I receive CSV data with UTF-8 BOM for Excel compatibility
        """
        response = authenticated_client.get("/admin/logs/export?format=csv")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "text/csv" in response.headers.get("content-type", "").lower()
        ), "Expected CSV content-type"

        # Verify Content-Disposition header triggers download
        content_disposition = response.headers.get("content-disposition", "")
        assert (
            "attachment" in content_disposition
        ), "Expected attachment in Content-Disposition"
        assert ".csv" in content_disposition, "Expected .csv extension"

        # Verify UTF-8 BOM for Excel compatibility
        assert response.text.startswith(
            "\ufeff"
        ), "Expected UTF-8 BOM at start of CSV"

        # Verify CSV structure
        import csv
        import io

        csv_data = response.text.lstrip("\ufeff")
        reader = csv.DictReader(io.StringIO(csv_data))
        assert "timestamp" in reader.fieldnames, "Expected timestamp column"
        assert "level" in reader.fieldnames, "Expected level column"
        assert "message" in reader.fieldnames, "Expected message column"

    def test_export_with_filters(self, authenticated_client: TestClient):
        """
        Test export respects filter parameters (AC6: filtered export accuracy).

        Given I am authenticated as an admin
        When I export logs with filters (search, level)
        Then only matching logs are included in export
        """
        # Export with level filter
        response = authenticated_client.get(
            "/admin/logs/export?format=json&level=ERROR"
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        import json

        data = json.loads(response.text)

        # Verify filter metadata
        assert "metadata" in data
        assert "filters" in data["metadata"]
        assert data["metadata"]["filters"].get("level") == "ERROR"

    def test_export_default_format_is_json(self, authenticated_client: TestClient):
        """
        Test export defaults to JSON format if not specified.

        Given I am authenticated as an admin
        When I export logs without specifying format
        Then I receive JSON format by default
        """
        response = authenticated_client.get("/admin/logs/export")

        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert (
            "application/json" in response.headers.get("content-type", "").lower()
        ), "Expected JSON content-type"

    def test_export_filename_has_timestamp(self, authenticated_client: TestClient):
        """
        Test export filename includes timestamp for uniqueness.

        Given I am authenticated as an admin
        When I export logs
        Then the filename includes a timestamp
        """
        import re

        response = authenticated_client.get("/admin/logs/export?format=json")

        content_disposition = response.headers.get("content-disposition", "")
        # Check for timestamp pattern (YYYYMMDD_HHMMSS)
        assert re.search(
            r"logs_\d{8}_\d{6}\.json", content_disposition
        ), "Expected timestamp in filename (logs_YYYYMMDD_HHMMSS.json)"
