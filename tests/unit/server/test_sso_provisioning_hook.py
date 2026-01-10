"""
Unit tests for SSO Auto-Provisioning Hook.

Story #708: SSO Auto-Provisioning with Default Group Assignment

Tests for the SSOProvisioningHook service:
- AC1: New SSO users assigned to "users" group with "system:sso-provisioning"
- AC3: Existing users' group membership unchanged on re-login
- AC4: User ID extracted from SSO token (sub claim or configured claim)
- AC6: Provisioning handles errors gracefully (auth succeeds, fallback to cidx-meta)

TDD: These tests are written FIRST, before implementation.
"""

import pytest
import tempfile
from pathlib import Path


from code_indexer.server.services.group_access_manager import (
    GroupAccessManager,
)
from code_indexer.server.services.sso_provisioning_hook import (
    SSOProvisioningHook,
    SystemConfigurationError,
    ensure_user_group_membership,
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
def group_manager(temp_db_path):
    """Create a GroupAccessManager with temp database."""
    return GroupAccessManager(temp_db_path)


class TestAC1_NewSSOUsersAssignedToUsersGroup:
    """Tests for AC1: New SSO users are assigned to the users group."""

    def test_new_user_assigned_to_users_group(self, group_manager):
        """Test that a new SSO user is automatically assigned to the users group."""
        # Given: A new user ID that has no existing group membership
        user_id = "new-sso-user"
        assert group_manager.get_user_group(user_id) is None

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user is assigned to the "users" group
        user_group = group_manager.get_user_group(user_id)
        assert user_group is not None
        assert user_group.name == "users"

    def test_new_user_assigned_by_system_sso_provisioning(self, group_manager):
        """Test that assigned_by is set to 'system:sso-provisioning'."""
        # Given: A new user ID
        user_id = "new-sso-user-2"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The membership record has assigned_by = "system:sso-provisioning"
        membership = group_manager.get_user_membership(user_id)
        assert membership is not None
        assert membership.assigned_by == "system:sso-provisioning"

    def test_user_group_membership_record_created(self, group_manager):
        """Test that a user_group_membership record is created."""
        # Given: A new user ID
        user_id = "new-sso-user-3"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: A membership record exists
        membership = group_manager.get_user_membership(user_id)
        assert membership is not None
        assert membership.user_id == user_id
        assert membership.group_id is not None

    def test_function_wrapper_ensure_user_group_membership(self, group_manager):
        """Test the standalone function wrapper for provisioning."""
        # Given: A new user ID
        user_id = "function-test-user"

        # When: The standalone function is called
        ensure_user_group_membership(user_id, group_manager)

        # Then: The user is assigned to the users group
        user_group = group_manager.get_user_group(user_id)
        assert user_group is not None
        assert user_group.name == "users"


class TestAC3_ExistingUsersUnchangedOnLogin:
    """Tests for AC3: Existing users' group membership is not changed on re-login."""

    def test_existing_user_membership_not_changed(self, group_manager):
        """Test that an existing user's group membership is not changed."""
        # Given: A user already assigned to the admins group
        user_id = "existing-admin-user"
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group(user_id, admins.id, "manual-assignment")

        # When: The provisioning hook is called (simulating re-login)
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user is still in the admins group
        user_group = group_manager.get_user_group(user_id)
        assert user_group.name == "admins"

    def test_existing_user_assigned_by_not_overwritten(self, group_manager):
        """Test that existing user's assigned_by is not overwritten."""
        # Given: A user assigned by a manual admin action
        user_id = "manual-assigned-user"
        powerusers = group_manager.get_group_by_name("powerusers")
        group_manager.assign_user_to_group(user_id, powerusers.id, "admin-john")

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The assigned_by is still "admin-john", not overwritten
        membership = group_manager.get_user_membership(user_id)
        assert membership.assigned_by == "admin-john"

    def test_no_new_membership_record_for_existing_user(self, group_manager):
        """Test that no new membership record is created for existing users."""
        # Given: A user already in the users group
        user_id = "existing-user"
        users = group_manager.get_group_by_name("users")
        group_manager.assign_user_to_group(user_id, users.id, "initial-setup")
        original_membership = group_manager.get_user_membership(user_id)
        original_assigned_at = original_membership.assigned_at

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The assigned_at timestamp is unchanged (no new record)
        membership = group_manager.get_user_membership(user_id)
        assert membership.assigned_at == original_assigned_at

    def test_multiple_logins_dont_change_membership(self, group_manager):
        """Test that multiple logins don't change membership."""
        # Given: A new user who goes through initial provisioning
        user_id = "multi-login-user"
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then an admin upgrades them to powerusers
        powerusers = group_manager.get_group_by_name("powerusers")
        group_manager.assign_user_to_group(user_id, powerusers.id, "admin-upgrade")

        # When: The user logs in again multiple times
        hook.ensure_group_membership(user_id)
        hook.ensure_group_membership(user_id)
        hook.ensure_group_membership(user_id)

        # Then: The user is still in powerusers (not reset to users)
        user_group = group_manager.get_user_group(user_id)
        assert user_group.name == "powerusers"


class TestAC4_UserIDExtractedFromSSOToken:
    """Tests for AC4: User ID is extracted from SSO token correctly."""

    def test_user_id_used_as_primary_key(self, group_manager):
        """Test that user_id is used as the primary key for membership."""
        # Given: A user ID from SSO token
        user_id = "sso-sub-claim-12345"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user_id is the primary key in membership
        membership = group_manager.get_user_membership(user_id)
        assert membership.user_id == user_id

    def test_different_user_ids_create_different_memberships(self, group_manager):
        """Test that different user IDs create separate memberships."""
        # Given: Multiple different user IDs
        user_ids = ["user-a", "user-b", "user-c"]

        # When: The provisioning hook is called for each
        hook = SSOProvisioningHook(group_manager)
        for uid in user_ids:
            hook.ensure_group_membership(uid)

        # Then: Each user has their own membership record
        for uid in user_ids:
            membership = group_manager.get_user_membership(uid)
            assert membership is not None
            assert membership.user_id == uid

    def test_user_id_with_special_characters(self, group_manager):
        """Test that user IDs with special characters are handled."""
        # Given: A user ID with email format (common in SSO)
        user_id = "user@example.com"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user is assigned correctly
        user_group = group_manager.get_user_group(user_id)
        assert user_group is not None
        assert user_group.name == "users"

    def test_user_id_with_uuid_format(self, group_manager):
        """Test that UUID-formatted user IDs work correctly."""
        # Given: A UUID-formatted user ID (common OIDC sub claim)
        user_id = "550e8400-e29b-41d4-a716-446655440000"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user is assigned correctly
        user_group = group_manager.get_user_group(user_id)
        assert user_group is not None
        assert user_group.name == "users"


class TestAC6_ProvisioningHandlesErrorsGracefully:
    """Tests for AC6: Provisioning handles errors gracefully."""

    def test_error_during_assignment_does_not_raise(self, temp_db_path):
        """Test that database errors don't raise exceptions."""
        # Given: A group manager with a simulated database error
        group_manager = GroupAccessManager(temp_db_path)
        hook = SSOProvisioningHook(group_manager)

        # Simulate database error by closing connection after lookup
        original_assign = group_manager.assign_user_to_group

        def failing_assign(*args, **kwargs):
            raise Exception("Database connection error")

        group_manager.assign_user_to_group = failing_assign

        # When: The provisioning hook is called
        # Then: No exception is raised (error is handled gracefully)
        result = hook.ensure_group_membership("error-test-user")

        # Restore original
        group_manager.assign_user_to_group = original_assign

        # Result indicates failure
        assert result is False

    def test_error_is_logged(self, temp_db_path, caplog):
        """Test that errors are logged for administrator review."""
        import logging

        # Given: A group manager with a simulated error
        group_manager = GroupAccessManager(temp_db_path)
        hook = SSOProvisioningHook(group_manager)

        original_assign = group_manager.assign_user_to_group

        def failing_assign(*args, **kwargs):
            raise Exception("Simulated database error")

        group_manager.assign_user_to_group = failing_assign

        # When: The provisioning hook is called with logging capture
        with caplog.at_level(logging.ERROR):
            hook.ensure_group_membership("log-test-user")

        # Restore original
        group_manager.assign_user_to_group = original_assign

        # Then: An error was logged
        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_logs) > 0
        assert (
            "log-test-user" in error_logs[0].message.lower()
            or "provisioning" in error_logs[0].message.lower()
        )

    def test_success_returns_true(self, group_manager):
        """Test that successful provisioning returns True."""
        # Given: A new user
        user_id = "success-test-user"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        result = hook.ensure_group_membership(user_id)

        # Then: Result is True
        assert result is True

    def test_existing_user_returns_true(self, group_manager):
        """Test that existing user check returns True (no provisioning needed)."""
        # Given: An existing user
        user_id = "existing-success-user"
        users = group_manager.get_group_by_name("users")
        group_manager.assign_user_to_group(user_id, users.id, "initial")

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        result = hook.ensure_group_membership(user_id)

        # Then: Result is True (user already has membership)
        assert result is True

    def test_users_group_missing_raises_system_configuration_error(self, temp_db_path):
        """Test that missing users group raises SystemConfigurationError.

        This is a PRECONDITION VIOLATION (database not properly initialized),
        not a runtime error. Per Anti-Fallback principle, we fail loudly
        rather than silently degrading to cidx-meta-only access.
        """
        # Given: A group manager where users group doesn't exist
        group_manager = GroupAccessManager(temp_db_path)
        hook = SSOProvisioningHook(group_manager)

        # Simulate users group not found (database misconfiguration)
        original_get = group_manager.get_group_by_name

        def no_users_group(name):
            if name == "users":
                return None
            return original_get(name)

        group_manager.get_group_by_name = no_users_group

        # When/Then: The provisioning hook raises SystemConfigurationError
        with pytest.raises(SystemConfigurationError) as exc_info:
            hook.ensure_group_membership("no-group-user")

        # Restore original
        group_manager.get_group_by_name = original_get

        # Verify error message is informative
        assert "users" in str(exc_info.value).lower()
        assert (
            "not found" in str(exc_info.value).lower()
            or "not properly initialized" in str(exc_info.value).lower()
        )

    def test_users_group_missing_error_includes_remediation_hint(self, temp_db_path):
        """Test that SystemConfigurationError includes a hint for how to fix it."""
        # Given: A group manager where users group doesn't exist
        group_manager = GroupAccessManager(temp_db_path)
        hook = SSOProvisioningHook(group_manager)

        # Simulate users group not found
        original_get = group_manager.get_group_by_name

        def no_users_group(name):
            if name == "users":
                return None
            return original_get(name)

        group_manager.get_group_by_name = no_users_group

        # When/Then: The error message includes remediation hint
        with pytest.raises(SystemConfigurationError) as exc_info:
            hook.ensure_group_membership("no-group-user")

        # Restore original
        group_manager.get_group_by_name = original_get

        # Error should mention database initialization
        error_msg = str(exc_info.value).lower()
        assert (
            "database" in error_msg
            or "initialization" in error_msg
            or "default groups" in error_msg
        )


class TestSSOProvisioningHookIntegration:
    """Integration tests for SSOProvisioningHook with GroupAccessManager."""

    def test_complete_new_user_provisioning_flow(self, group_manager):
        """Test the complete flow for provisioning a new user."""
        # Given: A new SSO user with no existing membership
        user_id = "complete-flow-user"
        assert group_manager.get_user_group(user_id) is None

        # When: Provisioning is triggered
        hook = SSOProvisioningHook(group_manager)
        result = hook.ensure_group_membership(user_id)

        # Then: User is in users group with correct metadata
        assert result is True
        user_group = group_manager.get_user_group(user_id)
        assert user_group.name == "users"

        membership = group_manager.get_user_membership(user_id)
        assert membership.assigned_by == "system:sso-provisioning"

    def test_hook_respects_group_access_after_provisioning(self, group_manager):
        """Test that provisioned user respects group-based access."""
        # Given: A provisioned user in the users group
        user_id = "access-test-user"
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The user's accessible repos should be cidx-meta only
        # (This is enforced by AccessFilteringService, but we verify group)
        user_group = group_manager.get_user_group(user_id)
        assert user_group.name == "users"

        # The users group should have cidx-meta access (implicit)
        users_repos = group_manager.get_group_repos(user_group.id)
        assert "cidx-meta" in users_repos


class TestAC7_AuditLoggingForSSOProvisioning:
    """Tests for AC7: Audit logging for SSO auto-provisioning actions.

    Story #710 AC7: Audit log for administrative actions.
    SSO auto-provisioning should record audit logs when new users are assigned.
    """

    def test_audit_log_created_for_new_user_provisioning(self, group_manager):
        """Test that an audit log entry is created when provisioning a new SSO user."""
        # Given: A new SSO user with no existing membership
        user_id = "audit-test-new-user"
        assert group_manager.get_user_group(user_id) is None

        # When: The provisioning hook assigns the user to users group
        hook = SSOProvisioningHook(group_manager)
        result = hook.ensure_group_membership(user_id)

        # Then: Result is successful
        assert result is True

        # And: An audit log entry was created
        logs, total = group_manager.get_audit_logs(
            action_type="user_assign",
            target_type="user",
            admin_id="system:sso-provisioning",
        )
        assert total >= 1

        # Find the log entry for this specific user
        user_log = None
        for log in logs:
            if log["target_id"] == user_id:
                user_log = log
                break

        assert user_log is not None, f"No audit log found for user '{user_id}'"
        assert user_log["admin_id"] == "system:sso-provisioning"
        assert user_log["action_type"] == "user_assign"
        assert user_log["target_type"] == "user"
        assert user_log["target_id"] == user_id
        assert "users" in user_log["details"].lower()  # Details mention 'users' group

    def test_no_audit_log_for_existing_user_relogin(self, group_manager):
        """Test that no new audit log is created when existing user logs in again."""
        # Given: A user already assigned to admins group (by admin)
        user_id = "audit-test-existing-user"
        admins = group_manager.get_group_by_name("admins")
        group_manager.assign_user_to_group(user_id, admins.id, "admin-assignment")

        # Capture audit log count before hook
        logs_before, count_before = group_manager.get_audit_logs(
            target_type="user",
            admin_id="system:sso-provisioning",
        )

        # When: The provisioning hook is called (simulating re-login)
        hook = SSOProvisioningHook(group_manager)
        result = hook.ensure_group_membership(user_id)

        # Then: Result is successful (user has membership)
        assert result is True

        # And: No new audit log was created by SSO provisioning
        logs_after, count_after = group_manager.get_audit_logs(
            target_type="user",
            admin_id="system:sso-provisioning",
        )

        # Count should be the same - no new SSO provisioning logs
        assert count_after == count_before

    def test_audit_log_details_include_group_name(self, group_manager):
        """Test that audit log details include the target group name."""
        # Given: A new SSO user
        user_id = "audit-details-test-user"

        # When: The provisioning hook is called
        hook = SSOProvisioningHook(group_manager)
        hook.ensure_group_membership(user_id)

        # Then: The audit log details mention the group name
        logs, _ = group_manager.get_audit_logs(
            action_type="user_assign",
            admin_id="system:sso-provisioning",
        )

        user_log = next((log for log in logs if log["target_id"] == user_id), None)
        assert user_log is not None
        # Details should mention "users" group
        assert "users" in user_log["details"].lower()
        assert (
            "auto-provisioned" in user_log["details"].lower()
            or "sso" in user_log["details"].lower()
        )
