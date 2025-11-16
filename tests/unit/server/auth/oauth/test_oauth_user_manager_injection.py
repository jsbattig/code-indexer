"""Test UserManager dependency injection in OAuth routes."""

from code_indexer.server.auth.oauth.routes import get_user_manager
from code_indexer.server.auth.user_manager import UserManager


class TestUserManagerInjection:
    """Test that UserManager can be overridden via dependency injection."""

    def test_get_user_manager_dependency_exists(self):
        """Test that get_user_manager dependency function exists."""
        # This test will fail if get_user_manager doesn't exist
        assert callable(get_user_manager)

    def test_get_user_manager_returns_user_manager_instance(self):
        """Test that get_user_manager returns a UserManager instance."""
        manager = get_user_manager()
        assert isinstance(manager, UserManager)
