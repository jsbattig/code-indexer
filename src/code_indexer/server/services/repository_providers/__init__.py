"""
Repository Providers for CIDX Server Auto-Discovery.

Provides abstract base class and concrete implementations for
discovering repositories from various platforms (GitLab, GitHub).
"""

from .base import RepositoryProviderBase
from .gitlab_provider import GitLabProvider, GitLabProviderError

__all__ = ["RepositoryProviderBase", "GitLabProvider", "GitLabProviderError"]
