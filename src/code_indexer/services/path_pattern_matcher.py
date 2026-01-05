"""
Path pattern matcher for file path exclusions.

Provides glob-style pattern matching with cross-platform support:
- Wildcard patterns (*, **, ?)
- Character sequences ([seq], [!seq])
- Path normalization (separators, case sensitivity)
- Pattern caching for performance
- Gitignore-style matching via pathspec library
"""

import pathspec
from pathlib import PurePosixPath
from typing import List


class PathPatternMatcher:
    """
    Matches file paths against glob patterns with cross-platform support.

    This class provides efficient glob-style pattern matching for file paths,
    with automatic path normalization and pattern caching for performance.

    Features:
    - Cross-platform path separator normalization
    - Standard glob patterns (*, **, ?, [seq], [!seq])
    - Pattern compilation caching
    - Case sensitivity based on platform

    Examples:
        >>> matcher = PathPatternMatcher()
        >>> matcher.matches_pattern("src/tests/test.py", "*/tests/*")
        True
        >>> matcher.matches_pattern("src/module.py", "*/tests/*")
        False
        >>> matcher.matches_any_pattern("dist/app.min.js", ["*.min.js", "*/vendor/**"])
        True
    """

    def __init__(self):
        """Initialize the pattern matcher with empty cache."""
        self._pattern_cache = {}

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path separators and components for consistent matching.

        Converts all paths to forward slashes and resolves . and .. components.
        This ensures patterns work consistently across platforms.

        Args:
            path: Path string to normalize

        Returns:
            Normalized path with forward slashes

        Examples:
            >>> matcher = PathPatternMatcher()
            >>> matcher._normalize_path("src\\\\tests\\\\test.py")
            'src/tests/test.py'
            >>> matcher._normalize_path("src/./tests/../tests/test.py")
            'src/tests/test.py'
        """
        if not path:
            return ""

        # Convert to PurePosixPath for consistent forward slash handling
        # This works on all platforms and normalizes separators
        try:
            # Handle both Windows and Unix paths
            normalized = PurePosixPath(path.replace("\\", "/"))

            # Resolve . and .. components
            # Note: PurePosixPath.parts includes '/' as first element for absolute paths
            parts: List[str] = []
            is_absolute = str(normalized).startswith("/")

            for part in normalized.parts:
                # Skip the root '/' part (it's just a marker for absolute paths)
                if part == "/":
                    continue
                if part == "..":
                    if parts and parts[-1] != "..":
                        parts.pop()
                    else:
                        parts.append(part)
                elif part != "." and part:
                    parts.append(part)

            result = "/".join(parts)

            # Preserve leading slash for absolute paths
            if is_absolute and result:
                result = "/" + result
            elif is_absolute and not result:
                result = "/"

            return result
        except (ValueError, TypeError):
            # Fallback: just replace backslashes
            return path.replace("\\", "/")

    def matches_pattern(self, path: str, pattern: str) -> bool:
        """
        Check if a path matches a glob pattern using gitignore-style matching.

        This method uses pathspec library for consistent gitignore-style glob matching,
        which properly handles ** patterns as "this directory and all subdirectories"
        rather than requiring at least one subdirectory level.

        Args:
            path: File path to check
            pattern: Glob pattern to match against (gitignore-style)

        Returns:
            True if path matches pattern, False otherwise

        Raises:
            TypeError: If pattern is None
            ValueError: If pattern is invalid

        Examples:
            >>> matcher = PathPatternMatcher()
            >>> matcher.matches_pattern("src/tests/test.py", "*/tests/*")
            True
            >>> matcher.matches_pattern("src/module.py", "*/tests/*")
            False
            >>> matcher.matches_pattern("code/src/Main.java", "code/src/**/*.java")
            True
            >>> matcher.matches_pattern("code/src/util/Helper.java", "code/src/**/*.java")
            True
        """
        if pattern is None:
            raise TypeError("Pattern cannot be None")

        if not pattern or pattern.strip() == "":
            return False

        # Normalize both path and pattern
        normalized_path = self._normalize_path(path)
        normalized_pattern = self._normalize_path(pattern.strip())

        if not normalized_pattern:
            return False

        try:
            # Check if pattern is in cache
            cache_key = normalized_pattern
            if cache_key not in self._pattern_cache:
                # Create PathSpec object and cache it
                # Use "gitwildmatch" for gitignore-style glob matching
                # This properly handles ** patterns and other glob features
                spec = pathspec.PathSpec.from_lines("gitwildmatch", [normalized_pattern])
                self._pattern_cache[cache_key] = spec
            else:
                spec = self._pattern_cache[cache_key]

            # Use pathspec to match the path
            # pathspec.match_file() handles:
            # - ** as "this directory and all subdirectories"
            # - * as single-level wildcard
            # - ?, [seq], [!seq] patterns
            # - Proper path separator handling
            return bool(spec.match_file(normalized_path))

        except Exception as e:
            # Invalid pattern - treat as ValueError
            raise ValueError(f"Invalid glob pattern: {pattern}") from e

    def matches_any_pattern(self, path: str, patterns: List[str]) -> bool:
        """
        Check if a path matches any of the given patterns.

        Args:
            path: File path to check
            patterns: List of glob patterns to match against

        Returns:
            True if path matches at least one pattern, False otherwise

        Examples:
            >>> matcher = PathPatternMatcher()
            >>> patterns = ["*/tests/*", "*.min.js", "**/vendor/**"]
            >>> matcher.matches_any_pattern("src/tests/test.py", patterns)
            True
            >>> matcher.matches_any_pattern("src/module.py", patterns)
            False
        """
        if not patterns:
            return False

        for pattern in patterns:
            try:
                if self.matches_pattern(path, pattern):
                    return True
            except (TypeError, ValueError):
                # Skip invalid patterns
                continue

        return False
