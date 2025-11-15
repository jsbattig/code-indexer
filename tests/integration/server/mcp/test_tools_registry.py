"""Unit tests for MCP tool registry."""

import pytest
from datetime import datetime, timezone
from code_indexer.server.auth.user_manager import UserRole, User


class TestToolRegistry:
    """Tests for tool registry and permission filtering."""

    @pytest.fixture
    def normal_user(self):
        """Create normal user for testing."""
        return User(
            username="normal",
            password_hash="hash",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_filter_tools_returns_list(self, normal_user):
        """Test that filter_tools_by_role returns a list."""
        from code_indexer.server.mcp.tools import filter_tools_by_role

        tools = filter_tools_by_role(normal_user)
        assert isinstance(tools, list)
