"""
Filter builder for path exclusion conditions.

Constructs Filesystem-compatible filter conditions for path exclusions:
- must_not filter construction
- Filter combination and merging
- Filter validation
"""

from typing import Dict, List, Any


class PathFilterBuilder:
    """
    Builds Filesystem filter conditions for path exclusions.

    This class constructs filter dictionaries that work with both Filesystem
    and filesystem vector stores for path-based exclusions.

    Examples:
        >>> builder = PathFilterBuilder()
        >>> filters = builder.build_exclusion_filter(["*/tests/*", "*.min.js"])
        >>> filters
        {'must_not': [{'key': 'path', 'match': {'text': '*/tests/*'}}, ...]}
    """

    def _normalize_pattern(self, pattern: str) -> str:
        """
        Normalize path pattern for cross-platform compatibility.

        Converts backslashes to forward slashes for consistent pattern matching.

        Args:
            pattern: Glob pattern to normalize

        Returns:
            Normalized pattern with forward slashes
        """
        if not pattern:
            return ""

        # Convert backslashes to forward slashes
        return pattern.replace("\\", "/")

    def build_exclusion_filter(self, patterns: List[str]) -> Dict[str, Any]:
        """
        Build must_not filter conditions from path exclusion patterns.

        Args:
            patterns: List of glob patterns to exclude

        Returns:
            Filter dictionary with must_not conditions

        Examples:
            >>> builder = PathFilterBuilder()
            >>> builder.build_exclusion_filter(["*/tests/*"])
            {'must_not': [{'key': 'path', 'match': {'text': '*/tests/*'}}]}
        """
        if not patterns:
            return {}

        must_not_conditions = []

        for pattern in patterns:
            if not pattern or not pattern.strip():
                continue

            # Normalize pattern for cross-platform compatibility
            normalized_pattern = self._normalize_pattern(pattern.strip())

            # Create must_not condition for this pattern
            # Use "text" for glob pattern matching (not "value" for exact match)
            must_not_conditions.append(
                {
                    "key": "path",  # Use "path" to match actual payload key in storage
                    "match": {"text": normalized_pattern},
                }
            )

        if not must_not_conditions:
            return {}

        return {"must_not": must_not_conditions}

    def add_path_exclusions(
        self, base_filters: Dict[str, Any], patterns: List[str]
    ) -> Dict[str, Any]:
        """
        Add path exclusion patterns to existing filter conditions.

        Merges path exclusions with existing filter conditions, preserving
        both must and must_not conditions.

        Args:
            base_filters: Existing filter conditions
            patterns: Path exclusion patterns to add

        Returns:
            Combined filter dictionary

        Examples:
            >>> builder = PathFilterBuilder()
            >>> base = {'must': [{'key': 'language', 'match': {'value': 'python'}}]}
            >>> builder.add_path_exclusions(base, ["*/tests/*"])
            {'must': [...], 'must_not': [{'key': 'path', ...}]}
        """
        if not patterns:
            return base_filters

        # Build exclusion filters
        exclusion_filters = self.build_exclusion_filter(patterns)

        if not exclusion_filters:
            return base_filters

        # Merge with base filters
        result = base_filters.copy()

        # Add or extend must_not conditions
        if "must_not" in exclusion_filters:
            if "must_not" in result:
                # Extend existing must_not
                result["must_not"].extend(exclusion_filters["must_not"])
            else:
                # Add new must_not
                result["must_not"] = exclusion_filters["must_not"]

        return result

    def validate_filter_structure(self, filter_dict: Dict[str, Any]) -> bool:
        """
        Validate that a filter dictionary has correct structure.

        Args:
            filter_dict: Filter dictionary to validate

        Returns:
            True if structure is valid, False otherwise

        Examples:
            >>> builder = PathFilterBuilder()
            >>> valid = {'must': [{'key': 'language', 'match': {'value': 'python'}}]}
            >>> builder.validate_filter_structure(valid)
            True
            >>> invalid = {'invalid_key': []}
            >>> builder.validate_filter_structure(invalid)
            False
        """
        if not isinstance(filter_dict, dict):
            return False

        # Valid keys for Filesystem filters
        valid_keys = {"must", "must_not", "should"}

        # Check that all keys are valid
        for key in filter_dict.keys():
            if key not in valid_keys:
                return False

        # Validate structure of each condition type
        for key in ["must", "must_not", "should"]:
            if key in filter_dict:
                conditions = filter_dict[key]

                if not isinstance(conditions, list):
                    return False

                # Each condition should have key and match
                for condition in conditions:
                    if not isinstance(condition, dict):
                        return False

                    # Check for required fields
                    if "key" not in condition:
                        return False

                    # match or text should be present
                    if "match" not in condition and "text" not in condition:
                        return False

        return True
