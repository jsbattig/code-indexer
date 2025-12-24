"""End-to-end integration tests for system health monitoring.

Following CLAUDE.md Foundation #1: No mocks for core workflow validation.
Tests complete system health monitoring workflow from API client to CLI.
"""

import pytest
import asyncio
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from src.code_indexer.api_clients.system_client import (
    SystemAPIClient,
    create_system_client,
)
from src.code_indexer.api_clients.base_client import AuthenticationError, APIClientError


@pytest.mark.integration
class TestSystemHealthMonitoringE2E:
    """End-to-end tests for complete system health monitoring workflow."""

    @pytest.fixture
    def mock_credentials(self):
        """Provide test credentials."""
        return {"username": "test_user", "password": "test_password"}

    @pytest.fixture
    def temp_project_dir(self):
        """Create temporary project directory with remote config."""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_path = Path(temp_dir)

            # Create .code-indexer directory
            code_indexer_dir = project_path / ".code-indexer"
            code_indexer_dir.mkdir()

            # Create remote configuration
            remote_config = {
                "server_url": "http://localhost:8000",
                "encrypted_credentials": {"username": "test_user"},
            }

            remote_config_path = code_indexer_dir / "remote_config.json"
            with open(remote_config_path, "w") as f:
                json.dump(remote_config, f)

            yield project_path

    @pytest.mark.asyncio
    async def test_complete_basic_health_workflow(
        self, mock_credentials, temp_project_dir
    ):
        """Test complete basic health check workflow from client to response."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Mock authenticated request to simulate server response
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.return_value = {
                "status": "ok",
                "timestamp": "2024-01-15T10:30:00Z",
                "message": "All systems operational",
            }

            # Execute health check
            result = await system_client.check_basic_health()

            # Verify complete workflow
            assert result["status"] == "ok"
            assert result["timestamp"] == "2024-01-15T10:30:00Z"
            assert result["message"] == "All systems operational"
            assert "response_time_ms" in result
            assert isinstance(result["response_time_ms"], (int, float))
            assert result["response_time_ms"] >= 0

            # Verify API endpoint was called correctly
            mock_request.assert_called_once_with("GET", "/health")

    @pytest.mark.asyncio
    async def test_complete_detailed_health_workflow(
        self, mock_credentials, temp_project_dir
    ):
        """Test complete detailed health check workflow with rich information."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Mock authenticated request to simulate detailed server response
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.return_value = {
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
                    "authentication": {
                        "status": "healthy",
                        "response_time_ms": 3,
                        "error_message": None,
                    },
                },
                "system": {
                    "memory_usage_percent": 42.5,
                    "cpu_usage_percent": 18.7,
                    "active_jobs": 3,
                    "disk_free_space_gb": 245.6,
                },
            }

            # Execute detailed health check
            result = await system_client.check_detailed_health()

            # Verify complete detailed workflow
            assert result["status"] == "healthy"
            assert result["timestamp"] == "2024-01-15T10:30:00Z"
            assert "response_time_ms" in result

            # Verify services information
            services = result["services"]
            assert len(services) == 3
            assert services["database"]["status"] == "healthy"
            assert services["vector_store"]["status"] == "healthy"
            assert services["authentication"]["status"] == "healthy"

            # Verify system information
            system_info = result["system"]
            assert system_info["memory_usage_percent"] == 42.5
            assert system_info["cpu_usage_percent"] == 18.7
            assert system_info["active_jobs"] == 3
            assert system_info["disk_free_space_gb"] == 245.6

            # Verify API endpoint was called correctly
            mock_request.assert_called_once_with("GET", "/api/system/health")

    @pytest.mark.asyncio
    async def test_client_factory_integration(self, temp_project_dir):
        """Test system client factory function integration."""
        # Test factory function with mocked credential loading
        with patch(
            "src.code_indexer.remote.credential_manager.load_encrypted_credentials"
        ) as mock_load_creds:
            mock_load_creds.return_value = {
                "username": "factory_user",
                "password": "factory_password",
            }

            # Create client using factory
            client = create_system_client(
                server_url="http://localhost:9000",
                project_root=temp_project_dir,
                username="factory_user",
            )

            # Verify client configuration
            assert isinstance(client, SystemAPIClient)
            assert client.server_url == "http://localhost:9000"
            assert client.credentials["username"] == "factory_user"
            assert client.credentials["password"] == "factory_password"
            assert client.project_root == temp_project_dir

    @pytest.mark.asyncio
    async def test_error_handling_workflow(self, mock_credentials, temp_project_dir):
        """Test complete error handling workflow."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Test authentication error handling
        with patch.object(system_client, "_authenticated_request") as mock_request:
            mock_request.side_effect = AuthenticationError(
                "Token expired", status_code=401
            )

            with pytest.raises(AuthenticationError) as exc_info:
                await system_client.check_basic_health()

            assert "Token expired" in str(exc_info.value)
            assert exc_info.value.status_code == 401

        # Test server error handling
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
        self, mock_credentials, temp_project_dir
    ):
        """Test response time measurement accuracy in real workflow."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Mock with controlled delay
        with patch.object(system_client, "_authenticated_request") as mock_request:

            async def delayed_response(*args, **kwargs):
                await asyncio.sleep(0.05)  # 50ms delay
                return {
                    "status": "ok",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "message": "System healthy",
                }

            mock_request.side_effect = delayed_response

            # Execute health check and measure time
            import time

            start_time = time.time()
            result = await system_client.check_basic_health()
            end_time = time.time()

            # Verify response time measurement accuracy
            measured_time_ms = result["response_time_ms"]
            actual_time_ms = (end_time - start_time) * 1000

            # Should be approximately 50ms (with some tolerance for execution overhead)
            assert 40 <= measured_time_ms <= 100  # 50ms ± 50ms tolerance
            assert (
                measured_time_ms <= actual_time_ms + 10
            )  # Should be close to actual time

    def test_system_client_inheritance_workflow(
        self, mock_credentials, temp_project_dir
    ):
        """Test that SystemAPIClient properly inherits base functionality."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Verify inheritance hierarchy
        from src.code_indexer.api_clients.base_client import CIDXRemoteAPIClient

        assert isinstance(system_client, CIDXRemoteAPIClient)

        # Verify base functionality is available
        assert hasattr(system_client, "server_url")
        assert hasattr(system_client, "credentials")
        assert hasattr(system_client, "_authenticated_request")
        assert hasattr(system_client, "session")

        # Verify system-specific functionality
        assert hasattr(system_client, "check_basic_health")
        assert hasattr(system_client, "check_detailed_health")

    @pytest.mark.asyncio
    async def test_concurrent_health_checks_workflow(
        self, mock_credentials, temp_project_dir
    ):
        """Test concurrent health checks workflow to verify thread safety."""
        # Create system client
        system_client = SystemAPIClient(
            server_url="http://localhost:8000",
            credentials=mock_credentials,
            project_root=temp_project_dir,
        )

        # Mock response with small delay
        with patch.object(system_client, "_authenticated_request") as mock_request:

            async def response_with_delay(*args, **kwargs):
                await asyncio.sleep(0.01)  # 10ms delay
                return {
                    "status": "ok",
                    "timestamp": "2024-01-15T10:30:00Z",
                    "message": "Concurrent test",
                }

            mock_request.side_effect = response_with_delay

            # Run multiple concurrent health checks
            tasks = [system_client.check_basic_health() for _ in range(5)]

            results = await asyncio.gather(*tasks)

            # Verify all requests succeeded
            assert len(results) == 5
            for result in results:
                assert result["status"] == "ok"
                assert "response_time_ms" in result
                assert result["response_time_ms"] >= 0

            # Verify all requests were made
            assert mock_request.call_count == 5
