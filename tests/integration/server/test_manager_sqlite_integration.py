"""
Integration tests for manager-SQLite backend integration.

Story #702: Migrate Central JSON Files to SQLite

These tests verify that the manager classes can use SQLite backends
instead of JSON files while maintaining the same interface behavior.

Tests written FIRST following TDD methodology.
"""

from pathlib import Path
import sqlite3


class TestGlobalRegistryWithSqliteBackend:
    """Tests for GlobalRegistry integration with GlobalReposSqliteBackend."""

    def test_register_global_repo_uses_sqlite_when_configured(
        self, tmp_path: Path
    ) -> None:
        """
        Given GlobalRegistry initialized with use_sqlite=True
        When register_global_repo() is called
        Then the repo is stored in SQLite database.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry
        from code_indexer.server.storage.database_manager import DatabaseSchema
        import sqlite3

        # Setup: create database
        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Create golden repos directory structure
        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        # Initialize registry with SQLite backend
        registry = GlobalRegistry(
            golden_repos_dir=str(golden_repos_dir),
            use_sqlite=True,
            db_path=str(db_path),
        )

        # Register a repo
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/test/repo.git",
            index_path=str(tmp_path / "index"),
            enable_temporal=True,
            temporal_options={"max_commits": 1000},
        )

        # Verify it's in SQLite
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT alias_name, repo_name FROM global_repos WHERE alias_name = ?",
            ("test-repo-global",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "test-repo-global"
        assert row[1] == "test-repo"

    def test_get_global_repo_retrieves_from_sqlite(self, tmp_path: Path) -> None:
        """
        Given a repo stored in SQLite via GlobalRegistry
        When get_global_repo() is called
        Then the repo is retrieved from SQLite.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(
            golden_repos_dir=str(golden_repos_dir),
            use_sqlite=True,
            db_path=str(db_path),
        )

        registry.register_global_repo(
            repo_name="retrieve-repo",
            alias_name="retrieve-repo-global",
            repo_url="https://github.com/retrieve/repo.git",
            index_path=str(tmp_path / "index"),
        )

        result = registry.get_global_repo("retrieve-repo-global")

        assert result is not None
        assert result["alias_name"] == "retrieve-repo-global"
        assert result["repo_name"] == "retrieve-repo"

    def test_list_global_repos_returns_all_from_sqlite(self, tmp_path: Path) -> None:
        """
        Given multiple repos stored in SQLite via GlobalRegistry
        When list_global_repos() is called
        Then all repos are returned.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(
            golden_repos_dir=str(golden_repos_dir),
            use_sqlite=True,
            db_path=str(db_path),
        )

        registry.register_global_repo(
            repo_name="repo1",
            alias_name="repo1-global",
            repo_url=None,
            index_path=str(tmp_path / "index1"),
        )
        registry.register_global_repo(
            repo_name="repo2",
            alias_name="repo2-global",
            repo_url=None,
            index_path=str(tmp_path / "index2"),
        )

        result = registry.list_global_repos()

        assert len(result) == 2
        alias_names = [r["alias_name"] for r in result]
        assert "repo1-global" in alias_names
        assert "repo2-global" in alias_names

    def test_unregister_global_repo_removes_from_sqlite(self, tmp_path: Path) -> None:
        """
        Given a repo stored in SQLite
        When unregister_global_repo() is called
        Then the repo is removed from SQLite.
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(
            golden_repos_dir=str(golden_repos_dir),
            use_sqlite=True,
            db_path=str(db_path),
        )

        registry.register_global_repo(
            repo_name="to-delete",
            alias_name="to-delete-global",
            repo_url=None,
            index_path=str(tmp_path / "index"),
        )

        # Verify exists
        assert registry.get_global_repo("to-delete-global") is not None

        # Unregister
        registry.unregister_global_repo("to-delete-global")

        # Verify removed
        assert registry.get_global_repo("to-delete-global") is None

    def test_json_fallback_when_sqlite_disabled(self, tmp_path: Path) -> None:
        """
        Given GlobalRegistry initialized with use_sqlite=False
        When register_global_repo() is called
        Then the repo is stored in JSON file (backward compatible).
        """
        from code_indexer.global_repos.global_registry import GlobalRegistry
        import json

        golden_repos_dir = tmp_path / "golden_repos"
        golden_repos_dir.mkdir(parents=True)

        registry = GlobalRegistry(
            golden_repos_dir=str(golden_repos_dir),
            use_sqlite=False,
        )

        registry.register_global_repo(
            repo_name="json-repo",
            alias_name="json-repo-global",
            repo_url=None,
            index_path=str(tmp_path / "index"),
        )

        # Verify it's in JSON file
        json_file = golden_repos_dir / "global_registry.json"
        assert json_file.exists()

        with open(json_file) as f:
            data = json.load(f)

        assert "json-repo-global" in data
        assert data["json-repo-global"]["repo_name"] == "json-repo"


class TestUserManagerWithSqliteBackend:
    """Tests for UserManager integration with UsersSqliteBackend."""

    def test_create_user_uses_sqlite_when_configured(self, tmp_path: Path) -> None:
        """
        Given UserManager initialized with use_sqlite=True
        When create_user() is called
        Then the user is stored in SQLite database.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        # Create user - must meet password requirements
        manager.create_user(
            username="sqliteuser",
            password="StrongP@ssword123!",
            role=UserRole.ADMIN,
        )

        # Verify in SQLite
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT username, role FROM users WHERE username = ?",
            ("sqliteuser",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "sqliteuser"
        assert row[1] == "admin"

    def test_authenticate_user_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given UserManager with use_sqlite=True and a user in SQLite
        When authenticate_user() is called with correct credentials
        Then the user is authenticated from SQLite.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.create_user(
            username="authuser",
            password="StrongP@ssword123!",
            role=UserRole.NORMAL_USER,
        )

        user = manager.authenticate_user("authuser", "StrongP@ssword123!")

        assert user is not None
        assert user.username == "authuser"
        assert user.role == UserRole.NORMAL_USER

    def test_get_user_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given UserManager with use_sqlite=True and a user in SQLite
        When get_user() is called
        Then the user is retrieved from SQLite.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.create_user(
            username="getuser",
            password="StrongP@ssword123!",
            role=UserRole.POWER_USER,
        )

        user = manager.get_user("getuser")

        assert user is not None
        assert user.username == "getuser"
        assert user.role == UserRole.POWER_USER

    def test_get_all_users_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given UserManager with use_sqlite=True and multiple users in SQLite
        When get_all_users() is called
        Then all users are retrieved from SQLite.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.create_user(username="user1", password="StrongP@ssword123!", role=UserRole.ADMIN)
        manager.create_user(username="user2", password="StrongP@ssword456!", role=UserRole.NORMAL_USER)

        users = manager.get_all_users()

        assert len(users) == 2
        usernames = [u.username for u in users]
        assert "user1" in usernames
        assert "user2" in usernames

    def test_update_user_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given UserManager with use_sqlite=True and a user in SQLite
        When update_user() is called
        Then the user is updated in SQLite.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.create_user(
            username="updateuser",
            password="StrongP@ssword123!",
            role=UserRole.NORMAL_USER,
        )

        result = manager.update_user("updateuser", new_email="new@example.com")

        assert result is True

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT email FROM users WHERE username = ?",
            ("updateuser",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "new@example.com"

    def test_delete_user_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given UserManager with use_sqlite=True and a user in SQLite
        When delete_user() is called
        Then the user is deleted from SQLite.
        """
        from code_indexer.server.auth.user_manager import UserManager, UserRole
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        users_file = tmp_path / "users.json"
        manager = UserManager(
            users_file_path=str(users_file),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.create_user(
            username="deleteuser",
            password="StrongP@ssword123!",
            role=UserRole.NORMAL_USER,
        )

        assert manager.get_user("deleteuser") is not None

        result = manager.delete_user("deleteuser")

        assert result is True
        assert manager.get_user("deleteuser") is None


class TestPasswordChangeSessionManagerWithSqliteBackend:
    """Tests for PasswordChangeSessionManager with SessionsSqliteBackend."""

    def test_invalidate_session_uses_sqlite(self, tmp_path: Path) -> None:
        """
        Given PasswordChangeSessionManager with use_sqlite=True
        When invalidate_specific_token() is called
        Then the session is stored in SQLite.
        """
        from code_indexer.server.auth.session_manager import (
            PasswordChangeSessionManager,
        )
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = PasswordChangeSessionManager(
            session_file_path=str(tmp_path / "sessions.json"),
            use_sqlite=True,
            db_path=str(db_path),
        )

        manager.invalidate_specific_token("testuser", "token-xyz")

        # Verify in SQLite
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT username, token_id FROM invalidated_sessions WHERE username = ? AND token_id = ?",
            ("testuser", "token-xyz"),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None


class TestCITokenManagerWithSqliteBackend:
    """Tests for CITokenManager integration with CITokensSqliteBackend."""

    def test_save_token_uses_sqlite_when_configured(self, tmp_path: Path) -> None:
        """
        Given CITokenManager initialized with use_sqlite=True
        When save_token() is called
        Then the encrypted token is stored in SQLite.
        """
        from code_indexer.server.services.ci_token_manager import CITokenManager
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "data" / "cidx_server.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = CITokenManager(
            server_dir_path=str(tmp_path),
            use_sqlite=True,
            db_path=str(db_path),
        )

        # Valid GitHub token format
        manager.save_token(
            platform="github",
            token="ghp_aB1cD2eF3gH4iJ5kL6mN7oP8qR9sT0uV1wX2",
        )

        # Verify in SQLite (encrypted, so just check existence)
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT platform, encrypted_token FROM ci_tokens WHERE platform = ?",
            ("github",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "github"
        assert row[1] is not None  # Encrypted token stored
