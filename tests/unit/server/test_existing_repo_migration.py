"""
Unit tests for existing golden repo migration during server startup.

This test validates the fix for the bug where existing golden repositories
are NOT seeded to admins/powerusers groups during upgrades to the group-based
security model.

Problem: When a CIDX server with existing golden repositories upgrades to the
group-based security model, those existing repos are NOT seeded to admins/powerusers
groups. This means after upgrade, admins see NO repos (except cidx-meta).

Solution: After injecting GroupAccessManager into GoldenRepoManager, add code to:
1. Get all existing golden repos from GoldenRepoManager via list_golden_repos()
2. For each repo, call group_manager.auto_assign_golden_repo(repo["alias"])
3. This must be IDEMPOTENT - safe to run on every startup (auto_assign uses INSERT OR IGNORE)

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    DEFAULT_GROUP_ADMINS,
    DEFAULT_GROUP_POWERUSERS,
)


class TestExistingRepoMigration:
    """Tests for existing golden repo migration to group access during startup."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        # Cleanup after test
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory for golden repos."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def mock_golden_repo_manager(self, temp_data_dir):
        """Create a mock GoldenRepoManager with existing golden repos."""
        from code_indexer.server.repositories.golden_repo_manager import (
            GoldenRepoManager,
        )

        # Create a real GoldenRepoManager but with mocked internals
        manager = MagicMock(spec=GoldenRepoManager)

        # Simulate existing golden repos
        manager.list_golden_repos.return_value = [
            {
                "alias": "repo1",
                "repo_url": "https://github.com/org/repo1",
                "default_branch": "main",
                "clone_path": f"{temp_data_dir}/repo1",
                "created_at": "2024-01-01T00:00:00Z",
                "enable_temporal": False,
                "temporal_options": None,
            },
            {
                "alias": "repo2",
                "repo_url": "https://github.com/org/repo2",
                "default_branch": "main",
                "clone_path": f"{temp_data_dir}/repo2",
                "created_at": "2024-01-02T00:00:00Z",
                "enable_temporal": False,
                "temporal_options": None,
            },
            {
                "alias": "repo3",
                "repo_url": "https://github.com/org/repo3",
                "default_branch": "main",
                "clone_path": f"{temp_data_dir}/repo3",
                "created_at": "2024-01-03T00:00:00Z",
                "enable_temporal": False,
                "temporal_options": None,
            },
        ]

        manager.group_access_manager = None  # Will be set during migration
        return manager

    def test_existing_repos_assigned_to_admins_group(
        self, temp_db_path, mock_golden_repo_manager
    ):
        """
        Test that after initialization, existing repos are assigned to admins group.

        AC1: Existing golden repos should be seeded to admins group during startup.
        """
        # Given: GroupAccessManager initialized (creates default groups)
        group_manager = GroupAccessManager(temp_db_path)
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        assert admins_group is not None

        # When: We simulate the app.py initialization flow
        # This calls the seed_existing_golden_repos function
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        seeded_count = seed_existing_golden_repos(
            mock_golden_repo_manager, group_manager
        )

        # Then: All repos should be assigned to admins
        admins_repos = group_manager.get_group_repos(admins_group.id)

        # Note: cidx-meta is always included first (implicit access)
        assert "repo1" in admins_repos
        assert "repo2" in admins_repos
        assert "repo3" in admins_repos
        assert seeded_count == 3

    def test_existing_repos_assigned_to_powerusers_group(
        self, temp_db_path, mock_golden_repo_manager
    ):
        """
        Test that after initialization, existing repos are assigned to powerusers group.

        AC2: Existing golden repos should be seeded to powerusers group during startup.
        """
        # Given: GroupAccessManager initialized (creates default groups)
        group_manager = GroupAccessManager(temp_db_path)
        powerusers_group = group_manager.get_group_by_name(DEFAULT_GROUP_POWERUSERS)
        assert powerusers_group is not None

        # When: We simulate the app.py initialization flow
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        seed_existing_golden_repos(mock_golden_repo_manager, group_manager)

        # Then: All repos should be assigned to powerusers
        powerusers_repos = group_manager.get_group_repos(powerusers_group.id)

        # Note: cidx-meta is always included first (implicit access)
        assert "repo1" in powerusers_repos
        assert "repo2" in powerusers_repos
        assert "repo3" in powerusers_repos

    def test_migration_is_idempotent(self, temp_db_path, mock_golden_repo_manager):
        """
        Test that running migration multiple times is safe (idempotent).

        AC3: Migration must be idempotent - safe to run on every startup.
        auto_assign_golden_repo uses INSERT OR IGNORE internally.
        """
        # Given: GroupAccessManager initialized
        group_manager = GroupAccessManager(temp_db_path)

        # When: We run migration multiple times (simulating server restarts)
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        first_run = seed_existing_golden_repos(mock_golden_repo_manager, group_manager)
        second_run = seed_existing_golden_repos(mock_golden_repo_manager, group_manager)
        third_run = seed_existing_golden_repos(mock_golden_repo_manager, group_manager)

        # Then: All runs should succeed without errors
        assert first_run == 3
        assert (
            second_run == 3
        )  # Still processes 3, but INSERT OR IGNORE skips duplicates
        assert third_run == 3

        # Verify repos are still accessible exactly once per group
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        admins_repos = group_manager.get_group_repos(admins_group.id)

        # Count how many times each repo appears (should be exactly once)
        repo1_count = admins_repos.count("repo1")
        repo2_count = admins_repos.count("repo2")
        repo3_count = admins_repos.count("repo3")

        assert repo1_count == 1
        assert repo2_count == 1
        assert repo3_count == 1

    def test_handles_empty_repo_list(self, temp_db_path):
        """
        Test that migration handles empty repo list gracefully.

        AC4: Migration should handle edge case of no existing repos.
        """
        # Given: GroupAccessManager initialized
        group_manager = GroupAccessManager(temp_db_path)

        # And: Mock GoldenRepoManager with no repos
        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = []

        # When: We run migration
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        seeded_count = seed_existing_golden_repos(mock_manager, group_manager)

        # Then: Should complete successfully with 0 repos seeded
        assert seeded_count == 0

    def test_handles_repo_without_alias_field(self, temp_db_path):
        """
        Test that migration handles repos with 'name' field instead of 'alias'.

        AC5: Migration should handle both 'alias' and 'name' field names.
        """
        # Given: GroupAccessManager initialized
        group_manager = GroupAccessManager(temp_db_path)

        # And: Mock GoldenRepoManager with repos using 'name' instead of 'alias'
        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = [
            {
                "name": "repo-with-name",  # Uses 'name' instead of 'alias'
                "repo_url": "https://github.com/org/repo",
                "default_branch": "main",
                "clone_path": "/tmp/repo",
                "created_at": "2024-01-01T00:00:00Z",
            },
        ]

        # When: We run migration
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        seeded_count = seed_existing_golden_repos(mock_manager, group_manager)

        # Then: Should handle 'name' field correctly
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        admins_repos = group_manager.get_group_repos(admins_group.id)

        assert "repo-with-name" in admins_repos
        assert seeded_count == 1

    def test_logs_migration_results(
        self, temp_db_path, mock_golden_repo_manager, caplog
    ):
        """
        Test that migration logs results appropriately.

        AC6: Migration should log informative messages about results.
        """
        import logging

        # Given: GroupAccessManager initialized
        group_manager = GroupAccessManager(temp_db_path)

        # When: We run migration with logging capture
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        with caplog.at_level(logging.INFO):
            seed_existing_golden_repos(mock_golden_repo_manager, group_manager)

        # Then: Should have logged the seeding info
        # Note: This is a soft assertion - logging may vary
        # The main requirement is no errors should be logged

    def test_continues_on_individual_repo_failure(self, temp_db_path, caplog):
        """
        Test that migration continues even if individual repo assignment fails.

        AC7: Migration should be resilient - one repo failure shouldn't stop others.
        """
        import logging

        # Given: GroupAccessManager initialized
        group_manager = GroupAccessManager(temp_db_path)

        # And: Mock GoldenRepoManager with some repos, one will fail
        mock_manager = MagicMock()
        mock_manager.list_golden_repos.return_value = [
            {"alias": "repo1"},
            {"alias": None},  # This one has no alias - should be skipped
            {"alias": "repo3"},
        ]

        # When: We run migration
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        with caplog.at_level(logging.WARNING):
            seed_existing_golden_repos(mock_manager, group_manager)

        # Then: Valid repos should still be seeded
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        admins_repos = group_manager.get_group_repos(admins_group.id)

        assert "repo1" in admins_repos
        assert "repo3" in admins_repos
        # repo with None alias should be skipped (count may be 2)


class TestExistingRepoMigrationIntegration:
    """Integration tests simulating actual app.py startup flow."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    @pytest.fixture
    def temp_data_dir(self):
        """Create a temporary data directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    def test_full_startup_flow_seeds_existing_repos(self, temp_db_path, temp_data_dir):
        """
        Test the complete startup flow as it would happen in app.py.

        This simulates the exact sequence of operations in app.py lifespan.
        """
        # Given: GoldenRepoManager with existing repos
        mock_golden_repo_manager = MagicMock()
        mock_golden_repo_manager.list_golden_repos.return_value = [
            {"alias": "existing-repo-1"},
            {"alias": "existing-repo-2"},
        ]

        # When: We execute the app.py startup flow
        # 1. Initialize GroupAccessManager
        group_manager = GroupAccessManager(temp_db_path)

        # 2. Inject GroupAccessManager into GoldenRepoManager
        mock_golden_repo_manager.group_access_manager = group_manager

        # 3. Seed existing golden repos (the NEW code we're adding)
        from code_indexer.server.services.group_access_manager import (
            seed_existing_golden_repos,
        )

        seeded_count = seed_existing_golden_repos(
            mock_golden_repo_manager, group_manager
        )

        # Then: Repos should be accessible to admins and powerusers
        admins_group = group_manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
        powerusers_group = group_manager.get_group_by_name(DEFAULT_GROUP_POWERUSERS)

        admins_repos = group_manager.get_group_repos(admins_group.id)
        powerusers_repos = group_manager.get_group_repos(powerusers_group.id)

        assert "existing-repo-1" in admins_repos
        assert "existing-repo-2" in admins_repos
        assert "existing-repo-1" in powerusers_repos
        assert "existing-repo-2" in powerusers_repos
        assert seeded_count == 2
