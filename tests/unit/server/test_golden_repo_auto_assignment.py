"""
Unit tests for Golden Repo Auto-Assignment Integration.

Story #706: Repository-to-Group Access Mapping with Auto-Assignment

This file covers AC3 integration:
- When golden repo is registered, auto_assign_golden_repo hook is called

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path

from code_indexer.server.services.group_access_manager import GroupAccessManager


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestGoldenRepoAutoAssignmentHook:
    """Tests for auto-assignment hook integration with golden repo manager."""

    def test_on_repo_added_calls_auto_assign(self, temp_db_path):
        """Test that on_repo_added hook triggers auto_assign_golden_repo."""
        from code_indexer.server.services.group_access_hooks import on_repo_added

        manager = GroupAccessManager(temp_db_path)

        # Call the hook
        on_repo_added("new-repo", manager)

        # Verify repo is now accessible by admins and powerusers
        admins = manager.get_group_by_name("admins")
        powerusers = manager.get_group_by_name("powerusers")
        users = manager.get_group_by_name("users")

        admins_repos = manager.get_group_repos(admins.id)
        powerusers_repos = manager.get_group_repos(powerusers.id)
        users_repos = manager.get_group_repos(users.id)

        assert "new-repo" in admins_repos
        assert "new-repo" in powerusers_repos
        assert "new-repo" not in users_repos

    def test_on_repo_added_is_idempotent(self, temp_db_path):
        """Test that calling on_repo_added twice doesn't create duplicates."""
        from code_indexer.server.services.group_access_hooks import on_repo_added

        manager = GroupAccessManager(temp_db_path)

        # Call the hook twice
        on_repo_added("new-repo", manager)
        on_repo_added("new-repo", manager)

        # Verify only one entry per group
        admins = manager.get_group_by_name("admins")
        admins_repos = manager.get_group_repos(admins.id)

        # cidx-meta + new-repo = 2 repos
        assert admins_repos.count("new-repo") == 1

    def test_on_repo_removed_revokes_access(self, temp_db_path):
        """Test that on_repo_removed hook revokes access from all groups."""
        from code_indexer.server.services.group_access_hooks import (
            on_repo_added,
            on_repo_removed,
        )

        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        # First add a repo via the hook
        on_repo_added("test-repo", manager)
        assert "test-repo" in manager.get_group_repos(admins.id)

        # Now remove it via the hook
        on_repo_removed("test-repo", manager)

        # Verify it's no longer accessible
        admins_repos = manager.get_group_repos(admins.id)
        assert "test-repo" not in admins_repos
