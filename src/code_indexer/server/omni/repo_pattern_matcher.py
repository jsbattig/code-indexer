"""
Repository pattern matching for omni-search.

Filters repository aliases by wildcard patterns and regex.
"""

import re
import pathspec
from typing import List


class RepoPatternMatcher:
    """Filters repository aliases by patterns (wildcards and regex)."""

    def __init__(self, patterns: List[str], metacharacters: str = "*?[]^$+|"):
        """
        Initialize pattern matcher.

        Args:
            patterns: List of patterns (wildcards or regex)
            metacharacters: Characters that indicate pattern matching
        """
        self.patterns = patterns
        self.metacharacters = metacharacters

    def is_pattern(self, text: str) -> bool:
        """
        Check if text contains pattern metacharacters.

        Args:
            text: Text to check

        Returns:
            True if text contains metacharacters, False otherwise
        """
        return any(char in text for char in self.metacharacters)

    def filter_repos(self, repos: List[str]) -> List[str]:
        """
        Filter repositories by patterns.

        Args:
            repos: List of repository aliases

        Returns:
            List of repositories matching any pattern (preserves input order)
        """
        if not self.patterns:
            return []

        matched = set()

        for pattern in self.patterns:
            if self.is_pattern(pattern):
                # Detect if pattern is regex (has anchors or complex operators)
                is_regex = any(op in pattern for op in ["^", "$", "+", "|"])

                if is_regex:
                    # Use regex for advanced patterns
                    try:
                        regex = re.compile(pattern)
                        for repo in repos:
                            if regex.search(repo):
                                matched.add(repo)
                    except Exception:
                        pass
                else:
                    # Use pathspec for wildcard patterns (*, ?, [abc], **)
                    # This correctly handles ** as "zero or more directories"
                    try:
                        spec = pathspec.PathSpec.from_lines("gitwildmatch", [pattern])
                        for repo in repos:
                            if spec.match_file(repo):
                                matched.add(repo)
                    except Exception:
                        pass
            else:
                # Exact match
                if pattern in repos:
                    matched.add(pattern)

        # Preserve input order by filtering original repos list
        return [repo for repo in repos if repo in matched]
