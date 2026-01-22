"""
Unit tests for SessionRegistry TTL-Based Cleanup - Story #731.

This module tests the TTL-based session cleanup functionality added to prevent
memory leaks from accumulated MCP sessions.

Tests follow TDD methodology - written first, implementation comes after.

Acceptance Criteria tested:
- AC1: MCPSessionState tracks last_activity timestamp
- AC2: last_activity is updated on each session access via get_or_create_session()
- AC3: Background cleanup task removes sessions idle > TTL (configurable)
- AC4: Cleanup task runs periodically (configurable interval)
- AC5: Cleanup logs count of removed sessions for observability
- AC6: Cleanup is registered in app startup
- AC7: Unit tests verify TTL cleanup behavior
"""

import asyncio
import pytest
import logging
from datetime import datetime, timezone, timedelta
from typing import List


class TestMCPSessionStateLastActivity:
    """Test MCPSessionState last_activity tracking (AC1, AC2)."""

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

    def test_last_activity_is_set_on_session_creation(self, admin_user):
        """Test that last_activity is set when MCPSessionState is created (AC1)."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        before_creation = datetime.now(timezone.utc)
        session = MCPSessionState(
            session_id="test-session", authenticated_user=admin_user
        )
        after_creation = datetime.now(timezone.utc)

        # last_activity should be set during creation
        assert hasattr(session, "last_activity")
        assert session.last_activity is not None
        assert isinstance(session.last_activity, datetime)

        # Timestamp should be between before and after creation
        assert before_creation <= session.last_activity <= after_creation

    def test_touch_updates_last_activity(self, admin_user):
        """Test that touch() updates last_activity timestamp (AC2)."""
        from code_indexer.server.auth.mcp_session_state import MCPSessionState
        import time

        session = MCPSessionState(
            session_id="test-session", authenticated_user=admin_user
        )
        original_activity = session.last_activity

        # Wait a small amount to ensure timestamp changes
        time.sleep(0.01)

        # Touch the session
        session.touch()

        # last_activity should be updated
        assert session.last_activity > original_activity

    def test_touch_is_thread_safe(self, admin_user):
        """Test that touch() is thread-safe for concurrent access."""
        import threading
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="test-session", authenticated_user=admin_user
        )
        errors: List[Exception] = []

        def touch_repeatedly():
            try:
                for _ in range(100):
                    session.touch()
            except Exception as e:
                errors.append(e)

        # Run touch from multiple threads
        threads = [threading.Thread(target=touch_repeatedly) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # last_activity should still be valid
        assert session.last_activity is not None

    def test_last_activity_property_is_thread_safe(self, admin_user):
        """Test that last_activity property read is thread-safe."""
        import threading
        from code_indexer.server.auth.mcp_session_state import MCPSessionState

        session = MCPSessionState(
            session_id="test-session", authenticated_user=admin_user
        )
        errors: List[Exception] = []
        activities: List[datetime] = []

        def read_activity():
            try:
                for _ in range(100):
                    activities.append(session.last_activity)
            except Exception as e:
                errors.append(e)

        def update_activity():
            try:
                for _ in range(100):
                    session.touch()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=read_activity)
        t2 = threading.Thread(target=update_activity)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # No errors should occur
        assert len(errors) == 0, f"Thread safety errors: {errors}"
        # All read activities should be valid datetimes
        assert all(isinstance(a, datetime) for a in activities)


class TestSessionRegistryTouchOnAccess:
    """Test that SessionRegistry updates last_activity on session access (AC2)."""

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
    def fresh_registry(self):
        """Create a fresh registry for testing."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        # Clear all sessions for clean test
        registry.clear_all()
        return registry

    def test_get_or_create_session_touches_existing_session(
        self, admin_user, fresh_registry
    ):
        """Test that get_or_create_session() calls touch() on existing session (AC2)."""
        import time

        session_id = "touch-test-001"

        # Create session
        session = fresh_registry.get_or_create_session(session_id, admin_user)
        original_activity = session.last_activity

        # Wait to ensure time passes
        time.sleep(0.01)

        # Get same session again
        session_again = fresh_registry.get_or_create_session(session_id, admin_user)

        # last_activity should be updated
        assert session_again.last_activity > original_activity
        assert session is session_again  # Same session object

    def test_get_session_touches_existing_session(self, admin_user, fresh_registry):
        """Test that get_session() calls touch() on existing session (AC2)."""
        import time

        session_id = "touch-test-002"

        # Create session
        session = fresh_registry.get_or_create_session(session_id, admin_user)
        original_activity = session.last_activity

        # Wait to ensure time passes
        time.sleep(0.01)

        # Get session via get_session()
        session_again = fresh_registry.get_session(session_id)

        # last_activity should be updated
        assert session_again.last_activity > original_activity

    def test_get_session_returns_none_for_nonexistent_without_touching(
        self, fresh_registry
    ):
        """Test that get_session() returns None for non-existent session (no touch needed)."""
        result = fresh_registry.get_session("nonexistent-session-xyz")
        assert result is None


class TestSessionRegistryCleanup:
    """Test SessionRegistry cleanup_stale_sessions functionality (AC3, AC5)."""

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
    def fresh_registry(self):
        """Create a fresh registry for testing."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        registry.clear_all()
        # Stop any running cleanup task
        registry.stop_background_cleanup()
        return registry

    def test_cleanup_removes_stale_sessions(self, admin_user, fresh_registry):
        """Test that cleanup_stale_sessions() removes sessions older than TTL (AC3)."""
        # Create session
        session_id = "stale-session-001"
        session = fresh_registry.get_or_create_session(session_id, admin_user)

        # Manually set last_activity to be old (2 hours ago)
        with session._lock:
            session._last_activity = datetime.now(timezone.utc) - timedelta(hours=2)

        # Set TTL to 1 hour
        fresh_registry._ttl_seconds = 3600  # 1 hour

        # Run cleanup
        removed_count = fresh_registry.cleanup_stale_sessions()

        # Session should be removed
        assert removed_count == 1
        assert fresh_registry.get_session(session_id) is None

    def test_cleanup_keeps_active_sessions(self, admin_user, fresh_registry):
        """Test that cleanup_stale_sessions() keeps sessions within TTL (AC3)."""
        # Create session (recent activity)
        session_id = "active-session-001"
        fresh_registry.get_or_create_session(session_id, admin_user)

        # Set TTL to 1 hour
        fresh_registry._ttl_seconds = 3600  # 1 hour

        # Run cleanup
        removed_count = fresh_registry.cleanup_stale_sessions()

        # Session should NOT be removed
        assert removed_count == 0
        assert fresh_registry.get_session(session_id) is not None

    def test_cleanup_returns_count_of_removed_sessions(
        self, admin_user, fresh_registry
    ):
        """Test that cleanup_stale_sessions() returns correct count (AC3, AC5)."""
        # Create multiple sessions
        for i in range(5):
            session = fresh_registry.get_or_create_session(
                f"cleanup-count-{i}", admin_user
            )
            # Make first 3 stale
            if i < 3:
                with session._lock:
                    session._last_activity = datetime.now(timezone.utc) - timedelta(
                        hours=2
                    )

        # Set TTL to 1 hour
        fresh_registry._ttl_seconds = 3600

        # Run cleanup
        removed_count = fresh_registry.cleanup_stale_sessions()

        # Exactly 3 sessions should be removed
        assert removed_count == 3
        # 2 active sessions should remain
        assert fresh_registry.session_count() == 2

    def test_cleanup_logs_when_sessions_removed(
        self, admin_user, fresh_registry, caplog
    ):
        """Test that cleanup logs the count of removed sessions (AC5)."""
        # Create a stale session
        session_id = "log-test-session"
        session = fresh_registry.get_or_create_session(session_id, admin_user)
        with session._lock:
            session._last_activity = datetime.now(timezone.utc) - timedelta(hours=2)

        fresh_registry._ttl_seconds = 3600

        # Run cleanup with logging captured
        with caplog.at_level(logging.INFO):
            removed_count = fresh_registry.cleanup_stale_sessions()

        # Should log the removal
        assert removed_count == 1
        assert "Cleaned up 1 stale MCP sessions" in caplog.text

    def test_cleanup_does_not_log_when_no_sessions_removed(
        self, admin_user, fresh_registry, caplog
    ):
        """Test that cleanup does not log when no sessions are removed (AC5)."""
        # Create an active session
        fresh_registry.get_or_create_session("active-no-log", admin_user)
        fresh_registry._ttl_seconds = 3600

        # Run cleanup with logging captured
        with caplog.at_level(logging.INFO):
            removed_count = fresh_registry.cleanup_stale_sessions()

        # Should not log anything about cleanup
        assert removed_count == 0
        assert "Cleaned up" not in caplog.text


class TestSessionRegistryBackgroundCleanup:
    """Test SessionRegistry background cleanup task (AC3, AC4)."""

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
    def fresh_registry(self):
        """Create a fresh registry for testing."""
        from code_indexer.server.mcp.session_registry import get_session_registry

        registry = get_session_registry()
        registry.clear_all()
        registry.stop_background_cleanup()
        return registry

    @pytest.mark.asyncio
    async def test_start_background_cleanup_creates_task(self, fresh_registry):
        """Test that start_background_cleanup creates an asyncio task (AC4)."""
        fresh_registry.start_background_cleanup(
            ttl_seconds=3600,
            cleanup_interval_seconds=900,
        )

        # Task should be created and running
        assert fresh_registry._cleanup_task is not None
        assert not fresh_registry._cleanup_task.done()

        # Cleanup
        fresh_registry.stop_background_cleanup()
        await asyncio.sleep(0.01)  # Allow task to cancel

    @pytest.mark.asyncio
    async def test_stop_background_cleanup_cancels_task(self, fresh_registry):
        """Test that stop_background_cleanup cancels the task (AC4)."""
        fresh_registry.start_background_cleanup(
            ttl_seconds=3600,
            cleanup_interval_seconds=900,
        )
        task = fresh_registry._cleanup_task

        fresh_registry.stop_background_cleanup()
        await asyncio.sleep(0.01)  # Allow task to cancel

        # Task should be cancelled
        assert task.cancelled() or task.done()

    @pytest.mark.asyncio
    async def test_background_cleanup_uses_configured_ttl(
        self, admin_user, fresh_registry
    ):
        """Test that background cleanup uses configured TTL value (AC3, AC4)."""
        # Start cleanup with short TTL (1 second) and very short interval
        fresh_registry.start_background_cleanup(
            ttl_seconds=1,
            cleanup_interval_seconds=0.1,  # 100ms for testing
        )

        # Create a session
        session_id = "background-ttl-test"
        session = fresh_registry.get_or_create_session(session_id, admin_user)

        # Make session stale (2 seconds old)
        with session._lock:
            session._last_activity = datetime.now(timezone.utc) - timedelta(seconds=2)

        # Wait for cleanup to run
        await asyncio.sleep(0.2)

        # Session should be removed by background cleanup
        assert fresh_registry.get_session(session_id) is None

        # Cleanup
        fresh_registry.stop_background_cleanup()

    @pytest.mark.asyncio
    async def test_start_background_cleanup_is_idempotent(self, fresh_registry):
        """Test that calling start_background_cleanup twice doesn't create duplicate tasks."""
        fresh_registry.start_background_cleanup(
            ttl_seconds=3600,
            cleanup_interval_seconds=900,
        )
        first_task = fresh_registry._cleanup_task

        # Call start again
        fresh_registry.start_background_cleanup(
            ttl_seconds=3600,
            cleanup_interval_seconds=900,
        )
        second_task = fresh_registry._cleanup_task

        # Should be the same task (not creating duplicates)
        assert first_task is second_task

        # Cleanup
        fresh_registry.stop_background_cleanup()
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_start_background_cleanup_logs_configuration(
        self, fresh_registry, caplog
    ):
        """Test that start_background_cleanup logs the configuration (AC5)."""
        with caplog.at_level(logging.INFO):
            fresh_registry.start_background_cleanup(
                ttl_seconds=3600,
                cleanup_interval_seconds=900,
            )

        # Should log configuration
        assert "Session cleanup started" in caplog.text
        assert "TTL=3600s" in caplog.text
        assert "interval=900s" in caplog.text

        # Cleanup
        fresh_registry.stop_background_cleanup()
        await asyncio.sleep(0.01)

    @pytest.mark.asyncio
    async def test_stop_background_cleanup_logs(self, fresh_registry, caplog):
        """Test that stop_background_cleanup logs when stopping (AC5)."""
        fresh_registry.start_background_cleanup(
            ttl_seconds=3600,
            cleanup_interval_seconds=900,
        )

        with caplog.at_level(logging.INFO):
            fresh_registry.stop_background_cleanup()
            await asyncio.sleep(0.01)

        # Should log stop
        assert "Session cleanup stopped" in caplog.text


class TestSessionRegistryDefaultConfiguration:
    """Test SessionRegistry default TTL configuration values."""

    def test_default_ttl_is_one_hour(self):
        """Test that default TTL is 1 hour (3600 seconds) as per AC3."""
        from code_indexer.server.mcp.session_registry import DEFAULT_SESSION_TTL_SECONDS

        assert DEFAULT_SESSION_TTL_SECONDS == 3600  # 1 hour

    def test_default_cleanup_interval_is_fifteen_minutes(self):
        """Test that default cleanup interval is 15 minutes (900 seconds) as per AC4."""
        from code_indexer.server.mcp.session_registry import (
            DEFAULT_CLEANUP_INTERVAL_SECONDS,
        )

        assert DEFAULT_CLEANUP_INTERVAL_SECONDS == 900  # 15 minutes
