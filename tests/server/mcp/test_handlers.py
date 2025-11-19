"""
Test MCP handler functions.

Tests the MCP tool handler implementations that wrap existing REST endpoints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from code_indexer.server.auth.user_manager import User, UserRole
from code_indexer.server.mcp import handlers


class TestSearchCodeHandler:
    """Test search_code handler function."""

    @pytest.fixture
    def mock_user(self) -> User:
        """Create a mock user for testing."""
        return User(
            username="testuser",
            password_hash="fake_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_search_code_no_repositories(self, mock_user: User):
        """Test search_code when user has no activated repositories."""
        # Arrange
        params = {
            "query_text": "authentication",
            "limit": 10,
            "min_score": 0.5,
            "search_mode": "semantic",
        }

        # Mock app-level activated_repo_manager
        with patch("code_indexer.server.app.activated_repo_manager") as mock_repo_mgr:
            mock_repo_mgr.list_activated_repositories.return_value = []

            # Act
            result = await handlers.search_code(params, mock_user)

            # Assert
            assert result["success"] is False
            assert "No activated repositories" in result["error"]
            assert result["results"] == []
            mock_repo_mgr.list_activated_repositories.assert_called_once_with(
                "testuser"
            )


class TestDiscoverRepositoriesHandler:
    """Test discover_repositories handler function."""

    @pytest.fixture
    def mock_user(self) -> User:
        """Create a mock user for testing."""
        return User(
            username="testuser",
            password_hash="fake_hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_discover_repositories_success(self, mock_user: User):
        """Test discover_repositories returns available repositories."""
        # Arrange
        params = {"source_type": "github"}

        # Act
        result = await handlers.discover_repositories(params, mock_user)

        # Assert
        assert result["success"] is True
        assert "result" in result
