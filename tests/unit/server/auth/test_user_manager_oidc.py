"""Tests for OIDC-related methods in UserManager."""

import tempfile
from pathlib import Path

import pytest

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


class TestUserManagerOIDCSQLite:
    """
    Test OIDC-related methods in UserManager with SQLite backend.

    Story #702 SSO fix: These methods were not updated for SQLite mode,
    causing AttributeError when trying to access users_file_path in SQLite mode.
    """

    @pytest.fixture
    def sqlite_db_path(self, tmp_path: Path) -> str:
        """Create and initialize a SQLite database for testing."""
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        return str(db_path)

    def test_get_user_by_email_sqlite_mode_returns_user(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with a user that has an email
        When get_user_by_email() is called
        Then it returns the User object.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user with email
        manager.create_user("sqliteuser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.update_user("sqliteuser", new_email="sqlite@example.com")

        # Get user by email
        user = manager.get_user_by_email("sqlite@example.com")

        assert user is not None
        assert user.username == "sqliteuser"

    def test_get_user_by_email_sqlite_mode_case_insensitive(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with a user
        When get_user_by_email() is called with different case
        Then it returns the User object (case-insensitive search).
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user with mixed-case email
        manager.create_user("caseuser", "SecurePass123!@#", UserRole.ADMIN)
        manager.update_user("caseuser", new_email="Case@Example.COM")

        # Get user with lowercase email
        user = manager.get_user_by_email("case@example.com")

        assert user is not None
        assert user.username == "caseuser"

    def test_get_user_by_email_sqlite_mode_returns_none_when_not_found(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode without a matching user
        When get_user_by_email() is called
        Then it returns None.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user with different email
        manager.create_user("otheruser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.update_user("otheruser", new_email="other@example.com")

        # Get user by non-existent email
        user = manager.get_user_by_email("nonexistent@example.com")

        assert user is None

    def test_set_oidc_identity_sqlite_mode_stores_identity(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with an existing user
        When set_oidc_identity() is called
        Then the OIDC identity is stored in SQLite database.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user
        manager.create_user("oidcuser", "SecurePass123!@#", UserRole.NORMAL_USER)

        # Set OIDC identity
        identity = {
            "subject": "sqlite-oidc-123",
            "email": "oidc@example.com",
            "linked_at": "2025-01-15T10:30:00Z",
            "last_login": "2025-01-15T10:30:00Z",
        }
        result = manager.set_oidc_identity("oidcuser", identity)

        assert result is True

        # Verify via the SQLite backend directly
        user_data = manager._sqlite_backend.get_user("oidcuser")
        assert user_data is not None
        assert user_data["oidc_identity"] is not None
        assert user_data["oidc_identity"]["subject"] == "sqlite-oidc-123"

    def test_set_oidc_identity_sqlite_mode_returns_false_for_nonexistent(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode without the specified user
        When set_oidc_identity() is called
        Then it returns False.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        identity = {"subject": "oidc-12345"}
        result = manager.set_oidc_identity("nonexistent", identity)

        assert result is False

    def test_set_oidc_identity_sqlite_mode_overwrites_existing(self, sqlite_db_path: str) -> None:
        """
        Given a user with existing OIDC identity in SQLite mode
        When set_oidc_identity() is called with new identity
        Then the identity is overwritten.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user
        manager.create_user("overwrite", "SecurePass123!@#", UserRole.NORMAL_USER)

        # Set initial identity
        identity1 = {"subject": "old-subject", "email": "old@example.com"}
        manager.set_oidc_identity("overwrite", identity1)

        # Overwrite with new identity
        identity2 = {"subject": "new-subject", "email": "new@example.com"}
        manager.set_oidc_identity("overwrite", identity2)

        # Verify new identity
        user_data = manager._sqlite_backend.get_user("overwrite")
        assert user_data["oidc_identity"]["subject"] == "new-subject"
        assert user_data["oidc_identity"]["email"] == "new@example.com"
