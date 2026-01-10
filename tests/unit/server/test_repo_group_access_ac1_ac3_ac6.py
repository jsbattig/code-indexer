"""
Unit tests for Repository-to-Group Access Mapping - Part 2.

Story #706: Repository-to-Group Access Mapping with Auto-Assignment

This file covers:
- AC1: Repository-Group Many-to-Many Relationship
- AC3: New Golden Repos Auto-Assigned to Admins and Powerusers
- AC4: Users Group Has No Auto-Assigned Repos
- AC5: Admin Manual Override for Repo Access
- AC6: Access Grant Metadata Recorded

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    RepoGroupAccess,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


class TestRepoGroupManyToMany:
    """Tests for AC1: Repository-Group Many-to-Many Relationship."""

    def test_repository_can_be_granted_to_multiple_groups(self, temp_db_path):
        """Test that a repository can be granted access to multiple groups."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")
        powerusers = manager.get_group_by_name("powerusers")
        users = manager.get_group_by_name("users")

        manager.grant_repo_access("shared-repo", admins.id, "admin")
        manager.grant_repo_access("shared-repo", powerusers.id, "admin")
        manager.grant_repo_access("shared-repo", users.id, "admin")

        admins_repos = manager.get_group_repos(admins.id)
        powerusers_repos = manager.get_group_repos(powerusers.id)
        users_repos = manager.get_group_repos(users.id)

        assert "shared-repo" in admins_repos
        assert "shared-repo" in powerusers_repos
        assert "shared-repo" in users_repos

    def test_group_can_access_multiple_repositories(self, temp_db_path):
        """Test that a group can access multiple repositories."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.grant_repo_access("repo-1", admins.id, "admin")
        manager.grant_repo_access("repo-2", admins.id, "admin")
        manager.grant_repo_access("repo-3", admins.id, "admin")

        repos = manager.get_group_repos(admins.id)

        assert "repo-1" in repos
        assert "repo-2" in repos
        assert "repo-3" in repos

    def test_get_repo_groups_returns_all_groups_with_access(self, temp_db_path):
        """Test that get_repo_groups returns all groups with access."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")
        powerusers = manager.get_group_by_name("powerusers")

        manager.grant_repo_access("test-repo", admins.id, "admin")
        manager.grant_repo_access("test-repo", powerusers.id, "admin")

        groups = manager.get_repo_groups("test-repo")

        group_names = [g.name for g in groups]
        assert "admins" in group_names
        assert "powerusers" in group_names
        assert len(groups) == 2


class TestAutoAssignGoldenRepos:
    """Tests for AC3: New Golden Repos Auto-Assigned to Admins and Powerusers."""

    def test_auto_assign_adds_to_admins_group(self, temp_db_path):
        """Test that auto_assign_golden_repo adds repo to admins group."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.auto_assign_golden_repo("new-golden-repo")

        admins_repos = manager.get_group_repos(admins.id)
        assert "new-golden-repo" in admins_repos

    def test_auto_assign_adds_to_powerusers_group(self, temp_db_path):
        """Test that auto_assign_golden_repo adds repo to powerusers group."""
        manager = GroupAccessManager(temp_db_path)
        powerusers = manager.get_group_by_name("powerusers")

        manager.auto_assign_golden_repo("new-golden-repo")

        powerusers_repos = manager.get_group_repos(powerusers.id)
        assert "new-golden-repo" in powerusers_repos

    def test_auto_assign_does_not_add_to_users_group(self, temp_db_path):
        """Test that auto_assign_golden_repo does NOT add to users group."""
        manager = GroupAccessManager(temp_db_path)
        users = manager.get_group_by_name("users")

        manager.auto_assign_golden_repo("new-golden-repo")

        users_repos = manager.get_group_repos(users.id)
        assert "new-golden-repo" not in users_repos
        assert "cidx-meta" in users_repos

    def test_auto_assign_sets_granted_by_system(self, temp_db_path):
        """Test that auto_assign_golden_repo sets granted_by correctly."""
        manager = GroupAccessManager(temp_db_path)

        manager.auto_assign_golden_repo("new-golden-repo")

        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT granted_by FROM repo_group_access WHERE repo_name = ?",
            ("new-golden-repo",),
        )
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            assert row["granted_by"] == "system:auto-assignment"


class TestUsersGroupNoAutoAssign:
    """Tests for AC4: Users Group Has No Auto-Assigned Repos."""

    def test_users_group_only_has_cidx_meta_initially(self, temp_db_path):
        """Test that users group only has cidx-meta initially."""
        manager = GroupAccessManager(temp_db_path)
        users = manager.get_group_by_name("users")

        repos = manager.get_group_repos(users.id)

        assert repos == ["cidx-meta"]

    def test_users_group_not_affected_by_auto_assign(self, temp_db_path):
        """Test that multiple auto-assignments don't affect users group."""
        manager = GroupAccessManager(temp_db_path)
        users = manager.get_group_by_name("users")

        manager.auto_assign_golden_repo("repo-1")
        manager.auto_assign_golden_repo("repo-2")
        manager.auto_assign_golden_repo("repo-3")

        users_repos = manager.get_group_repos(users.id)

        assert users_repos == ["cidx-meta"]


class TestAdminManualOverride:
    """Tests for AC5: Admin Manual Override for Repo Access."""

    def test_admin_can_add_repo_to_group(self, temp_db_path):
        """Test that admin can add a repository to any group."""
        manager = GroupAccessManager(temp_db_path)
        users = manager.get_group_by_name("users")

        result = manager.grant_repo_access("test-repo", users.id, "admin_user")

        assert result is True
        repos = manager.get_group_repos(users.id)
        assert "test-repo" in repos

    def test_admin_can_remove_repo_from_group(self, temp_db_path):
        """Test that admin can remove a repository from a group."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.grant_repo_access("test-repo", admins.id, "admin_user")
        assert "test-repo" in manager.get_group_repos(admins.id)

        result = manager.revoke_repo_access("test-repo", admins.id)

        assert result is True
        repos = manager.get_group_repos(admins.id)
        assert "test-repo" not in repos

    def test_revoke_nonexistent_repo_returns_false(self, temp_db_path):
        """Test that revoking nonexistent repo access returns False."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        result = manager.revoke_repo_access("nonexistent-repo", admins.id)

        assert result is False

    def test_grant_repo_to_nonexistent_group_fails(self, temp_db_path):
        """Test that granting repo to nonexistent group fails."""
        manager = GroupAccessManager(temp_db_path)

        with pytest.raises(ValueError) as exc_info:
            manager.grant_repo_access("test-repo", 99999, "admin")

        assert "not found" in str(exc_info.value).lower()


class TestAccessGrantMetadata:
    """Tests for AC6: Access Grant Metadata Recorded."""

    def test_grant_records_repo_name(self, temp_db_path):
        """Test that grant records include repo_name."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.grant_repo_access("my-test-repo", admins.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT repo_name FROM repo_group_access WHERE group_id = ?", (admins.id,)
        )
        row = cursor.fetchone()
        conn.close()

        assert row["repo_name"] == "my-test-repo"

    def test_grant_records_group_id(self, temp_db_path):
        """Test that grant records include group_id."""
        manager = GroupAccessManager(temp_db_path)
        powerusers = manager.get_group_by_name("powerusers")

        manager.grant_repo_access("test-repo", powerusers.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT group_id FROM repo_group_access WHERE repo_name = ?", ("test-repo",)
        )
        row = cursor.fetchone()
        conn.close()

        assert row["group_id"] == powerusers.id

    def test_grant_records_granted_at_timestamp(self, temp_db_path):
        """Test that grant records include granted_at timestamp."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        before_grant = datetime.now(timezone.utc)
        manager.grant_repo_access("test-repo", admins.id, "admin")

        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT granted_at FROM repo_group_access WHERE repo_name = ?",
            ("test-repo",),
        )
        row = cursor.fetchone()
        conn.close()

        granted_at_str = row["granted_at"]
        granted_at = datetime.fromisoformat(granted_at_str.replace("Z", "+00:00"))

        assert granted_at.date() == before_grant.date()

    def test_grant_records_granted_by_user(self, temp_db_path):
        """Test that grant records include granted_by field."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.grant_repo_access("test-repo", admins.id, "john_admin")

        conn = sqlite3.connect(str(temp_db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT granted_by FROM repo_group_access WHERE repo_name = ?",
            ("test-repo",),
        )
        row = cursor.fetchone()
        conn.close()

        assert row["granted_by"] == "john_admin"

    def test_get_repo_access_returns_metadata(self, temp_db_path):
        """Test that get_repo_access returns full metadata record."""
        manager = GroupAccessManager(temp_db_path)
        admins = manager.get_group_by_name("admins")

        manager.grant_repo_access("test-repo", admins.id, "admin_user")

        record = manager.get_repo_access("test-repo", admins.id)

        assert record is not None
        assert isinstance(record, RepoGroupAccess)
        assert record.repo_name == "test-repo"
        assert record.group_id == admins.id
        assert record.granted_by == "admin_user"
        assert record.granted_at is not None
        assert isinstance(record.granted_at, datetime)
