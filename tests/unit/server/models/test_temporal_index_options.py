"""
Unit tests for TemporalIndexOptions model.

Tests validation rules for temporal indexing parameters used in golden repo registration.
"""

import pytest
from pydantic import ValidationError
from code_indexer.server.models.api_models import TemporalIndexOptions


class TestTemporalIndexOptionsValidation:
    """Test TemporalIndexOptions model validation."""

    def test_default_values(self):
        """Test that TemporalIndexOptions has correct defaults."""
        options = TemporalIndexOptions()

        assert options.max_commits is None
        assert options.since_date is None
        assert options.diff_context == 5  # Default: 5 lines

    def test_diff_context_below_minimum_fails(self):
        """Test that diff_context < 0 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TemporalIndexOptions(diff_context=-1)

        assert "diff_context" in str(exc_info.value)

    def test_diff_context_above_maximum_fails(self):
        """Test that diff_context > 50 is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            TemporalIndexOptions(diff_context=51)

        assert "diff_context" in str(exc_info.value)

    def test_max_commits_must_be_positive(self):
        """Test that max_commits must be positive integer."""
        # Valid: positive integer
        options = TemporalIndexOptions(max_commits=100)
        assert options.max_commits == 100

        # Invalid: zero
        with pytest.raises(ValidationError):
            TemporalIndexOptions(max_commits=0)

        # Invalid: negative
        with pytest.raises(ValidationError):
            TemporalIndexOptions(max_commits=-10)

    def test_since_date_invalid_format_fails(self):
        """Test that since_date rejects invalid date formats."""
        # Invalid format: MM/DD/YYYY
        with pytest.raises(ValidationError):
            TemporalIndexOptions(since_date="01/01/2024")

    def test_field_descriptions_exist(self):
        """Test that model has proper field descriptions."""
        schema = TemporalIndexOptions.model_json_schema()

        assert "properties" in schema
        assert "max_commits" in schema["properties"]
        assert "description" in schema["properties"]["max_commits"]

        assert "since_date" in schema["properties"]
        assert "description" in schema["properties"]["since_date"]

        assert "diff_context" in schema["properties"]
        assert "description" in schema["properties"]["diff_context"]
        assert (
            "context lines"
            in schema["properties"]["diff_context"]["description"].lower()
        )
