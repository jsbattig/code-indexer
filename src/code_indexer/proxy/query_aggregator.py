"""Query result aggregator for proxy mode.

This module aggregates, merges, sorts, and formats query results from
multiple repositories into a unified output (Stories 3.2, 3.3, 3.4).
"""

import logging
from typing import Dict, List, Optional

from .constants import DEFAULT_QUERY_LIMIT
from .query_parser import QueryResultParser
from .query_result import QueryResult


logger = logging.getLogger(__name__)


class QueryResultAggregator:
    """Aggregate and format query results from multiple repositories.

    Handles the complete aggregation pipeline:
    1. Parse results from each repository (Story 3.1)
    2. Merge all results into single list (Story 3.2)
    3. Sort by score descending (Story 3.2)
    4. Apply global limit (Story 3.3)
    5. Format output preserving repository context (Story 3.4)
    """

    def __init__(self):
        """Initialize aggregator with parser."""
        self.parser = QueryResultParser()

    def aggregate_results(
        self,
        repository_outputs: Dict[str, str],
        limit: Optional[int] = DEFAULT_QUERY_LIMIT,
        repo_name_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """Aggregate query results from all repositories.

        Args:
            repository_outputs: Map of repo_path -> query output string
            limit: Maximum number of results to return (None or 0 = unlimited)

        Returns:
            Formatted output string matching single-repo query format

        Examples:
            >>> repo_outputs = {
            ...     "/repo1": "0.95 /repo1/auth.py:1-10\\n  1: code",
            ...     "/repo2": "0.85 /repo2/user.py:5-15\\n  5: code"
            ... }
            >>> aggregator.aggregate_results(repo_outputs, limit=10)
            '0.95 /repo1/auth.py:1-10\\n  1: code\\n\\n0.85 /repo2/user.py:5-15\\n  5: code'
        """
        # Step 1: Parse results from each repository
        all_results = []

        for repo_path, output in repository_outputs.items():
            if not output or not output.strip():
                continue

            # Skip error outputs
            if self._is_error_output(output):
                logger.warning(f"Skipping error output from {repo_path}")
                continue

            try:
                # Get repository name for path prefixing
                repo_name = repo_name_map.get(repo_path, "") if repo_name_map else ""

                results = self.parser.parse_repository_output(output, repo_path)

                # Prefix file paths with repository name for disambiguation
                if repo_name:
                    for result in results:
                        # Transform "README.md" -> "repo1/README.md"
                        result.file_path = f"{repo_name}/{result.file_path}"

                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Failed to parse output from {repo_path}: {e}")
                continue

        # Step 2 & 3: Merge and sort by score (descending)
        all_results.sort(key=lambda r: r.score, reverse=True)

        # Step 4: Apply global limit
        if limit and limit > 0:
            all_results = all_results[:limit]

        # Step 5: Format output
        return self._format_results(all_results)

    def _is_error_output(self, output: str) -> bool:
        """Check if output indicates an error.

        Args:
            output: Raw output string to check

        Returns:
            True if output appears to be an error message
        """
        error_indicators = [
            "Error:",
            "Failed to",
            "Cannot connect",
            "No such file",
            "Permission denied",
            "Connection refused",
        ]
        return any(indicator in output for indicator in error_indicators)

    def _format_results(self, results: List[QueryResult]) -> str:
        """Format results for output matching single-repo query format.

        Format matches real CIDX output:
            <score> <absolute_path>:<start>-<end>
              <line_num>: <code>
              <line_num>: <code>

            <score> <absolute_path>:<start>-<end>
              <line_num>: <code>

        Args:
            results: List of QueryResult objects sorted by score

        Returns:
            Formatted output string
        """
        if not results:
            return ""

        output_lines = []

        for result in results:
            # Format result header: score path:line_range
            header = f"{result.score} {result.file_path}:{result.line_range[0]}-{result.line_range[1]}"
            output_lines.append(header)

            # Add code content (already formatted with line numbers)
            if result.content:
                output_lines.append(result.content)

            # Add blank line between results
            output_lines.append("")

        # Join with newlines, remove trailing blank line
        return "\n".join(output_lines).rstrip() + "\n" if output_lines else ""
