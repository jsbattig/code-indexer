"""
Omni-search service for cross-repository search.

Orchestrates parallel search across multiple repositories.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Dict, List, Optional, Any

from .repo_pattern_matcher import RepoPatternMatcher
from .result_aggregator import ResultAggregator
from .omni_cache import OmniCache
from ..utils.config_manager import OmniSearchConfig

logger = logging.getLogger(__name__)


class OmniSearchService:
    """Orchestrates cross-repository search with parallel execution."""

    def __init__(
        self,
        config: OmniSearchConfig,
        query_service: Any,
        repo_manager: Any,
    ):
        """
        Initialize omni-search service.

        Args:
            config: Omni-search configuration
            query_service: Query service for single-repo searches
            repo_manager: Repository manager for getting repo aliases
        """
        self.config = config
        self.query_service = query_service
        self.repo_manager = repo_manager
        self.cache = OmniCache(
            max_entries=config.cache_max_entries,
            ttl_seconds=config.cache_ttl_seconds,
        )

    def search(
        self,
        repository_patterns: List[str],
        query: str,
        limit: Optional[int] = None,
        aggregation_mode: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """
        Search across multiple repositories in parallel.

        Args:
            repository_patterns: List of repo patterns (wildcards/regex or exact names)
            query: Search query string
            limit: Maximum number of results (default from config)
            aggregation_mode: "global" or "per_repo" (default from config)
            **kwargs: Additional search parameters passed to query service

        Returns:
            Dict with cursor, total_results, total_repos_searched, results, errors
        """
        # Set defaults
        if limit is None:
            limit = self.config.default_limit
        if aggregation_mode is None:
            aggregation_mode = self.config.default_aggregation_mode

        # Validate limit
        limit = min(limit, self.config.max_limit)

        # Get all repository aliases
        all_repos = self.repo_manager.get_all_aliases()

        # Filter repos by patterns
        matcher = RepoPatternMatcher(
            patterns=repository_patterns,
            metacharacters=self.config.pattern_metacharacters,
        )
        target_repos = matcher.filter_repos(all_repos)

        if not target_repos:
            # No matching repos
            empty_cursor = self.cache.store_results([], page_size=limit)
            return {
                "cursor": empty_cursor,
                "total_results": 0,
                "total_repos_searched": 0,
                "results": [],
                "errors": {},
            }

        # Execute searches in parallel
        repo_results = {}
        errors = {}

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Submit all search tasks
            future_to_repo = {
                executor.submit(
                    self._search_single_repo,
                    repo_alias,
                    query,
                    **kwargs,
                ): repo_alias
                for repo_alias in target_repos
            }

            # Collect results as they complete
            for future in as_completed(future_to_repo):
                repo_alias = future_to_repo[future]

                try:
                    result = future.result(timeout=self.config.per_repo_timeout_seconds)
                    if result and "results" in result:
                        repo_results[repo_alias] = result["results"][
                            : self.config.max_results_per_repo
                        ]
                    else:
                        repo_results[repo_alias] = []
                except TimeoutError:
                    errors[repo_alias] = (
                        f"Search timeout after {self.config.per_repo_timeout_seconds}s"
                    )
                    logger.warning(f"Search timeout for repo {repo_alias}")
                except Exception as e:
                    errors[repo_alias] = str(e)
                    logger.error(f"Search error for repo {repo_alias}: {e}")

        # Aggregate results
        aggregator = ResultAggregator(mode=aggregation_mode, limit=limit)
        aggregated_results = aggregator.aggregate(repo_results)

        # Store in cache
        cursor = self.cache.store_results(aggregated_results, page_size=limit)

        return {
            "cursor": cursor,
            "total_results": len(aggregated_results),
            "total_repos_searched": len(repo_results),
            "results": aggregated_results[:limit],
            "errors": errors,
        }

    def _search_single_repo(self, repo_alias: str, query: str, **kwargs) -> Dict:
        """
        Search a single repository.

        Args:
            repo_alias: Repository alias
            query: Search query
            **kwargs: Additional search parameters

        Returns:
            Search result dict from query service
        """
        return self.query_service.query(repo_alias, query, **kwargs)

    def get_page(self, cursor: str, page: int) -> Optional[List[Dict]]:
        """
        Retrieve a page of cached results.

        Args:
            cursor: Cursor from search()
            page: Page number (0-indexed)

        Returns:
            List of results for the page, or None if invalid/expired
        """
        return self.cache.get_page(cursor, page)

    def get_metadata(self, cursor: str) -> Optional[Dict]:
        """
        Retrieve metadata for cached results.

        Args:
            cursor: Cursor from search()

        Returns:
            Metadata dict or None if invalid/expired
        """
        return self.cache.get_metadata(cursor)
