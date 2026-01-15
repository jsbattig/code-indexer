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

    def test_get_user_by_email_sqlite_mode_returns_user(
        self, sqlite_db_path: str
    ) -> None:
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

    def test_get_user_by_email_sqlite_mode_case_insensitive(
        self, sqlite_db_path: str
    ) -> None:
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

    def test_get_user_by_email_sqlite_mode_returns_none_when_not_found(
        self, sqlite_db_path: str
    ) -> None:
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

    def test_set_oidc_identity_sqlite_mode_stores_identity(
        self, sqlite_db_path: str
    ) -> None:
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

    def test_set_oidc_identity_sqlite_mode_returns_false_for_nonexistent(
        self, sqlite_db_path: str
    ) -> None:
        """
        Given a UserManager in SQLite mode without the specified user
        When set_oidc_identity() is called
        Then it returns False.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        identity = {"subject": "oidc-12345"}
        result = manager.set_oidc_identity("nonexistent", identity)

        assert result is False

    def test_set_oidc_identity_sqlite_mode_overwrites_existing(
        self, sqlite_db_path: str
    ) -> None:
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


class TestUserManagerSQLiteMCPAndOIDC:
    """
    Test MCP credential and OIDC methods in UserManager with SQLite backend.

    Story #702 SQLite migration: These methods were missing SQLite delegation,
    causing AttributeError when operating in SQLite mode.
    """

    @pytest.fixture
    def sqlite_db_path(self, tmp_path: Path) -> str:
        """Create and initialize a SQLite database for testing."""
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()
        return str(db_path)

    def test_delete_mcp_credential_sqlite_mode(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with a user with MCP credentials
        When delete_mcp_credential() is called
        Then it delegates to SQLite backend and removes the credential.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user and add MCP credentials
        manager.create_user("mcpuser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.add_mcp_credential(
            username="mcpuser",
            credential_id="cred-1",
            client_id="mcp_abc123",
            client_secret_hash="hash1",
            client_id_prefix="mcp_",
            name="Cred 1",
            created_at="2025-01-15T10:00:00Z",
        )
        manager.add_mcp_credential(
            username="mcpuser",
            credential_id="cred-2",
            client_id="mcp_def456",
            client_secret_hash="hash2",
            client_id_prefix="mcp_",
            name="Cred 2",
            created_at="2025-01-15T11:00:00Z",
        )

        # Delete one credential
        result = manager.delete_mcp_credential("mcpuser", "cred-1")

        assert result is True

        # Verify only one credential remains
        creds = manager.get_mcp_credentials("mcpuser")
        assert len(creds) == 1
        assert creds[0]["credential_id"] == "cred-2"

    def test_update_mcp_credential_last_used_sqlite_mode(
        self, sqlite_db_path: str
    ) -> None:
        """
        Given a UserManager in SQLite mode with a user with MCP credentials
        When update_mcp_credential_last_used() is called
        Then it delegates to SQLite backend and updates the timestamp.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create a user and add MCP credential
        manager.create_user("lastuseduser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.add_mcp_credential(
            username="lastuseduser",
            credential_id="cred-update",
            client_id="mcp_abc123",
            client_secret_hash="hash",
            client_id_prefix="mcp_",
            name="Update Cred",
            created_at="2025-01-15T10:00:00Z",
        )

        # Update last_used_at
        result = manager.update_mcp_credential_last_used("lastuseduser", "cred-update")

        assert result is True

        # Verify via SQLite backend
        user_data = manager._sqlite_backend.get_user("lastuseduser")
        assert user_data["mcp_credentials"][0]["last_used_at"] is not None

    def test_list_all_mcp_credentials_sqlite_mode(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with multiple users with MCP credentials
        When list_all_mcp_credentials() is called
        Then it delegates to SQLite backend and returns all credentials.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create users and add MCP credentials
        manager.create_user("user1", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.create_user("user2", "SecurePass123!@#", UserRole.ADMIN)
        manager.add_mcp_credential(
            username="user1",
            credential_id="cred-u1",
            client_id="mcp_u1",
            client_secret_hash="hash1",
            client_id_prefix="mcp_",
            name="User1 Cred",
            created_at="2025-01-15T10:00:00Z",
        )
        manager.add_mcp_credential(
            username="user2",
            credential_id="cred-u2",
            client_id="mcp_u2",
            client_secret_hash="hash2",
            client_id_prefix="mcp_",
            name="User2 Cred",
            created_at="2025-01-15T11:00:00Z",
        )

        # List all credentials
        credentials = manager.list_all_mcp_credentials()

        assert len(credentials) == 2
        usernames = [c["username"] for c in credentials]
        assert "user1" in usernames
        assert "user2" in usernames

    def test_remove_oidc_identity_sqlite_mode(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode with a user with OIDC identity
        When remove_oidc_identity() is called
        Then it delegates to SQLite backend and removes the identity.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create user and set OIDC identity
        manager.create_user("oidcremoveuser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.set_oidc_identity(
            "oidcremoveuser",
            {
                "subject": "oidc-123",
                "email": "oidc@example.com",
            },
        )

        # Verify identity exists
        user_data = manager._sqlite_backend.get_user("oidcremoveuser")
        assert user_data["oidc_identity"] is not None

        # Remove identity
        result = manager.remove_oidc_identity("oidcremoveuser")

        assert result is True

        # Verify identity is removed
        user_data = manager._sqlite_backend.get_user("oidcremoveuser")
        assert user_data["oidc_identity"] is None

    def test_create_oidc_user_sqlite_mode(self, sqlite_db_path: str) -> None:
        """
        Given a UserManager in SQLite mode
        When create_oidc_user() is called (JIT provisioning)
        Then it delegates to SQLite backend and creates user with OIDC identity.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        identity = {
            "subject": "oidc-jit-123",
            "email": "jit@example.com",
            "linked_at": "2025-01-15T10:00:00Z",
        }
        user = manager.create_oidc_user(
            username="jituser",
            role=UserRole.NORMAL_USER,
            email="jit@example.com",
            oidc_identity=identity,
        )

        # Verify user was created
        assert user is not None
        assert user.username == "jituser"
        assert user.role == UserRole.NORMAL_USER

        # Verify via SQLite backend
        user_data = manager._sqlite_backend.get_user("jituser")
        assert user_data is not None
        assert user_data["email"] == "jit@example.com"
        assert user_data["oidc_identity"]["subject"] == "oidc-jit-123"

    def test_get_mcp_credentials_with_secrets_sqlite_mode(
        self, sqlite_db_path: str
    ) -> None:
        """
        Given a UserManager in SQLite mode with a user with MCP credentials
        When get_mcp_credentials_with_secrets() is called
        Then it returns credentials including client_secret_hash for verification.
        """
        manager = UserManager(use_sqlite=True, db_path=sqlite_db_path)

        # Create user and add MCP credential
        manager.create_user("secretuser", "SecurePass123!@#", UserRole.NORMAL_USER)
        manager.add_mcp_credential(
            username="secretuser",
            credential_id="secret-cred",
            client_id="mcp_secret123",
            client_secret_hash="argon2$hash$goes$here",
            client_id_prefix="mcp_",
            name="Secret Cred",
            created_at="2025-01-15T10:00:00Z",
        )

        # Get credentials with secrets
        creds = manager.get_mcp_credentials_with_secrets("secretuser")

        assert len(creds) == 1
        assert creds[0]["credential_id"] == "secret-cred"
        assert creds[0]["client_id"] == "mcp_secret123"
        assert (
            creds[0]["client_secret_hash"] == "argon2$hash$goes$here"
        )  # Hash should be included
