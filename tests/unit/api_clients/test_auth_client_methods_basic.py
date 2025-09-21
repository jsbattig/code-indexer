"""Basic tests for AuthAPIClient password management methods.

Simple tests to verify methods exist and have correct signatures.
"""

from pathlib import Path

from code_indexer.api_clients.auth_client import AuthAPIClient


class TestAuthAPIClientBasic:
    """Basic tests for AuthAPIClient password management."""

    def setup_method(self):
        """Set up test fixtures."""
        self.server_url = "https://test.example.com"
        self.project_root = Path("/test/project")
        self.credentials = {"username": "testuser", "password": "testpass"}

        self.client = AuthAPIClient(
            server_url=self.server_url,
            project_root=self.project_root,
            credentials=self.credentials,
        )

    def test_change_password_method_exists(self):
        """Test that change_password method exists."""
        assert hasattr(self.client, "change_password")
        assert callable(getattr(self.client, "change_password"))

    def test_reset_password_method_exists(self):
        """Test that reset_password method exists."""
        assert hasattr(self.client, "reset_password")
        assert callable(getattr(self.client, "reset_password"))

    def test_change_password_method_signature(self):
        """Test change_password method signature."""
        import inspect

        sig = inspect.signature(self.client.change_password)
        params = list(sig.parameters.keys())

        # Should have current_password and new_password parameters
        assert "current_password" in params
        assert "new_password" in params
        assert len(params) == 2  # Excluding self

    def test_reset_password_method_signature(self):
        """Test reset_password method signature."""
        import inspect

        sig = inspect.signature(self.client.reset_password)
        params = list(sig.parameters.keys())

        # Should have username parameter
        assert "username" in params
        assert len(params) == 1  # Excluding self
