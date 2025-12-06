"""
Result aggregation for omni-search.

Aggregates search results from multiple repositories.
"""

from typing import Dict, List
import math


class ResultAggregator:
    """Aggregates results from multiple repositories."""

    def __init__(self, mode: str, limit: int):
        """
        Initialize result aggregator.

        Args:
            mode: Aggregation mode ("global" or "per_repo")
            limit: Maximum number of results to return

        Raises:
            ValueError: If mode is invalid or limit is negative
        """
        if mode not in ["global", "per_repo"]:
            raise ValueError(
                f"Invalid aggregation mode: {mode}. Must be 'global' or 'per_repo'"
            )

        if limit < 0:
            raise ValueError(f"Limit must be non-negative, got {limit}")

        self.mode = mode
        self.limit = limit

    def aggregate(self, repo_results: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Aggregate results from multiple repositories.

        Args:
            repo_results: Dict mapping repository alias to list of results

        Returns:
            Aggregated list of results with repository_alias added
        """
        if not repo_results or self.limit == 0:
            return []

        if self.mode == "global":
            return self._aggregate_global(repo_results)
        else:  # per_repo
            return self._aggregate_per_repo(repo_results)

    def _aggregate_global(self, repo_results: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Global aggregation: top-K by score across all repos.

        Args:
            repo_results: Dict mapping repository alias to list of results

        Returns:
            Top-K results sorted by score
        """
        all_results = []

        for repo_alias, results in repo_results.items():
            for result in results:
                # Add repository_alias to each result
                result_with_repo = result.copy()
                result_with_repo["repository_alias"] = repo_alias
                all_results.append(result_with_repo)

        # Sort by score (descending)
        all_results.sort(key=lambda x: x.get("score", 0.0), reverse=True)

        return all_results[: self.limit]

    def _aggregate_per_repo(self, repo_results: Dict[str, List[Dict]]) -> List[Dict]:
        """
        Per-repo aggregation: proportional sampling with interleaving.

        Args:
            repo_results: Dict mapping repository alias to list of results

        Returns:
            Interleaved results with proportional sampling
        """
        # Filter out empty result lists
        non_empty_repos = {k: v for k, v in repo_results.items() if v}

        if not non_empty_repos:
            return []

        # Calculate total results
        total_results = sum(len(results) for results in non_empty_repos.values())

        # Calculate proportional allocation per repo
        repo_allocations = {}
        for repo_alias, results in non_empty_repos.items():
            proportion = len(results) / total_results
            allocation = max(1, int(math.ceil(proportion * self.limit)))
            repo_allocations[repo_alias] = min(allocation, len(results))

        # Adjust allocations to not exceed limit
        while sum(repo_allocations.values()) > self.limit:
            # Reduce allocation from repo with most allocated
            max_repo = max(repo_allocations.keys(), key=lambda k: repo_allocations[k])
            repo_allocations[max_repo] -= 1
            if repo_allocations[max_repo] == 0:
                del repo_allocations[max_repo]

        # Create iterators for each repo (sorted by score)
        repo_iterators = {}
        for repo_alias, allocation in repo_allocations.items():
            results = non_empty_repos[repo_alias]
            sorted_results = sorted(
                results, key=lambda x: x.get("score", 0.0), reverse=True
            )
            repo_iterators[repo_alias] = iter(sorted_results[:allocation])

        # Interleave results
        aggregated = []
        while len(aggregated) < self.limit and repo_iterators:
            for repo_alias in list(repo_iterators.keys()):
                try:
                    result = next(repo_iterators[repo_alias])
                    result_with_repo = result.copy()
                    result_with_repo["repository_alias"] = repo_alias
                    aggregated.append(result_with_repo)

                    if len(aggregated) >= self.limit:
                        break
                except StopIteration:
                    del repo_iterators[repo_alias]

        return aggregated
