"""
Unit tests for Admin Full Access bug fix.

Bug: Admin users only see repos explicitly assigned to the admins group.
Fix: Admin users must see ALL repos from ALL groups in the system.

TDD: These tests are written FIRST, before the fix is implemented.
"""

import pytest
import tempfile
from pathlib import Path

from code_indexer.server.services.group_access_manager import GroupAccessManager
from code_indexer.server.services.access_filtering_service import (
    AccessFilteringService,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def group_access_manager(temp_db_path):
    """Create a GroupAccessManager with test data for admin full access test."""
    manager = GroupAccessManager(temp_db_path)
    return manager


@pytest.fixture
def access_filtering_service(group_access_manager):
    """Create an AccessFilteringService with test data."""
    return AccessFilteringService(group_access_manager)


class TestAdminFullAccessBug:
    """
    Tests for the admin full access bug fix.

    Bug: get_accessible_repos() for admin users only returns repos
    explicitly assigned to the admins group.

    Expected: Admin users should see ALL repos from ALL groups in the system.
    """

    def test_admin_sees_all_repos_from_all_groups(
        self, group_access_manager, access_filtering_service
    ):
        """
        Admin user must see ALL repos from ALL groups, not just admins group repos.

        Setup:
        - Create custom group X with repos A, B assigned
        - Create custom group Y with repos C, D assigned
        - Admin user in admins group
        - Regular user in users group

        Verify:
        - Admin can see A, B, C, D (all repos from all groups)
        - Regular user only sees cidx-meta
        """
        # Get default groups
        admins = group_access_manager.get_group_by_name("admins")
        users = group_access_manager.get_group_by_name("users")

        # Create custom groups
        group_x = group_access_manager.create_group(
            "group_x", "Custom group X for testing"
        )
        group_y = group_access_manager.create_group(
            "group_y", "Custom group Y for testing"
        )

        # Assign repos to custom groups (NOT to admins group)
        group_access_manager.grant_repo_access("repo-a", group_x.id, "system:test")
        group_access_manager.grant_repo_access("repo-b", group_x.id, "system:test")
        group_access_manager.grant_repo_access("repo-c", group_y.id, "system:test")
        group_access_manager.grant_repo_access("repo-d", group_y.id, "system:test")

        # Assign users to groups
        group_access_manager.assign_user_to_group("admin_user", admins.id, "system")
        group_access_manager.assign_user_to_group("regular_user", users.id, "system")

        # Test admin user - should see ALL repos from ALL groups
        admin_repos = access_filtering_service.get_accessible_repos("admin_user")

        assert "cidx-meta" in admin_repos, "Admin must see cidx-meta"
        assert "repo-a" in admin_repos, "Admin must see repo-a from group_x"
        assert "repo-b" in admin_repos, "Admin must see repo-b from group_x"
        assert "repo-c" in admin_repos, "Admin must see repo-c from group_y"
        assert "repo-d" in admin_repos, "Admin must see repo-d from group_y"

        # Test regular user - should only see cidx-meta
        regular_repos = access_filtering_service.get_accessible_repos("regular_user")

        assert "cidx-meta" in regular_repos, "Regular user must see cidx-meta"
        assert "repo-a" not in regular_repos, "Regular user must NOT see repo-a"
        assert "repo-b" not in regular_repos, "Regular user must NOT see repo-b"
        assert "repo-c" not in regular_repos, "Regular user must NOT see repo-c"
        assert "repo-d" not in regular_repos, "Regular user must NOT see repo-d"

    def test_admin_sees_repos_assigned_only_to_non_admin_groups(
        self, group_access_manager, access_filtering_service
    ):
        """
        Admin should see repos even if admins group has NO explicit repo assignments.

        This tests the core bug: admins group has no repos assigned, but admin
        users should still see all repos assigned to other groups.
        """
        admins = group_access_manager.get_group_by_name("admins")
        powerusers = group_access_manager.get_group_by_name("powerusers")

        # Assign repos ONLY to powerusers, NOT to admins
        group_access_manager.grant_repo_access(
            "secret-repo", powerusers.id, "system:test"
        )
        group_access_manager.grant_repo_access(
            "another-repo", powerusers.id, "system:test"
        )

        # Admin user in admins group (admins group has NO repos assigned)
        group_access_manager.assign_user_to_group("admin_user", admins.id, "system")

        # Admin should still see ALL repos from powerusers group
        admin_repos = access_filtering_service.get_accessible_repos("admin_user")

        assert (
            "secret-repo" in admin_repos
        ), "Admin must see secret-repo from powerusers group"
        assert (
            "another-repo" in admin_repos
        ), "Admin must see another-repo from powerusers group"

    def test_admin_full_access_includes_all_custom_groups(
        self, group_access_manager, access_filtering_service
    ):
        """
        Admin should see repos from multiple custom groups.

        Tests that admin access aggregates across:
        - Default groups (admins, powerusers, users)
        - Custom groups created by admins
        """
        admins = group_access_manager.get_group_by_name("admins")
        powerusers = group_access_manager.get_group_by_name("powerusers")

        # Create multiple custom groups
        team_alpha = group_access_manager.create_group("team_alpha", "Team Alpha")
        team_beta = group_access_manager.create_group("team_beta", "Team Beta")
        team_gamma = group_access_manager.create_group("team_gamma", "Team Gamma")

        # Assign repos to various groups (spread across default and custom)
        group_access_manager.grant_repo_access(
            "alpha-repo", team_alpha.id, "system:test"
        )
        group_access_manager.grant_repo_access("beta-repo", team_beta.id, "system:test")
        group_access_manager.grant_repo_access(
            "gamma-repo", team_gamma.id, "system:test"
        )
        group_access_manager.grant_repo_access(
            "shared-repo", powerusers.id, "system:test"
        )

        # Admin user
        group_access_manager.assign_user_to_group("admin_user", admins.id, "system")

        # Admin should see ALL repos from ALL groups
        admin_repos = access_filtering_service.get_accessible_repos("admin_user")

        assert "alpha-repo" in admin_repos, "Admin must see alpha-repo from team_alpha"
        assert "beta-repo" in admin_repos, "Admin must see beta-repo from team_beta"
        assert "gamma-repo" in admin_repos, "Admin must see gamma-repo from team_gamma"
        assert (
            "shared-repo" in admin_repos
        ), "Admin must see shared-repo from powerusers"
        assert "cidx-meta" in admin_repos, "Admin must see cidx-meta"

    def test_admin_full_access_with_duplicate_repos_across_groups(
        self, group_access_manager, access_filtering_service
    ):
        """
        Admin should not get duplicate repos when same repo is in multiple groups.

        Repos can be assigned to multiple groups. Admin should see each unique
        repo only once in the accessible repos set.
        """
        admins = group_access_manager.get_group_by_name("admins")
        powerusers = group_access_manager.get_group_by_name("powerusers")

        group_x = group_access_manager.create_group("group_x", "Group X")
        group_y = group_access_manager.create_group("group_y", "Group Y")

        # Same repo assigned to multiple groups
        group_access_manager.grant_repo_access(
            "shared-repo", powerusers.id, "system:test"
        )
        group_access_manager.grant_repo_access("shared-repo", group_x.id, "system:test")
        group_access_manager.grant_repo_access("shared-repo", group_y.id, "system:test")

        # Also some unique repos
        group_access_manager.grant_repo_access("unique-x", group_x.id, "system:test")
        group_access_manager.grant_repo_access("unique-y", group_y.id, "system:test")

        # Admin user
        group_access_manager.assign_user_to_group("admin_user", admins.id, "system")

        admin_repos = access_filtering_service.get_accessible_repos("admin_user")

        # Should be a set, so duplicates naturally deduplicated
        assert isinstance(admin_repos, set), "get_accessible_repos should return a set"
        assert "shared-repo" in admin_repos, "Admin must see shared-repo"
        assert "unique-x" in admin_repos, "Admin must see unique-x"
        assert "unique-y" in admin_repos, "Admin must see unique-y"

        # Count occurrences - should be exactly 1 (sets handle this automatically)
        repo_list = list(admin_repos)
        assert (
            repo_list.count("shared-repo") == 1
        ), "shared-repo should appear exactly once"
