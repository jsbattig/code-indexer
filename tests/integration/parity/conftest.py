"""Pytest fixtures for MCP/REST parity tests."""

import pytest
from typing import Generator
from fastapi.testclient import TestClient

from code_indexer.server.app import create_app
from code_indexer.server.auth.user_manager import User, UserRole


@pytest.fixture(scope="module")
def test_client() -> Generator[TestClient, None, None]:
    """Create FastAPI test client for REST endpoint testing."""
    app = create_app()
    with TestClient(app) as client:
        yield client


@pytest.fixture
def mock_user() -> User:
    """Create a mock user for authentication in MCP handlers."""
    return User(
        username="testuser",
        role=UserRole.USER,
        created_at="2024-01-01T00:00:00Z"
    )


@pytest.fixture
def admin_user() -> User:
    """Create a mock admin user for administrative operations."""
    return User(
        username="admin",
        role=UserRole.ADMIN,
        created_at="2024-01-01T00:00:00Z"
    )


@pytest.fixture
def auth_headers() -> dict:
    """Get authentication headers for REST API calls."""
    # This fixture would normally obtain a JWT token
    # For now, return a mock token structure
    # In real tests, this would call the /auth/token endpoint
    return {
        "Authorization": "Bearer mock_test_token"
    }


@pytest.fixture
def mcp_tool_registry():
    """Import and return the MCP TOOL_REGISTRY for schema inspection."""
    from code_indexer.server.mcp.tools import TOOL_REGISTRY
    return TOOL_REGISTRY


@pytest.fixture
def rest_app():
    """Get the FastAPI app instance for route inspection."""
    return create_app()
