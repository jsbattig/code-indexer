"""Tests for OIDC-related methods in UserManager."""

import tempfile
from pathlib import Path
from code_indexer.server.auth.user_manager import UserManager, UserRole


class TestUserManagerOIDC:
    """Test OIDC-related methods in UserManager."""

    def test_get_user_by_email_returns_user_when_exists(self):
        """Test that get_user_by_email returns user when email matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            users_file = str(Path(tmpdir) / "users.json")
            manager = UserManager(users_file_path=users_file)

            # Create a user
            manager.create_user("testuser", "SecurePass123!@#", UserRole.NORMAL_USER)

            # Add email to user using update_user
            manager.update_user("testuser", new_email="test@example.com")

            # Try to get user by email
            user = manager.get_user_by_email("test@example.com")

            assert user is not None
            assert user.username == "testuser"

    def test_set_oidc_identity_stores_identity_in_users_json(self):
        """Test that set_oidc_identity adds OIDC identity to user."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            users_file = str(Path(tmpdir) / "users.json")
            manager = UserManager(users_file_path=users_file)

            # Create a user
            manager.create_user("testuser", "SecurePass123!@#", UserRole.NORMAL_USER)

            # Set OIDC identity
            identity = {
                "subject": "oidc-12345",
                "email": "test@example.com",
                "linked_at": "2025-01-15T10:30:00Z",
                "last_login": "2025-01-15T10:30:00Z",
            }
            result = manager.set_oidc_identity("testuser", identity)

            assert result is True

            # Verify identity was stored
            with open(users_file, "r") as f:
                users_data = json.load(f)

            assert "oidc_identity" in users_data["testuser"]
            assert users_data["testuser"]["oidc_identity"]["subject"] == "oidc-12345"

    def test_remove_oidc_identity_removes_identity_from_user(self):
        """Test that remove_oidc_identity removes OIDC identity from user."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            users_file = str(Path(tmpdir) / "users.json")
            manager = UserManager(users_file_path=users_file)

            # Create a user with OIDC identity
            manager.create_user("testuser", "SecurePass123!@#", UserRole.NORMAL_USER)
            identity = {"subject": "oidc-12345", "email": "test@example.com"}
            manager.set_oidc_identity("testuser", identity)

            # Remove OIDC identity
            result = manager.remove_oidc_identity("testuser")

            assert result is True

            # Verify identity was removed
            with open(users_file, "r") as f:
                users_data = json.load(f)

            assert "oidc_identity" not in users_data["testuser"]

    def test_create_oidc_user_creates_user_without_password(self):
        """Test that create_oidc_user creates a user via JIT provisioning."""
        import json

        with tempfile.TemporaryDirectory() as tmpdir:
            users_file = str(Path(tmpdir) / "users.json")
            manager = UserManager(users_file_path=users_file)

            # Create OIDC user
            identity = {
                "subject": "oidc-12345",
                "email": "newuser@example.com",
                "linked_at": "2025-01-15T10:30:00Z",
            }
            user = manager.create_oidc_user(
                username="newuser",
                role=UserRole.NORMAL_USER,
                email="newuser@example.com",
                oidc_identity=identity,
            )

            # Verify user was created
            assert user is not None
            assert user.username == "newuser"
            assert user.role == UserRole.NORMAL_USER

            # Verify user data in users.json
            with open(users_file, "r") as f:
                users_data = json.load(f)

            assert "newuser" in users_data
            assert users_data["newuser"]["email"] == "newuser@example.com"
            assert users_data["newuser"]["oidc_identity"]["subject"] == "oidc-12345"
            assert "password_hash" in users_data["newuser"]  # Should have placeholder
