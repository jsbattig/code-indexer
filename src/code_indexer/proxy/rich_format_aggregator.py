"""Rich format result aggregator for proxy mode.

This module aggregates, merges, sorts, and formats query results from
multiple repositories in rich format (non-quiet mode) with full metadata
preservation.
"""

import logging
from typing import Dict, List, Optional

from .constants import DEFAULT_QUERY_LIMIT
from .rich_format_parser import RichFormatParser
from .query_result import QueryResult


logger = logging.getLogger(__name__)


class RichFormatAggregator:
    """Aggregate and format rich query results from multiple repositories.

    Handles the complete aggregation pipeline for rich format output:
    1. Parse rich results from each repository (with full metadata)
    2. Merge all results into single list
    3. Sort by score descending
    4. Apply global limit
    5. Format output preserving rich format with repository context
    """

    def __init__(self):
        """Initialize aggregator with rich format parser."""
        self.parser = RichFormatParser()

    def aggregate_results(
        self,
        repository_outputs: Dict[str, str],
        limit: Optional[int] = DEFAULT_QUERY_LIMIT,
        repo_name_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """Aggregate rich query results from all repositories.

        Args:
            repository_outputs: Map of repo_path -> rich query output string
            limit: Maximum number of results to return (None or 0 = unlimited)

        Returns:
            Formatted rich output string with full metadata and repository context

        Examples:
            >>> repo_outputs = {
            ...     "/repo1": "📄 File: /repo1/auth.py:1-10 | ...",
            ...     "/repo2": "📄 File: /repo2/user.py:5-15 | ..."
            ... }
            >>> aggregator.aggregate_results(repo_outputs, limit=10)
            '📄 File: /repo1/auth.py:1-10 | ... (full rich format)'
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

        # Step 5: Format output in rich format
        return self._format_rich_results(all_results)

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

    def _format_rich_results(self, results: List[QueryResult]) -> str:
        """Format results for output in rich format with full metadata.

        Rich format matches real CIDX output:
            📄 File: <path>:<start>-<end> | 🏷️  Language: <lang> | 📊 Score: <score>
            📏 Size: <size> bytes | 🕒 Indexed: <timestamp> | 🌿 Branch: <branch> | 📦 Commit: <commit> | 🏗️  Project: <project>

            📖 Content (Lines <start>-<end>):
            ──────────────────────────────────────────────────
              <line_num>: <code>

            ================================================================================

        Args:
            results: List of QueryResult objects sorted by score

        Returns:
            Formatted rich output string
        """
        if not results:
            return ""

        output_lines = []

        # Add header
        output_lines.append(f"✅ Found {len(results)} results:")
        output_lines.append("=" * 80)
        output_lines.append("")

        for i, result in enumerate(results):
            # Format first line: File info, language, score
            first_line = (
                f"📄 File: {result.file_path}:{result.line_range[0]}-{result.line_range[1]} | "
                f"🏷️  Language: {result.language or 'unknown'} | "
                f"📊 Score: {result.score:.3f}"
            )
            output_lines.append(first_line)

            # Format second line: Size, timestamp, branch, commit, project
            second_line = (
                f"📏 Size: {result.size or 0} bytes | "
                f"🕒 Indexed: {result.indexed_timestamp or 'unknown'} | "
                f"🌿 Branch: {result.branch or 'unknown'} | "
                f"📦 Commit: {result.commit or 'unknown'} | "
                f"🏗️  Project: {result.project_name or 'unknown'}"
            )
            output_lines.append(second_line)

            # Add blank line
            output_lines.append("")

            # Add content header
            content_header = (
                f"📖 Content (Lines {result.line_range[0]}-{result.line_range[1]}):"
            )
            output_lines.append(content_header)
            output_lines.append("─" * 50)

            # Add code content (already formatted with line numbers)
            if result.content:
                output_lines.append(result.content)

            # Add separator between results (except last)
            output_lines.append("─" * 50)
            if i < len(results) - 1:
                output_lines.append("")
                output_lines.append("=" * 80)
                output_lines.append("")

        # Join with newlines
        return "\n".join(output_lines) + "\n"
