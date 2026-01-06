"""
Repository Discovery Service for CIDX Server.

Provides high-level business logic for discovering matching repositories
by git URL with proper authentication and access control.
"""

from code_indexer.server.middleware.correlation import get_correlation_id

import logging
from typing import List, Optional
from datetime import datetime, timezone

from ..auth.user_manager import User
from .git_url_normalizer import GitUrlNormalizer, GitUrlNormalizationError
from .repository_matcher import RepositoryMatcher, RepositoryMatchResult, MatchingError
from ..models.repository_discovery import (
    RepositoryDiscoveryResponse,
    RepositoryMatch,
)


logger = logging.getLogger(__name__)


class RepositoryDiscoveryError(Exception):
    """Exception raised when repository discovery operations fail."""

    pass


class RepositoryDiscoveryService:
    """Service for discovering matching repositories by git URL."""

    def __init__(
        self,
        golden_repo_manager,
        activated_repo_manager,
        git_url_normalizer: Optional[GitUrlNormalizer] = None,
        repository_matcher: Optional[RepositoryMatcher] = None,
    ):
        """
        Initialize the repository discovery service.

        Args:
            golden_repo_manager: Manager for golden repositories
            activated_repo_manager: Manager for activated repositories
            git_url_normalizer: URL normalizer (created if not provided)
            repository_matcher: Repository matcher (created if not provided)
        """
        self.golden_repo_manager = golden_repo_manager
        self.activated_repo_manager = activated_repo_manager

        # Initialize normalizer
        self.git_url_normalizer = git_url_normalizer or GitUrlNormalizer()

        # Initialize matcher (we'll need an access control manager)
        if repository_matcher:
            self.repository_matcher = repository_matcher
        else:
            # Create a simple access control manager for now
            from .access_control_manager import AccessControlManager

            access_control_manager = AccessControlManager(
                golden_repo_manager=golden_repo_manager,
                activated_repo_manager=activated_repo_manager,
            )
            self.repository_matcher = RepositoryMatcher(
                golden_repo_manager=golden_repo_manager,
                activated_repo_manager=activated_repo_manager,
                access_control_manager=access_control_manager,
            )

    async def discover_repositories(
        self,
        repo_url: str,
        user: User,
    ) -> RepositoryDiscoveryResponse:
        """
        Discover matching repositories for a given git URL.

        Args:
            repo_url: Git URL to search for
            user: User making the request

        Returns:
            RepositoryDiscoveryResponse with matching repositories

        Raises:
            RepositoryDiscoveryError: If discovery operation fails
        """
        try:
            logger.debug(
                f"Discovering repositories for URL: {repo_url}, User: {user.username}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Normalize the git URL
            try:
                normalized_url = self.git_url_normalizer.normalize(repo_url)
            except GitUrlNormalizationError as e:
                raise RepositoryDiscoveryError(f"Invalid git URL: {str(e)}") from e

            logger.debug(
                f"Normalized URL: {normalized_url.canonical_form}",
                extra={"correlation_id": get_correlation_id()},
            )

            # Find matching repositories
            try:
                (
                    golden_matches,
                    activated_matches,
                ) = await self.repository_matcher.find_all_matching_repositories(
                    canonical_url=normalized_url.canonical_form,
                    user=user,
                )
            except MatchingError as e:
                raise RepositoryDiscoveryError(
                    f"Failed to find matching repositories: {str(e)}"
                ) from e

            # Convert to response format
            golden_repositories = [
                self._convert_match_result_to_repository_match(match)
                for match in golden_matches
            ]

            activated_repositories = [
                self._convert_match_result_to_repository_match(match)
                for match in activated_matches
            ]

            total_matches = len(golden_repositories) + len(activated_repositories)

            logger.debug(
                f"Discovery complete: {len(golden_repositories)} golden, "
                f"{len(activated_repositories)} activated, {total_matches} total",
                extra={"correlation_id": get_correlation_id()},
            )

            return RepositoryDiscoveryResponse(
                query_url=repo_url,
                normalized_url=normalized_url.canonical_form,
                golden_repositories=golden_repositories,
                activated_repositories=activated_repositories,
                total_matches=total_matches,
            )

        except RepositoryDiscoveryError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error during repository discovery: {str(e)}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise RepositoryDiscoveryError(error_msg) from e

    def _convert_match_result_to_repository_match(
        self,
        match_result: RepositoryMatchResult,
    ) -> RepositoryMatch:
        """
        Convert RepositoryMatchResult to RepositoryMatch for API response.

        Args:
            match_result: Repository match result from matcher

        Returns:
            RepositoryMatch for API response
        """
        return RepositoryMatch(
            alias=match_result.alias,
            repository_type=match_result.repository_type.value,
            git_url=match_result.git_url,
            available_branches=match_result.available_branches,
            default_branch=match_result.default_branch,
            last_indexed=match_result.last_indexed,
            display_name=match_result.alias.replace("-", " ").title(),
            description=f"Repository {match_result.alias} ({match_result.repository_type.value})",
        )

    async def validate_repository_access(
        self,
        repo_url: str,
        user: User,
    ) -> bool:
        """
        Validate that a user has access to any repositories matching the given URL.

        Args:
            repo_url: Git URL to check
            user: User to validate access for

        Returns:
            True if user has access to any matching repositories

        Raises:
            RepositoryDiscoveryError: If validation fails
        """
        try:
            discovery_result = await self.discover_repositories(repo_url, user)
            return discovery_result.total_matches > 0
        except RepositoryDiscoveryError:
            raise
        except Exception as e:
            error_msg = f"Failed to validate repository access: {str(e)}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise RepositoryDiscoveryError(error_msg) from e

    async def get_repository_suggestions(
        self,
        repo_url: str,
        user: User,
        limit: int = 5,
    ) -> List[RepositoryMatch]:
        """
        Get repository suggestions based on partial URL or similar repositories.

        Args:
            repo_url: Partial or complete git URL
            user: User requesting suggestions
            limit: Maximum number of suggestions

        Returns:
            List of suggested repositories

        Raises:
            RepositoryDiscoveryError: If suggestion operation fails
        """
        try:
            # For now, implement as exact match discovery
            # In the future, this could include fuzzy matching, domain suggestions, etc.
            discovery_result = await self.discover_repositories(repo_url, user)

            all_suggestions = (
                discovery_result.golden_repositories
                + discovery_result.activated_repositories
            )

            # Sort by last_indexed (most recent first) and limit
            all_suggestions.sort(
                key=lambda x: x.last_indexed
                or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True,
            )

            return all_suggestions[:limit]

        except RepositoryDiscoveryError:
            raise
        except Exception as e:
            error_msg = f"Failed to get repository suggestions: {str(e)}"
            logger.error(error_msg, extra={"correlation_id": get_correlation_id()})
            raise RepositoryDiscoveryError(error_msg) from e
