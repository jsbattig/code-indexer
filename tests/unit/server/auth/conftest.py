"""
Fixtures for auth tests to ensure clean state between tests.

Following CLAUDE.md principles: Real implementations, no mocks.
"""

import pytest
from code_indexer.server.auth.rate_limiter import (
    password_change_rate_limiter,
    refresh_token_rate_limiter,
)
from code_indexer.server.auth.session_manager import session_manager


@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Reset all singleton instances before each test to ensure clean state.

    This is critical for tests that rely on rate limiting, session management,
    and token tracking which use global singleton instances.
    """
    # Clear rate limiter state
    password_change_rate_limiter._attempts.clear()
    refresh_token_rate_limiter._attempts.clear()

    # Clear session manager state
    session_manager._invalidated_sessions.clear()
    session_manager._password_change_timestamps.clear()

    yield

    # Clean up after test as well
    password_change_rate_limiter._attempts.clear()
    refresh_token_rate_limiter._attempts.clear()
    session_manager._invalidated_sessions.clear()
    session_manager._password_change_timestamps.clear()
