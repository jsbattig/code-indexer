"""
Unit tests for database_manager.py - SQLite database connection pooling and schema management.

Tests written FIRST following TDD methodology.
Story #702: Migrate Central JSON Files to SQLite
"""

import sqlite3
from pathlib import Path

import pytest


class TestDatabaseSchema:
    """Tests for DatabaseSchema class that creates and manages SQLite tables."""

    def test_database_schema_creates_all_required_tables(self, tmp_path: Path) -> None:
        """
        Given a fresh database path
        When DatabaseSchema.initialize_database() is called
        Then all 11 tables are created with correct structure.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Verify all tables exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        expected_tables = [
            "ci_tokens",
            "global_repos",
            "invalidated_sessions",
            "password_change_timestamps",
            "ssh_key_hosts",
            "ssh_keys",
            "sync_jobs",
            "user_api_keys",
            "user_mcp_credentials",
            "user_oidc_identities",
            "users",
        ]
        assert sorted(tables) == sorted(expected_tables)

    def test_database_schema_global_repos_table_structure(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When we inspect global_repos table
        Then it has correct columns with proper types.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(global_repos)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {
            "alias_name": "TEXT",
            "repo_name": "TEXT",
            "repo_url": "TEXT",
            "index_path": "TEXT",
            "created_at": "TEXT",
            "last_refresh": "TEXT",
            "enable_temporal": "BOOLEAN",
            "temporal_options": "TEXT",
        }
        assert columns == expected_columns

    def test_database_schema_wal_mode_enabled(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When we check the journal mode
        Then WAL (Write-Ahead Logging) is enabled for concurrent reads.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        conn.close()

        assert journal_mode.lower() == "wal"

    def test_database_schema_users_table_structure(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When we inspect users table
        Then it has correct columns for normalized user data.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}
        conn.close()

        expected_columns = {
            "username": "TEXT",
            "password_hash": "TEXT",
            "role": "TEXT",
            "email": "TEXT",
            "created_at": "TEXT",
            "oidc_identity": "TEXT",
        }
        assert columns == expected_columns

    def test_database_schema_user_api_keys_foreign_key_cascade(
        self, tmp_path: Path
    ) -> None:
        """
        Given an initialized database with a user and api_key
        When we delete the user
        Then related api_keys are cascaded (deleted).
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Insert user
        conn.execute(
            """INSERT INTO users (username, password_hash, role, created_at)
               VALUES ('testuser', 'hash123', 'admin', '2024-01-01T00:00:00Z')"""
        )
        # Insert api key
        conn.execute(
            """INSERT INTO user_api_keys
               (key_id, username, key_hash, key_prefix, created_at)
               VALUES ('key1', 'testuser', 'keyhash', 'cidx_', '2024-01-01T00:00:00Z')"""
        )
        conn.commit()

        # Verify api key exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_api_keys WHERE username='testuser'"
        )
        assert cursor.fetchone()[0] == 1

        # Delete user
        conn.execute("DELETE FROM users WHERE username='testuser'")
        conn.commit()

        # Verify api key was cascaded
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_api_keys WHERE username='testuser'"
        )
        assert cursor.fetchone()[0] == 0

        conn.close()

    def test_database_schema_ssh_key_hosts_foreign_key_cascade(
        self, tmp_path: Path
    ) -> None:
        """
        Given an initialized database with an SSH key and host assignments
        When we delete the SSH key
        Then related host assignments are cascaded (deleted).
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")

        # Insert SSH key
        conn.execute(
            """INSERT INTO ssh_keys
               (name, fingerprint, key_type, private_path, public_path)
               VALUES ('mykey', 'fp123', 'ed25519', '/path/mykey', '/path/mykey.pub')"""
        )
        # Insert host assignment
        conn.execute(
            """INSERT INTO ssh_key_hosts (key_name, hostname)
               VALUES ('mykey', 'github.com')"""
        )
        conn.commit()

        # Verify host assignment exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM ssh_key_hosts WHERE key_name='mykey'"
        )
        assert cursor.fetchone()[0] == 1

        # Delete SSH key
        conn.execute("DELETE FROM ssh_keys WHERE name='mykey'")
        conn.commit()

        # Verify host assignment was cascaded
        cursor = conn.execute(
            "SELECT COUNT(*) FROM ssh_key_hosts WHERE key_name='mykey'"
        )
        assert cursor.fetchone()[0] == 0

        conn.close()


class TestDatabaseConnectionManager:
    """Tests for DatabaseConnectionManager with thread-local connection pooling."""

    def test_get_connection_returns_valid_connection(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When get_connection() is called
        Then it returns a valid SQLite connection.
        """
        from code_indexer.server.storage.database_manager import (
            DatabaseConnectionManager,
            DatabaseSchema,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = DatabaseConnectionManager(str(db_path))
        conn = manager.get_connection()

        assert conn is not None
        # Verify connection works
        cursor = conn.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

        manager.close_all()

    def test_get_connection_reuses_thread_local_connection(
        self, tmp_path: Path
    ) -> None:
        """
        Given an initialized database and a thread
        When get_connection() is called multiple times from same thread
        Then it returns the same connection object.
        """
        from code_indexer.server.storage.database_manager import (
            DatabaseConnectionManager,
            DatabaseSchema,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = DatabaseConnectionManager(str(db_path))
        conn1 = manager.get_connection()
        conn2 = manager.get_connection()

        assert conn1 is conn2

        manager.close_all()

    def test_execute_atomic_commits_on_success(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When execute_atomic() succeeds
        Then changes are committed.
        """
        from code_indexer.server.storage.database_manager import (
            DatabaseConnectionManager,
            DatabaseSchema,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = DatabaseConnectionManager(str(db_path))

        def operation(conn):
            conn.execute(
                """INSERT INTO users (username, password_hash, role, created_at)
                   VALUES ('testuser', 'hash', 'admin', '2024-01-01')"""
            )
            return True

        result = manager.execute_atomic(operation)
        assert result is True

        # Verify data persisted
        conn = manager.get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE username='testuser'")
        assert cursor.fetchone()[0] == 1

        manager.close_all()

    def test_execute_atomic_rolls_back_on_error(self, tmp_path: Path) -> None:
        """
        Given an initialized database with existing data
        When execute_atomic() raises an exception
        Then changes are rolled back.
        """
        from code_indexer.server.storage.database_manager import (
            DatabaseConnectionManager,
            DatabaseSchema,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        manager = DatabaseConnectionManager(str(db_path))

        # Insert initial user
        def setup(conn):
            conn.execute(
                """INSERT INTO users (username, password_hash, role, created_at)
                   VALUES ('existinguser', 'hash', 'admin', '2024-01-01')"""
            )
            return True

        manager.execute_atomic(setup)

        # Try operation that will fail
        def failing_operation(conn):
            conn.execute(
                """INSERT INTO users (username, password_hash, role, created_at)
                   VALUES ('newuser', 'hash', 'admin', '2024-01-01')"""
            )
            raise RuntimeError("Simulated failure")

        with pytest.raises(RuntimeError, match="Simulated failure"):
            manager.execute_atomic(failing_operation)

        # Verify rollback occurred - newuser should not exist
        conn = manager.get_connection()
        cursor = conn.execute("SELECT COUNT(*) FROM users WHERE username='newuser'")
        assert cursor.fetchone()[0] == 0

        # Verify existing data still exists
        cursor = conn.execute(
            "SELECT COUNT(*) FROM users WHERE username='existinguser'"
        )
        assert cursor.fetchone()[0] == 1

        manager.close_all()
