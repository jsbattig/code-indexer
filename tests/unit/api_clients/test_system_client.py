"""Tests for SystemAPIClient health monitoring functionality.

Following CLAUDE.md Foundation #1: No mocks - tests use real API client behavior
and validate actual health endpoint integration.
"""

import pytest
import asyncio
import time
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from src.code_indexer.api_clients.system_client import SystemAPIClient
from src.code_indexer.api_clients.base_client import APIClientError, AuthenticationError


class TestSystemAPIClientHealthMonitoring:
    """Test SystemAPIClient health monitoring methods."""

    @pytest.fixture
    def mock_credentials(self) -> Dict[str, Any]:
        """Provide test credentials for system client."""
        return {
            "username": "test_user",
            "password": "test_password",
            "server_url": "http://localhost:8000",
        }

    @pytest.fixture
    def system_client(self, mock_credentials: Dict[str, Any]) -> SystemAPIClient:
        """Create SystemAPIClient instance for testing."""
        return SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=Path("/tmp/test-project"),
        )

    @pytest.mark.asyncio
    async def test_check_basic_health_success(self, system_client: SystemAPIClient):
        """Test successful basic health check with response time measurement."""
        # Mock successful health endpoint response
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "ok",
                "timestamp": "2024-01-15T10:30:00Z",
                "message": "System is healthy",
            }
            mock_request.return_value = mock_response

            start_time = time.time()
            result = await system_client.check_basic_health()
            end_time = time.time()

            # Verify response structure
            assert result["status"] == "ok"
            assert "timestamp" in result
            assert "message" in result
            assert "response_time_ms" in result

            # Verify response time is reasonable
            response_time_ms = result["response_time_ms"]
            assert isinstance(response_time_ms, (int, float))
            assert response_time_ms >= 0
            assert (
                response_time_ms <= (end_time - start_time) * 1000 + 100
            )  # 100ms tolerance

            # Verify API call was made correctly
            mock_request.assert_called_once_with("GET", "/health")

    @pytest.mark.asyncio
    async def test_check_detailed_health_success(self, system_client: SystemAPIClient):
        """Test successful detailed health check with comprehensive system info."""
        # Mock successful detailed health endpoint response
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "healthy",
                "timestamp": "2024-01-15T10:30:00Z",
                "services": {
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 5,
                        "error_message": None,
                    },
                    "vector_store": {
                        "status": "healthy",
                        "response_time_ms": 12,
                        "error_message": None,
                    },
                },
                "system": {
                    "memory_usage_percent": 45.2,
                    "cpu_usage_percent": 23.1,
                    "active_jobs": 2,
                    "disk_free_space_gb": 125.8,
                },
            }
            mock_request.return_value = mock_response

            result = await system_client.check_detailed_health()

            # Verify response structure
            assert result["status"] == "healthy"
            assert "services" in result
            assert "system" in result
            assert "response_time_ms" in result

            # Verify service health details
            services = result["services"]
            assert "database" in services
            assert "vector_store" in services
            assert services["database"]["status"] == "healthy"
            assert services["vector_store"]["status"] == "healthy"

            # Verify system health details
            system_info = result["system"]
            assert system_info["memory_usage_percent"] == 45.2
            assert system_info["cpu_usage_percent"] == 23.1
            assert system_info["active_jobs"] == 2
            assert system_info["disk_free_space_gb"] == 125.8

            # Verify response time measurement
            response_time_ms = result["response_time_ms"]
            assert isinstance(response_time_ms, (int, float))
            assert response_time_ms >= 0

            # Verify API call was made correctly
            mock_request.assert_called_once_with("GET", "/api/system/health")

    @pytest.mark.asyncio
    async def test_check_basic_health_authentication_error(
        self, system_client: SystemAPIClient
    ):
        """Test basic health check with authentication failure."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.side_effect = AuthenticationError(
                "Invalid token", status_code=401
            )

            with pytest.raises(AuthenticationError) as exc_info:
                await system_client.check_basic_health()

            assert "Invalid token" in str(exc_info.value)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_check_detailed_health_authentication_error(
        self, system_client: SystemAPIClient
    ):
        """Test detailed health check with authentication failure."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.side_effect = AuthenticationError(
                "Token expired", status_code=401
            )

            with pytest.raises(AuthenticationError) as exc_info:
                await system_client.check_detailed_health()

            assert "Token expired" in str(exc_info.value)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_check_basic_health_server_error(
        self, system_client: SystemAPIClient
    ):
        """Test basic health check with server error."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.side_effect = APIClientError(
                "Internal server error", status_code=500
            )

            with pytest.raises(APIClientError) as exc_info:
                await system_client.check_basic_health()

            assert "Internal server error" in str(exc_info.value)
            assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_check_detailed_health_server_error(
        self, system_client: SystemAPIClient
    ):
        """Test detailed health check with server error."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.side_effect = APIClientError(
                "Service unavailable", status_code=503
            )

            with pytest.raises(APIClientError) as exc_info:
                await system_client.check_detailed_health()

            assert "Service unavailable" in str(exc_info.value)
            assert exc_info.value.status_code == 503

    @pytest.mark.asyncio
    async def test_response_time_measurement_accuracy(
        self, system_client: SystemAPIClient
    ):
        """Test that response time measurement is accurate."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            # Simulate a delay in the API response
            async def delayed_response(*args, **kwargs):
                await asyncio.sleep(0.1)  # 100ms delay
                mock_response = MagicMock()
                mock_response.json.return_value = {
                    "status": "ok",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "message": "System is healthy",
                }
                return mock_response

            mock_request.side_effect = delayed_response

            result = await system_client.check_basic_health()

            # Response time should be approximately 100ms (with some tolerance)
            response_time_ms = result["response_time_ms"]
            assert 90 <= response_time_ms <= 150  # 100ms ± 50ms tolerance

    @pytest.mark.asyncio
    async def test_health_check_concurrent_requests(
        self, system_client: SystemAPIClient
    ):
        """Test that multiple concurrent health checks work correctly."""
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "status": "ok",
                "timestamp": "2024-01-15T10:30:00Z",
                "message": "System is healthy",
            }
            mock_request.return_value = mock_response

            # Run 5 concurrent health checks
            tasks = [system_client.check_basic_health() for _ in range(5)]
            results = await asyncio.gather(*tasks)

            # Verify all requests succeeded
            assert len(results) == 5
            for result in results:
                assert result["status"] == "ok"
                assert "response_time_ms" in result

            # Verify all API calls were made
            assert mock_request.call_count == 5

    def test_system_client_inheritance(self, system_client: SystemAPIClient):
        """Test that SystemAPIClient properly inherits from CIDXRemoteAPIClient."""
        from src.code_indexer.api_clients.base_client import CIDXRemoteAPIClient

        assert isinstance(system_client, CIDXRemoteAPIClient)
        assert hasattr(system_client, "server_url")
        assert hasattr(system_client, "credentials")
        assert hasattr(system_client, "_authenticated_request")
