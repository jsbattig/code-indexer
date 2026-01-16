"""
Unit tests for SessionRegistry - Session State Management for MCP Protocol.

Story #722: Session Impersonation for Delegated Queries - Critical fixes

These tests follow TDD methodology - written first, implementation comes after.
Tests the SessionRegistry singleton that manages MCPSessionState instances
across multiple tool calls within a session.
"""

import pytest
import threading
from datetime import datetime, timezone
from typing import List


class TestSessionRegistryBasics:
    """Test SessionRegistry basic operations."""

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
    def normal_user(self):
        """Create a normal user for testing."""
        from code_indexer.server.auth.user_manager import User, UserRole

        return User(
            username="normal_user",
            password_hash="hashed_password",
            role=UserRole.NORMAL_USER,
            created_at=datetime.now(timezone.utc),
        )

    def test_session_registry_import(self):
        """Test that SessionRegistry can be imported."""
        from code_indexer.server.mcp.session_registry import SessionRegistry

        assert SessionRegistry is not None

    def test_session_registry_is_singleton(self):
        """Test that SessionRegistry follows singleton pattern."""
        from code_indexer.server.mcp.session_registry import (
            get_session_registry,
            SessionRegistry,
        )

        registry1 = get_session_registry()
        registry2 = get_session_registry()

        assert registry1 is registry2
        assert isinstance(registry1, SessionRegistry)

    def test_get_or_create_session_creates_new_session(self, admin_user):
        """Test that get_or_create_session creates a new MCPSessionState."""
        from code_indexer.server.mcp.session_registry import get_session_registry
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        registry = get_session_registry()
        session_id = "test-session-001"

        # Clear any existing session first
        registry.remove_session(session_id)

        session = registry.get_or_create_session(session_id, admin_user)

        assert session is not None
        assert isinstance(session, MCPSessionState)
        assert session.session_id == session_id
        assert session.authenticated_user == admin_user

        # Cleanup
        registry.remove_session(session_id)

    def test_get_or_create_session_returns_existing_session(self, admin_user):
        """Test that get_or_create_session returns existing session on second call."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-002"

        # Clear any existing session first
        registry.remove_session(session_id)

        session1 = registry.get_or_create_session(session_id, admin_user)
        session2 = registry.get_or_create_session(session_id, admin_user)

        assert session1 is session2

        # Cleanup
        registry.remove_session(session_id)

    def test_get_session_returns_existing_session(self, admin_user):
        """Test that get_session returns an existing session."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-003"

        # Clear any existing session first
        registry.remove_session(session_id)

        # Create session
        created_session = registry.get_or_create_session(session_id, admin_user)

        # Get session
        retrieved_session = registry.get_session(session_id)

        assert retrieved_session is created_session

        # Cleanup
        registry.remove_session(session_id)

    def test_get_session_returns_none_for_nonexistent(self):
        """Test that get_session returns None for non-existent session."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session = registry.get_session("nonexistent-session-id")

        assert session is None

    def test_remove_session_removes_existing(self, admin_user):
        """Test that remove_session removes an existing session."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "test-session-004"

        # Create session
        registry.get_or_create_session(session_id, admin_user)

        # Verify it exists
        assert registry.get_session(session_id) is not None

        # Remove session
        result = registry.remove_session(session_id)

        assert result is True
        assert registry.get_session(session_id) is None

    def test_remove_session_returns_false_for_nonexistent(self):
        """Test that remove_session returns False for non-existent session."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        result = registry.remove_session("nonexistent-session-id-999")

        assert result is False

    def test_session_count_returns_correct_count(self, admin_user, normal_user):
        """Test that session_count returns correct number of sessions."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()

        # Clear test sessions
        registry.remove_session("count-test-001")
        registry.remove_session("count-test-002")

        initial_count = registry.session_count()

        # Create two sessions
        registry.get_or_create_session("count-test-001", admin_user)
        registry.get_or_create_session("count-test-002", normal_user)

        assert registry.session_count() == initial_count + 2

        # Cleanup
        registry.remove_session("count-test-001")
        registry.remove_session("count-test-002")


class TestSessionRegistryImpersonationPersistence:
    """Test that impersonation persists across tool calls via registry."""

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

    def test_impersonation_persists_across_get_calls(self, admin_user, target_user):
        """Test that impersonation set in one call persists in subsequent get_session calls."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "impersonation-persist-001"

        # Clear any existing session
        registry.remove_session(session_id)

        # Create session and set impersonation
        session = registry.get_or_create_session(session_id, admin_user)
        session.set_impersonation(target_user)

        # Verify impersonation was set
        assert session.is_impersonating is True
        assert session.effective_user == target_user

        # Get session again (simulating another tool call)
        session_again = registry.get_session(session_id)

        # Verify impersonation persists
        assert session_again.is_impersonating is True
        assert session_again.effective_user == target_user
        assert session_again.authenticated_user == admin_user

        # Cleanup
        registry.remove_session(session_id)

    def test_impersonation_persists_across_get_or_create_calls(
        self, admin_user, target_user
    ):
        """Test that impersonation persists when using get_or_create_session."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "impersonation-persist-002"

        # Clear any existing session
        registry.remove_session(session_id)

        # First call - create session and set impersonation
        session1 = registry.get_or_create_session(session_id, admin_user)
        session1.set_impersonation(target_user)

        # Second call - should get same session with impersonation intact
        session2 = registry.get_or_create_session(session_id, admin_user)

        assert session2 is session1
        assert session2.is_impersonating is True
        assert session2.effective_user == target_user

        # Cleanup
        registry.remove_session(session_id)


class TestSessionRegistryThreadSafety:
    """Test SessionRegistry thread safety."""

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

    def test_concurrent_session_creation(self, admin_user):
        """Test that concurrent session creation is thread-safe."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_ids = [f"concurrent-test-{i}" for i in range(10)]

        # Clear test sessions
        for sid in session_ids:
            registry.remove_session(sid)

        created_sessions: List = []
        errors: List[Exception] = []

        def create_session(session_id):
            try:
                session = registry.get_or_create_session(session_id, admin_user)
                created_sessions.append(session)
            except Exception as e:
                errors.append(e)

        # Create sessions concurrently
        threads = [
            threading.Thread(target=create_session, args=(sid,)) for sid in session_ids
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors and all sessions created
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(created_sessions) == len(session_ids)

        # Verify all sessions are retrievable
        for sid in session_ids:
            assert registry.get_session(sid) is not None

        # Cleanup
        for sid in session_ids:
            registry.remove_session(sid)

    def test_concurrent_session_access(self, admin_user):
        """Test that concurrent session access is thread-safe."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        session_id = "concurrent-access-test"

        # Clear and create session
        registry.remove_session(session_id)
        registry.get_or_create_session(session_id, admin_user)

        retrieved_sessions: List = []
        errors: List[Exception] = []

        def get_session_func():
            try:
                for _ in range(100):
                    session = registry.get_session(session_id)
                    if session:
                        retrieved_sessions.append(session.session_id)
            except Exception as e:
                errors.append(e)

        # Access session concurrently from multiple threads
        threads = [threading.Thread(target=get_session_func) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(retrieved_sessions) == 500  # 5 threads * 100 iterations

        # Cleanup
        registry.remove_session(session_id)


class TestSessionRegistryClear:
    """Test SessionRegistry clear functionality."""

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

    def test_clear_all_removes_all_sessions(self, admin_user):
        """Test that clear_all removes all sessions."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()

        # Create some sessions
        registry.get_or_create_session("clear-test-001", admin_user)
        registry.get_or_create_session("clear-test-002", admin_user)
        registry.get_or_create_session("clear-test-003", admin_user)

        assert registry.session_count() >= 3

        # Clear all
        registry.clear_all()

        # Verify all cleared
        assert registry.session_count() == 0
        assert registry.get_session("clear-test-001") is None
        assert registry.get_session("clear-test-002") is None
        assert registry.get_session("clear-test-003") is None
