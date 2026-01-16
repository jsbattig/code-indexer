"""Unit tests for TemporalConfig schema (Story #443 - AC1, AC7).

Tests the configuration schema for diff context lines with validation and defaults.
"""

import pytest
from pydantic import ValidationError

from src.code_indexer.config import Config, TemporalConfig


class TestTemporalConfigSchema:
    """Test TemporalConfig schema and validation."""

    def test_default_diff_context_is_5_lines(self):
        """AC1: Default temporal indexing uses 5 lines of context (U5)."""
        config = Config()

        # Should have temporal config with default diff_context_lines=5
        assert hasattr(config, "temporal")
        assert config.temporal is not None
        assert config.temporal.diff_context_lines == 5

    def test_diff_context_rejects_negative_values(self):
        """AC7: Validate range (0-50) and reject invalid values."""
        with pytest.raises(ValidationError, match="greater than or equal to 0"):
            # Try creating config with negative diff_context
            TemporalConfig(diff_context_lines=-1)

    def test_diff_context_rejects_values_above_50(self):
        """AC7: Validate range (0-50) and reject values above maximum."""
        with pytest.raises(ValidationError, match="less than or equal to 50"):
            TemporalConfig(diff_context_lines=51)

    def test_diff_context_accepts_valid_boundaries(self):
        """AC2, AC3: Support diff_context 0 (minimal) and 50 (maximum)."""
        # Test minimum (0) - minimal storage
        config_min = TemporalConfig(diff_context_lines=0)
        assert config_min.diff_context_lines == 0

        # Test maximum (50)
        config_max = TemporalConfig(diff_context_lines=50)
        assert config_max.diff_context_lines == 50
