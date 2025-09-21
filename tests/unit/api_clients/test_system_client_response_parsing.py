"""Unit tests for SystemAPIClient response parsing fixes.

Tests that SystemAPIClient properly parses JSON responses and doesn't
try to treat httpx.Response objects as dictionaries.
"""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import httpx

from src.code_indexer.api_clients.system_client import SystemAPIClient


class TestSystemClientResponseParsing:
    """Test SystemAPIClient response parsing."""

    @pytest.fixture
    def system_client(self):
        """Create SystemAPIClient for testing."""
        return SystemAPIClient(
            server_url="http://localhost:8096",
            credentials={"username": "testuser"},
            project_root=Path("/test/project"),
        )

    @pytest.mark.asyncio
    async def test_check_basic_health_parses_json_response(self, system_client):
        """Test that check_basic_health properly parses JSON and adds response time."""
        # Mock the _authenticated_request to return an httpx.Response
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.return_value = {
            "status": "ok",
            "message": "System is healthy",
        }
        mock_response.status_code = 200

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            result = await system_client.check_basic_health()

            # Should return a dictionary with the parsed JSON plus response_time_ms
            assert isinstance(result, dict)
            assert result["status"] == "ok"
            assert result["message"] == "System is healthy"
            assert "response_time_ms" in result
            assert isinstance(result["response_time_ms"], (int, float))

    @pytest.mark.asyncio
    async def test_check_detailed_health_parses_json_response(self, system_client):
        """Test that check_detailed_health properly parses JSON and adds response time."""
        # Mock the _authenticated_request to return an httpx.Response
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.return_value = {
            "status": "healthy",
            "services": {"database": {"status": "ok"}, "api": {"status": "ok"}},
            "system": {"memory_usage_percent": 45.2},
        }
        mock_response.status_code = 200

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            result = await system_client.check_detailed_health()

            # Should return a dictionary with the parsed JSON plus response_time_ms
            assert isinstance(result, dict)
            assert result["status"] == "healthy"
            assert "services" in result
            assert "system" in result
            assert "response_time_ms" in result
            assert isinstance(result["response_time_ms"], (int, float))

    @pytest.mark.asyncio
    async def test_basic_health_doesnt_modify_response_object(self, system_client):
        """Test that the method doesn't try to modify the httpx.Response object directly.

        This verifies the bug fix where response["response_time_ms"] would fail
        because response is an httpx.Response, not a dict.
        """
        # Mock the _authenticated_request to return an httpx.Response
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.return_value = {
            "status": "ok",
            "message": "System is healthy",
        }
        mock_response.status_code = 200

        # If the bug existed, this would try response["response_time_ms"] = value
        # which would fail because mock_response doesn't support item assignment

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            # This should not raise a TypeError about item assignment
            result = await system_client.check_basic_health()

            # Verify the mock response object was not modified (it's still a Mock)
            assert not hasattr(mock_response, "__getitem__") or not hasattr(
                mock_response, "__setitem__"
            )

            # But the result should be a proper dictionary
            assert isinstance(result, dict)
            assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_detailed_health_doesnt_modify_response_object(self, system_client):
        """Test that detailed health check doesn't try to modify the httpx.Response object directly."""
        # Mock the _authenticated_request to return an httpx.Response
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.return_value = {"status": "healthy", "services": {}}
        mock_response.status_code = 200

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            # This should not raise a TypeError about item assignment
            result = await system_client.check_detailed_health()

            # Verify the mock response object was not modified (it's still a Mock)
            assert not hasattr(mock_response, "__getitem__") or not hasattr(
                mock_response, "__setitem__"
            )

            # But the result should be a proper dictionary
            assert isinstance(result, dict)
            assert "response_time_ms" in result

    @pytest.mark.asyncio
    async def test_response_time_calculation_accuracy(self, system_client):
        """Test that response time is calculated and added correctly."""
        # Mock the _authenticated_request to return an httpx.Response
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.return_value = {"status": "ok"}
        mock_response.status_code = 200

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            result = await system_client.check_basic_health()

            # Response time should be present and reasonable (< 1000ms for a mock call)
            assert "response_time_ms" in result
            assert isinstance(result["response_time_ms"], (int, float))
            assert (
                0 <= result["response_time_ms"] < 1000
            )  # Should be very fast for a mock

    @pytest.mark.asyncio
    async def test_json_parsing_error_handling(self, system_client):
        """Test that JSON parsing errors are handled gracefully."""
        from src.code_indexer.api_clients.base_client import APIClientError

        # Mock the _authenticated_request to return an httpx.Response with invalid JSON
        mock_response = Mock(spec=httpx.Response)
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.status_code = 200

        with patch.object(
            system_client, "_authenticated_request", return_value=mock_response
        ):
            # Should raise an APIClientError wrapping the JSON parsing error
            # The important thing is it doesn't raise a TypeError about item assignment
            with pytest.raises(
                APIClientError, match="Health check failed.*Invalid JSON"
            ):
                await system_client.check_basic_health()
