"""
Filter conflict detection service for query filters.

This service detects contradictory or problematic filter combinations
and provides warnings to users before executing queries.

Design principles:
- Detect exact conflicts (include AND exclude same thing)
- Warn about potential issues (excluding too much)
- Provide clear, actionable messages
- Fast performance (<5ms)
"""

from typing import List, Optional
from dataclasses import dataclass


@dataclass
class FilterConflict:
    """Represents a detected filter conflict."""

    severity: str  # "error" or "warning"
    message: str
    affected_items: List[str]  # Languages, paths, etc. involved


class FilterConflictDetector:
    """
    Detects conflicts and issues in filter combinations.

    Detects:
    1. Direct conflicts (--language python --exclude-language python)
    2. Path overlaps (--path-filter X --exclude-path X)
    3. Over-exclusion warnings (excluding many languages)
    4. Empty result warnings (filters that would exclude everything)
    """

    # Threshold for warning about too many exclusions
    EXCESSIVE_EXCLUSION_THRESHOLD = 5

    def detect_conflicts(
        self,
        include_languages: Optional[List[str]] = None,
        exclude_languages: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        exclude_paths: Optional[List[str]] = None,
    ) -> List[FilterConflict]:
        """
        Detect conflicts in filter combinations.

        Args:
            include_languages: Languages to include (--language)
            exclude_languages: Languages to exclude (--exclude-language)
            include_paths: Paths to include (--path-filter)
            exclude_paths: Paths to exclude (--exclude-path)

        Returns:
            List of detected conflicts with severity and messages
        """
        conflicts = []

        # Normalize inputs
        include_languages = include_languages or []
        exclude_languages = exclude_languages or []
        include_paths = include_paths or []
        exclude_paths = exclude_paths or []

        # Detect language conflicts
        conflicts.extend(
            self._detect_language_conflicts(include_languages, exclude_languages)
        )

        # Detect path conflicts
        conflicts.extend(self._detect_path_conflicts(include_paths, exclude_paths))

        # Detect over-exclusion warnings
        conflicts.extend(
            self._detect_over_exclusion(include_languages, exclude_languages)
        )

        return conflicts

    def _detect_language_conflicts(
        self, include_languages: List[str], exclude_languages: List[str]
    ) -> List[FilterConflict]:
        """Detect conflicts between language inclusions and exclusions."""
        conflicts = []

        # Convert to sets for efficient comparison (case-insensitive)
        include_set = {lang.lower() for lang in include_languages}
        exclude_set = {lang.lower() for lang in exclude_languages}

        # Find overlaps
        overlaps = include_set & exclude_set

        if overlaps:
            for lang in overlaps:
                conflicts.append(
                    FilterConflict(
                        severity="error",
                        message=f"Language '{lang}' is both included and excluded. "
                        f"Exclusion will override inclusion, resulting in no {lang} files.",
                        affected_items=[lang],
                    )
                )

        return conflicts

    def _detect_path_conflicts(
        self, include_paths: List[str], exclude_paths: List[str]
    ) -> List[FilterConflict]:
        """Detect conflicts between path inclusions and exclusions."""
        conflicts = []

        # Check for exact matches
        include_set = set(include_paths)
        exclude_set = set(exclude_paths)

        exact_overlaps = include_set & exclude_set

        if exact_overlaps:
            for path in exact_overlaps:
                conflicts.append(
                    FilterConflict(
                        severity="error",
                        message=f"Path pattern '{path}' is both included and excluded. "
                        f"This will exclude all matching files.",
                        affected_items=[path],
                    )
                )

        # Check for potential parent-child overlaps (warning, not error)
        # This is not necessarily wrong, just potentially confusing
        for inc_path in include_paths:
            for exc_path in exclude_paths:
                if self._is_path_overlap(inc_path, exc_path) and inc_path != exc_path:
                    # This is actually a valid use case (narrowing results)
                    # Only warn if exclusion is not more specific
                    if not self._is_more_specific(exc_path, inc_path):
                        conflicts.append(
                            FilterConflict(
                                severity="warning",
                                message=f"Path inclusion '{inc_path}' may conflict with "
                                f"exclusion '{exc_path}'. Verify this produces expected results.",
                                affected_items=[inc_path, exc_path],
                            )
                        )

        return conflicts

    def _detect_over_exclusion(
        self, include_languages: List[str], exclude_languages: List[str]
    ) -> List[FilterConflict]:
        """Detect warnings about excluding too many languages."""
        conflicts = []

        # If no inclusions but many exclusions, warn
        if (
            not include_languages
            and len(exclude_languages) >= self.EXCESSIVE_EXCLUSION_THRESHOLD
        ):
            conflicts.append(
                FilterConflict(
                    severity="warning",
                    message=f"Excluding {len(exclude_languages)} languages without any "
                    f"inclusion filters may result in unexpected results. "
                    f"Consider using --language to specify what you want instead.",
                    affected_items=exclude_languages,
                )
            )

        return conflicts

    def _is_path_overlap(self, path1: str, path2: str) -> bool:
        """
        Check if two path patterns potentially overlap.

        This is a simple heuristic check, not exact pattern matching.
        """
        # Normalize paths
        p1 = path1.replace("\\", "/").strip("*")
        p2 = path2.replace("\\", "/").strip("*")

        # Check if one is a substring of the other
        return p1 in p2 or p2 in p1

    def _is_more_specific(self, path1: str, path2: str) -> bool:
        """
        Check if path1 is more specific than path2.

        More specific means it has more path components or is a subpath.
        """
        # Simple heuristic: more slashes = more specific
        # This works for common cases like */src/* vs */src/tests/*
        p1_clean = path1.replace("\\", "/").strip("*")
        p2_clean = path2.replace("\\", "/").strip("*")

        # path1 is more specific if it contains path2 and has more components
        if p2_clean in p1_clean:
            return p1_clean.count("/") > p2_clean.count("/")

        return False

    def format_conflicts_for_display(
        self, conflicts: List[FilterConflict]
    ) -> List[str]:
        """
        Format conflicts for user-friendly CLI display.

        Returns:
            List of formatted warning/error messages
        """
        messages = []

        errors = [c for c in conflicts if c.severity == "error"]
        warnings = [c for c in conflicts if c.severity == "warning"]

        if errors:
            messages.append("🚫 Filter Conflicts (Errors):")
            for conflict in errors:
                messages.append(f"  • {conflict.message}")

        if warnings:
            if errors:
                messages.append("")  # Blank line between errors and warnings
            messages.append("⚠️  Filter Warnings:")
            for conflict in warnings:
                messages.append(f"  • {conflict.message}")

        return messages
