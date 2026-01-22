"""
Unit tests for MCPSessionState class - Session Impersonation for Delegated Queries.

Story #722: Implement session-scoped impersonation for MCP sessions, allowing
authenticated ADMIN users to assume another user's identity for the duration
of their session.

These tests follow TDD methodology - written first, implementation comes after.
"""

import pytest
from datetime import datetime, timezone
from code_indexer.server.auth.user_manager import User, UserRole


class TestMCPSessionState:
    """Test MCPSessionState class behavior."""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user for testing."""
        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def power_user(self) -> User:
        """Create a power user for testing."""
        return User(
            username="power_user",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def normal_user(self) -> User:
        """Create a normal user for testing."""
        return User(
            username="normal_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self) -> User:
        """Create a target user for impersonation testing."""
        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_session_state_initialization(self, admin_user: User):
        """Test that MCPSessionState initializes with correct default values."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        assert session.session_id == "session-123"
        assert session.authenticated_user == admin_user
        assert session.impersonated_user is None

    def test_effective_user_returns_authenticated_when_not_impersonating(
        self, admin_user: User
    ):
        """Test effective_user returns authenticated user when no impersonation is set."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        assert session.effective_user == admin_user
        assert session.effective_user.username == "admin_user"

    def test_effective_user_returns_impersonated_when_impersonating(
        self, admin_user: User, target_user: User
    ):
        """Test effective_user returns impersonated user when impersonation is set."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)

        assert session.effective_user == target_user
        assert session.effective_user.username == "target_user"
        # Authenticated user should remain unchanged
        assert session.authenticated_user == admin_user

    def test_set_impersonation_stores_target_user(
        self, admin_user: User, target_user: User
    ):
        """Test set_impersonation stores the target user correctly."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)

        assert session.impersonated_user == target_user
        assert session.impersonated_user.username == "target_user"
        assert session.impersonated_user.role == UserRole.NORMAL_USER

    def test_clear_impersonation_removes_impersonated_user(
        self, admin_user: User, target_user: User
    ):
        """Test clear_impersonation removes the impersonated user."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)

        # Verify impersonation is set
        assert session.impersonated_user == target_user

        # Clear impersonation
        session.clear_impersonation()

        # Verify impersonation is cleared
        assert session.impersonated_user is None
        assert session.effective_user == admin_user

    def test_is_impersonating_property_returns_false_when_not_impersonating(
        self, admin_user: User
    ):
        """Test is_impersonating returns False when no impersonation is active."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        assert session.is_impersonating is False

    def test_is_impersonating_property_returns_true_when_impersonating(
        self, admin_user: User, target_user: User
    ):
        """Test is_impersonating returns True when impersonation is active."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)

        assert session.is_impersonating is True

    def test_impersonation_preserves_original_admin_permissions(
        self, admin_user: User, target_user: User
    ):
        """Test that impersonation doesn't affect the authenticated_user object."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)

        # Original admin should still have admin role
        assert session.authenticated_user.role == UserRole.ADMIN
        # Effective user should have target's role (normal_user)
        assert session.effective_user.role == UserRole.NORMAL_USER

    def test_multiple_impersonation_changes(
        self, admin_user: User, target_user: User, power_user: User
    ):
        """Test that impersonation can be changed multiple times."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        # First impersonation
        session.set_impersonation(target_user)
        assert session.effective_user.username == "target_user"

        # Change impersonation to different user
        session.set_impersonation(power_user)
        assert session.effective_user.username == "power_user"

        # Clear impersonation
        session.clear_impersonation()
        assert session.effective_user.username == "admin_user"


class TestMCPSessionStateWithGroups:
    """Test MCPSessionState behavior with group memberships."""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user."""
        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sales_user(self) -> User:
        """Create a sales user (simulating group membership via role)."""
        return User(
            username="sales_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_impersonation_uses_target_user_permissions(
        self, admin_user: User, sales_user: User
    ):
        """Test that effective permissions come from impersonated user."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        # Admin has manage_users permission
        assert session.effective_user.has_permission("manage_users") is True

        # Set impersonation to sales_user
        session.set_impersonation(sales_user)

        # Now effective user should NOT have manage_users (they're normal_user)
        assert session.effective_user.has_permission("manage_users") is False
        # But should have query_repos (normal user base permission)
        assert session.effective_user.has_permission("query_repos") is True

    def test_impersonation_constrains_to_target_permissions(
        self, admin_user: User, sales_user: User
    ):
        """Test that impersonation constrains to target user's permissions, not elevates."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(sales_user)

        # Verify the effective user has ONLY the target user's permissions
        # Admin-only permissions should be denied
        assert session.effective_user.has_permission("manage_users") is False
        assert session.effective_user.has_permission("manage_golden_repos") is False
        assert session.effective_user.has_permission("repository:admin") is False

        # Power user permissions should be denied
        assert session.effective_user.has_permission("activate_repos") is False
        assert session.effective_user.has_permission("repository:write") is False

        # Normal user permissions should be granted
        assert session.effective_user.has_permission("query_repos") is True
        assert session.effective_user.has_permission("repository:read") is True


class TestMCPSessionStateAdminChecks:
    """Test MCPSessionState admin-only impersonation requirement."""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user."""
        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def power_user(self) -> User:
        """Create a power user."""
        return User(
            username="power_user",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def normal_user(self) -> User:
        """Create a normal user."""
        return User(
            username="normal_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self) -> User:
        """Create a target user for impersonation."""
        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_can_impersonate_returns_true_for_admin(self, admin_user: User):
        """Test that admin users are allowed to impersonate."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )

        assert session.can_impersonate() is True

    def test_can_impersonate_returns_false_for_power_user(self, power_user: User):
        """Test that power users are NOT allowed to impersonate."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=power_user
        )

        assert session.can_impersonate() is False

    def test_can_impersonate_returns_false_for_normal_user(self, normal_user: User):
        """Test that normal users are NOT allowed to impersonate."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=normal_user
        )

        assert session.can_impersonate() is False

    def test_try_set_impersonation_succeeds_for_admin(
        self, admin_user: User, target_user: User
    ):
        """Test try_set_impersonation succeeds for admin users."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        result = session.try_set_impersonation(target_user)

        assert result.success is True
        assert result.error is None
        assert session.impersonated_user == target_user

    def test_try_set_impersonation_fails_for_power_user(
        self, power_user: User, target_user: User
    ):
        """Test try_set_impersonation fails for power users."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=power_user
        )
        result = session.try_set_impersonation(target_user)

        assert result.success is False
        assert result.error == "Impersonation requires ADMIN role"
        assert session.impersonated_user is None

    def test_try_set_impersonation_fails_for_normal_user(
        self, normal_user: User, target_user: User
    ):
        """Test try_set_impersonation fails for normal users."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=normal_user
        )
        result = session.try_set_impersonation(target_user)

        assert result.success is False
        assert result.error == "Impersonation requires ADMIN role"
        assert session.impersonated_user is None


class TestMCPSessionStateToDict:
    """Test MCPSessionState serialization to dictionary."""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user."""
        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self) -> User:
        """Create a target user."""
        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_to_dict_without_impersonation(self, admin_user: User):
        """Test to_dict when not impersonating."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        result = session.to_dict()

        assert result["session_id"] == "session-123"
        assert result["authenticated_user"] == "admin_user"
        assert result["impersonated_user"] is None
        assert result["is_impersonating"] is False

    def test_to_dict_with_impersonation(self, admin_user: User, target_user: User):
        """Test to_dict when impersonating."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)
        result = session.to_dict()

        assert result["session_id"] == "session-123"
        assert result["authenticated_user"] == "admin_user"
        assert result["impersonated_user"] == "target_user"
        assert result["is_impersonating"] is True

    def test_to_dict_includes_effective_user_when_not_impersonating(
        self, admin_user: User
    ):
        """Test to_dict includes effective_user when not impersonating (HIGH 1 fix)."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        result = session.to_dict()

        # effective_user should be included and match authenticated_user
        assert "effective_user" in result
        assert result["effective_user"] == "admin_user"

    def test_to_dict_includes_effective_user_when_impersonating(
        self, admin_user: User, target_user: User
    ):
        """Test to_dict includes effective_user when impersonating (HIGH 1 fix)."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)
        result = session.to_dict()

        # effective_user should be the impersonated user
        assert "effective_user" in result
        assert result["effective_user"] == "target_user"


class TestMCPSessionStateThreadSafety:
    """Test MCPSessionState thread safety (MEDIUM 1 fix)."""

    @pytest.fixture
    def admin_user(self) -> User:
        """Create an admin user."""
        return User(
            username="admin_user",
            password_hash="hashed_password",
            role=UserRole.ADMIN,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def target_user(self) -> User:
        """Create a target user."""
        return User(
            username="target_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def second_target_user(self) -> User:
        """Create a second target user."""
        return User(
            username="second_target",
            password_hash="hashed_password",
            role=UserRole.POWER_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_concurrent_set_impersonation_is_thread_safe(
        self, admin_user: User, target_user: User, second_target_user: User
    ):
        """Test that concurrent set_impersonation calls are thread-safe."""
        import threading
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        errors = []

        def set_impersonation_target():
            try:
                for _ in range(100):
                    session.set_impersonation(target_user)
            except Exception as e:
                errors.append(e)

        def set_impersonation_second():
            try:
                for _ in range(100):
                    session.set_impersonation(second_target_user)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=set_impersonation_target)
        t2 = threading.Thread(target=set_impersonation_second)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # Impersonation should be set to one of the targets
        assert session.impersonated_user in [target_user, second_target_user]

    def test_concurrent_read_write_is_thread_safe(
        self, admin_user: User, target_user: User
    ):
        """Test that concurrent reads and writes are thread-safe."""
        import threading
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        errors = []
        effective_users = []

        def write_impersonation():
            try:
                for _ in range(100):
                    session.set_impersonation(target_user)
                    session.clear_impersonation()
            except Exception as e:
                errors.append(e)

        def read_effective_user():
            try:
                for _ in range(100):
                    user = session.effective_user
                    effective_users.append(user.username)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=write_impersonation)
        t2 = threading.Thread(target=read_effective_user)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # All read usernames should be valid
        for username in effective_users:
            assert username in ["admin_user", "target_user"]

    def test_concurrent_clear_impersonation_is_thread_safe(
        self, admin_user: User, target_user: User
    ):
        """Test that concurrent clear_impersonation calls are thread-safe."""
        import threading
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="session-123", authenticated_user=admin_user
        )
        session.set_impersonation(target_user)
        errors = []

        def clear_impersonation():
            try:
                for _ in range(100):
                    session.clear_impersonation()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=clear_impersonation) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # Impersonation should be cleared
        assert session.impersonated_user is None
