"""
Git URL Normalization Service for CIDX Server.

Provides comprehensive git URL normalization to enable matching between different
URL formats (HTTP vs SSH, with/without .git suffix, etc.) for repository discovery.
"""

import re
from pydantic import BaseModel


class GitUrlNormalizationError(Exception):
    """Exception raised when git URL normalization fails."""

    pass


class NormalizedGitUrl(BaseModel):
    """Normalized git URL representation."""

    original_url: str
    canonical_form: str
    domain: str
    user: str
    repo: str

    def __eq__(self, other) -> bool:
        """Compare NormalizedGitUrl objects based on canonical form."""
        if not isinstance(other, NormalizedGitUrl):
            return False
        return self.canonical_form == other.canonical_form

    def __hash__(self) -> int:
        """Hash based on canonical form for use in sets/dicts."""
        return hash(self.canonical_form)


class GitUrlNormalizer:
    """Service for normalizing git URLs to canonical forms."""

    def __init__(self):
        """Initialize the git URL normalizer."""
        # Regex patterns for different git URL formats
        self.https_pattern = re.compile(r"^https?://([^/]+)/(.+?)(?:\.git)?/?$")
        self.ssh_pattern = re.compile(r"^(?:ssh://)?git@([^:/]+)[:/](.+?)(?:\.git)?/?$")

    def normalize(self, git_url: str) -> NormalizedGitUrl:
        """
        Normalize a git URL to canonical form.

        Args:
            git_url: The git URL to normalize

        Returns:
            NormalizedGitUrl object with canonical representation

        Raises:
            GitUrlNormalizationError: If URL cannot be normalized
        """
        if not git_url or not git_url.strip():
            raise GitUrlNormalizationError("Git URL cannot be empty")

        git_url = git_url.strip()

        # Try HTTPS format first
        https_match = self.https_pattern.match(git_url)
        if https_match:
            domain, path = https_match.groups()
            return self._create_normalized_url(git_url, domain, path)

        # Try SSH format
        ssh_match = self.ssh_pattern.match(git_url)
        if ssh_match:
            domain, path = ssh_match.groups()
            return self._create_normalized_url(git_url, domain, path)

        # If no patterns match, it's not a valid git URL
        raise GitUrlNormalizationError(f"Invalid git URL format: {git_url}")

    def _create_normalized_url(
        self, original_url: str, domain: str, path: str
    ) -> NormalizedGitUrl:
        """
        Create a normalized URL object from parsed components.

        Args:
            original_url: The original git URL
            domain: The git server domain
            path: The repository path

        Returns:
            NormalizedGitUrl object

        Raises:
            GitUrlNormalizationError: If path is invalid
        """
        # Clean up the path
        path = path.strip("/")
        if not path:
            raise GitUrlNormalizationError("Repository path cannot be empty")

        # Split path into components
        path_parts = path.split("/")
        if len(path_parts) < 2:
            raise GitUrlNormalizationError(f"Invalid repository path format: {path}")

        # For complex paths like "group/subgroup/project", the repo is the last part
        # and the user/organization is everything before it
        repo = path_parts[-1]
        user = "/".join(path_parts[:-1])

        if not repo or not user:
            raise GitUrlNormalizationError(f"Invalid user/repo format in path: {path}")

        # Create canonical form: domain/user/repo
        canonical_form = f"{domain}/{path}"

        return NormalizedGitUrl(
            original_url=original_url,
            canonical_form=canonical_form,
            domain=domain,
            user=user,
            repo=repo,
        )

    def are_equivalent(self, url1: str, url2: str) -> bool:
        """
        Check if two git URLs are equivalent (normalize to same canonical form).

        Args:
            url1: First git URL
            url2: Second git URL

        Returns:
            True if URLs are equivalent, False otherwise
        """
        try:
            normalized1 = self.normalize(url1)
            normalized2 = self.normalize(url2)
            return normalized1.canonical_form == normalized2.canonical_form
        except GitUrlNormalizationError:
            return False

    def get_canonical_form(self, git_url: str) -> str:
        """
        Get the canonical form of a git URL.

        Args:
            git_url: The git URL to normalize

        Returns:
            Canonical form string

        Raises:
            GitUrlNormalizationError: If URL cannot be normalized
        """
        normalized = self.normalize(git_url)
        return normalized.canonical_form
