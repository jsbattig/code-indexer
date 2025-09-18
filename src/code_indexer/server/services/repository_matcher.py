"""
Repository Matching Service for CIDX Server.

Provides logic for finding and matching golden and activated repositories
based on canonical git URLs with proper access control.
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum

from ..auth.user_manager import User


logger = logging.getLogger(__name__)


class RepositoryType(str, Enum):
    """Repository type enumeration."""

    GOLDEN = "golden"
    ACTIVATED = "activated"


class AccessLevel(str, Enum):
    """Access level enumeration."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class RepositoryMatchResult(BaseModel):
    """Result of a repository matching operation."""

    repository_id: str = Field(..., description="Unique repository identifier")
    repository_type: RepositoryType = Field(..., description="Type of repository")
    alias: str = Field(..., description="Repository alias")
    git_url: str = Field(..., description="Original git URL")
    canonical_url: str = Field(..., description="Canonical URL form")
    available_branches: List[str] = Field(..., description="Available branches")
    default_branch: str = Field(..., description="Default branch name")
    access_level: AccessLevel = Field(..., description="User's access level")
    last_indexed: Optional[datetime] = Field(
        None, description="Last indexing timestamp"
    )
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")

    @field_validator("repository_type")
    @classmethod
    def validate_repository_type(cls, v):
        """Validate repository type."""
        if isinstance(v, str):
            try:
                return RepositoryType(v)
            except ValueError:
                raise ValueError(f"Invalid repository type: {v}")
        return v

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v):
        """Validate access level."""
        if isinstance(v, str):
            try:
                return AccessLevel(v)
            except ValueError:
                raise ValueError(f"Invalid access level: {v}")
        return v


class MatchingError(Exception):
    """Exception raised when repository matching operations fail."""

    pass


class RepositoryMatcher:
    """Service for matching repositories based on canonical URLs."""

    def __init__(
        self,
        golden_repo_manager,
        activated_repo_manager,
        access_control_manager,
    ):
        """
        Initialize the repository matcher.

        Args:
            golden_repo_manager: Manager for golden repositories
            activated_repo_manager: Manager for activated repositories
            access_control_manager: Manager for access control
        """
        self.golden_repo_manager = golden_repo_manager
        self.activated_repo_manager = activated_repo_manager
        self.access_control_manager = access_control_manager

    async def find_matching_golden_repositories(
        self,
        canonical_url: str,
        user: User,
    ) -> List[RepositoryMatchResult]:
        """
        Find golden repositories matching the canonical URL.

        Args:
            canonical_url: Canonical form of git URL
            user: User requesting the repositories

        Returns:
            List of matching golden repositories with access control applied

        Raises:
            MatchingError: If matching operation fails
        """
        try:
            logger.debug(f"Finding golden repositories for URL: {canonical_url}")

            # Find repositories by canonical URL
            golden_repos = self.golden_repo_manager.find_by_canonical_url(canonical_url)

            if not golden_repos:
                logger.debug(f"No golden repositories found for URL: {canonical_url}")
                return []

            results = []
            for repo_data in golden_repos:
                # Check user access
                access_level = self.access_control_manager.get_user_access_level(
                    repo_data, user
                )

                if access_level is None:
                    logger.debug(
                        f"User {user.username} has no access to golden repository {repo_data.get('alias')}"
                    )
                    continue

                # Convert to match result
                match_result = self._convert_golden_repo_to_match_result(
                    repo_data, access_level
                )
                results.append(match_result)

            logger.debug(f"Found {len(results)} accessible golden repositories")
            return results

        except Exception as e:
            error_msg = f"Failed to find matching golden repositories: {str(e)}"
            logger.error(error_msg)
            raise MatchingError(error_msg) from e

    async def find_matching_activated_repositories(
        self,
        canonical_url: str,
        user: User,
    ) -> List[RepositoryMatchResult]:
        """
        Find activated repositories matching the canonical URL.

        Args:
            canonical_url: Canonical form of git URL
            user: User requesting the repositories

        Returns:
            List of matching activated repositories with access control applied

        Raises:
            MatchingError: If matching operation fails
        """
        try:
            logger.debug(f"Finding activated repositories for URL: {canonical_url}")

            # Find repositories by canonical URL
            activated_repos = self.activated_repo_manager.find_by_canonical_url(
                canonical_url
            )

            if not activated_repos:
                logger.debug(
                    f"No activated repositories found for URL: {canonical_url}"
                )
                return []

            results = []
            for repo_data in activated_repos:
                # Check user access (typically users can only access their own activated repos)
                access_level = self.access_control_manager.get_user_access_level(
                    repo_data, user
                )

                if access_level is None:
                    logger.debug(
                        f"User {user.username} has no access to activated repository {repo_data.get('id')}"
                    )
                    continue

                # Convert to match result
                match_result = self._convert_activated_repo_to_match_result(
                    repo_data, access_level
                )
                results.append(match_result)

            logger.debug(f"Found {len(results)} accessible activated repositories")
            return results

        except Exception as e:
            error_msg = f"Failed to find matching activated repositories: {str(e)}"
            logger.error(error_msg)
            raise MatchingError(error_msg) from e

    async def find_all_matching_repositories(
        self,
        canonical_url: str,
        user: User,
    ) -> Tuple[List[RepositoryMatchResult], List[RepositoryMatchResult]]:
        """
        Find all matching repositories (both golden and activated).

        Args:
            canonical_url: Canonical form of git URL
            user: User requesting the repositories

        Returns:
            Tuple of (golden_repositories, activated_repositories)

        Raises:
            MatchingError: If matching operation fails
        """
        try:
            # Find both types concurrently
            golden_repos = await self.find_matching_golden_repositories(
                canonical_url, user
            )
            activated_repos = await self.find_matching_activated_repositories(
                canonical_url, user
            )

            return golden_repos, activated_repos

        except MatchingError:
            raise
        except Exception as e:
            error_msg = f"Failed to find all matching repositories: {str(e)}"
            logger.error(error_msg)
            raise MatchingError(error_msg) from e

    def _convert_golden_repo_to_match_result(
        self,
        repo_data: Dict[str, Any],
        access_level: str,
    ) -> RepositoryMatchResult:
        """
        Convert golden repository data to match result.

        Args:
            repo_data: Raw repository data from manager
            access_level: User's access level

        Returns:
            RepositoryMatchResult object
        """
        # Parse timestamps if they exist
        last_indexed = None
        if repo_data.get("last_indexed"):
            if isinstance(repo_data["last_indexed"], datetime):
                last_indexed = repo_data["last_indexed"]
            elif isinstance(repo_data["last_indexed"], str):
                try:
                    last_indexed = datetime.fromisoformat(
                        repo_data["last_indexed"].replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid last_indexed timestamp: {repo_data['last_indexed']}"
                    )

        created_at = None
        if repo_data.get("created_at"):
            if isinstance(repo_data["created_at"], datetime):
                created_at = repo_data["created_at"]
            elif isinstance(repo_data["created_at"], str):
                try:
                    created_at = datetime.fromisoformat(
                        repo_data["created_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid created_at timestamp: {repo_data['created_at']}"
                    )

        return RepositoryMatchResult(
            repository_id=repo_data.get("id", repo_data.get("alias", "unknown")),
            repository_type=RepositoryType.GOLDEN,
            alias=repo_data.get("alias", "unknown"),
            git_url=repo_data.get("repo_url", ""),
            canonical_url=repo_data.get("canonical_url", ""),
            available_branches=repo_data.get(
                "branches", [repo_data.get("default_branch", "main")]
            ),
            default_branch=repo_data.get("default_branch", "main"),
            access_level=AccessLevel(access_level),
            last_indexed=last_indexed,
            created_at=created_at,
        )

    def _convert_activated_repo_to_match_result(
        self,
        repo_data: Dict[str, Any],
        access_level: str,
    ) -> RepositoryMatchResult:
        """
        Convert activated repository data to match result.

        Args:
            repo_data: Raw repository data from manager
            access_level: User's access level

        Returns:
            RepositoryMatchResult object
        """
        # Parse timestamps if they exist
        last_accessed = None
        if repo_data.get("last_accessed"):
            if isinstance(repo_data["last_accessed"], datetime):
                last_accessed = repo_data["last_accessed"]
            elif isinstance(repo_data["last_accessed"], str):
                try:
                    last_accessed = datetime.fromisoformat(
                        repo_data["last_accessed"].replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid last_accessed timestamp: {repo_data['last_accessed']}"
                    )

        activated_at = None
        if repo_data.get("activated_at"):
            if isinstance(repo_data["activated_at"], datetime):
                activated_at = repo_data["activated_at"]
            elif isinstance(repo_data["activated_at"], str):
                try:
                    activated_at = datetime.fromisoformat(
                        repo_data["activated_at"].replace("Z", "+00:00")
                    )
                except ValueError:
                    logger.warning(
                        f"Invalid activated_at timestamp: {repo_data['activated_at']}"
                    )

        # Create composite alias for activated repositories
        user_alias = repo_data.get("user_alias", "unknown")
        golden_alias = repo_data.get("golden_repo_alias", "unknown")
        composite_alias = f"{user_alias}/{golden_alias}"

        return RepositoryMatchResult(
            repository_id=repo_data.get("id", composite_alias),
            repository_type=RepositoryType.ACTIVATED,
            alias=composite_alias,
            git_url=repo_data.get("git_url", repo_data.get("repo_url", "")),
            canonical_url=repo_data.get("canonical_url", ""),
            available_branches=repo_data.get(
                "branches", [repo_data.get("current_branch", "main")]
            ),
            default_branch=repo_data.get("current_branch", "main"),
            access_level=AccessLevel(access_level),
            last_accessed=last_accessed,
            created_at=activated_at,
        )
