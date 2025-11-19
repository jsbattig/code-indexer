"""Test for datetime serialization in MCP handlers.

This test verifies that Pydantic models with datetime fields are correctly
serialized to ISO format strings when returned by MCP handlers.

Bug fixed: "Object of type datetime is not JSON serializable"
Solution: Using model_dump(mode='json') instead of model_dump()
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from pydantic import BaseModel, Field

from code_indexer.server.mcp.handlers import check_health
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture
def mock_user():
    """Create a mock user for testing."""
    return User(
        username="testuser",
        role=UserRole.NORMAL_USER,
        password_hash="hashed_password",
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
class TestDatetimeSerialization:
    """Test datetime serialization in handlers using Pydantic models."""

    async def test_check_health_with_real_datetime_objects(self, mock_user):
        """Test that check_health correctly serializes datetime objects to ISO strings.

        This test verifies the fix for: "Object of type datetime is not JSON serializable"

        The test:
        1. Creates a Pydantic model with actual datetime objects
        2. Calls check_health handler
        3. Verifies JSON serialization succeeds (no TypeError)
        4. Verifies datetime fields are ISO format strings in the response
        """

        # Create a Pydantic model with datetime field (simulates HealthCheckResponse)
        class MockHealthResponse(BaseModel):
            status: str = Field(default="healthy")
            timestamp: datetime = Field(
                default_factory=lambda: datetime.now(timezone.utc)
            )
            uptime: int = Field(default=3600)

        with patch(
            "code_indexer.server.services.health_service.health_service"
        ) as mock_service:
            # Create response with REAL datetime object (not a string)
            mock_response = MockHealthResponse()

            # Verify the mock has a real datetime object (not a string)
            assert isinstance(mock_response.timestamp, datetime)

            mock_service.get_system_health = Mock(return_value=mock_response)

            # Call handler - this would fail with TypeError if mode='json' wasn't used
            result = await check_health({}, mock_user)

            # Verify MCP format with content array
            assert "content" in result
            assert isinstance(result["content"], list)
            assert len(result["content"]) > 0
            assert result["content"][0]["type"] == "text"

            # Parse the JSON - this proves datetime was serialized properly
            # Without mode='json', this would raise: "Object of type datetime is not JSON serializable"
            data = json.loads(result["content"][0]["text"])

            # Verify response structure
            assert data["success"] is True
            assert "health" in data

            # Verify datetime was serialized to string (ISO format)
            health_data = data["health"]
            assert "timestamp" in health_data
            assert isinstance(health_data["timestamp"], str)

            # Verify it's valid ISO format by parsing it
            # Note: Python 3.9 fromisoformat() doesn't support 'Z' suffix, replace with '+00:00'
            timestamp_str = health_data["timestamp"].replace("Z", "+00:00")
            parsed_timestamp = datetime.fromisoformat(timestamp_str)
            assert isinstance(parsed_timestamp, datetime)
