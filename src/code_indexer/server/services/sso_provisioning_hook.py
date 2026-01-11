"""
SSO Auto-Provisioning Hook for CIDX Server.

Story #708: SSO Auto-Provisioning with Default Group Assignment

Provides automatic provisioning of new SSO users to the default "users" group.
This ensures new users can immediately query cidx-meta without manual intervention.

Key behaviors:
- New SSO users are auto-assigned to "users" group
- Existing users' group membership is NOT changed on re-login
- assigned_by is set to "system:sso-provisioning" for auto-provisioned users
- Errors are logged but do not block authentication
"""

import logging
from typing import TYPE_CHECKING

from .constants import DEFAULT_GROUP_USERS

if TYPE_CHECKING:
    from .group_access_manager import GroupAccessManager

logger = logging.getLogger(__name__)

# Constant for assigned_by value used in SSO auto-provisioning
SSO_PROVISIONING_ASSIGNED_BY = "system:sso-provisioning"


class SystemConfigurationError(Exception):
    """Raised when system invariants are violated.

    This exception indicates a PRECONDITION VIOLATION, not a runtime error.
    Examples: missing default groups, database not properly initialized.

    Per Anti-Fallback principle, we fail loudly rather than silently
    degrading service quality.
    """

    pass


class SSOProvisioningHook:
    """
    Hook for auto-provisioning SSO users to the default group.

    This hook is called during SSO authentication to ensure new users
    have a group membership. Existing users are not modified.
    """

    def __init__(self, group_manager: "GroupAccessManager"):
        """
        Initialize the SSO provisioning hook.

        Args:
            group_manager: The GroupAccessManager instance for group operations
        """
        self.group_manager = group_manager

    def ensure_group_membership(self, user_id: str) -> bool:
        """
        Ensure the user has a group membership, defaulting to users group.

        AC1: New users are assigned to "users" group with "system:sso-provisioning"
        AC3: Existing users' membership is NOT changed
        AC6: Errors are logged but do not block authentication

        Args:
            user_id: The user's unique identifier (from SSO token sub claim)

        Returns:
            True if user has membership (existing or newly created),
            False if provisioning failed
        """
        try:
            # Check if user already has a group membership
            existing_group = self.group_manager.get_user_group(user_id)

            if existing_group is not None:
                # AC3: User already has membership - do not modify
                logger.debug(
                    f"SSO user '{user_id}' already has group membership: {existing_group.name}"
                )
                return True

            # New user - assign to "users" group
            users_group = self.group_manager.get_group_by_name(DEFAULT_GROUP_USERS)

            if users_group is None:
                # PRECONDITION VIOLATION: Database not properly initialized
                # Per Anti-Fallback principle, fail loudly instead of silent degradation
                raise SystemConfigurationError(
                    f"SSO provisioning failed: '{DEFAULT_GROUP_USERS}' group not found. "
                    "Database may not be properly initialized. "
                    "Run database initialization to create default groups."
                )

            # AC1: Assign new user to users group
            self.group_manager.assign_user_to_group(
                user_id=user_id,
                group_id=users_group.id,
                assigned_by=SSO_PROVISIONING_ASSIGNED_BY,
            )

            # AC7 (Story #710): Log to audit trail for administrative actions
            self.group_manager.log_audit(
                admin_id=SSO_PROVISIONING_ASSIGNED_BY,
                action_type="user_assign",
                target_type="user",
                target_id=user_id,
                details=f"SSO auto-provisioned to '{DEFAULT_GROUP_USERS}' group",
            )

            logger.info(
                f"SSO auto-provisioned user '{user_id}' to '{DEFAULT_GROUP_USERS}' group"
            )
            return True

        except SystemConfigurationError:
            # PRECONDITION VIOLATION - re-raise to fail loudly
            # This is NOT a runtime error, it's a database misconfiguration
            raise
        except Exception as e:
            # AC6: Log RUNTIME errors but do not block authentication
            logger.error(
                f"SSO provisioning failed for user '{user_id}': {e}. "
                f"User will have fallback cidx-meta-only access."
            )
            return False


def ensure_user_group_membership(
    user_id: str, group_manager: "GroupAccessManager"
) -> bool:
    """
    Standalone function wrapper for SSO provisioning.

    Convenience function that can be called directly without
    instantiating SSOProvisioningHook.

    Args:
        user_id: The user's unique identifier (from SSO token sub claim)
        group_manager: The GroupAccessManager instance

    Returns:
        True if user has membership (existing or newly created),
        False if provisioning failed
    """
    hook = SSOProvisioningHook(group_manager)
    return hook.ensure_group_membership(user_id)
