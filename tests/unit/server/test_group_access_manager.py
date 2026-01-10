"""
Unit tests for GroupAccessManager service.

Tests:
- AC1: Default groups created at bootstrap (admins, powerusers, users)
- AC2: Default groups cannot be deleted
- AC3: Users assigned to exactly one group (1:1)
- AC4: Group membership records assignment metadata
- AC6: Idempotent bootstrap (no duplicates on restart)

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

# These imports will fail initially - that's the TDD approach
from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
    Group,
    DefaultGroupCannotBeDeletedError,
)


class TestGroupAccessManagerBootstrap:
    """Tests for AC1: Default groups created at bootstrap."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        # Cleanup after test
        if db_path.exists():
            db_path.unlink()

    def test_default_groups_created_at_bootstrap(self, temp_db_path):
        """Test that three default groups exist after system initialization."""
        # When: GroupAccessManager is initialized
        manager = GroupAccessManager(temp_db_path)

        # Then: Three default groups should exist
        groups = manager.get_all_groups()
        assert len(groups) == 3

        group_names = {g.name for g in groups}
        assert group_names == {"admins", "powerusers", "users"}

    def test_default_groups_have_correct_descriptions(self, temp_db_path):
        """Test that default groups have appropriate descriptions."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        powerusers = manager.get_group_by_name("powerusers")
        users = manager.get_group_by_name("users")

        assert admins is not None
        assert (
            "administrative" in admins.description.lower()
            or "admin" in admins.description.lower()
        )

        assert powerusers is not None
        assert (
            "golden" in powerusers.description.lower()
            or "repositories" in powerusers.description.lower()
        )

        assert users is not None
        assert (
            "basic" in users.description.lower() or "meta" in users.description.lower()
        )

    def test_default_groups_have_is_default_true(self, temp_db_path):
        """Test that default groups have is_default=TRUE."""
        manager = GroupAccessManager(temp_db_path)

        for group in manager.get_all_groups():
            assert (
                group.is_default is True
            ), f"Group {group.name} should have is_default=TRUE"

    def test_default_groups_have_unique_integer_ids(self, temp_db_path):
        """Test that each default group has a unique integer ID."""
        manager = GroupAccessManager(temp_db_path)

        groups = manager.get_all_groups()
        ids = [g.id for g in groups]

        # All IDs should be integers
        assert all(isinstance(id_, int) for id_ in ids)

        # All IDs should be unique
        assert len(ids) == len(set(ids))

    def test_default_groups_have_created_at_timestamps(self, temp_db_path):
        """Test that groups table contains created_at timestamps."""
        manager = GroupAccessManager(temp_db_path)

        for group in manager.get_all_groups():
            assert group.created_at is not None
            assert isinstance(group.created_at, datetime)


class TestDefaultGroupDeletionProtection:
    """Tests for AC2: Default groups cannot be deleted."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    def test_delete_default_group_fails_with_error(self, temp_db_path):
        """Test that attempting to delete a default group fails with an error."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        assert admins is not None

        with pytest.raises(DefaultGroupCannotBeDeletedError) as exc_info:
            manager.delete_group(admins.id)

        # AC5: Error message indicates default groups cannot be deleted
        error_msg = str(exc_info.value).lower()
        assert (
            "default" in error_msg and "cannot" in error_msg and "delete" in error_msg
        )

    def test_delete_default_group_leaves_group_unchanged(self, temp_db_path):
        """Test that default group remains in database after delete attempt."""
        manager = GroupAccessManager(temp_db_path)

        powerusers = manager.get_group_by_name("powerusers")
        original_id = powerusers.id

        try:
            manager.delete_group(powerusers.id)
        except DefaultGroupCannotBeDeletedError:
            pass

        # Group should still exist unchanged
        powerusers_after = manager.get_group_by_name("powerusers")
        assert powerusers_after is not None
        assert powerusers_after.id == original_id
        assert powerusers_after.is_default is True

    def test_delete_all_default_groups_fails(self, temp_db_path):
        """Test that all default groups cannot be deleted."""
        manager = GroupAccessManager(temp_db_path)

        for group_name in ["admins", "powerusers", "users"]:
            group = manager.get_group_by_name(group_name)
            with pytest.raises(DefaultGroupCannotBeDeletedError):
                manager.delete_group(group.id)

    def test_delete_custom_group_succeeds(self, temp_db_path):
        """Test that custom (non-default) groups can be deleted."""
        manager = GroupAccessManager(temp_db_path)

        # Create a custom group
        custom_group = manager.create_group("test_group", "Test group for deletion")
        assert custom_group.is_default is False

        # Delete should succeed
        result = manager.delete_group(custom_group.id)
        assert result is True

        # Group should no longer exist
        assert manager.get_group(custom_group.id) is None


class TestUserGroupAssignment:
    """Tests for AC3: Users assigned to exactly one group (1:1)."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    def test_assign_user_to_group(self, temp_db_path):
        """Test that a user can be assigned to a group."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        manager.assign_user_to_group("user1", admins.id, "admin")

        user_group = manager.get_user_group("user1")
        assert user_group is not None
        assert user_group.name == "admins"

    def test_user_belongs_to_exactly_one_group(self, temp_db_path):
        """Test that user belongs to exactly one group at a time."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        users = manager.get_group_by_name("users")

        # Assign to admins first
        manager.assign_user_to_group("user1", admins.id, "admin")
        assert manager.get_user_group("user1").name == "admins"

        # Reassign to users - should replace
        manager.assign_user_to_group("user1", users.id, "admin")
        assert manager.get_user_group("user1").name == "users"

        # Verify only one membership exists via direct DB check
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM user_group_membership WHERE user_id = ?", ("user1",)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "User should have exactly one group membership row"

    def test_previous_group_assignment_is_replaced(self, temp_db_path):
        """Test that previous group assignment is replaced when reassigning."""
        manager = GroupAccessManager(temp_db_path)

        powerusers = manager.get_group_by_name("powerusers")
        users = manager.get_group_by_name("users")

        # Assign to powerusers
        manager.assign_user_to_group("user2", powerusers.id, "admin")
        users_in_powerusers = manager.get_users_in_group(powerusers.id)
        assert "user2" in users_in_powerusers

        # Reassign to users
        manager.assign_user_to_group("user2", users.id, "admin")

        # User should no longer be in powerusers
        users_in_powerusers = manager.get_users_in_group(powerusers.id)
        assert "user2" not in users_in_powerusers

        # User should now be in users group
        users_in_users = manager.get_users_in_group(users.id)
        assert "user2" in users_in_users

    def test_user_group_membership_table_has_one_row_per_user(self, temp_db_path):
        """Test that user_group_membership table has at most one row per user_id."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        powerusers = manager.get_group_by_name("powerusers")
        users_group = manager.get_group_by_name("users")

        # Assign user to multiple groups sequentially
        manager.assign_user_to_group("user3", admins.id, "admin")
        manager.assign_user_to_group("user3", powerusers.id, "admin")
        manager.assign_user_to_group("user3", users_group.id, "admin")

        # Direct database check
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM user_group_membership WHERE user_id = ?", ("user3",)
        )
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1, "Should have at most one row per user_id"


class TestGroupMembershipMetadata:
    """Tests for AC4: Group membership records assignment metadata."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    def test_membership_records_user_id(self, temp_db_path):
        """Test that membership record includes user_id."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        manager.assign_user_to_group("test_user", admins.id, "admin_user")

        # Get membership record directly
        membership = manager.get_user_membership("test_user")
        assert membership is not None
        assert membership.user_id == "test_user"

    def test_membership_records_group_id(self, temp_db_path):
        """Test that membership record includes group_id."""
        manager = GroupAccessManager(temp_db_path)

        powerusers = manager.get_group_by_name("powerusers")
        manager.assign_user_to_group("test_user", powerusers.id, "admin_user")

        membership = manager.get_user_membership("test_user")
        assert membership is not None
        assert membership.group_id == powerusers.id

    def test_membership_records_assigned_at_timestamp(self, temp_db_path):
        """Test that membership record includes assigned_at timestamp."""
        manager = GroupAccessManager(temp_db_path)

        before_assignment = datetime.now(timezone.utc)

        users = manager.get_group_by_name("users")
        manager.assign_user_to_group("test_user", users.id, "admin_user")

        membership = manager.get_user_membership("test_user")
        assert membership is not None
        assert membership.assigned_at is not None
        assert isinstance(membership.assigned_at, datetime)
        # Assigned_at should be between before and after
        # Allow for timezone differences by comparing just the date
        assert membership.assigned_at.date() == before_assignment.date()

    def test_membership_records_assigned_by_admin_user(self, temp_db_path):
        """Test that membership record includes assigned_by (admin user ID)."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        manager.assign_user_to_group("new_user", admins.id, "super_admin")

        membership = manager.get_user_membership("new_user")
        assert membership is not None
        assert membership.assigned_by == "super_admin"


class TestIdempotentBootstrap:
    """Tests for AC6: Idempotent bootstrap."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    def test_no_duplicate_groups_on_restart(self, temp_db_path):
        """Test that server restart does not create duplicate groups."""
        # First initialization
        manager1 = GroupAccessManager(temp_db_path)
        initial_groups = manager1.get_all_groups()
        initial_count = len(initial_groups)
        initial_ids = {g.id for g in initial_groups}

        # Simulate restart - create new manager instance
        manager2 = GroupAccessManager(temp_db_path)
        after_restart_groups = manager2.get_all_groups()

        # Should have same number of groups
        assert len(after_restart_groups) == initial_count == 3

        # Should have same IDs (no duplicates)
        after_restart_ids = {g.id for g in after_restart_groups}
        assert after_restart_ids == initial_ids

    def test_existing_group_data_unchanged_on_restart(self, temp_db_path):
        """Test that existing group data remains unchanged after restart."""
        # First initialization
        manager1 = GroupAccessManager(temp_db_path)
        original_admins = manager1.get_group_by_name("admins")
        original_created_at = original_admins.created_at

        # Simulate restart
        manager2 = GroupAccessManager(temp_db_path)
        admins_after = manager2.get_group_by_name("admins")

        # Data should be unchanged
        assert admins_after.id == original_admins.id
        assert admins_after.name == original_admins.name
        assert admins_after.description == original_admins.description
        assert admins_after.is_default == original_admins.is_default
        assert admins_after.created_at == original_created_at

    def test_multiple_restarts_no_duplicates(self, temp_db_path):
        """Test that multiple restarts do not create duplicates."""
        # Create managers multiple times (simulating multiple restarts)
        for _ in range(5):
            manager = GroupAccessManager(temp_db_path)
            groups = manager.get_all_groups()
            assert len(groups) == 3

    def test_no_errors_logged_on_restart(self, temp_db_path, caplog):
        """Test that no errors are logged during idempotent bootstrap."""
        import logging

        # First initialization
        GroupAccessManager(temp_db_path)

        # Clear captured logs
        caplog.clear()

        # Restart with logging capture
        with caplog.at_level(logging.ERROR):
            GroupAccessManager(temp_db_path)

        # Should have no error logs
        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert (
            len(error_logs) == 0
        ), f"Unexpected errors during restart: {[r.message for r in error_logs]}"


class TestGroupCRUDOperations:
    """Tests for GroupAccessManager CRUD operations."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary database file for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        if db_path.exists():
            db_path.unlink()

    def test_get_all_groups(self, temp_db_path):
        """Test get_all_groups returns list of groups."""
        manager = GroupAccessManager(temp_db_path)
        groups = manager.get_all_groups()

        assert isinstance(groups, list)
        assert all(isinstance(g, Group) for g in groups)

    def test_get_group_by_id(self, temp_db_path):
        """Test get_group returns group by ID."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        group_by_id = manager.get_group(admins.id)

        assert group_by_id is not None
        assert group_by_id.name == "admins"

    def test_get_group_returns_none_for_nonexistent(self, temp_db_path):
        """Test get_group returns None for nonexistent ID."""
        manager = GroupAccessManager(temp_db_path)

        result = manager.get_group(99999)
        assert result is None

    def test_get_group_by_name(self, temp_db_path):
        """Test get_group_by_name returns group by name."""
        manager = GroupAccessManager(temp_db_path)

        group = manager.get_group_by_name("powerusers")
        assert group is not None
        assert group.name == "powerusers"

    def test_get_group_by_name_returns_none_for_nonexistent(self, temp_db_path):
        """Test get_group_by_name returns None for nonexistent name."""
        manager = GroupAccessManager(temp_db_path)

        result = manager.get_group_by_name("nonexistent")
        assert result is None

    def test_create_group(self, temp_db_path):
        """Test create_group creates a new custom group."""
        manager = GroupAccessManager(temp_db_path)

        group = manager.create_group("developers", "Development team members")

        assert group.name == "developers"
        assert group.description == "Development team members"
        assert group.is_default is False
        assert group.id is not None
        assert group.created_at is not None

    def test_create_group_with_duplicate_name_fails(self, temp_db_path):
        """Test create_group fails for duplicate name."""
        manager = GroupAccessManager(temp_db_path)

        with pytest.raises(ValueError) as exc_info:
            manager.create_group("admins", "Duplicate admins group")

        assert "already exists" in str(exc_info.value).lower()

    def test_get_users_in_group(self, temp_db_path):
        """Test get_users_in_group returns list of user IDs."""
        manager = GroupAccessManager(temp_db_path)

        admins = manager.get_group_by_name("admins")
        manager.assign_user_to_group("user1", admins.id, "admin")
        manager.assign_user_to_group("user2", admins.id, "admin")

        users = manager.get_users_in_group(admins.id)
        assert isinstance(users, list)
        assert "user1" in users
        assert "user2" in users

    def test_get_users_in_empty_group(self, temp_db_path):
        """Test get_users_in_group returns empty list for group with no users."""
        manager = GroupAccessManager(temp_db_path)

        custom = manager.create_group("empty_group", "No users yet")
        users = manager.get_users_in_group(custom.id)

        assert isinstance(users, list)
        assert len(users) == 0

    def test_get_user_group_returns_none_for_unassigned_user(self, temp_db_path):
        """Test get_user_group returns None for user not assigned to any group."""
        manager = GroupAccessManager(temp_db_path)

        result = manager.get_user_group("unassigned_user")
        assert result is None
