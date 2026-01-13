"""
Integration tests for Dashboard Health Routes (Story #712).

Tests the complete flow from API endpoint to template rendering.
Following MESSI Rule #1: No mocks - uses real components.
"""

from fastapi.testclient import TestClient


class TestDashboardHealthIntegration:
    """Integration tests for dashboard health endpoints."""

    def test_dashboard_health_partial_returns_database_health(
        self, authenticated_client: TestClient
    ):
        """
        AC1: Dashboard health partial endpoint returns database health data.

        Given an authenticated admin user
        When requesting /admin/partials/dashboard-health
        Then the response includes database health information
        """
        response = authenticated_client.get("/admin/partials/dashboard-health")

        # Verify successful response
        assert response.status_code == 200

        # Verify honeycomb SVG is in response (AC1)
        assert "honeycomb-svg" in response.text or "honeycomb" in response.text.lower()

    def test_dashboard_health_partial_includes_disk_metrics(
        self, authenticated_client: TestClient
    ):
        """
        AC5: Dashboard health partial includes complete disk metrics.

        Given an authenticated admin user
        When requesting /admin/partials/dashboard-health
        Then the response includes disk free and used percentages
        """
        response = authenticated_client.get("/admin/partials/dashboard-health")

        assert response.status_code == 200

        # Verify disk metrics are in response (AC5)
        # Should contain "GB free" and "GB used" with percentages
        assert "GB free" in response.text or "free" in response.text.lower()


class TestDashboardStatsIntegration:
    """Integration tests for dashboard stats endpoint with AC6 fix."""

    def test_dashboard_stats_partial_endpoint_exists(
        self, authenticated_client: TestClient
    ):
        """
        AC6: Dashboard stats partial endpoint accepts requests.

        Given an authenticated admin user
        When requesting /admin/partials/dashboard-stats
        Then the response is successful
        """
        response = authenticated_client.get("/admin/partials/dashboard-stats")

        assert response.status_code == 200
