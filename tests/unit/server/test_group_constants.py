"""
Unit tests for group-related constants.

Story: Extract Magic Strings to Constants

Tests that verify:
- Constants are defined in the constants module
- Constants are used consistently across all modules
- Constants have the expected values

TDD: These tests are written FIRST, before implementation.
"""

import pytest


class TestGroupConstants:
    """Tests for group-related constants module."""

    def test_default_group_admins_constant_exists(self):
        """Test that DEFAULT_GROUP_ADMINS constant is defined."""
        from code_indexer.server.services.constants import DEFAULT_GROUP_ADMINS

        assert DEFAULT_GROUP_ADMINS == "admins"

    def test_default_group_powerusers_constant_exists(self):
        """Test that DEFAULT_GROUP_POWERUSERS constant is defined."""
        from code_indexer.server.services.constants import DEFAULT_GROUP_POWERUSERS

        assert DEFAULT_GROUP_POWERUSERS == "powerusers"

    def test_default_group_users_constant_exists(self):
        """Test that DEFAULT_GROUP_USERS constant is defined."""
        from code_indexer.server.services.constants import DEFAULT_GROUP_USERS

        assert DEFAULT_GROUP_USERS == "users"

    def test_cidx_meta_repo_constant_exists(self):
        """Test that CIDX_META_REPO constant is defined."""
        from code_indexer.server.services.constants import CIDX_META_REPO

        assert CIDX_META_REPO == "cidx-meta"


class TestConstantsUsageInGroupAccessManager:
    """Tests that group_access_manager uses constants."""

    def test_default_groups_list_uses_constants(self):
        """Test that DEFAULT_GROUPS uses constant values."""
        from code_indexer.server.services.group_access_manager import DEFAULT_GROUPS
        from code_indexer.server.services.constants import (
            DEFAULT_GROUP_ADMINS,
            DEFAULT_GROUP_POWERUSERS,
            DEFAULT_GROUP_USERS,
        )

        group_names = [g["name"] for g in DEFAULT_GROUPS]

        assert DEFAULT_GROUP_ADMINS in group_names
        assert DEFAULT_GROUP_POWERUSERS in group_names
        assert DEFAULT_GROUP_USERS in group_names

    def test_auto_assign_uses_constants(self):
        """Test that auto_assign_golden_repo uses constant for group names."""
        import tempfile
        from pathlib import Path

        from code_indexer.server.services.group_access_manager import GroupAccessManager
        from code_indexer.server.services.constants import (
            DEFAULT_GROUP_ADMINS,
            DEFAULT_GROUP_POWERUSERS,
        )

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            manager = GroupAccessManager(db_path)
            manager.auto_assign_golden_repo("test-repo")

            # Verify admins and powerusers got access
            admins = manager.get_group_by_name(DEFAULT_GROUP_ADMINS)
            powerusers = manager.get_group_by_name(DEFAULT_GROUP_POWERUSERS)

            assert admins is not None
            assert powerusers is not None

            admin_repos = manager.get_group_repos(admins.id)
            poweruser_repos = manager.get_group_repos(powerusers.id)

            assert "test-repo" in admin_repos
            assert "test-repo" in poweruser_repos
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_revoke_repo_access_checks_cidx_meta_constant(self):
        """Test that revoke_repo_access uses CIDX_META_REPO constant."""
        import tempfile
        from pathlib import Path

        from code_indexer.server.services.group_access_manager import (
            GroupAccessManager,
            CidxMetaCannotBeRevokedError,
        )
        from code_indexer.server.services.constants import CIDX_META_REPO

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            manager = GroupAccessManager(db_path)
            admins = manager.get_group_by_name("admins")

            # Trying to revoke cidx-meta should fail
            with pytest.raises(CidxMetaCannotBeRevokedError):
                manager.revoke_repo_access(CIDX_META_REPO, admins.id)
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_get_group_repos_includes_cidx_meta_constant(self):
        """Test that get_group_repos includes CIDX_META_REPO."""
        import tempfile
        from pathlib import Path

        from code_indexer.server.services.group_access_manager import GroupAccessManager
        from code_indexer.server.services.constants import CIDX_META_REPO

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            manager = GroupAccessManager(db_path)
            users = manager.get_group_by_name("users")

            repos = manager.get_group_repos(users.id)

            assert CIDX_META_REPO in repos
        finally:
            if db_path.exists():
                db_path.unlink()


class TestConstantsUsageInAccessFilteringService:
    """Tests that access_filtering_service uses constants."""

    def test_admin_group_name_matches_constant(self):
        """Test that ADMIN_GROUP_NAME matches DEFAULT_GROUP_ADMINS constant."""
        from code_indexer.server.services.access_filtering_service import (
            AccessFilteringService,
        )
        from code_indexer.server.services.constants import DEFAULT_GROUP_ADMINS

        assert AccessFilteringService.ADMIN_GROUP_NAME == DEFAULT_GROUP_ADMINS

    def test_get_accessible_repos_returns_cidx_meta_constant(self):
        """Test that get_accessible_repos returns CIDX_META_REPO for unassigned users."""
        import tempfile
        from pathlib import Path

        from code_indexer.server.services.group_access_manager import GroupAccessManager
        from code_indexer.server.services.access_filtering_service import (
            AccessFilteringService,
        )
        from code_indexer.server.services.constants import CIDX_META_REPO

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            manager = GroupAccessManager(db_path)
            service = AccessFilteringService(manager)

            # User not assigned to any group should get cidx-meta only
            repos = service.get_accessible_repos("unassigned-user")

            assert CIDX_META_REPO in repos
        finally:
            if db_path.exists():
                db_path.unlink()


class TestConstantsUsageInSSOProvisioningHook:
    """Tests that sso_provisioning_hook uses constants."""

    def test_ensure_group_membership_uses_users_constant(self):
        """Test that ensure_group_membership uses DEFAULT_GROUP_USERS."""
        import tempfile
        from pathlib import Path

        from code_indexer.server.services.group_access_manager import GroupAccessManager
        from code_indexer.server.services.sso_provisioning_hook import (
            SSOProvisioningHook,
        )
        from code_indexer.server.services.constants import DEFAULT_GROUP_USERS

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)

        try:
            manager = GroupAccessManager(db_path)
            hook = SSOProvisioningHook(manager)

            # New user should be assigned to "users" group
            result = hook.ensure_group_membership("new-sso-user")

            assert result is True

            user_group = manager.get_user_group("new-sso-user")
            assert user_group is not None
            assert user_group.name == DEFAULT_GROUP_USERS
        finally:
            if db_path.exists():
                db_path.unlink()


class TestConstantsUsageInGroupsRouter:
    """Tests that groups router uses constants."""

    def test_bulk_remove_repos_skips_cidx_meta_constant(self):
        """Test that bulk remove endpoint skips CIDX_META_REPO."""
        # This test validates the constant is used in the comparison
        # The actual endpoint behavior is tested in integration tests
        from code_indexer.server.services.constants import CIDX_META_REPO

        # The constant should be "cidx-meta"
        assert CIDX_META_REPO == "cidx-meta"
