"""
Integration tests for Session Impersonation across tool calls.

Story #722: Session Impersonation for Delegated Queries - Critical fixes

Tests that:
1. Session registry correctly maintains sessions (CRITICAL 1)
2. Impersonation persists across multiple tool calls (CRITICAL 2)
3. Session state is properly passed to handlers (CRITICAL 3)
4. Effective user is used for permission checks when impersonating
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock


class TestSessionImpersonationProtocolIntegration:
    """Test session impersonation at the protocol level."""

    @pytest.fixture
    def admin_user(self):
        """Create an admin user for testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self):
        """Create a target user for impersonation testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def normal_user(self):
        """Create a normal user for testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="normal_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture(autouse=True)
    def clean_session_registry(self):
        """Clean session registry before and after each test."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        yield
        registry.clear_all()

    @pytest.mark.asyncio
    async def test_session_registry_creates_session_on_first_tool_call(
        self, admin_user
    ):
        """Test that session registry creates session on first tool call."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-001"

        # Verify session doesn't exist
        assert registry.get_session(session_id) is None

        # Create session (simulating protocol layer behavior)
        session = registry.get_or_create_session(session_id, admin_user)

        # Verify session was created
        assert session is not None
        assert session.session_id == session_id
        assert session.authenticated_user == admin_user
        assert session.is_impersonating is False

    @pytest.mark.asyncio
    async def test_impersonation_persists_across_registry_calls(
        self, admin_user, target_user
    ):
        """Test that impersonation persists across multiple tool calls."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-002"

        # First tool call - create session and set impersonation
        session1 = registry.get_or_create_session(session_id, admin_user)
        session1.set_impersonation(target_user)

        # Verify impersonation is set
        assert session1.is_impersonating is True
        assert session1.effective_user == target_user

        # Second tool call - get session (simulating subsequent tool call)
        session2 = registry.get_or_create_session(session_id, admin_user)

        # Verify impersonation persists
        assert session2 is session1  # Same session object
        assert session2.is_impersonating is True
        assert session2.effective_user == target_user
        assert session2.authenticated_user == admin_user

    @pytest.mark.asyncio
    async def test_effective_user_permissions_apply_when_impersonating(
        self, admin_user, target_user
    ):
        """Test that effective_user's permissions apply when impersonating."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-003"

        # Create session and set impersonation
        session = registry.get_or_create_session(session_id, admin_user)
        session.set_impersonation(target_user)

        # Admin permissions should NOT apply when impersonating normal_user
        effective_user = session.effective_user
        assert effective_user.has_permission("manage_users") is False
        assert effective_user.has_permission("query_repos") is True

        # Original authenticated user still has admin permissions
        assert session.authenticated_user.has_permission("manage_users") is True

    @pytest.mark.asyncio
    async def test_clear_impersonation_restores_admin_permissions(
        self, admin_user, target_user
    ):
        """Test that clearing impersonation restores original permissions."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-004"

        # Create session and set impersonation
        session = registry.get_or_create_session(session_id, admin_user)
        session.set_impersonation(target_user)

        # Verify impersonating - limited permissions
        assert session.effective_user.has_permission("manage_users") is False

        # Clear impersonation
        session.clear_impersonation()

        # Verify admin permissions restored
        assert session.effective_user.has_permission("manage_users") is True
        assert session.effective_user == admin_user


class TestSessionImpersonationHandlerIntegration:
    """Test session impersonation handler with session state."""

    @pytest.fixture
    def admin_user(self):
        """Create an admin user for testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self):
        """Create a target user for impersonation testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture(autouse=True)
    def clean_session_registry(self):
        """Clean session registry before and after each test."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        yield
        registry.clear_all()

    @pytest.mark.asyncio
    async def test_handler_sets_impersonation_with_session_state(
        self, admin_user, target_user
    ):
        """Test that handler sets impersonation when session_state is provided."""
        from code_indexer.server.mcp.handlers import handle_set_session_impersonation
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        from code_indexer.server.auth.user_manager import UserManager
        import json

        # Create session state
        session_state = MCPSessionState(
            session_id="handler-test-001", authenticated_user=admin_user
        )

        # Mock UserManager.get_user to return target_user
        with patch.object(UserManager, "get_user", return_value=target_user):
            # Call handler with session_state
            result = await handle_set_session_impersonation(
                {"username": "target_user"}, admin_user, session_state=session_state
            )

        # Verify response
        content = result["content"][0]["text"]
        response_data = json.loads(content)
        assert response_data["status"] == "ok"
        assert response_data["impersonating"] == "target_user"

        # Verify session_state was updated
        assert session_state.is_impersonating is True
        assert session_state.effective_user.username == "target_user"

    @pytest.mark.asyncio
    async def test_handler_clears_impersonation_with_session_state(
        self, admin_user, target_user
    ):
        """Test that handler clears impersonation when username is None."""
        from code_indexer.server.mcp.handlers import handle_set_session_impersonation
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        import json

        # Create session state with active impersonation
        session_state = MCPSessionState(
            session_id="handler-test-002", authenticated_user=admin_user
        )
        session_state.set_impersonation(target_user)

        # Verify impersonation is active
        assert session_state.is_impersonating is True

        # Call handler to clear impersonation
        result = await handle_set_session_impersonation(
            {"username": None}, admin_user, session_state=session_state
        )

        # Verify response
        content = result["content"][0]["text"]
        response_data = json.loads(content)
        assert response_data["status"] == "ok"
        assert response_data["impersonating"] is None

        # Verify session_state was cleared
        assert session_state.is_impersonating is False
        assert session_state.effective_user == admin_user

    @pytest.mark.asyncio
    async def test_handler_rejects_non_admin_impersonation(self, target_user):
        """Test that handler rejects impersonation from non-admin users."""
        from code_indexer.server.mcp.handlers import handle_set_session_impersonation
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        import json

        # Create session state for non-admin user
        session_state = MCPSessionState(
            session_id="handler-test-003", authenticated_user=target_user
        )

        # Call handler (should fail - target_user is not admin)
        result = await handle_set_session_impersonation(
            {"username": "someone"}, target_user, session_state=session_state
        )

        # Verify error response
        content = result["content"][0]["text"]
        response_data = json.loads(content)
        assert response_data["status"] == "error"
        assert "ADMIN role" in response_data["error"]

        # Verify session_state was NOT modified
        assert session_state.is_impersonating is False


class TestSessionImpersonationAuditLogging:
    """Test that impersonation actions are properly audit logged."""

    @pytest.fixture
    def admin_user(self):
        """Create an admin user for testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self):
        """Create a target user for impersonation testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_impersonation_set_is_audit_logged(self, admin_user, target_user):
        """Test that setting impersonation is logged."""
        from code_indexer.server.mcp.handlers import handle_set_session_impersonation
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        from code_indexer.server.auth.user_manager import UserManager
        from code_indexer.server.auth import audit_logger

        session_state = MCPSessionState(
            session_id="audit-test-001", authenticated_user=admin_user
        )

        with patch.object(UserManager, "get_user", return_value=target_user), patch.object(
            audit_logger.password_audit_logger, "log_impersonation_set"
        ) as mock_log_set:
            await handle_set_session_impersonation(
                {"username": "target_user"}, admin_user, session_state=session_state
            )

            # Verify audit log was called
            mock_log_set.assert_called_once_with(
                actor_username="admin_user",
                target_username="target_user",
                session_id="audit-test-001",
                ip_address="unknown",  # HIGH 2 - needs to be fixed to pass real IP
            )

    @pytest.mark.asyncio
    async def test_impersonation_clear_is_audit_logged(self, admin_user, target_user):
        """Test that clearing impersonation is logged."""
        from code_indexer.server.mcp.handlers import handle_set_session_impersonation
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        from code_indexer.server.auth import audit_logger

        session_state = MCPSessionState(
            session_id="audit-test-002", authenticated_user=admin_user
        )
        session_state.set_impersonation(target_user)

        with patch.object(
            audit_logger.password_audit_logger, "log_impersonation_cleared"
        ) as mock_log_cleared:
            await handle_set_session_impersonation(
                {"username": None}, admin_user, session_state=session_state
            )

            # Verify audit log was called
            mock_log_cleared.assert_called_once_with(
                actor_username="admin_user",
                previous_target="target_user",
                session_id="audit-test-002",
                ip_address="unknown",  # HIGH 2 - needs to be fixed to pass real IP
            )
