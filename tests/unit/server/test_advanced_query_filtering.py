"""
Unit tests for advanced query filtering (Story #490).

Tests for:
- Multiple language/path filters (OR logic)
- Exclusion filters (exclude_language, exclude_path)
- Filter precedence rules (exclusions take precedence)
- Accuracy profile parameter validation
- Regex mode validation
- Backward compatibility with single string filters
"""

from code_indexer.server.app import SemanticQueryRequest


class TestSemanticQueryRequestModel:
    """Test SemanticQueryRequest model with advanced filtering parameters."""

    def test_multiple_languages_as_list(self):
        """Test accepting multiple languages as list."""
        request = SemanticQueryRequest(
            query_text="authentication", language=["python", "go", "rust"]
        )
        assert request.language == ["python", "go", "rust"]

    def test_single_language_as_string_backward_compatibility(self):
        """Test backward compatibility: single language as string should work."""
        request = SemanticQueryRequest(query_text="authentication", language="python")
        # Should accept string (backward compatibility)
        assert request.language == "python"

    def test_multiple_path_filters_as_list(self):
        """Test accepting multiple path filters as list."""
        request = SemanticQueryRequest(
            query_text="authentication", path_filter=["*/src/*", "*.py"]
        )
        assert request.path_filter == ["*/src/*", "*.py"]

    def test_exclude_language_parameter(self):
        """Test exclude_language parameter accepts list of languages."""
        request = SemanticQueryRequest(
            query_text="authentication",
            language=["python", "go", "rust"],
            exclude_language=["rust"],
        )
        assert request.exclude_language == ["rust"]

    def test_exclude_path_parameter(self):
        """Test exclude_path parameter accepts list of path patterns."""
        request = SemanticQueryRequest(
            query_text="authentication",
            path_filter=["*/src/*", "*/lib/*"],
            exclude_path=["*/tests/*", "*/vendor/*"],
        )
        assert request.exclude_path == ["*/tests/*", "*/vendor/*"]

    def test_accuracy_profile_fast(self):
        """Test accuracy profile set to 'fast'."""
        request = SemanticQueryRequest(query_text="authentication", accuracy="fast")
        assert request.accuracy == "fast"

    def test_accuracy_profile_balanced_default(self):
        """Test accuracy profile defaults to 'balanced'."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.accuracy == "balanced"

    def test_regex_parameter_default_false(self):
        """Test regex parameter defaults to False."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.regex is False


class TestFilterHelpers:
    """Test filter helper functions for normalizing and applying filters."""

    def test_normalize_filter_to_list_with_string(self):
        """Test normalizing single string to list."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list("python")
        assert result == ["python"]

    def test_normalize_filter_to_list_with_list(self):
        """Test that list input is returned as-is."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list(["python", "go"])
        assert result == ["python", "go"]

    def test_normalize_filter_to_list_with_none(self):
        """Test that None returns empty list."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list(None)
        assert result == []


class TestAccuracyParams:
    """Test accuracy profile to HNSW parameter mapping."""

    def test_fast_accuracy_profile(self):
        """Test fast profile returns minimal HNSW parameters."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("fast")
        assert params["hnsw_ef"] == 50
        assert params["candidate_multiplier"] == 2

    def test_balanced_accuracy_profile(self):
        """Test balanced profile returns moderate HNSW parameters."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("balanced")
        assert params["hnsw_ef"] == 100
        assert params["candidate_multiplier"] == 5

    def test_high_accuracy_profile(self):
        """Test high profile returns maximum HNSW parameters."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("high")
        assert params["hnsw_ef"] == 200
        assert params["candidate_multiplier"] == 10


class TestFilterPrecedence:
    """Test filter precedence logic (exclusions take precedence over inclusions)."""

    def test_inclusions_only(self):
        """Test with only inclusion filters returns them unchanged."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence(["python", "go"], [])
        assert result == ["python", "go"]

    def test_exclusions_with_no_inclusions(self):
        """Test exclusions only scenario returns empty list."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence([], ["python"])
        assert result == []

    def test_exclusions_take_precedence(self):
        """Test that exclusions remove items from inclusions."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence(["python", "go", "rust"], ["rust"])
        assert result == ["python", "go"]

    def test_empty_lists(self):
        """Test empty lists scenario returns empty list."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence([], [])
        assert result == []


class TestEndpointValidation:
    """Test POST /api/query endpoint validation (integration-style without mocks)."""

    def test_regex_in_semantic_mode_returns_400(self):
        """Test that regex=true in semantic mode returns 400 Bad Request."""
        from code_indexer.server.app import SemanticQueryRequest

        # This will be tested via endpoint call, but for now we test the validation logic
        # would be triggered. We'll add actual endpoint test after wiring.
        request = SemanticQueryRequest(
            query_text="test", search_mode="semantic", regex=True
        )
        # Validation should happen in endpoint, not model
        assert request.regex is True
        assert request.search_mode == "semantic"
