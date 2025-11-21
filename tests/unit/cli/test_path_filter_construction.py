"""
Test-driven development for filter construction with path exclusions.

Tests the construction of Filesystem filter conditions for path exclusions:
- Single exclusion pattern
- Multiple exclusion patterns
- Combining with must conditions
- Filter structure validation
- Integration with existing filters
"""


class TestFilterStructureConstruction:
    """Test construction of filter structures for path exclusions."""

    def test_single_path_exclusion_creates_must_not_filter(self):
        """Test that single path exclusion creates correct must_not filter."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        filter_conditions = builder.build_exclusion_filter(["*/tests/*"])

        # Should create must_not structure
        # Uses 'text' for glob pattern matching (not 'value' for exact match)
        assert "must_not" in filter_conditions
        assert len(filter_conditions["must_not"]) == 1
        assert filter_conditions["must_not"][0] == {
            "key": "path",  # Changed from "file_path" to "path" (Bug Fix #5)
            "match": {"text": "*/tests/*"},
        }

    def test_multiple_path_exclusions_create_multiple_must_not_filters(self):
        """Test that multiple path exclusions create multiple must_not filters."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        patterns = ["*/tests/*", "*.min.js", "**/vendor/**"]
        filter_conditions = builder.build_exclusion_filter(patterns)

        # Should create must_not array with all patterns
        assert "must_not" in filter_conditions
        assert len(filter_conditions["must_not"]) == 3

        # Verify each pattern is in must_not
        # Uses 'text' for glob pattern matching
        must_not_values = [f["match"]["text"] for f in filter_conditions["must_not"]]
        assert "*/tests/*" in must_not_values
        assert "*.min.js" in must_not_values
        assert "**/vendor/**" in must_not_values

    def test_empty_exclusion_list_creates_empty_filter(self):
        """Test that empty exclusion list creates no filters."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        filter_conditions = builder.build_exclusion_filter([])

        # Should be empty dict or have empty must_not
        assert filter_conditions == {} or filter_conditions.get("must_not", []) == []

    def test_path_separator_normalization_in_filters(self):
        """Test that path separators are normalized in filter construction."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        # Pattern with backslashes should be normalized to forward slashes
        filter_conditions = builder.build_exclusion_filter(["*\\tests\\*"])

        # Should normalize to forward slashes
        # Uses 'text' for glob pattern matching
        assert filter_conditions["must_not"][0]["match"]["text"] == "*/tests/*"


class TestFilterCombination:
    """Test combining path exclusion filters with other filter types."""

    def test_combine_path_exclusion_with_language_filter(self):
        """Test that path exclusions combine correctly with language filters."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        # Start with language filter (must condition)
        base_filters = {"must": [{"key": "language", "match": {"value": "python"}}]}

        # Add path exclusion
        path_exclusions = ["*/tests/*"]
        combined_filters = builder.add_path_exclusions(base_filters, path_exclusions)

        # Should have both must and must_not
        assert "must" in combined_filters
        assert "must_not" in combined_filters
        assert len(combined_filters["must"]) == 1
        assert len(combined_filters["must_not"]) == 1

    def test_combine_path_exclusion_with_existing_must_not(self):
        """Test that path exclusions extend existing must_not conditions."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        # Start with existing must_not (e.g., language exclusion)
        base_filters = {
            "must_not": [{"key": "language", "match": {"value": "javascript"}}]
        }

        # Add path exclusion
        path_exclusions = ["*/tests/*"]
        combined_filters = builder.add_path_exclusions(base_filters, path_exclusions)

        # Should have both language exclusion and path exclusion
        assert "must_not" in combined_filters
        assert len(combined_filters["must_not"]) == 2

        # Verify both conditions exist
        must_not_keys = [f["key"] for f in combined_filters["must_not"]]
        assert "language" in must_not_keys
        assert (
            "path" in must_not_keys
        )  # Changed from "file_path" to "path" (Bug Fix #5)

    def test_combine_with_complex_existing_filters(self):
        """Test combining path exclusions with complex existing filters."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        # Complex existing filters
        base_filters = {
            "must": [
                {"key": "language", "match": {"value": "python"}},
                {"key": "git_available", "match": {"value": True}},
            ],
            "must_not": [{"key": "language", "match": {"value": "javascript"}}],
        }

        # Add path exclusions
        path_exclusions = ["*/tests/*", "*.min.js"]
        combined_filters = builder.add_path_exclusions(base_filters, path_exclusions)

        # Should preserve must conditions and extend must_not
        assert len(combined_filters["must"]) == 2
        assert len(combined_filters["must_not"]) == 3


class TestFilterValidation:
    """Test validation of filter structures."""

    def test_validate_filter_structure_valid(self):
        """Test validation accepts valid filter structures."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        valid_filter = {
            "must": [{"key": "language", "match": {"value": "python"}}],
            "must_not": [{"key": "file_path", "match": {"text": "*/tests/*"}}],
        }

        # Should not raise exception
        assert builder.validate_filter_structure(valid_filter) is True

    def test_validate_filter_structure_invalid_key(self):
        """Test validation rejects invalid filter keys."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        invalid_filter = {
            "invalid_key": [{"key": "language", "match": {"value": "python"}}]
        }

        # Should raise exception or return False
        assert builder.validate_filter_structure(invalid_filter) is False

    def test_validate_filter_structure_malformed_condition(self):
        """Test validation rejects malformed filter conditions."""
        from code_indexer.services.path_filter_builder import PathFilterBuilder

        builder = PathFilterBuilder()

        malformed_filter = {
            "must_not": [{"wrong_structure": "bad_value"}]  # Missing key/match
        }

        # Should raise exception or return False
        assert builder.validate_filter_structure(malformed_filter) is False
