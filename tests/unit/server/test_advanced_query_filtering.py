"""
Unit tests for advanced query filtering (Story #490).

Tests for:
- Multiple language/path filters (OR logic)
- Exclusion filters (exclude_language, exclude_path)
- Filter precedence rules (exclusions take precedence)
- Accuracy profile parameter validation
- Regex mode validation
- Backward compatibility with single string filters

NOTE: Most tests in this file are for PHASE 2 (Story #490) which implements
list-based filters. These tests are marked with @pytest.mark.skip until Phase 2
is implemented. Phase 1 (Story #503) only implements single string values.
"""

import pytest
from code_indexer.server.app import SemanticQueryRequest


class TestSemanticQueryRequestModel:
    """Test SemanticQueryRequest model with advanced filtering parameters."""

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): list-based language filters not yet implemented"
    )
    def test_multiple_languages_as_list(self):
        """Test accepting multiple languages as list (PHASE 2)."""
        request = SemanticQueryRequest(
            query_text="authentication", language=["python", "go", "rust"]
        )
        assert request.language == ["python", "go", "rust"]

    def test_single_language_as_string_backward_compatibility(self):
        """Test backward compatibility: single language as string should work."""
        request = SemanticQueryRequest(query_text="authentication", language="python")
        # Should accept string (backward compatibility)
        assert request.language == "python"

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): list-based path filters not yet implemented"
    )
    def test_multiple_path_filters_as_list(self):
        """Test accepting multiple path filters as list (PHASE 2)."""
        request = SemanticQueryRequest(
            query_text="authentication", path_filter=["*/src/*", "*.py"]
        )
        assert request.path_filter == ["*/src/*", "*.py"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): list-based exclude_language not yet implemented"
    )
    def test_exclude_language_parameter(self):
        """Test exclude_language parameter accepts list of languages (PHASE 2)."""
        request = SemanticQueryRequest(
            query_text="authentication",
            language=["python", "go", "rust"],
            exclude_language=["rust"],
        )
        assert request.exclude_language == ["rust"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): list-based exclude_path not yet implemented"
    )
    def test_exclude_path_parameter(self):
        """Test exclude_path parameter accepts list of path patterns (PHASE 2)."""
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
    """Test filter helper functions for normalizing and applying filters (PHASE 2)."""

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): normalize_filter_to_list() not yet implemented"
    )
    def test_normalize_filter_to_list_with_string(self):
        """Test normalizing single string to list (PHASE 2)."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list("python")
        assert result == ["python"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): normalize_filter_to_list() not yet implemented"
    )
    def test_normalize_filter_to_list_with_list(self):
        """Test that list input is returned as-is (PHASE 2)."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list(["python", "go"])
        assert result == ["python", "go"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): normalize_filter_to_list() not yet implemented"
    )
    def test_normalize_filter_to_list_with_none(self):
        """Test that None returns empty list (PHASE 2)."""
        from code_indexer.server.app import normalize_filter_to_list

        result = normalize_filter_to_list(None)
        assert result == []


class TestAccuracyParams:
    """Test accuracy profile to HNSW parameter mapping (PHASE 2)."""

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): get_accuracy_params() not yet implemented"
    )
    def test_fast_accuracy_profile(self):
        """Test fast profile returns minimal HNSW parameters (PHASE 2)."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("fast")
        assert params["hnsw_ef"] == 50
        assert params["candidate_multiplier"] == 2

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): get_accuracy_params() not yet implemented"
    )
    def test_balanced_accuracy_profile(self):
        """Test balanced profile returns moderate HNSW parameters (PHASE 2)."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("balanced")
        assert params["hnsw_ef"] == 100
        assert params["candidate_multiplier"] == 5

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): get_accuracy_params() not yet implemented"
    )
    def test_high_accuracy_profile(self):
        """Test high profile returns maximum HNSW parameters (PHASE 2)."""
        from code_indexer.server.app import get_accuracy_params

        params = get_accuracy_params("high")
        assert params["hnsw_ef"] == 200
        assert params["candidate_multiplier"] == 10


class TestFilterPrecedence:
    """Test filter precedence logic (exclusions take precedence over inclusions) (PHASE 2)."""

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): apply_filter_precedence() not yet implemented"
    )
    def test_inclusions_only(self):
        """Test with only inclusion filters returns them unchanged (PHASE 2)."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence(["python", "go"], [])
        assert result == ["python", "go"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): apply_filter_precedence() not yet implemented"
    )
    def test_exclusions_with_no_inclusions(self):
        """Test exclusions only scenario returns empty list (PHASE 2)."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence([], ["python"])
        assert result == []

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): apply_filter_precedence() not yet implemented"
    )
    def test_exclusions_take_precedence(self):
        """Test that exclusions remove items from inclusions (PHASE 2)."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence(["python", "go", "rust"], ["rust"])
        assert result == ["python", "go"]

    @pytest.mark.skip(
        reason="Phase 2 (Story #490): apply_filter_precedence() not yet implemented"
    )
    def test_empty_lists(self):
        """Test empty lists scenario returns empty list (PHASE 2)."""
        from code_indexer.server.app import apply_filter_precedence

        result = apply_filter_precedence([], [])
        assert result == []


class TestEndpointValidation:
    """Test POST /api/query endpoint validation (integration-style without mocks)."""

    @pytest.mark.skip(
        reason="Phase 1 (Story #503): Validation moved to model validator, this test is obsolete"
    )
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
