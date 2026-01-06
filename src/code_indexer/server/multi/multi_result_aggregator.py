"""
Multi-repository search result aggregator.

Handles result aggregation in per-repository mode with proper attribution.
"""

from typing import Dict, List, Any, Optional


class MultiResultAggregator:
    """
    Aggregates search results from multiple repositories.

    Always uses per-repository mode:
    - Results are grouped by repository
    - Each result includes a "repository" field
    - Per-repo limit is enforced independently
    - No cross-repository deduplication
    - Optional score filtering applied before limit
    """

    def __init__(self, limit: int, min_score: Optional[float] = None):
        """
        Initialize result aggregator.

        Args:
            limit: Maximum number of results per repository
            min_score: Minimum relevance score threshold (0.0-1.0). Results below
                      this threshold will be filtered out before applying limit.
        """
        self.limit = limit
        self.min_score = min_score

    def aggregate(self, repo_results: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Aggregate results in per-repository mode with optional score filtering.

        Args:
            repo_results: Dictionary mapping repository ID to list of results

        Returns:
            Dictionary mapping repository ID to aggregated results,
            with each result containing a "repository" field
        """
        aggregated = {}

        for repo_id, results in repo_results.items():
            # Apply score filtering BEFORE limit (AC2: Score Filtering Consistency)
            if self.min_score is not None:
                filtered_results = [
                    r for r in results if r.get("score", 0.0) >= self.min_score
                ]
            else:
                filtered_results = results

            # Apply per-repo limit after filtering
            limited_results = filtered_results[: self.limit]

            # Add repository field to each result
            for result in limited_results:
                result["repository"] = repo_id

            aggregated[repo_id] = limited_results

        return aggregated
