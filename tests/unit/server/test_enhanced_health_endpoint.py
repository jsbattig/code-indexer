"""
Unit tests for enhanced health check endpoint.

Tests the enhanced /health endpoint that provides detailed server status,
uptime, job queue health, and system resource usage.
Following TDD methodology - these tests will fail initially.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app


class TestEnhancedHealthEndpoint:
    """Test suite for enhanced health check endpoint."""

    def setup_method(self):
        """Set up test fixtures."""
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_health_endpoint_returns_basic_status_when_healthy(self):
        """Test health endpoint returns basic status information when healthy."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 2
                mock_job_manager.get_pending_job_count.return_value = (
                    1  # Low pending count
                )
                mock_job_manager.get_failed_job_count.return_value = 0  # No failed jobs
                mock_uptime.return_value = 3600

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "healthy"
                assert data["message"] == "CIDX Server is running"
                assert data["uptime"] == 3600
                assert data["active_jobs"] == 2

    def test_health_endpoint_includes_system_resource_usage(self):
        """Test health endpoint includes system resource usage information."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                with patch(
                    "code_indexer.server.app.get_system_resources"
                ) as mock_resources:
                    mock_job_manager.get_active_job_count.return_value = 1
                    mock_job_manager.get_pending_job_count.return_value = 0
                    mock_job_manager.get_failed_job_count.return_value = 0
                    mock_uptime.return_value = 1800
                    mock_resources.return_value = {
                        "memory_usage_mb": 256,
                        "memory_usage_percent": 15.2,
                        "cpu_usage_percent": 8.5,
                    }

                    response = self.client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    assert "system_resources" in data
                    assert data["system_resources"]["memory_usage_mb"] == 256
                    assert data["system_resources"]["memory_usage_percent"] == 15.2
                    assert data["system_resources"]["cpu_usage_percent"] == 8.5

    def test_health_endpoint_includes_job_queue_health(self):
        """Test health endpoint includes background job queue health."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 3
                mock_job_manager.get_pending_job_count.return_value = 1
                mock_job_manager.get_failed_job_count.return_value = 0
                mock_uptime.return_value = 7200

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert "job_queue" in data
                assert data["job_queue"]["active_jobs"] == 3
                assert data["job_queue"]["pending_jobs"] == 1
                assert data["job_queue"]["failed_jobs"] == 0

    def test_health_endpoint_shows_degraded_status_with_failed_jobs(self):
        """Test health endpoint shows degraded status when jobs are failing."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 2
                mock_job_manager.get_pending_job_count.return_value = 5
                mock_job_manager.get_failed_job_count.return_value = 3
                mock_uptime.return_value = 3600

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "degraded"
                assert "failed jobs detected" in data["message"].lower()

    def test_health_endpoint_shows_warning_with_high_pending_jobs(self):
        """Test health endpoint shows warning with high pending job count."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 1
                mock_job_manager.get_pending_job_count.return_value = (
                    10  # High pending count
                )
                mock_job_manager.get_failed_job_count.return_value = 0
                mock_uptime.return_value = 3600

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "warning"
                assert "high pending job count" in data["message"].lower()

    def test_health_endpoint_includes_recent_errors_if_available(self):
        """Test health endpoint includes recent error information if available."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                with patch("code_indexer.server.app.get_recent_errors") as mock_errors:
                    mock_job_manager.get_active_job_count.return_value = 1
                    mock_job_manager.get_pending_job_count.return_value = 0
                    mock_job_manager.get_failed_job_count.return_value = 0
                    mock_uptime.return_value = 3600
                    mock_errors.return_value = [
                        {
                            "timestamp": "2024-01-01T12:00:00Z",
                            "error": "Connection timeout to vector database",
                            "count": 2,
                        }
                    ]

                    response = self.client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    assert "recent_errors" in data
                    assert len(data["recent_errors"]) == 1
                    assert (
                        data["recent_errors"][0]["error"]
                        == "Connection timeout to vector database"
                    )

    def test_health_endpoint_handles_uptime_calculation_error(self):
        """Test health endpoint handles uptime calculation errors gracefully."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 0
                mock_job_manager.get_pending_job_count.return_value = 0
                mock_job_manager.get_failed_job_count.return_value = 0
                mock_uptime.side_effect = Exception("Failed to calculate uptime")

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "degraded"
                assert data["uptime"] is None

    def test_health_endpoint_handles_job_manager_errors(self):
        """Test health endpoint handles background job manager errors."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.side_effect = Exception(
                    "Job manager error"
                )
                mock_job_manager.get_pending_job_count.side_effect = Exception(
                    "Job manager error"
                )
                mock_job_manager.get_failed_job_count.side_effect = Exception(
                    "Job manager error"
                )
                mock_uptime.return_value = 3600

                response = self.client.get("/health")

                assert response.status_code == 200
                data = response.json()

                assert data["status"] == "healthy"
                assert data["message"] == "CIDX Server is running"

    def test_health_endpoint_requires_no_authentication(self):
        """Test health endpoint is accessible without authentication."""
        # This test should pass even with current implementation
        response = self.client.get("/health")

        assert response.status_code == 200
        # Should not get 401 Unauthorized

    def test_health_endpoint_includes_server_version(self):
        """Test health endpoint includes server version information."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                with patch("code_indexer.__version__", "1.2.3"):
                    mock_job_manager.get_active_job_count.return_value = 0
                    mock_job_manager.get_pending_job_count.return_value = 0
                    mock_job_manager.get_failed_job_count.return_value = 0
                    mock_uptime.return_value = 3600

                    response = self.client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    assert "version" in data
                    assert data["version"] == "1.2.3"

    def test_health_endpoint_includes_startup_time(self):
        """Test health endpoint includes server startup timestamp."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                with patch(
                    "code_indexer.server.app.get_server_start_time"
                ) as mock_start_time:
                    mock_job_manager.get_active_job_count.return_value = 2
                    mock_job_manager.get_pending_job_count.return_value = 0
                    mock_job_manager.get_failed_job_count.return_value = 0
                    mock_uptime.return_value = 3600
                    mock_start_time.return_value = "2024-01-01T00:00:00Z"

                    response = self.client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    assert "started_at" in data
                    assert data["started_at"] == "2024-01-01T00:00:00Z"

    def test_health_endpoint_performance_under_load(self):
        """Test health endpoint responds quickly under load simulation."""
        import time

        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                mock_job_manager.get_active_job_count.return_value = 5
                mock_job_manager.get_pending_job_count.return_value = 0
                mock_job_manager.get_failed_job_count.return_value = 0
                mock_uptime.return_value = 3600

                start_time = time.time()
                response = self.client.get("/health")
                end_time = time.time()

                assert response.status_code == 200
                assert (end_time - start_time) < 0.5  # Should respond in under 500ms

    def test_health_endpoint_includes_database_connectivity(self):
        """Test health endpoint includes database connectivity status."""
        with patch(
            "code_indexer.server.app.background_job_manager"
        ) as mock_job_manager:
            with patch("code_indexer.server.app.get_server_uptime") as mock_uptime:
                with patch(
                    "code_indexer.server.app.check_database_health"
                ) as mock_db_health:
                    mock_job_manager.get_active_job_count.return_value = 1
                    mock_job_manager.get_pending_job_count.return_value = 0
                    mock_job_manager.get_failed_job_count.return_value = 0
                    mock_uptime.return_value = 3600
                    mock_db_health.return_value = {
                        "users_db": "healthy",
                        "jobs_db": "healthy",
                    }

                    response = self.client.get("/health")

                    assert response.status_code == 200
                    data = response.json()

                    assert "database" in data
                    assert data["database"]["users_db"] == "healthy"
                    assert data["database"]["jobs_db"] == "healthy"
