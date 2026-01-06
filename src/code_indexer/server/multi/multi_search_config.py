"""
Multi-search configuration for cross-repository search.

Provides configuration management for multi-repository search operations
with sensible defaults and environment variable overrides.
"""

import os
from dataclasses import dataclass


@dataclass
class MultiSearchConfig:
    """
    Configuration for multi-repository search operations.

    Attributes:
        max_workers: Maximum number of concurrent search threads (default: 10)
        query_timeout_seconds: Timeout for each repository search in seconds (default: 30)
        max_repos_per_query: Maximum number of repositories allowed in a single query (default: 50)
        max_results_per_repo: Maximum number of results to return per repository (default: 100)
    """

    max_workers: int = 10
    query_timeout_seconds: int = 30
    max_repos_per_query: int = 50
    max_results_per_repo: int = 100

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_workers <= 0:
            raise ValueError("max_workers must be positive")
        if self.query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        if self.max_repos_per_query <= 0:
            raise ValueError("max_repos_per_query must be positive")
        if self.max_results_per_repo <= 0:
            raise ValueError("max_results_per_repo must be positive")

    @classmethod
    def from_env(cls) -> "MultiSearchConfig":
        """
        Create configuration from environment variables.

        Environment variables:
            CIDX_MULTI_MAX_WORKERS: Override max_workers
            CIDX_MULTI_QUERY_TIMEOUT: Override query_timeout_seconds
            CIDX_MULTI_MAX_REPOS: Override max_repos_per_query
            CIDX_MULTI_MAX_RESULTS_PER_REPO: Override max_results_per_repo

        Returns:
            MultiSearchConfig with environment overrides applied
        """
        max_workers = int(os.getenv("CIDX_MULTI_MAX_WORKERS", "10"))
        query_timeout_seconds = int(os.getenv("CIDX_MULTI_QUERY_TIMEOUT", "30"))
        max_repos_per_query = int(os.getenv("CIDX_MULTI_MAX_REPOS", "50"))
        max_results_per_repo = int(os.getenv("CIDX_MULTI_MAX_RESULTS_PER_REPO", "100"))

        return cls(
            max_workers=max_workers,
            query_timeout_seconds=query_timeout_seconds,
            max_repos_per_query=max_repos_per_query,
            max_results_per_repo=max_results_per_repo,
        )
