"""
Unit tests for migration_service.py - Legacy JSON to SQLite migration.

Tests written FIRST following TDD methodology.
Story #702: Migrate Central JSON Files to SQLite
"""

import json
from pathlib import Path

import pytest


class TestMigrationServiceInit:
    """Tests for MigrationService initialization."""

    def test_init_creates_instance_with_paths(self, tmp_path: Path) -> None:
        """
        Given valid source and target paths
        When MigrationService is instantiated
        Then it initializes without error.
        """
        from code_indexer.server.storage.migration_service import MigrationService

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        db_path = tmp_path / "target.db"

        service = MigrationService(str(source_dir), str(db_path))

        assert service.source_dir == str(source_dir)
        assert service.db_path == str(db_path)


class TestGlobalReposMigration:
    """Tests for migrating global_registry.json to SQLite."""

    def test_migrate_global_repos_transfers_all_records(self, tmp_path: Path) -> None:
        """
        Given a global_registry.json with multiple repos
        When migrate_global_repos() is called
        Then all repos are transferred to SQLite.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService
        from code_indexer.server.storage.sqlite_backends import GlobalReposSqliteBackend

        # Setup source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        registry_file = source_dir / "global_registry.json"
        registry_data = {
            "repo1-global": {
                "repo_name": "repo1",
                "alias_name": "repo1-global",
                "repo_url": "https://github.com/test/repo1.git",
                "index_path": "/path/to/repo1",
                "created_at": "2024-01-01T00:00:00+00:00",
                "last_refresh": "2024-01-02T00:00:00+00:00",
                "enable_temporal": True,
                "temporal_options": {"max_commits": 100},
            },
            "repo2-global": {
                "repo_name": "repo2",
                "alias_name": "repo2-global",
                "repo_url": None,
                "index_path": "/path/to/repo2",
                "created_at": "2024-02-01T00:00:00+00:00",
                "last_refresh": "2024-02-02T00:00:00+00:00",
                "enable_temporal": False,
                "temporal_options": None,
            },
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # Setup target database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Migrate
        service = MigrationService(str(source_dir), str(db_path))
        result = service.migrate_global_repos()

        # Verify
        assert result["migrated"] == 2
        assert result["errors"] == 0

        backend = GlobalReposSqliteBackend(str(db_path))
        repos = backend.list_repos()
        backend.close()

        assert len(repos) == 2
        assert "repo1-global" in repos
        assert "repo2-global" in repos
        assert repos["repo1-global"]["enable_temporal"] is True
        assert repos["repo1-global"]["temporal_options"] == {"max_commits": 100}

    def test_migrate_global_repos_skips_missing_file(self, tmp_path: Path) -> None:
        """
        Given no global_registry.json exists
        When migrate_global_repos() is called
        Then it returns with zero migrations and no errors.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        # No global_registry.json created

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        service = MigrationService(str(source_dir), str(db_path))
        result = service.migrate_global_repos()

        assert result["migrated"] == 0
        assert result["errors"] == 0
        assert result["skipped"] is True


class TestUsersMigration:
    """Tests for migrating users.json to SQLite."""

    def test_migrate_users_transfers_user_with_api_keys(self, tmp_path: Path) -> None:
        """
        Given a users.json with a user having api_keys
        When migrate_users() is called
        Then user and api_keys are transferred to normalized tables.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        # Setup source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        users_file = source_dir / "users.json"
        users_data = {
            "testuser": {
                "password_hash": "hash123",
                "role": "admin",
                "created_at": "2024-01-01T00:00:00+00:00",
                "email": "test@example.com",
                "api_keys": [
                    {
                        "key_id": "key1",
                        "hash": "keyhash1",
                        "key_prefix": "cidx_sk_",
                        "name": "My Key",
                        "created_at": "2024-01-02T00:00:00+00:00",
                    }
                ],
            }
        }
        users_file.write_text(json.dumps(users_data, indent=2))

        # Setup target database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Migrate
        service = MigrationService(str(source_dir), str(db_path))
        result = service.migrate_users()

        # Verify
        assert result["migrated"] == 1
        assert result["errors"] == 0

        backend = UsersSqliteBackend(str(db_path))
        user = backend.get_user("testuser")
        backend.close()

        assert user is not None
        assert user["username"] == "testuser"
        assert user["role"] == "admin"
        assert user["email"] == "test@example.com"
        assert len(user["api_keys"]) == 1
        assert user["api_keys"][0]["key_id"] == "key1"

    def test_migrate_users_transfers_mcp_credentials(self, tmp_path: Path) -> None:
        """
        Given a users.json with mcp_credentials
        When migrate_users() is called
        Then mcp_credentials are transferred to normalized table.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService
        from code_indexer.server.storage.sqlite_backends import UsersSqliteBackend

        # Setup source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        users_file = source_dir / "users.json"
        users_data = {
            "mcpuser": {
                "password_hash": "hash456",
                "role": "user",
                "created_at": "2024-01-01T00:00:00+00:00",
                "mcp_credentials": [
                    {
                        "credential_id": "cred1",
                        "client_id": "client123",
                        "client_secret_hash": "secrethash",
                        "client_id_prefix": "mcp_",
                        "name": "MCP Cred",
                        "created_at": "2024-01-03T00:00:00+00:00",
                        "last_used_at": None,
                    }
                ],
            }
        }
        users_file.write_text(json.dumps(users_data, indent=2))

        # Setup target database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Migrate
        service = MigrationService(str(source_dir), str(db_path))
        result = service.migrate_users()

        # Verify
        assert result["migrated"] == 1

        backend = UsersSqliteBackend(str(db_path))
        user = backend.get_user("mcpuser")
        backend.close()

        assert user is not None
        assert len(user["mcp_credentials"]) == 1
        assert user["mcp_credentials"][0]["credential_id"] == "cred1"


class TestMigrationIdempotency:
    """Tests for migration idempotency - running multiple times should be safe."""

    def test_migration_is_idempotent(self, tmp_path: Path) -> None:
        """
        Given a migration has already been run
        When migrate_all() is called again
        Then it succeeds without duplicating data.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService
        from code_indexer.server.storage.sqlite_backends import GlobalReposSqliteBackend

        # Setup source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        registry_file = source_dir / "global_registry.json"
        registry_data = {
            "repo1-global": {
                "repo_name": "repo1",
                "alias_name": "repo1-global",
                "repo_url": "https://github.com/test/repo1.git",
                "index_path": "/path/to/repo1",
                "created_at": "2024-01-01T00:00:00+00:00",
                "last_refresh": "2024-01-02T00:00:00+00:00",
                "enable_temporal": False,
                "temporal_options": None,
            },
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # Setup target database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Run migration twice
        service = MigrationService(str(source_dir), str(db_path))
        result1 = service.migrate_global_repos()
        result2 = service.migrate_global_repos()

        # Second run should report as already migrated or update-in-place
        backend = GlobalReposSqliteBackend(str(db_path))
        repos = backend.list_repos()
        backend.close()

        # Should still have exactly 1 repo (not duplicated)
        assert len(repos) == 1


class TestMigrationStatus:
    """Tests for checking migration status."""

    def test_is_migration_needed_returns_true_when_json_exists(
        self, tmp_path: Path
    ) -> None:
        """
        Given legacy JSON files exist and database is empty
        When is_migration_needed() is called
        Then it returns True.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService

        # Setup source JSON
        source_dir = tmp_path / "source"
        source_dir.mkdir()
        (source_dir / "global_registry.json").write_text("{}")

        # Setup empty database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        service = MigrationService(str(source_dir), str(db_path))
        assert service.is_migration_needed() is True

    def test_is_migration_needed_returns_false_when_no_json(
        self, tmp_path: Path
    ) -> None:
        """
        Given no legacy JSON files exist
        When is_migration_needed() is called
        Then it returns False.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService

        source_dir = tmp_path / "source"
        source_dir.mkdir()
        # No JSON files

        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        service = MigrationService(str(source_dir), str(db_path))
        assert service.is_migration_needed() is False


class TestMigrateAll:
    """Tests for the migrate_all() orchestration method."""

    def test_migrate_all_runs_all_migrations(self, tmp_path: Path) -> None:
        """
        Given multiple JSON files exist
        When migrate_all() is called
        Then all data is migrated to SQLite.
        """
        from code_indexer.server.storage.database_manager import DatabaseSchema
        from code_indexer.server.storage.migration_service import MigrationService
        from code_indexer.server.storage.sqlite_backends import (
            GlobalReposSqliteBackend,
            UsersSqliteBackend,
        )

        # Setup source JSON files
        source_dir = tmp_path / "source"
        source_dir.mkdir()

        # global_registry.json
        registry_file = source_dir / "global_registry.json"
        registry_data = {
            "repo1-global": {
                "repo_name": "repo1",
                "alias_name": "repo1-global",
                "repo_url": None,
                "index_path": "/path/to/repo1",
                "created_at": "2024-01-01T00:00:00+00:00",
                "last_refresh": "2024-01-02T00:00:00+00:00",
                "enable_temporal": False,
                "temporal_options": None,
            },
        }
        registry_file.write_text(json.dumps(registry_data, indent=2))

        # users.json
        users_file = source_dir / "users.json"
        users_data = {
            "testuser": {
                "password_hash": "hash123",
                "role": "admin",
                "created_at": "2024-01-01T00:00:00+00:00",
            }
        }
        users_file.write_text(json.dumps(users_data, indent=2))

        # Setup target database
        db_path = tmp_path / "test.db"
        schema = DatabaseSchema(str(db_path))
        schema.initialize_database()

        # Migrate all
        service = MigrationService(str(source_dir), str(db_path))
        results = service.migrate_all()

        # Verify
        assert "global_repos" in results
        assert "users" in results
        assert results["global_repos"]["migrated"] == 1
        assert results["users"]["migrated"] == 1

        # Verify data in SQLite
        repos_backend = GlobalReposSqliteBackend(str(db_path))
        assert len(repos_backend.list_repos()) == 1
        repos_backend.close()

        users_backend = UsersSqliteBackend(str(db_path))
        assert users_backend.get_user("testuser") is not None
        users_backend.close()
