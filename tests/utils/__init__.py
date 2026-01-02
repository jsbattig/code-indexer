"""
Test utilities package for CIDX multi-user server testing.

This package provides comprehensive testing infrastructure including:
- Test data factories for consistent test environments
- Server lifecycle management helpers
- Authentication testing utilities
- Container management for tests
- Repository management utilities
"""

from .test_data_factory import TestDataFactory, TestRepository, TestUser
from .server_test_helpers import ServerTestHelper, ServerLifecycleManager
from .auth_test_helpers import AuthTestHelper, JWTTokenManager


class EnvironmentManager:
    """
    Stub class for removed container infrastructure.

    Tests importing this will fail since container support was removed.
    This stub prevents collection errors.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "Container infrastructure was removed - EnvironmentManager cannot be instantiated"
        )


__all__ = [
    "TestDataFactory",
    "TestRepository",
    "TestUser",
    "ServerTestHelper",
    "ServerLifecycleManager",
    "AuthTestHelper",
    "JWTTokenManager",
    "EnvironmentManager",
]
