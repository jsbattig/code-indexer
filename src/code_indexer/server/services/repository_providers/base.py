"""
Repository Provider Base Class for CIDX Server.

Defines the abstract interface that all repository discovery providers
(GitLab, GitHub) must implement.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from code_indexer.server.models.auto_discovery import RepositoryDiscoveryResult


class RepositoryProviderBase(ABC):
    """Abstract base class for repository discovery providers."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Return the platform name (gitlab, github)."""
        ...

    @abstractmethod
    async def is_configured(self) -> bool:
        """
        Check if the provider is properly configured.

        Returns:
            True if the provider has valid configuration (e.g., API token),
            False otherwise.
        """
        ...

    @abstractmethod
    async def discover_repositories(
        self, page: int = 1, page_size: int = 50, search: Optional[str] = None
    ) -> "RepositoryDiscoveryResult":
        """
        Discover repositories from the platform.

        Args:
            page: Page number (1-indexed)
            page_size: Number of repositories per page
            search: Optional search string to filter repositories by name,
                   description, commit hash, or committer (case-insensitive)

        Returns:
            RepositoryDiscoveryResult with discovered repositories

        Raises:
            DiscoveryProviderError: If API call fails
        """
        ...
