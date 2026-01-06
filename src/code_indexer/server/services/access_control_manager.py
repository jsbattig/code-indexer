"""
Access Control Manager for CIDX Server.

Provides access control logic for repository operations with proper
user permission validation and role-based access control.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
from typing import Dict, Any, Optional

from ..auth.user_manager import User, UserRole


logger = logging.getLogger(__name__)


class AccessControlManager:
    """Manager for repository access control operations."""

    def __init__(
        self,
        golden_repo_manager,
        activated_repo_manager,
    ):
        """
        Initialize the access control manager.

        Args:
            golden_repo_manager: Manager for golden repositories
            activated_repo_manager: Manager for activated repositories
        """
        self.golden_repo_manager = golden_repo_manager
        self.activated_repo_manager = activated_repo_manager

    def get_user_access_level(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> Optional[str]:
        """
        Get the access level for a user on a specific repository.

        Args:
            repo_data: Repository data dictionary
            user: User to check access for

        Returns:
            Access level string ('read', 'write', 'admin') or None if no access
        """
        try:
            # Admin users have admin access to all repositories
            if user.role == UserRole.ADMIN:
                return "admin"

            # Check if this is a golden repository
            if self._is_golden_repository(repo_data):
                return self._get_golden_repo_access(repo_data, user)

            # Check if this is an activated repository
            elif self._is_activated_repository(repo_data):
                return self._get_activated_repo_access(repo_data, user)

            else:
                logger.warning(f"Unknown repository type for data: {repo_data}", extra={"correlation_id": get_correlation_id()})
                return None

        except Exception as e:
            logger.error(f"Error checking access for user {user.username}: {str(e)}", extra={"correlation_id": get_correlation_id()})
            return None

    def _is_golden_repository(self, repo_data: Dict[str, Any]) -> bool:
        """Check if repository data represents a golden repository."""
        # Golden repositories typically have 'repo_url' and 'default_branch'
        return "repo_url" in repo_data and "default_branch" in repo_data

    def _is_activated_repository(self, repo_data: Dict[str, Any]) -> bool:
        """Check if repository data represents an activated repository."""
        # Activated repositories typically have 'user_alias' and 'golden_repo_alias'
        return "user_alias" in repo_data and "golden_repo_alias" in repo_data

    def _get_golden_repo_access(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> Optional[str]:
        """
        Get access level for golden repository.

        Args:
            repo_data: Golden repository data
            user: User to check access for

        Returns:
            Access level or None
        """
        # Check if repository has explicit access control
        access_control = repo_data.get("access_control", [])

        if access_control:
            # If access control is defined, check if user is in the list
            if user.username in access_control:
                return "read"
            else:
                return None

        # If no explicit access control, check for public repositories
        is_public = repo_data.get("is_public", True)  # Default to public
        if is_public:
            return "read"

        # If repository is private and user not in access list, deny access
        return None

    def _get_activated_repo_access(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> Optional[str]:
        """
        Get access level for activated repository.

        Args:
            repo_data: Activated repository data
            user: User to check access for

        Returns:
            Access level or None
        """
        # Users can only access their own activated repositories
        repo_user = repo_data.get("user_alias")
        if repo_user == user.username:
            return "write"  # Users have write access to their own activated repos

        # No access to other users' activated repositories
        return None

    def user_can_read_repository(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> bool:
        """
        Check if user can read a repository.

        Args:
            repo_data: Repository data
            user: User to check

        Returns:
            True if user can read repository
        """
        access_level = self.get_user_access_level(repo_data, user)
        return access_level in ["read", "write", "admin"]

    def user_can_write_repository(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> bool:
        """
        Check if user can write to a repository.

        Args:
            repo_data: Repository data
            user: User to check

        Returns:
            True if user can write to repository
        """
        access_level = self.get_user_access_level(repo_data, user)
        return access_level in ["write", "admin"]

    def user_can_admin_repository(
        self,
        repo_data: Dict[str, Any],
        user: User,
    ) -> bool:
        """
        Check if user can administer a repository.

        Args:
            repo_data: Repository data
            user: User to check

        Returns:
            True if user can administer repository
        """
        access_level = self.get_user_access_level(repo_data, user)
        return access_level == "admin"
