"""
Group Access Lifecycle Hooks for CIDX Server.

Provides hooks for integrating group access management with other components:
- on_repo_added: Called when a golden repository is registered
- on_repo_removed: Called when a golden repository is removed

Story #706: Repository-to-Group Access Mapping with Auto-Assignment
"""

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .group_access_manager import GroupAccessManager

logger = logging.getLogger(__name__)


def on_repo_added(repo_name: str, group_manager: "GroupAccessManager") -> None:
    """
    Lifecycle hook called when a golden repository is registered.

    Auto-assigns the repository to admins and powerusers groups.
    AC3: New golden repos are automatically assigned to admins and powerusers.

    Args:
        repo_name: The repository name/alias that was added
        group_manager: The GroupAccessManager instance
    """
    try:
        group_manager.auto_assign_golden_repo(repo_name)
        logger.info(
            f"Auto-assigned golden repo '{repo_name}' to admins and powerusers groups"
        )
    except Exception as e:
        # Log error but don't fail the golden repo registration
        logger.error(
            f"Failed to auto-assign golden repo '{repo_name}' to groups: {e}. "
            f"Repository is registered but may not be accessible to all expected groups."
        )


def on_repo_removed(repo_name: str, group_manager: "GroupAccessManager") -> None:
    """
    Lifecycle hook called when a golden repository is removed.

    Revokes the repository access from all groups.

    Args:
        repo_name: The repository name/alias that was removed
        group_manager: The GroupAccessManager instance
    """
    try:
        # Get all groups that have access to this repo
        groups = group_manager.get_repo_groups(repo_name)

        for group in groups:
            try:
                group_manager.revoke_repo_access(repo_name, group.id)
                logger.debug(
                    f"Revoked access to '{repo_name}' from group '{group.name}'"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to revoke access to '{repo_name}' from group '{group.name}': {e}"
                )

        logger.info(f"Revoked golden repo '{repo_name}' access from all groups")

    except Exception as e:
        # Log error but don't fail the golden repo removal
        logger.error(
            f"Failed to revoke golden repo '{repo_name}' access from groups: {e}. "
            f"Repository is removed but access records may remain."
        )
