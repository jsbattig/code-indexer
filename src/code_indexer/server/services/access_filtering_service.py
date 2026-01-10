"""
Access Filtering Service for CIDX Server.

Story #707: Query-Time Access Enforcement and Repo Visibility Filtering

Provides centralized access filtering for:
- Query results filtering by user group membership
- Repository listing filtering
- cidx-meta summary filtering

Key principles:
- Invisible repo pattern: No 403 errors, repos simply don't appear
- cidx-meta always accessible to everyone
- admins group has full access to all repos
- Group membership checked fresh each query (no caching)
"""

import logging
from typing import Any, List, Protocol, Set, runtime_checkable

from .constants import CIDX_META_REPO, DEFAULT_GROUP_ADMINS
from .group_access_manager import GroupAccessManager

logger = logging.getLogger(__name__)


@runtime_checkable
class QueryResultProtocol(Protocol):
    """Protocol for query result objects that can be filtered."""

    repository_alias: str


class AccessFilteringService:
    """
    Centralized service for access filtering at query time.

    Filters query results and repository listings based on user's group
    membership. Implements the invisible repo pattern - inaccessible
    repositories are simply not returned, with no indication they exist.
    """

    # Default over-fetch multiplier for compensating filtered results
    DEFAULT_OVER_FETCH_FACTOR = 2

    # Special group name that has full access to all repos
    ADMIN_GROUP_NAME = DEFAULT_GROUP_ADMINS

    def __init__(self, group_access_manager: GroupAccessManager):
        """
        Initialize the AccessFilteringService.

        Args:
            group_access_manager: Manager for group and access data
        """
        self.group_manager = group_access_manager

    def get_accessible_repos(self, user_id: str) -> Set[str]:
        """
        Get set of repos accessible by user's group.

        cidx-meta is always included. For admin users, all repos are
        accessible (returns special marker for full access).

        Args:
            user_id: The user's unique identifier

        Returns:
            Set of repository names the user can access
        """
        group = self.group_manager.get_user_group(user_id)

        if not group:
            # User not assigned to any group - cidx-meta only
            return {CIDX_META_REPO}

        # Admin group has full access to ALL repos from ALL groups
        if group.name == self.ADMIN_GROUP_NAME:
            # Collect repos from ALL groups in the system
            all_repos: Set[str] = set()
            for grp in self.group_manager.get_all_groups():
                group_repos = self.group_manager.get_group_repos(grp.id)
                all_repos.update(group_repos)
            all_repos.add(CIDX_META_REPO)
            return all_repos

        # Regular group - get explicitly assigned repos
        repos = set(self.group_manager.get_group_repos(group.id))
        repos.add(CIDX_META_REPO)  # Always include cidx-meta
        return repos

    def is_admin_user(self, user_id: str) -> bool:
        """
        Check if user belongs to the admin group.

        Args:
            user_id: The user's unique identifier

        Returns:
            True if user is in admins group
        """
        group = self.group_manager.get_user_group(user_id)
        return group is not None and group.name == self.ADMIN_GROUP_NAME

    def _get_repo_alias(self, result: Any) -> str:
        """
        Get repository_alias from a result, handling both objects and dicts.

        Args:
            result: A QueryResult object or dictionary

        Returns:
            The repository_alias value or empty string if not found
        """
        if isinstance(result, dict):
            return str(result.get("repository_alias", ""))
        return str(getattr(result, "repository_alias", ""))

    def filter_query_results(self, results: List[Any], user_id: str) -> List[Any]:
        """
        Filter query results by user's accessible repos.

        Implements AC1 and AC2: Users only see results from repos their
        group can access. Admins see all results.

        Args:
            results: List of QueryResult objects or dictionaries with
                    repository_alias attribute/key
            user_id: The user's unique identifier

        Returns:
            Filtered list containing only results from accessible repos
        """
        if not results:
            return []

        # Admin users see everything
        if self.is_admin_user(user_id):
            return results

        accessible = self.get_accessible_repos(user_id)

        return [r for r in results if self._get_repo_alias(r) in accessible]

    def filter_repo_listing(self, repos: List[str], user_id: str) -> List[str]:
        """
        Filter repository listing by user's accessible repos.

        Implements AC4: Repository listing only returns repos the user's
        group can access.

        Args:
            repos: List of repository names
            user_id: The user's unique identifier

        Returns:
            Filtered list containing only accessible repos
        """
        if not repos:
            return []

        # Admin users see everything
        if self.is_admin_user(user_id):
            return repos

        accessible = self.get_accessible_repos(user_id)
        return [r for r in repos if r in accessible]

    def filter_cidx_meta_results(self, results: List[Any], user_id: str) -> List[Any]:
        """
        Filter cidx-meta summaries that reference inaccessible repos.

        Implements AC3: When querying cidx-meta, summaries referencing
        inaccessible repos are filtered out.

        Args:
            results: List of QueryResult objects from cidx-meta
            user_id: The user's unique identifier

        Returns:
            Filtered list with inaccessible repo references removed
        """
        if not results:
            return []

        # Admin users see everything
        if self.is_admin_user(user_id):
            return results

        accessible = self.get_accessible_repos(user_id)
        filtered = []

        for result in results:
            # Check if result has metadata with referenced_repo
            metadata = getattr(result, "metadata", None)
            if metadata is None:
                # No metadata - pass through
                filtered.append(result)
                continue

            referenced_repo = metadata.get("referenced_repo")
            if referenced_repo is None:
                # No referenced_repo in metadata - pass through
                filtered.append(result)
                continue

            # Only include if referenced repo is accessible
            if referenced_repo in accessible:
                filtered.append(result)

        return filtered

    def calculate_over_fetch_limit(self, requested_limit: int) -> int:
        """
        Calculate over-fetch limit for HNSW queries.

        To compensate for post-query filtering reducing results,
        we over-fetch from HNSW by a factor.

        Args:
            requested_limit: Original requested result limit

        Returns:
            Adjusted limit for HNSW query
        """
        return requested_limit * self.DEFAULT_OVER_FETCH_FACTOR
