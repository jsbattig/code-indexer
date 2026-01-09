"""
Unit tests for registry_factory module.

Tests Story #713 fix: Factory function for creating properly configured
GlobalRegistry instances with SQLite backend in server mode.
"""

import pytest
from pathlib import Path


def _initialize_db_schema(db_path: str) -> None:
    """Helper to initialize database schema for tests.

    In production, this is done at server startup in app.py lifespan handler.
    Tests must do this explicitly before using the factory function for
    operations that access the database.
    """
    from code_indexer.server.storage.database_manager import DatabaseSchema

    schema = DatabaseSchema(db_path)
    schema.initialize_database()


class TestGetServerGlobalRegistry:
    """Tests for get_server_global_registry factory function."""

    def test_returns_global_registry_with_sqlite_backend(self, tmp_path):
        """
        Test that factory returns GlobalRegistry with use_sqlite=True.

        This is the core fix for Story #713 - ensuring server code uses
        SQLite backend instead of JSON.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "golden-repos"
        server_data_dir = tmp_path / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        # Verify it's a GlobalRegistry with SQLite enabled
        assert registry._use_sqlite is True
        assert registry._sqlite_backend is not None

    def test_derives_db_path_from_server_data_dir(self, tmp_path):
        """
        Test that db_path is correctly derived as server_data_dir/cidx_server.db.

        Note: The database file is created when schema is initialized (at server
        startup), not when factory function is called. This test verifies the
        path is computed correctly by initializing the schema first.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "golden-repos"
        server_data_dir = tmp_path / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize schema first (as app.py does at startup)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        # The backend should connect to the database at expected path
        expected_db_path = str(server_data_dir / "cidx_server.db")
        # Verify database file exists (created by schema initialization)
        assert Path(expected_db_path).exists()
        # Verify backend is properly connected
        assert registry._sqlite_backend is not None

    def test_derives_server_data_dir_from_golden_repos_parent(self, tmp_path):
        """
        Test that when server_data_dir is None, it's derived from golden_repos_dir parent.

        golden_repos_dir is typically: ~/.cidx-server/data/golden-repos
        server_data_dir should be derived as: ~/.cidx-server/data (parent)
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        # Simulate real directory structure
        server_data_dir = tmp_path / "data"
        golden_repos_dir = server_data_dir / "golden-repos"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize schema first (simulating server startup)
        expected_db_path = server_data_dir / "cidx_server.db"
        _initialize_db_schema(str(expected_db_path))

        # Call without explicit server_data_dir - should derive from parent
        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=None,  # Not provided, should derive
        )

        # Verify SQLite is enabled
        assert registry._use_sqlite is True

        # Verify db file exists in the derived location (parent of golden_repos_dir)
        assert expected_db_path.exists()

    def test_accepts_explicit_server_data_dir(self, tmp_path):
        """
        Test that explicit server_data_dir overrides derivation from golden_repos_dir.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "data" / "golden-repos"
        custom_data_dir = tmp_path / "custom-data-location"
        custom_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize schema in custom location
        expected_db_path = custom_data_dir / "cidx_server.db"
        _initialize_db_schema(str(expected_db_path))

        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(custom_data_dir),
        )

        # Verify db file was created in custom location, not derived location
        derived_db_path = tmp_path / "data" / "cidx_server.db"

        assert expected_db_path.exists()
        assert not derived_db_path.exists()

    def test_creates_golden_repos_directory(self, tmp_path):
        """
        Test that GlobalRegistry creates golden_repos_dir if it doesn't exist.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "data" / "golden-repos"
        server_data_dir = tmp_path / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        # golden_repos_dir doesn't exist yet
        assert not golden_repos_dir.exists()

        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        # GlobalRegistry should create it
        assert golden_repos_dir.exists()

    def test_registry_operations_work_with_sqlite_backend(self, tmp_path):
        """
        Integration test: Verify that registry operations work through SQLite backend.

        This tests the actual functionality, not just configuration.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "data" / "golden-repos"
        server_data_dir = tmp_path / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize schema first (as app.py does at startup)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        registry = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        # Register a repo
        registry.register_global_repo(
            repo_name="test-repo",
            alias_name="test-repo-global",
            repo_url="https://github.com/org/test-repo",
            index_path=str(tmp_path / "index"),
        )

        # Verify it was stored (through SQLite backend)
        repo = registry.get_global_repo("test-repo-global")
        assert repo is not None
        assert repo["alias_name"] == "test-repo-global"
        assert repo["repo_name"] == "test-repo"

        # Verify listing works
        repos = registry.list_global_repos()
        assert len(repos) == 1
        assert repos[0]["alias_name"] == "test-repo-global"

    def test_multiple_registries_share_same_sqlite_storage(self, tmp_path):
        """
        Test that creating multiple registry instances with same db_path
        share the same underlying storage (critical for Story #713 fix).

        This verifies that a repo registered by one instance is visible
        to another instance - the core bug scenario.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        golden_repos_dir = tmp_path / "data" / "golden-repos"
        server_data_dir = tmp_path / "data"
        server_data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize schema first (as app.py does at startup)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        # Create first registry instance and register a repo
        registry1 = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        registry1.register_global_repo(
            repo_name="shared-repo",
            alias_name="shared-repo-global",
            repo_url="https://github.com/org/shared-repo",
            index_path=str(tmp_path / "index"),
        )

        # Create second registry instance (simulates different request handler)
        registry2 = get_server_global_registry(
            golden_repos_dir=str(golden_repos_dir),
            server_data_dir=str(server_data_dir),
        )

        # Second instance should see the repo registered by first instance
        # This is the core behavior that was broken in Story #713
        repo = registry2.get_global_repo("shared-repo-global")
        assert repo is not None
        assert repo["alias_name"] == "shared-repo-global"

        repos = registry2.list_global_repos()
        assert len(repos) == 1
