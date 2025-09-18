"""Exact Branch Matching for CIDX Remote Repository Linking Mode.

Implements intelligent repository linking based on exact local branch matching,
prioritizing activated repositories over golden repositories and providing
clear user feedback and repository link storage.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from enum import Enum

from ..services.git_topology_service import GitTopologyService
from ..api_clients.repository_linking_client import (
    RepositoryLinkingClient,
    RepositoryDiscoveryResponse as ClientDiscoveryResponse,
    RepositoryNotFoundError,
    ActivatedRepository,
    ActivationError,
)
from ..api_clients.base_client import NetworkError

logger = logging.getLogger(__name__)


class RepositoryType(Enum):
    """Type of repository match."""

    ACTIVATED = "activated"
    GOLDEN = "golden"


class MatchQuality(Enum):
    """Quality of branch match."""

    EXACT = "exact"
    FALLBACK = "fallback"
    NONE = "none"


class RepositoryLinkingError(Exception):
    """Exception raised when repository linking operations fail."""

    pass


class BranchMatchingError(RepositoryLinkingError):
    """Exception raised when branch matching fails."""

    pass


class NoMatchFoundError(BranchMatchingError):
    """Exception raised when no matching repositories are found."""

    pass


class UserCancelledActivationError(RepositoryLinkingError):
    """Exception raised when user cancels repository activation."""

    pass


class RepositoryActivationError(RepositoryLinkingError):
    """Exception raised when repository activation fails."""

    pass


@dataclass
class RepositoryMatch:
    """Information about a matching repository with branch and priority details."""

    alias: str
    repository_type: RepositoryType
    branch: str
    match_quality: MatchQuality
    priority: int
    git_url: str
    display_name: str
    description: str
    available_branches: List[str]
    last_updated: str
    access_level: str


@dataclass
class RepositoryLink:
    """Repository link information for local storage."""

    alias: str
    git_url: str
    branch: str
    repository_type: RepositoryType
    server_url: str
    linked_at: str
    display_name: str
    description: str
    access_level: str
    match_reason: Optional[str] = None
    parent_branch: Optional[str] = None


@dataclass
class RepositoryDiscoveryResponse:
    """Response from repository discovery with exact branch matching applied."""

    activated_repositories: List[RepositoryMatch]
    golden_repositories: List[RepositoryMatch]
    exact_matches: List[RepositoryMatch]
    total_discovered: int
    local_branch: Optional[str]
    match_strategy: str


class ExactBranchMatcher:
    """Handles exact branch matching for CIDX remote repository linking."""

    def __init__(self, repository_client: RepositoryLinkingClient):
        """Initialize exact branch matcher.

        Args:
            repository_client: API client for repository operations
        """
        self.repository_client = repository_client
        self.git_service: Optional[GitTopologyService] = None
        self.fallback_matcher: Optional[BranchFallbackMatcher] = None
        self.auto_activator: Optional[AutoRepositoryActivator] = None

    async def find_exact_branch_match(
        self, local_repo_path: Path, repo_url: str
    ) -> Optional[RepositoryLink]:
        """Find repository with exact branch match for local repository.

        Args:
            local_repo_path: Path to local git repository
            repo_url: Git repository URL to discover

        Returns:
            RepositoryLink if exact match found, None otherwise

        Raises:
            RepositoryLinkingError: If discovery or matching fails
            BranchMatchingError: If branch matching logic fails
        """
        try:
            # Initialize git service for local branch detection
            if self.git_service is None:
                self.git_service = GitTopologyService(local_repo_path)

            # Detect current local branch
            local_branch = self._detect_local_branch()
            if not local_branch:
                raise BranchMatchingError(
                    "Unable to detect local branch. Repository may not be a git repository or in detached HEAD state."
                )

            logger.info(f"Local branch detected: {local_branch}")

            # Discover remote repositories
            try:
                discovery_response = await self.repository_client.discover_repositories(
                    repo_url
                )
            except RepositoryNotFoundError as e:
                logger.warning(f"No repositories found for URL {repo_url}: {e}")
                return None
            except NetworkError as e:
                raise RepositoryLinkingError(
                    f"Network error during repository discovery: {e}"
                )

            # Filter for exact branch matches
            exact_matches = self._filter_exact_matches(discovery_response, local_branch)
            if not exact_matches:
                logger.info(
                    f"No repositories found with exact branch match for '{local_branch}'"
                )

                # Try fallback matching if exact matching fails
                fallback_result = await self._try_fallback_matching(
                    local_repo_path, discovery_response
                )
                if fallback_result:
                    # Set server URL and linked timestamp for fallback result
                    fallback_result.server_url = self.repository_client.server_url
                    fallback_result.linked_at = datetime.utcnow().isoformat() + "Z"
                    return fallback_result

                return None

            # Check for auto-activation scenario: only golden repositories match
            activated_matches = [
                m
                for m in exact_matches
                if m.repository_type == RepositoryType.ACTIVATED
            ]
            golden_matches = [
                m for m in exact_matches if m.repository_type == RepositoryType.GOLDEN
            ]

            if not activated_matches and golden_matches:
                # Only golden repositories match - trigger auto-activation
                logger.info(
                    f"Only golden repositories found for branch '{local_branch}' - attempting auto-activation"
                )

                best_golden = golden_matches[0]  # First golden repo (highest priority)
                auto_activated_link = await self._try_auto_activation(
                    best_golden, local_repo_path
                )

                if auto_activated_link:
                    return auto_activated_link
                # If auto-activation fails or is cancelled, continue with regular linking

            # Select best match based on priority
            best_match = self._select_best_match(exact_matches)
            if not best_match:
                raise BranchMatchingError(
                    "Failed to select best match from exact matches"
                )

            # Create repository link
            repository_link = RepositoryLink(
                alias=best_match.alias,
                git_url=best_match.git_url,
                branch=best_match.branch,
                repository_type=best_match.repository_type,
                server_url=self.repository_client.server_url,
                linked_at=datetime.utcnow().isoformat() + "Z",
                display_name=best_match.display_name,
                description=best_match.description,
                access_level=best_match.access_level,
            )

            logger.info(
                f"Found exact branch match: {best_match.repository_type.value} repository "
                f"'{best_match.alias}' with branch '{best_match.branch}'"
            )

            return repository_link

        except Exception as e:
            if isinstance(e, (RepositoryLinkingError, BranchMatchingError)):
                raise
            raise RepositoryLinkingError(
                f"Unexpected error during exact branch matching: {e}"
            )

    def _detect_local_branch(self) -> Optional[str]:
        """Detect current local branch with graceful error handling.

        Returns:
            Local branch name or None if detection fails
        """
        if not self.git_service:
            logger.error("Git service not initialized")
            return None

        try:
            current_branch = self.git_service.get_current_branch()

            if not current_branch:
                logger.warning(
                    "Unable to detect current branch - not in a git repository"
                )
                return None

            # Handle detached HEAD state
            if current_branch.startswith("detached-"):
                logger.warning(
                    f"Repository is in detached HEAD state: {current_branch}"
                )
                # For exact branch matching, we can't match against detached HEAD
                # Return None to indicate no branch available for matching
                return None

            return current_branch

        except Exception as e:
            logger.warning(f"Error detecting local branch: {e}")
            return None

    def _filter_exact_matches(
        self, discovery_response: ClientDiscoveryResponse, target_branch: str
    ) -> List[RepositoryMatch]:
        """Filter discovered repositories for exact branch matches.

        Args:
            discovery_response: Response from repository discovery
            target_branch: Local branch to match against

        Returns:
            List of repositories with exact branch matches, prioritized
        """
        exact_matches = []

        # Process discovered repositories and classify by type
        # Combine all matches from golden and activated repositories
        all_matches = (
            discovery_response.golden_repositories
            + discovery_response.activated_repositories
        )
        for repo_match in all_matches:
            if target_branch in repo_match.available_branches:
                # Determine repository type based on alias pattern
                repository_type = self._determine_repository_type(repo_match.alias)

                # Set priority: activated repositories have higher priority
                priority = 1 if repository_type == RepositoryType.ACTIVATED else 2

                match = RepositoryMatch(
                    alias=repo_match.alias,
                    repository_type=repository_type,
                    branch=target_branch,
                    match_quality=MatchQuality.EXACT,
                    priority=priority,
                    git_url=repo_match.git_url,
                    display_name=repo_match.alias,  # Use alias as display name
                    description=f"{repo_match.repository_type.title()} repository: {repo_match.alias}",  # Generate description
                    available_branches=repo_match.available_branches,
                    last_updated=(
                        repo_match.last_indexed.isoformat()
                        if repo_match.last_indexed
                        else "Never"
                    ),  # Convert datetime to string
                    access_level="read",  # Default access level
                )
                exact_matches.append(match)

        # Sort by priority (activated repositories first)
        exact_matches.sort(key=lambda x: x.priority)

        logger.debug(
            f"Found {len(exact_matches)} exact branch matches for '{target_branch}'"
        )

        return exact_matches

    def _determine_repository_type(self, alias: str) -> RepositoryType:
        """Determine repository type based on alias pattern.

        Args:
            alias: Repository alias

        Returns:
            Repository type (activated or golden)
        """
        # Activated repositories typically have user-specific suffixes
        # Golden repositories typically end with '-golden' or are base names
        if alias.endswith("-golden") or "-" not in alias:
            return RepositoryType.GOLDEN
        else:
            return RepositoryType.ACTIVATED

    def _select_best_match(
        self, exact_matches: List[RepositoryMatch]
    ) -> Optional[RepositoryMatch]:
        """Select best repository match based on priority and criteria.

        Args:
            exact_matches: List of exact branch matches

        Returns:
            Best repository match or None if no matches
        """
        if not exact_matches:
            return None

        # Matches are already sorted by priority, so return the first one
        best_match = exact_matches[0]

        logger.debug(
            f"Selected best match: {best_match.repository_type.value} repository "
            f"'{best_match.alias}' (priority {best_match.priority})"
        )

        return best_match

    async def _try_fallback_matching(
        self, local_repo_path: Path, discovery_response: ClientDiscoveryResponse
    ) -> Optional[RepositoryLink]:
        """Try fallback branch matching when exact matching fails.

        Args:
            local_repo_path: Path to local git repository
            discovery_response: Response from repository discovery

        Returns:
            RepositoryLink with fallback match if found, None otherwise
        """
        try:
            # Initialize fallback matcher if not already done
            if not self.fallback_matcher:
                if not self.git_service:
                    logger.warning("Git service not available for fallback matching")
                    return None
                self.fallback_matcher = BranchFallbackMatcher(self.git_service)

            logger.info("Attempting fallback branch matching...")
            fallback_result = self.fallback_matcher.find_fallback_branch_match(
                local_repo_path, discovery_response
            )

            if fallback_result:
                logger.info(
                    f"Fallback matching succeeded: {fallback_result.repository_type.value} repository "
                    f"'{fallback_result.alias}' with branch '{fallback_result.branch}'"
                )

                # Check if fallback result is golden repository - try auto-activation
                if fallback_result.repository_type == RepositoryType.GOLDEN:
                    logger.info(
                        "Fallback match is golden repository - attempting auto-activation"
                    )

                    # Create RepositoryMatch for auto-activation (need to find the original match)
                    golden_repo_match = self._find_repository_match_by_alias(
                        fallback_result.alias, discovery_response
                    )

                    if golden_repo_match:
                        # Set the branch to the fallback branch found
                        golden_repo_match.branch = fallback_result.branch

                        auto_activated_link = await self._try_auto_activation(
                            golden_repo_match, local_repo_path
                        )

                        if auto_activated_link:
                            # Copy fallback-specific fields
                            auto_activated_link.match_reason = (
                                fallback_result.match_reason
                            )
                            auto_activated_link.parent_branch = (
                                fallback_result.parent_branch
                            )
                            return auto_activated_link

                # Auto-activation failed or cancelled - return original fallback result
                return fallback_result
            else:
                logger.info(
                    "Fallback matching failed: no suitable parent branches found"
                )

            return fallback_result

        except Exception as e:
            logger.warning(f"Fallback matching error: {e}")
            return None

    async def _try_auto_activation(
        self, golden_repo: RepositoryMatch, local_repo_path: Path
    ) -> Optional[RepositoryLink]:
        """Try auto-activation of golden repository when only golden repositories match.

        Args:
            golden_repo: Golden repository to activate
            local_repo_path: Path to local repository for context

        Returns:
            RepositoryLink for activated repository if successful, None otherwise
        """
        try:
            # Initialize auto-activator if not already done
            if not self.auto_activator:
                self.auto_activator = AutoRepositoryActivator(self.repository_client)

            # Attempt auto-activation
            activated_repo = await self.auto_activator.auto_activate_golden_repository(
                golden_repo, local_repo_path
            )

            # Convert activated repository to RepositoryLink for consistency
            repository_link = RepositoryLink(
                alias=activated_repo.user_alias,  # Use user alias for activated repo
                git_url=golden_repo.git_url,
                branch=activated_repo.branch,
                repository_type=RepositoryType.ACTIVATED,  # Mark as activated
                server_url=self.repository_client.server_url,
                linked_at=activated_repo.activated_at,
                display_name=golden_repo.display_name,
                description=golden_repo.description,
                access_level=golden_repo.access_level,
            )

            logger.info(
                f"Auto-activation successful: created activated repository link '{activated_repo.user_alias}'"
            )
            return repository_link

        except UserCancelledActivationError:
            logger.info(
                "User cancelled auto-activation - continuing with golden repository linking"
            )
            return None
        except RepositoryActivationError as e:
            logger.warning(
                f"Auto-activation failed: {e} - continuing with golden repository linking"
            )
            return None
        except Exception as e:
            logger.error(f"Unexpected error during auto-activation: {e}")
            return None

    def _find_repository_match_by_alias(
        self, alias: str, discovery_response: ClientDiscoveryResponse
    ) -> Optional[RepositoryMatch]:
        """Find RepositoryMatch by alias in discovery response.

        Args:
            alias: Repository alias to find
            discovery_response: Discovery response containing matches

        Returns:
            RepositoryMatch if found, None otherwise
        """
        # Combine all matches from golden and activated repositories
        all_matches = (
            discovery_response.golden_repositories
            + discovery_response.activated_repositories
        )
        for repo_match in all_matches:
            if repo_match.alias == alias:
                # Convert ClientDiscoveryResponse match to RepositoryMatch
                repository_type = self._determine_repository_type(repo_match.alias)
                priority = 1 if repository_type == RepositoryType.ACTIVATED else 2

                return RepositoryMatch(
                    alias=repo_match.alias,
                    repository_type=repository_type,
                    branch="",  # Will be set by caller
                    match_quality=MatchQuality.FALLBACK,
                    priority=priority,
                    git_url=repo_match.git_url,
                    display_name=repo_match.display_name,
                    description=repo_match.description,
                    available_branches=repo_match.available_branches,
                    last_updated=(
                        repo_match.last_indexed.isoformat()
                        if repo_match.last_indexed
                        else "Never"
                    ),  # Convert datetime to string
                    access_level="read",  # Default access level
                )

        return None


class BranchFallbackMatcher:
    """Handles branch fallback hierarchy matching for CIDX remote repository linking."""

    # Branch hierarchy priority order from story requirements
    PRIORITY_BRANCHES = ["main", "master", "develop", "development", "release"]

    def __init__(self, git_service: GitTopologyService):
        """Initialize branch fallback matcher.

        Args:
            git_service: Git topology service for merge-base analysis
        """
        self.git_service = git_service

    def find_fallback_branch_match(
        self, local_repo_path: Path, discovery_response: ClientDiscoveryResponse
    ) -> Optional[RepositoryLink]:
        """Find repository with fallback branch match using git merge-base analysis.

        Args:
            local_repo_path: Path to local git repository
            discovery_response: Response from repository discovery

        Returns:
            RepositoryLink with fallback match if found, None otherwise

        Raises:
            BranchMatchingError: If fallback matching logic fails
        """
        try:
            current_branch = self.git_service.get_current_branch()
            if not current_branch or current_branch.startswith("detached-"):
                logger.warning(
                    "Cannot perform fallback matching from detached HEAD or invalid branch"
                )
                return None

            logger.info(f"Starting fallback analysis for branch: {current_branch}")

            # Analyze branch ancestry to find parent branches
            ancestry = self._analyze_branch_ancestry(current_branch)
            if not ancestry:
                logger.info(f"No branch ancestry found for {current_branch}")
                return None

            # Prioritize parent branches by hierarchy
            prioritized_branches = self._prioritize_parent_branches(ancestry)
            if not prioritized_branches:
                logger.info(
                    f"No prioritized parent branches found for {current_branch}"
                )
                return None

            # Try to find parent branch match in prioritized order
            for parent_branch in prioritized_branches:
                fallback_link = self._find_parent_branch_match(
                    parent_branch, discovery_response
                )
                if fallback_link:
                    # Set fallback-specific fields
                    fallback_link.match_reason = self._create_match_reason(
                        current_branch, parent_branch
                    )
                    fallback_link.parent_branch = parent_branch

                    logger.info(
                        f"Found fallback match: branch '{parent_branch}' for original branch '{current_branch}'"
                    )
                    return fallback_link

            logger.info(f"No fallback matches found for {current_branch}")
            return None

        except Exception as e:
            raise BranchMatchingError(f"Fallback branch matching failed: {e}")

    def _analyze_branch_ancestry(self, current_branch: str) -> List[str]:
        """Analyze branch ancestry using GitTopologyService merge-base analysis.

        Args:
            current_branch: Current local branch name

        Returns:
            List of potential parent branches found through merge-base analysis
        """
        ancestry = []

        # Check merge-base with each priority branch
        for priority_branch in self.PRIORITY_BRANCHES:
            try:
                merge_base = self.git_service._get_merge_base(
                    current_branch, priority_branch
                )
                if merge_base:
                    ancestry.append(priority_branch)
                    logger.debug(
                        f"Found merge-base between {current_branch} and {priority_branch}: {merge_base[:8]}"
                    )
            except Exception as e:
                logger.debug(
                    f"Failed to get merge-base for {current_branch}..{priority_branch}: {e}"
                )
                continue

        return ancestry

    def _prioritize_parent_branches(self, ancestry: List[str]) -> List[str]:
        """Prioritize parent branches based on hierarchy and recency.

        Args:
            ancestry: List of parent branches found in ancestry analysis

        Returns:
            List of branches sorted by priority (highest first)
        """
        # Sort ancestry by priority order defined in PRIORITY_BRANCHES
        prioritized = []

        # First add branches that match our priority order
        for priority_branch in self.PRIORITY_BRANCHES:
            if priority_branch in ancestry:
                prioritized.append(priority_branch)

        # Then add any remaining branches not in priority list
        for branch in ancestry:
            if branch not in prioritized:
                prioritized.append(branch)

        logger.debug(f"Prioritized parent branches: {prioritized}")
        return prioritized

    def _find_parent_branch_match(
        self, parent_branch: str, discovery_response: ClientDiscoveryResponse
    ) -> Optional[RepositoryLink]:
        """Find repository match for specific parent branch.

        Args:
            parent_branch: Parent branch to match against
            discovery_response: Response from repository discovery

        Returns:
            RepositoryLink if parent branch found in any repository, None otherwise
        """
        # Find all repositories that have the parent branch
        matching_repos = []
        # Combine all matches from golden and activated repositories
        all_matches = (
            discovery_response.golden_repositories
            + discovery_response.activated_repositories
        )
        for repo_match in all_matches:
            if parent_branch in repo_match.available_branches:
                repository_type = self._determine_repository_type(repo_match.alias)
                matching_repos.append((repo_match, repository_type))

        if not matching_repos:
            return None

        # Sort by repository type priority: activated first, then golden
        matching_repos.sort(key=lambda x: (x[1] == RepositoryType.GOLDEN, x[0].alias))

        # Take the first (highest priority) match
        best_repo, repository_type = matching_repos[0]

        # Create repository link
        repository_link = RepositoryLink(
            alias=best_repo.alias,
            git_url=best_repo.git_url,
            branch=parent_branch,
            repository_type=repository_type,
            server_url="",  # Will be set by caller
            linked_at="",  # Will be set by caller
            display_name=best_repo.display_name,
            description=best_repo.description,
            access_level="read",  # Default access level for server model instances
        )

        logger.debug(
            f"Found parent branch match: {repository_type.value} repository '{best_repo.alias}' with branch '{parent_branch}'"
        )
        return repository_link

    def _determine_repository_type(self, alias: str) -> RepositoryType:
        """Determine repository type based on alias pattern.

        Args:
            alias: Repository alias

        Returns:
            Repository type (activated or golden)
        """
        # Activated repositories typically have user-specific suffixes
        # Golden repositories typically end with '-golden' or are base names
        if alias.endswith("-golden") or "-" not in alias:
            return RepositoryType.GOLDEN
        else:
            return RepositoryType.ACTIVATED

    def _create_match_reason(self, original_branch: str, fallback_branch: str) -> str:
        """Create human-readable match reason for fallback scenarios.

        Args:
            original_branch: Original branch that failed exact matching
            fallback_branch: Fallback branch that was matched

        Returns:
            Human-readable explanation of fallback reasoning
        """
        return (
            f"Exact branch '{original_branch}' not found. "
            f"Fell back to parent branch '{fallback_branch}' via merge-base analysis."
        )


class AutoRepositoryActivator:
    """Handles automatic repository activation when only golden repositories match."""

    def __init__(self, repository_client: RepositoryLinkingClient):
        """Initialize auto repository activator.

        Args:
            repository_client: API client for repository operations
        """
        self.repository_client = repository_client

    async def auto_activate_golden_repository(
        self, golden_repo: RepositoryMatch, project_context: Path
    ) -> ActivatedRepository:
        """Automatically activate a golden repository for user access.

        Args:
            golden_repo: Golden repository match to activate
            project_context: Path to project for context in alias generation

        Returns:
            Activated repository information

        Raises:
            UserCancelledActivationError: If user cancels activation
            RepositoryActivationError: If activation fails
        """
        try:
            # Generate meaningful user alias with branch context
            base_alias = self._generate_user_alias(golden_repo, project_context)

            # Ensure alias uniqueness across user's activated repositories
            user_alias = await self._ensure_unique_alias(base_alias)

            # Confirm activation with user
            if not self._confirm_activation(golden_repo, user_alias):
                raise UserCancelledActivationError(
                    f"User cancelled activation of repository '{golden_repo.alias}'"
                )

            # Activate the repository
            logger.info(
                f"Auto-activating golden repository: {golden_repo.alias} -> {user_alias}"
            )
            activated_repo = await self.repository_client.activate_repository(
                golden_repo.alias, golden_repo.branch, user_alias
            )

            # Display activation success
            self._display_activation_success(activated_repo)

            return activated_repo

        except (UserCancelledActivationError, RepositoryActivationError):
            raise
        except ActivationError as e:
            raise RepositoryActivationError(f"Repository activation failed: {e}")
        except Exception as e:
            raise RepositoryActivationError(
                f"Unexpected error during auto-activation: {e}"
            )

    def _generate_user_alias(
        self, golden_repo: RepositoryMatch, project_context: Path
    ) -> str:
        """Generate descriptive alias combining project and branch context.

        Args:
            golden_repo: Golden repository to generate alias for
            project_context: Project path for context

        Returns:
            Generated base alias combining project and branch names
        """
        # Extract project name from path
        project_name = project_context.name

        # Normalize project name
        project_parts = self._normalize_name_parts(project_name)

        # Extract branch name components
        branch_name = golden_repo.branch
        branch_parts = self._normalize_branch_parts(branch_name)

        # Combine project and branch components
        alias_parts = project_parts + branch_parts

        # Create base alias
        base_alias = "-".join(alias_parts)

        logger.debug(f"Generated base alias: {base_alias}")
        return base_alias

    def _normalize_name_parts(self, name: str) -> list[str]:
        """Normalize name string into clean parts for alias generation.

        Args:
            name: Name string to normalize

        Returns:
            List of normalized name parts
        """
        import re

        # Replace special characters with hyphens, then split
        normalized = re.sub(r"[^a-zA-Z0-9-]", "-", name)

        # Split on hyphens and filter out empty parts
        parts = [part.lower() for part in normalized.split("-") if part]

        return parts

    def _normalize_branch_parts(self, branch_name: str) -> list[str]:
        """Normalize branch name into clean parts for alias generation.

        Args:
            branch_name: Branch name to normalize

        Returns:
            List of normalized branch parts
        """
        # Handle common branch prefixes by including the prefix type
        if branch_name.startswith("feature/"):
            prefix_parts = ["feature"]
            remaining = branch_name[8:]  # Remove 'feature/'
        elif branch_name.startswith("bugfix/"):
            prefix_parts = ["bugfix"]
            remaining = branch_name[7:]  # Remove 'bugfix/'
        elif branch_name.startswith("hotfix/"):
            prefix_parts = ["hotfix"]
            remaining = branch_name[7:]  # Remove 'hotfix/'
        else:
            prefix_parts = []
            remaining = branch_name

        # Normalize the remaining part
        remaining_parts = self._normalize_name_parts(remaining)

        # Combine prefix and remaining parts
        return prefix_parts + remaining_parts

    async def _ensure_unique_alias(self, base_alias: str) -> str:
        """Ensure alias uniqueness across user's activated repositories.

        Args:
            base_alias: Base alias to make unique

        Returns:
            Unique alias with timestamp or suffix if needed
        """
        try:
            # Get existing activated repositories
            existing_repos = await self.repository_client.list_user_repositories()
            existing_aliases = {repo.user_alias for repo in existing_repos}

            # Generate timestamped alias
            timestamp = datetime.utcnow().strftime("%Y%m%d")
            timestamped_alias = f"{base_alias}-{timestamp}"

            # If no conflict, return timestamped alias
            if timestamped_alias not in existing_aliases:
                return timestamped_alias

            # If conflict, add suffix
            counter = 1
            while f"{timestamped_alias}-{counter}" in existing_aliases:
                counter += 1

            unique_alias = f"{timestamped_alias}-{counter}"
            logger.debug(f"Generated unique alias: {unique_alias}")
            return unique_alias

        except Exception as e:
            logger.warning(f"Error checking alias uniqueness: {e}")
            # Fallback to timestamped alias even if check failed
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            return f"{base_alias}-{timestamp}"

    def _confirm_activation(
        self, golden_repo: RepositoryMatch, user_alias: str
    ) -> bool:
        """Confirm activation with user through Rich console interface.

        Args:
            golden_repo: Repository to activate
            user_alias: Generated user alias

        Returns:
            True if user confirms, False if user cancels
        """
        print("\n" + "=" * 70)
        print("🔗 AUTO REPOSITORY ACTIVATION")
        print("=" * 70)
        print(f"Golden Repository: {golden_repo.display_name}")
        print(f"Repository Alias:  {golden_repo.alias}")
        print(f"Branch:           {golden_repo.branch}")
        print(f"Git URL:          {golden_repo.git_url}")
        print(f"Your Alias:       {user_alias}")
        print(f"Access Level:     {golden_repo.access_level}")
        print("\nThis will activate the repository for your personal use.")
        print("You'll be able to query it using the user alias above.")
        print("=" * 70)

        while True:
            response = (
                input("\nDo you want to activate this repository? (y/n): ")
                .strip()
                .lower()
            )
            if response in ["y", "yes"]:
                return True
            elif response in ["n", "no"]:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")

    def _display_activation_success(self, activated_repo: ActivatedRepository) -> None:
        """Display activation success with repository details.

        Args:
            activated_repo: Successfully activated repository
        """
        print("\n" + "=" * 70)
        print("✅ REPOSITORY ACTIVATION SUCCESSFUL")
        print("=" * 70)
        print(f"Repository:       {activated_repo.golden_alias}")
        print(f"Your Alias:       {activated_repo.user_alias}")
        print(f"Branch:           {activated_repo.branch}")
        print(f"Status:           {activated_repo.status}")
        print(f"Activated At:     {activated_repo.activated_at}")
        print(f"Expires At:       {activated_repo.expires_at}")
        print(f"Query Endpoint:   {activated_repo.query_endpoint}")
        print(f"Permissions:      {', '.join(activated_repo.access_permissions)}")
        print("\nUsage Instructions:")
        print(f"• Use alias '{activated_repo.user_alias}' for queries")
        print(f"• Query endpoint: {activated_repo.query_endpoint}")
        if activated_repo.usage_limits:
            print(f"• Usage limits: {activated_repo.usage_limits}")
        print("=" * 70)


def store_repository_link(project_root: Path, repository_link: RepositoryLink) -> None:
    """Store repository link in local remote configuration.

    Args:
        project_root: Path to project root directory
        repository_link: Repository link to store

    Raises:
        RepositoryLinkingError: If storage fails
    """
    try:
        config_dir = project_root / ".code-indexer"
        config_dir.mkdir(exist_ok=True)

        config_path = config_dir / ".remote-config"

        # Load existing configuration or create new
        config_data = {}
        if config_path.exists():
            try:
                with open(config_path, "r") as f:
                    config_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                # Start with fresh config if existing is corrupted
                config_data = {}

        # Update with repository link information
        repository_link_data = {
            "alias": repository_link.alias,
            "git_url": repository_link.git_url,
            "branch": repository_link.branch,
            "repository_type": repository_link.repository_type.value,
            "server_url": repository_link.server_url,
            "linked_at": repository_link.linked_at,
            "display_name": repository_link.display_name,
            "description": repository_link.description,
            "access_level": repository_link.access_level,
        }

        # Add optional fallback fields if present
        if repository_link.match_reason:
            repository_link_data["match_reason"] = repository_link.match_reason
        if repository_link.parent_branch:
            repository_link_data["parent_branch"] = repository_link.parent_branch

        config_data.update(
            {
                "mode": "remote",
                "repository_link": repository_link_data,
            }
        )

        # Write updated configuration
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(
            f"Stored repository link for '{repository_link.alias}' to {config_path}"
        )

    except Exception as e:
        raise RepositoryLinkingError(f"Failed to store repository link: {e}")


def load_repository_link(project_root: Path) -> Optional[RepositoryLink]:
    """Load repository link from local remote configuration.

    Args:
        project_root: Path to project root directory

    Returns:
        Repository link if found, None otherwise

    Raises:
        RepositoryLinkingError: If loading fails due to corruption
    """
    try:
        config_path = project_root / ".code-indexer" / ".remote-config"

        if not config_path.exists():
            return None

        with open(config_path, "r") as f:
            config_data = json.load(f)

        repository_link_data = config_data.get("repository_link")
        if not repository_link_data:
            return None

        # Validate required fields
        required_fields = [
            "alias",
            "git_url",
            "branch",
            "repository_type",
            "server_url",
            "linked_at",
        ]
        for field in required_fields:
            if field not in repository_link_data:
                raise RepositoryLinkingError(
                    f"Invalid repository link configuration: missing {field}"
                )

        repository_link = RepositoryLink(
            alias=repository_link_data["alias"],
            git_url=repository_link_data["git_url"],
            branch=repository_link_data["branch"],
            repository_type=RepositoryType(repository_link_data["repository_type"]),
            server_url=repository_link_data["server_url"],
            linked_at=repository_link_data["linked_at"],
            display_name=repository_link_data.get("display_name", ""),
            description=repository_link_data.get("description", ""),
            access_level=repository_link_data.get("access_level", "read"),
            match_reason=repository_link_data.get("match_reason"),
            parent_branch=repository_link_data.get("parent_branch"),
        )

        return repository_link

    except json.JSONDecodeError as e:
        raise RepositoryLinkingError(f"Corrupted repository link configuration: {e}")
    except ValueError as e:
        raise RepositoryLinkingError(f"Invalid repository link configuration: {e}")
    except Exception as e:
        raise RepositoryLinkingError(f"Failed to load repository link: {e}")
