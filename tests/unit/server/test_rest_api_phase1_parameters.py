"""
Unit tests for Phase 1 REST API parameters (Story #503).

Tests for:
- exclude_language parameter validation
- exclude_path parameter validation
- accuracy parameter validation and enum enforcement
- regex parameter validation and compatibility rules
"""

import pytest
from code_indexer.server.app import SemanticQueryRequest


class TestExcludeLanguageParameter:
    """Test exclude_language parameter."""

    def test_exclude_language_accepts_string(self):
        """Test exclude_language accepts string value."""
        request = SemanticQueryRequest(
            query_text="authentication", exclude_language="python"
        )
        assert request.exclude_language == "python"

    def test_exclude_language_optional_default_none(self):
        """Test exclude_language is optional and defaults to None."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.exclude_language is None


class TestExcludePathParameter:
    """Test exclude_path parameter."""

    def test_exclude_path_accepts_glob_pattern(self):
        """Test exclude_path accepts glob patterns."""
        request = SemanticQueryRequest(
            query_text="authentication", exclude_path="*/tests/*"
        )
        assert request.exclude_path == "*/tests/*"

    def test_exclude_path_optional_default_none(self):
        """Test exclude_path is optional and defaults to None."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.exclude_path is None


class TestAccuracyParameter:
    """Test accuracy parameter."""

    def test_accuracy_accepts_fast(self):
        """Test accuracy accepts 'fast' value."""
        request = SemanticQueryRequest(query_text="authentication", accuracy="fast")
        assert request.accuracy == "fast"

    def test_accuracy_accepts_balanced(self):
        """Test accuracy accepts 'balanced' value."""
        request = SemanticQueryRequest(query_text="authentication", accuracy="balanced")
        assert request.accuracy == "balanced"

    def test_accuracy_accepts_high(self):
        """Test accuracy accepts 'high' value."""
        request = SemanticQueryRequest(query_text="authentication", accuracy="high")
        assert request.accuracy == "high"

    def test_accuracy_defaults_to_balanced(self):
        """Test accuracy defaults to 'balanced'."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.accuracy == "balanced"

    def test_accuracy_rejects_invalid_value(self):
        """Test accuracy rejects invalid values."""
        with pytest.raises(ValueError):
            SemanticQueryRequest(
                query_text="authentication",
                accuracy="turbo",  # Invalid value
            )


class TestRegexParameter:
    """Test regex parameter."""

    def test_regex_accepts_true(self):
        """Test regex accepts True value."""
        request = SemanticQueryRequest(
            query_text="def.*auth", search_mode="fts", regex=True
        )
        assert request.regex is True

    def test_regex_defaults_to_false(self):
        """Test regex defaults to False."""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.regex is False

    def test_regex_requires_fts_mode(self):
        """Test regex=true requires search_mode='fts' or 'hybrid'."""
        with pytest.raises(ValueError, match="requires search_mode"):
            SemanticQueryRequest(
                query_text="def.*auth",
                search_mode="semantic",  # Invalid for regex
                regex=True,
            )

    def test_regex_works_with_fts_mode(self):
        """Test regex=true works with search_mode='fts'."""
        request = SemanticQueryRequest(
            query_text="def.*auth", search_mode="fts", regex=True
        )
        assert request.regex is True
        assert request.search_mode == "fts"

    def test_regex_works_with_hybrid_mode(self):
        """Test regex=true works with search_mode='hybrid'."""
        request = SemanticQueryRequest(
            query_text="def.*auth", search_mode="hybrid", regex=True
        )
        assert request.regex is True
        assert request.search_mode == "hybrid"

    def test_regex_incompatible_with_fuzzy(self):
        """Test regex=true is incompatible with fuzzy=true."""
        with pytest.raises(ValueError, match="incompatible with fuzzy"):
            SemanticQueryRequest(
                query_text="def.*auth",
                search_mode="fts",
                regex=True,
                fuzzy=True,  # Incompatible
            )


class TestParameterCombinations:
    """Test combinations of Phase 1 parameters."""

    def test_all_phase1_parameters_together(self):
        """Test all Phase 1 parameters can be used together."""
        request = SemanticQueryRequest(
            query_text="authentication",
            exclude_language="python",
            exclude_path="*/tests/*",
            accuracy="high",
            search_mode="semantic",  # regex=False (default)
        )
        assert request.exclude_language == "python"
        assert request.exclude_path == "*/tests/*"
        assert request.accuracy == "high"
        assert request.regex is False

    def test_exclusion_filters_with_inclusion_filters(self):
        """Test exclusion filters work alongside inclusion filters."""
        request = SemanticQueryRequest(
            query_text="authentication",
            language="python",
            path_filter="*/src/*",
            exclude_language="python",  # Can coexist
            exclude_path="*/tests/*",  # Can coexist
        )
        assert request.language == "python"
        assert request.path_filter == "*/src/*"
        assert request.exclude_language == "python"
        assert request.exclude_path == "*/tests/*"
