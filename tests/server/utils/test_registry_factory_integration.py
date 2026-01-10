"""
Integration tests for Story #713 fix: GlobalRegistry storage mismatch.

Tests the core bug scenario: golden repo created by GoldenRepoManager
should be immediately queryable via GlobalRegistry when using the
factory function (SQLite backend consistency).
"""

import pytest


def _initialize_db_schema(db_path: str) -> None:
    """Helper to initialize database schema for tests."""
    from code_indexer.server.storage.database_manager import DatabaseSchema

    schema = DatabaseSchema(db_path)
    schema.initialize_database()


class TestGoldenRepoToAliasResolution:
    """
    Integration tests for the core bug scenario:
    Multiple GlobalRegistry instances sharing SQLite storage.

    This was the bug - GlobalRegistry was reading from JSON by default,
    causing different instances to have stale or missing data.
    The fix ensures all server code uses SQLite backend via factory function.
    """

    def test_multiple_registry_instances_see_same_data(self, tmp_path):
        """
        Test that multiple GlobalRegistry instances (created at different times)
        all see the same data when using SQLite backend.

        This simulates the production scenario where each request handler
        creates its own GlobalRegistry instance.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        # Setup
        server_data_dir = tmp_path / "data"
        golden_repos_dir = server_data_dir / "golden-repos"
        server_data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        # Simulate handler 1: create registry, register repo
        registry1 = get_server_global_registry(str(golden_repos_dir))
        registry1.register_global_repo(
            repo_name="repo-from-handler1",
            alias_name="repo-from-handler1-global",
            repo_url="https://github.com/org/repo1",
            index_path=str(tmp_path / "index1"),
        )

        # Simulate handler 2: different time, different instance
        registry2 = get_server_global_registry(str(golden_repos_dir))
        registry2.register_global_repo(
            repo_name="repo-from-handler2",
            alias_name="repo-from-handler2-global",
            repo_url="https://github.com/org/repo2",
            index_path=str(tmp_path / "index2"),
        )

        # Simulate handler 3: query - should see both repos
        registry3 = get_server_global_registry(str(golden_repos_dir))
        all_repos = registry3.list_global_repos()

        # Should see repos from both handlers
        aliases = {r["alias_name"] for r in all_repos}
        assert "repo-from-handler1-global" in aliases
        assert "repo-from-handler2-global" in aliases
        assert len(all_repos) == 2

    def test_registry_persistence_across_instances(self, tmp_path):
        """
        Test that data persists across registry instances (SQLite persistence).

        This verifies that the SQLite backend provides proper persistence,
        unlike JSON which could have race conditions or stale reads.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        # Setup
        server_data_dir = tmp_path / "data"
        golden_repos_dir = server_data_dir / "golden-repos"
        server_data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        # Phase 1: Create registry, register repo, let instance go out of scope
        registry1 = get_server_global_registry(str(golden_repos_dir))
        registry1.register_global_repo(
            repo_name="persistent-repo",
            alias_name="persistent-repo-global",
            repo_url="https://github.com/org/persistent",
            index_path=str(tmp_path / "index"),
        )
        del registry1  # Explicitly delete to simulate instance destruction

        # Phase 2: Create new registry instance - should see persisted data
        registry2 = get_server_global_registry(str(golden_repos_dir))
        repo = registry2.get_global_repo("persistent-repo-global")

        assert repo is not None
        assert repo["alias_name"] == "persistent-repo-global"

    def test_alias_resolution_works_for_newly_created_repo(self, tmp_path):
        """
        Test the specific use case: create golden repo, immediately resolve alias.

        This is the exact workflow that was broken - MCP handler creates repo,
        then later another handler tries to resolve the alias.
        """
        from code_indexer.server.utils.registry_factory import (
            get_server_global_registry,
        )

        # Setup
        server_data_dir = tmp_path / "data"
        golden_repos_dir = server_data_dir / "golden-repos"
        server_data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(server_data_dir / "cidx_server.db")
        _initialize_db_schema(db_path)

        # Step 1: Create repo (simulates golden-repo-create MCP handler)
        create_handler_registry = get_server_global_registry(str(golden_repos_dir))
        create_handler_registry.register_global_repo(
            repo_name="new-golden",
            alias_name="new-golden-global",
            repo_url="https://github.com/org/new-golden",
            index_path=str(tmp_path / "new-golden-index"),
        )

        # Step 2: Resolve alias (simulates query handler checking repo exists)
        query_handler_registry = get_server_global_registry(str(golden_repos_dir))

        # Get repo by alias
        repo = query_handler_registry.get_global_repo("new-golden-global")
        assert repo is not None, "Alias resolution failed for newly created repo"

        # Get index path (what query handlers need)
        index_path = repo.get("index_path")
        assert index_path is not None
        assert "new-golden-index" in index_path

        # List repos (what list handlers need)
        all_repos = query_handler_registry.list_global_repos()
        assert len(all_repos) == 1
        assert all_repos[0]["alias_name"] == "new-golden-global"
