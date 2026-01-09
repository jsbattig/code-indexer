"""
Unit tests for sqlite_backends.py - SQLite implementations for all managers.

Tests written FIRST following TDD methodology.
Story #702: Migrate Central JSON Files to SQLite
"""

import json
import sqlite3
from pathlib import Path

import pytest


class TestGlobalReposSqliteBackend:
    """Tests for GlobalReposSqliteBackend CRUD operations."""

    def test_register_repo_inserts_new_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When register_repo() is called with repo details
        Then a new record is inserted in global_repos table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        backend.register_repo(
            alias_name="test-repo-global",
            repo_name="test-repo",
            repo_url="https://github.com/test/repo.git",
            index_path="/path/to/index",
            enable_temporal=False,
            temporal_options=None,
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT alias_name, repo_name, repo_url, index_path FROM global_repos"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "test-repo-global"
        assert row[1] == "test-repo"
        assert row[2] == "https://github.com/test/repo.git"
        assert row[3] == "/path/to/index"

    def test_get_repo_returns_existing_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing repo
        When get_repo() is called with the alias
        Then it returns the repo details as a dictionary.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        backend.register_repo(
            alias_name="my-repo-global",
            repo_name="my-repo",
            repo_url="https://github.com/my/repo.git",
            index_path="/path/to/my/index",
            enable_temporal=True,
            temporal_options={"time_range": "all"},
        )

        result = backend.get_repo("my-repo-global")

        assert result is not None
        assert result["alias_name"] == "my-repo-global"
        assert result["repo_name"] == "my-repo"
        assert result["enable_temporal"] is True
        assert result["temporal_options"] == {"time_range": "all"}

    def test_get_repo_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested repo
        When get_repo() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        result = backend.get_repo("nonexistent-repo")

        assert result is None

    def test_list_repos_returns_all_records(self, tmp_path: Path) -> None:
        """
        Given a database with multiple repos
        When list_repos() is called
        Then it returns all repos as a dictionary keyed by alias.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        backend.register_repo(
            alias_name="repo1-global",
            repo_name="repo1",
            repo_url=None,
            index_path="/path/1",
            enable_temporal=False,
            temporal_options=None,
        )
        backend.register_repo(
            alias_name="repo2-global",
            repo_name="repo2",
            repo_url=None,
            index_path="/path/2",
            enable_temporal=False,
            temporal_options=None,
        )

        result = backend.list_repos()

        assert len(result) == 2
        assert "repo1-global" in result
        assert "repo2-global" in result
        assert result["repo1-global"]["repo_name"] == "repo1"
        assert result["repo2-global"]["repo_name"] == "repo2"

    def test_delete_repo_removes_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing repo
        When delete_repo() is called
        Then the record is removed.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        backend.register_repo(
            alias_name="to-delete-global",
            repo_name="to-delete",
            repo_url=None,
            index_path="/path/delete",
            enable_temporal=False,
            temporal_options=None,
        )

        # Verify it exists
        assert backend.get_repo("to-delete-global") is not None

        # Delete it
        backend.delete_repo("to-delete-global")

        # Verify it's gone
        assert backend.get_repo("to-delete-global") is None

    def test_update_last_refresh_updates_timestamp(self, tmp_path: Path) -> None:
        """
        Given a database with an existing repo
        When update_last_refresh() is called
        Then the last_refresh timestamp is updated.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
        )
        import time

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GlobalReposSqliteBackend(str(db_path))
        backend.register_repo(
            alias_name="refresh-repo-global",
            repo_name="refresh-repo",
            repo_url=None,
            index_path="/path/refresh",
            enable_temporal=False,
            temporal_options=None,
        )

        # Get initial timestamp
        initial = backend.get_repo("refresh-repo-global")
        assert initial is not None
        initial_refresh = initial["last_refresh"]

        # Wait a moment to ensure timestamp changes
        time.sleep(0.01)

        # Update the timestamp
        backend.update_last_refresh("refresh-repo-global")

        # Verify timestamp was updated
        updated = backend.get_repo("refresh-repo-global")
        assert updated is not None
        assert updated["last_refresh"] != initial_refresh


class TestUsersSqliteBackend:
    """Tests for UsersSqliteBackend with normalized tables."""

    def test_create_user_inserts_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When create_user() is called
        Then a new user record is inserted.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(
            username="testuser",
            password_hash="hash123",
            role="admin",
            email="test@example.com",
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT username, role, email FROM users")
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "testuser"
        assert row[1] == "admin"
        assert row[2] == "test@example.com"

    def test_get_user_returns_user_with_api_keys(self, tmp_path: Path) -> None:
        """
        Given a user with api_keys
        When get_user() is called
        Then it returns user with api_keys array populated.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(
            username="apiuser",
            password_hash="hash",
            role="user",
        )
        backend.add_api_key(
            username="apiuser",
            key_id="key1",
            key_hash="keyhash1",
            key_prefix="cidx_",
            name="My Key",
        )

        result = backend.get_user("apiuser")

        assert result is not None
        assert result["username"] == "apiuser"
        assert "api_keys" in result
        assert len(result["api_keys"]) == 1
        assert result["api_keys"][0]["key_id"] == "key1"

    def test_list_users_returns_all_users(self, tmp_path: Path) -> None:
        """
        Given a database with multiple users
        When list_users() is called
        Then it returns all users.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(username="user1", password_hash="hash1", role="admin")
        backend.create_user(username="user2", password_hash="hash2", role="normal_user")
        backend.create_user(username="user3", password_hash="hash3", role="power_user")

        result = backend.list_users()

        assert len(result) == 3
        usernames = [u["username"] for u in result]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "user3" in usernames

    def test_update_user_modifies_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing user
        When update_user() is called with new values
        Then the user record is updated.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(
            username="update_user",
            password_hash="hash",
            role="normal_user",
            email="old@example.com",
        )

        # Update username and email
        backend.update_user(
            username="update_user",
            new_username="updated_user",
            email="new@example.com",
        )

        # Old username should not exist
        assert backend.get_user("update_user") is None

        # New username should exist with updated data
        result = backend.get_user("updated_user")
        assert result is not None
        assert result["email"] == "new@example.com"

    def test_update_user_modifies_email_only(self, tmp_path: Path) -> None:
        """
        Given a database with an existing user
        When update_user() is called with only email
        Then only the email is updated.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(
            username="email_user",
            password_hash="hash",
            role="admin",
            email="old@example.com",
        )

        # Update only email
        backend.update_user(username="email_user", email="updated@example.com")

        result = backend.get_user("email_user")
        assert result is not None
        assert result["email"] == "updated@example.com"
        assert result["role"] == "admin"

    def test_update_user_returns_false_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the user
        When update_user() is called
        Then it returns False.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))

        result = backend.update_user(username="nonexistent", email="x@y.com")

        assert result is False

    def test_delete_user_cascades_to_api_keys(self, tmp_path: Path) -> None:
        """
        Given a user with api_keys and mcp_credentials
        When delete_user() is called
        Then all related records are cascade deleted.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = UsersSqliteBackend(str(db_path))
        backend.create_user(
            username="cascade_user",
            password_hash="hash",
            role="user",
        )
        backend.add_api_key(
            username="cascade_user",
            key_id="key1",
            key_hash="keyhash",
            key_prefix="cidx_",
        )
        backend.add_mcp_credential(
            username="cascade_user",
            credential_id="cred1",
            client_id="client123",
            client_secret_hash="secrethash",
            client_id_prefix="mcp_",
        )

        # Verify records exist
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_api_keys WHERE username='cascade_user'"
        )
        assert cursor.fetchone()[0] == 1
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_mcp_credentials WHERE username='cascade_user'"
        )
        assert cursor.fetchone()[0] == 1
        conn.close()

        # Delete user
        backend.delete_user("cascade_user")

        # Verify cascades occurred
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_api_keys WHERE username='cascade_user'"
        )
        assert cursor.fetchone()[0] == 0
        cursor = conn.execute(
            "SELECT COUNT(*) FROM user_mcp_credentials WHERE username='cascade_user'"
        )
        assert cursor.fetchone()[0] == 0
        conn.close()


class TestSyncJobsSqliteBackend:
    """Tests for SyncJobsSqliteBackend with JSON blob columns."""

    def test_create_job_inserts_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When create_job() is called with job details
        Then a new record is inserted in sync_jobs table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(
            job_id="job-001",
            username="testuser",
            user_alias="Test User",
            job_type="sync",
            status="pending",
            repository_url="https://github.com/test/repo.git",
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT job_id, username, user_alias, job_type, status FROM sync_jobs"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "job-001"
        assert row[1] == "testuser"
        assert row[2] == "Test User"
        assert row[3] == "sync"
        assert row[4] == "pending"

    def test_get_job_returns_existing_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing job
        When get_job() is called with the job_id
        Then it returns the job details as a dictionary.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(
            job_id="job-002",
            username="user2",
            user_alias="User Two",
            job_type="refresh",
            status="running",
            repository_url="https://github.com/user2/repo.git",
        )

        result = backend.get_job("job-002")

        assert result is not None
        assert result["job_id"] == "job-002"
        assert result["username"] == "user2"
        assert result["status"] == "running"

    def test_get_job_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested job
        When get_job() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        result = backend.get_job("nonexistent-job")

        assert result is None

    def test_update_job_modifies_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing job
        When update_job() is called with new values
        Then the record is updated.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(
            job_id="job-003",
            username="user3",
            user_alias="User Three",
            job_type="sync",
            status="pending",
        )

        # Update job
        backend.update_job(
            job_id="job-003",
            status="completed",
            progress=100,
            error_message=None,
        )

        result = backend.get_job("job-003")
        assert result is not None
        assert result["status"] == "completed"
        assert result["progress"] == 100

    def test_list_jobs_returns_all_records(self, tmp_path: Path) -> None:
        """
        Given a database with multiple jobs
        When list_jobs() is called
        Then it returns all jobs.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(job_id="job-a", username="user1", user_alias="U1", job_type="sync", status="pending")
        backend.create_job(job_id="job-b", username="user2", user_alias="U2", job_type="refresh", status="running")

        result = backend.list_jobs()

        assert len(result) == 2
        job_ids = [j["job_id"] for j in result]
        assert "job-a" in job_ids
        assert "job-b" in job_ids

    def test_delete_job_removes_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing job
        When delete_job() is called
        Then the record is removed.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(job_id="job-del", username="user", user_alias="U", job_type="sync", status="pending")

        # Verify it exists
        assert backend.get_job("job-del") is not None

        # Delete it
        backend.delete_job("job-del")

        # Verify it's gone
        assert backend.get_job("job-del") is None

    def test_update_job_with_json_blob_columns(self, tmp_path: Path) -> None:
        """
        Given a database with an existing job
        When update_job() is called with complex nested data (phases, analytics)
        Then the JSON blob columns are stored correctly.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SyncJobsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SyncJobsSqliteBackend(str(db_path))
        backend.create_job(
            job_id="job-json",
            username="user",
            user_alias="User",
            job_type="sync",
            status="running",
        )

        phases = {"clone": {"status": "completed", "progress": 100}, "index": {"status": "running", "progress": 50}}
        phase_weights = {"clone": 0.3, "index": 0.7}
        analytics_data = {"files_processed": 100, "duration_seconds": 120}

        backend.update_job(
            job_id="job-json",
            phases=phases,
            phase_weights=phase_weights,
            current_phase="index",
            analytics_data=analytics_data,
        )

        result = backend.get_job("job-json")
        assert result is not None
        assert result["phases"] == phases
        assert result["phase_weights"] == phase_weights
        assert result["current_phase"] == "index"
        assert result["analytics_data"] == analytics_data


class TestCITokensSqliteBackend:
    """Tests for CITokensSqliteBackend CRUD operations."""

    def test_save_token_inserts_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When save_token() is called
        Then a new record is inserted in ci_tokens table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import CITokensSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = CITokensSqliteBackend(str(db_path))
        backend.save_token(
            platform="github",
            encrypted_token="encrypted_value_123",
            base_url=None,
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT platform, encrypted_token, base_url FROM ci_tokens"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "github"
        assert row[1] == "encrypted_value_123"
        assert row[2] is None

    def test_get_token_returns_existing_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing token
        When get_token() is called
        Then it returns the token data.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import CITokensSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = CITokensSqliteBackend(str(db_path))
        backend.save_token(
            platform="gitlab",
            encrypted_token="gitlab_encrypted_token",
            base_url="https://gitlab.example.com",
        )

        result = backend.get_token("gitlab")

        assert result is not None
        assert result["platform"] == "gitlab"
        assert result["encrypted_token"] == "gitlab_encrypted_token"
        assert result["base_url"] == "https://gitlab.example.com"

    def test_get_token_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested token
        When get_token() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import CITokensSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = CITokensSqliteBackend(str(db_path))
        result = backend.get_token("nonexistent")

        assert result is None

    def test_delete_token_removes_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing token
        When delete_token() is called
        Then the record is removed.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import CITokensSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = CITokensSqliteBackend(str(db_path))
        backend.save_token(platform="github", encrypted_token="token123")

        # Verify it exists
        assert backend.get_token("github") is not None

        # Delete it
        backend.delete_token("github")

        # Verify it's gone
        assert backend.get_token("github") is None

    def test_list_tokens_returns_all_platforms(self, tmp_path: Path) -> None:
        """
        Given a database with multiple tokens
        When list_tokens() is called
        Then it returns all tokens keyed by platform.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import CITokensSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = CITokensSqliteBackend(str(db_path))
        backend.save_token(platform="github", encrypted_token="gh_token")
        backend.save_token(platform="gitlab", encrypted_token="gl_token")

        result = backend.list_tokens()

        assert len(result) == 2
        assert "github" in result
        assert "gitlab" in result


class TestSessionsSqliteBackend:
    """Tests for SessionsSqliteBackend (invalidated_sessions and password_change_timestamps)."""

    def test_invalidate_session_inserts_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When invalidate_session() is called
        Then a record is inserted in invalidated_sessions table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        backend.invalidate_session(
            username="testuser",
            token_id="token-abc-123",
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT username, token_id FROM invalidated_sessions"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "testuser"
        assert row[1] == "token-abc-123"

    def test_is_session_invalidated_returns_true_for_invalidated(self, tmp_path: Path) -> None:
        """
        Given a database with an invalidated session
        When is_session_invalidated() is called
        Then it returns True.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        backend.invalidate_session(username="user1", token_id="tok-1")

        result = backend.is_session_invalidated("user1", "tok-1")

        assert result is True

    def test_is_session_invalidated_returns_false_for_valid(self, tmp_path: Path) -> None:
        """
        Given a database without the session invalidated
        When is_session_invalidated() is called
        Then it returns False.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        result = backend.is_session_invalidated("user1", "valid-token")

        assert result is False

    def test_set_password_change_timestamp(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When set_password_change_timestamp() is called
        Then a record is inserted/updated in password_change_timestamps table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        backend.set_password_change_timestamp("testuser", "2025-01-15T10:30:00Z")

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT username, changed_at FROM password_change_timestamps"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "testuser"
        assert row[1] == "2025-01-15T10:30:00Z"

    def test_get_password_change_timestamp_returns_value(self, tmp_path: Path) -> None:
        """
        Given a database with a password change timestamp
        When get_password_change_timestamp() is called
        Then it returns the timestamp.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        backend.set_password_change_timestamp("user2", "2025-01-20T14:00:00Z")

        result = backend.get_password_change_timestamp("user2")

        assert result == "2025-01-20T14:00:00Z"

    def test_get_password_change_timestamp_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without password change timestamp for user
        When get_password_change_timestamp() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        result = backend.get_password_change_timestamp("nonexistent")

        assert result is None

    def test_clear_invalidated_sessions_for_user(self, tmp_path: Path) -> None:
        """
        Given a database with invalidated sessions for a user
        When clear_invalidated_sessions() is called
        Then all sessions for that user are removed.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SessionsSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SessionsSqliteBackend(str(db_path))
        backend.invalidate_session("user1", "tok-1")
        backend.invalidate_session("user1", "tok-2")
        backend.invalidate_session("user2", "tok-3")

        # Clear user1's sessions
        backend.clear_invalidated_sessions("user1")

        # user1's sessions should be gone
        assert backend.is_session_invalidated("user1", "tok-1") is False
        assert backend.is_session_invalidated("user1", "tok-2") is False
        # user2's session should remain
        assert backend.is_session_invalidated("user2", "tok-3") is True


class TestSSHKeysSqliteBackend:
    """Tests for SSHKeysSqliteBackend with junction table for hosts."""

    def test_create_key_inserts_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When create_key() is called
        Then a new record is inserted in ssh_keys table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(
            name="my-key",
            fingerprint="SHA256:abc123",
            key_type="ed25519",
            private_path="/home/user/.ssh/my-key",
            public_path="/home/user/.ssh/my-key.pub",
            public_key="ssh-ed25519 AAAAC3...",
            email="user@example.com",
            description="My SSH key",
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT name, fingerprint, key_type, private_path FROM ssh_keys"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "my-key"
        assert row[1] == "SHA256:abc123"
        assert row[2] == "ed25519"
        assert row[3] == "/home/user/.ssh/my-key"

    def test_get_key_returns_existing_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing key
        When get_key() is called
        Then it returns the key details with hosts list.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(
            name="get-key",
            fingerprint="SHA256:xyz789",
            key_type="rsa",
            private_path="/path/to/key",
            public_path="/path/to/key.pub",
        )

        result = backend.get_key("get-key")

        assert result is not None
        assert result["name"] == "get-key"
        assert result["fingerprint"] == "SHA256:xyz789"
        assert result["hosts"] == []  # No hosts assigned yet

    def test_get_key_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested key
        When get_key() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        result = backend.get_key("nonexistent-key")

        assert result is None

    def test_assign_host_to_key(self, tmp_path: Path) -> None:
        """
        Given a database with an existing key
        When assign_host() is called
        Then the host is added to the junction table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(
            name="host-key",
            fingerprint="SHA256:host123",
            key_type="ed25519",
            private_path="/path/key",
            public_path="/path/key.pub",
        )

        # Assign hosts
        backend.assign_host("host-key", "github.com")
        backend.assign_host("host-key", "gitlab.com")

        result = backend.get_key("host-key")
        assert result is not None
        assert len(result["hosts"]) == 2
        assert "github.com" in result["hosts"]
        assert "gitlab.com" in result["hosts"]

    def test_remove_host_from_key(self, tmp_path: Path) -> None:
        """
        Given a key with assigned hosts
        When remove_host() is called
        Then the host is removed from the junction table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(
            name="remove-host-key",
            fingerprint="SHA256:rem123",
            key_type="ed25519",
            private_path="/path/key",
            public_path="/path/key.pub",
        )
        backend.assign_host("remove-host-key", "github.com")
        backend.assign_host("remove-host-key", "gitlab.com")

        # Remove one host
        backend.remove_host("remove-host-key", "github.com")

        result = backend.get_key("remove-host-key")
        assert result is not None
        assert len(result["hosts"]) == 1
        assert "gitlab.com" in result["hosts"]
        assert "github.com" not in result["hosts"]

    def test_delete_key_cascades_to_hosts(self, tmp_path: Path) -> None:
        """
        Given a key with assigned hosts
        When delete_key() is called
        Then the key and all host assignments are removed (cascade).
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(
            name="cascade-key",
            fingerprint="SHA256:casc123",
            key_type="ed25519",
            private_path="/path/key",
            public_path="/path/key.pub",
        )
        backend.assign_host("cascade-key", "github.com")
        backend.assign_host("cascade-key", "gitlab.com")

        # Delete the key
        backend.delete_key("cascade-key")

        # Verify key is gone
        assert backend.get_key("cascade-key") is None

        # Verify hosts are also gone (cascade)
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.execute(
            "SELECT COUNT(*) FROM ssh_key_hosts WHERE key_name='cascade-key'"
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0

    def test_list_keys_returns_all_records(self, tmp_path: Path) -> None:
        """
        Given a database with multiple keys
        When list_keys() is called
        Then it returns all keys with their hosts.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import SSHKeysSqliteBackend

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = SSHKeysSqliteBackend(str(db_path))
        backend.create_key(name="key1", fingerprint="fp1", key_type="ed25519", private_path="/p1", public_path="/p1.pub")
        backend.create_key(name="key2", fingerprint="fp2", key_type="rsa", private_path="/p2", public_path="/p2.pub")
        backend.assign_host("key1", "github.com")

        result = backend.list_keys()

        assert len(result) == 2
        key_names = [k["name"] for k in result]
        assert "key1" in key_names
        assert "key2" in key_names

        # Verify hosts are populated
        key1_result = next(k for k in result if k["name"] == "key1")
        assert "github.com" in key1_result["hosts"]


class TestGoldenRepoMetadataSqliteBackend:
    """Tests for GoldenRepoMetadataSqliteBackend CRUD operations (Story #711)."""

    def test_add_repo_inserts_new_record(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When add_repo() is called with repo details
        Then a new record is inserted in golden_repos_metadata table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="test-golden-repo",
            repo_url="https://github.com/test/repo.git",
            default_branch="main",
            clone_path="/data/golden-repos/test-golden-repo",
            created_at="2025-01-15T10:00:00Z",
            enable_temporal=False,
            temporal_options=None,
        )

        # Verify record was inserted
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT alias, repo_url, default_branch, clone_path, enable_temporal "
            "FROM golden_repos_metadata"
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "test-golden-repo"
        assert row[1] == "https://github.com/test/repo.git"
        assert row[2] == "main"
        assert row[3] == "/data/golden-repos/test-golden-repo"
        assert row[4] == 0  # False stored as 0

    def test_add_repo_with_temporal_options_stores_json(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When add_repo() is called with temporal_options
        Then the temporal_options are stored as JSON blob.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        temporal_options = {
            "max_commits": 500,
            "since_date": "2024-01-01",
            "diff_context": 10,
        }

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="temporal-repo",
            repo_url="https://github.com/test/temporal.git",
            default_branch="main",
            clone_path="/data/golden-repos/temporal-repo",
            created_at="2025-01-15T10:00:00Z",
            enable_temporal=True,
            temporal_options=temporal_options,
        )

        # Verify record with JSON blob
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute(
            "SELECT enable_temporal, temporal_options FROM golden_repos_metadata "
            "WHERE alias = ?",
            ("temporal-repo",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row[0] == 1  # True stored as 1
        stored_options = json.loads(row[1])
        assert stored_options == temporal_options

    def test_add_repo_with_null_temporal_options(self, tmp_path: Path) -> None:
        """
        Given an initialized database
        When add_repo() is called with None temporal_options
        Then the repo is stored correctly with null temporal_options.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="no-temporal",
            repo_url="https://github.com/test/no-temporal.git",
            default_branch="main",
            clone_path="/data/golden-repos/no-temporal",
            created_at="2025-01-15T10:00:00Z",
            enable_temporal=False,
            temporal_options=None,
        )

        result = backend.get_repo("no-temporal")

        assert result is not None
        assert result["enable_temporal"] is False
        assert result["temporal_options"] is None

    def test_get_repo_returns_existing_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing golden repo
        When get_repo() is called with the alias
        Then it returns the repo details as a dictionary.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="get-golden-repo",
            repo_url="https://github.com/test/get-repo.git",
            default_branch="develop",
            clone_path="/data/golden-repos/get-golden-repo",
            created_at="2025-01-15T12:00:00Z",
            enable_temporal=True,
            temporal_options={"max_commits": 100},
        )

        result = backend.get_repo("get-golden-repo")

        assert result is not None
        assert result["alias"] == "get-golden-repo"
        assert result["repo_url"] == "https://github.com/test/get-repo.git"
        assert result["default_branch"] == "develop"
        assert result["clone_path"] == "/data/golden-repos/get-golden-repo"
        assert result["created_at"] == "2025-01-15T12:00:00Z"
        assert result["enable_temporal"] is True
        assert result["temporal_options"] == {"max_commits": 100}

    def test_get_repo_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested repo
        When get_repo() is called
        Then it returns None.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        result = backend.get_repo("nonexistent-golden-repo")

        assert result is None

    def test_list_repos_returns_all_records(self, tmp_path: Path) -> None:
        """
        Given a database with multiple golden repos
        When list_repos() is called
        Then it returns all repos as a list.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="repo1",
            repo_url="https://github.com/test/repo1.git",
            default_branch="main",
            clone_path="/data/golden-repos/repo1",
            created_at="2025-01-15T10:00:00Z",
        )
        backend.add_repo(
            alias="repo2",
            repo_url="https://github.com/test/repo2.git",
            default_branch="develop",
            clone_path="/data/golden-repos/repo2",
            created_at="2025-01-15T11:00:00Z",
        )

        result = backend.list_repos()

        assert len(result) == 2
        aliases = [r["alias"] for r in result]
        assert "repo1" in aliases
        assert "repo2" in aliases

    def test_remove_repo_deletes_record(self, tmp_path: Path) -> None:
        """
        Given a database with an existing golden repo
        When remove_repo() is called
        Then the record is removed and True is returned.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="to-delete",
            repo_url="https://github.com/test/delete.git",
            default_branch="main",
            clone_path="/data/golden-repos/to-delete",
            created_at="2025-01-15T10:00:00Z",
        )

        # Verify it exists
        assert backend.get_repo("to-delete") is not None

        # Delete it
        deleted = backend.remove_repo("to-delete")

        # Verify deletion
        assert deleted is True
        assert backend.get_repo("to-delete") is None

    def test_remove_repo_returns_false_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested repo
        When remove_repo() is called
        Then False is returned.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        deleted = backend.remove_repo("nonexistent")

        assert deleted is False

    def test_repo_exists_returns_true_for_existing(self, tmp_path: Path) -> None:
        """
        Given a database with an existing golden repo
        When repo_exists() is called
        Then it returns True.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="exists-repo",
            repo_url="https://github.com/test/exists.git",
            default_branch="main",
            clone_path="/data/golden-repos/exists-repo",
            created_at="2025-01-15T10:00:00Z",
        )

        assert backend.repo_exists("exists-repo") is True

    def test_repo_exists_returns_false_for_nonexistent(self, tmp_path: Path) -> None:
        """
        Given a database without the requested repo
        When repo_exists() is called
        Then it returns False.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))

        assert backend.repo_exists("nonexistent") is False

    def test_add_repo_duplicate_raises_integrity_error(self, tmp_path: Path) -> None:
        """
        Given a database with an existing golden repo
        When add_repo() is called with the same alias
        Then sqlite3.IntegrityError is raised.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.sqlite_backends import (
            GoldenRepoMetadataSqliteBackend,
        )

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        backend = GoldenRepoMetadataSqliteBackend(str(db_path))
        backend.add_repo(
            alias="duplicate-test",
            repo_url="https://github.com/test/first.git",
            default_branch="main",
            clone_path="/data/golden-repos/duplicate-test",
            created_at="2025-01-15T10:00:00Z",
        )

        # Attempt to add duplicate
        with pytest.raises(sqlite3.IntegrityError):
            backend.add_repo(
                alias="duplicate-test",
                repo_url="https://github.com/test/second.git",
                default_branch="develop",
                clone_path="/data/golden-repos/duplicate-test-2",
                created_at="2025-01-15T11:00:00Z",
            )
