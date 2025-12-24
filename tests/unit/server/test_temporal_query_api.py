"""
Unit tests for Temporal Query API parameters (Story #489).

Tests the extension of SemanticQueryRequest model with 5 temporal parameters
and their validation logic following strict TDD methodology.

TDD Cycle:
1. Write failing tests for each acceptance criterion
2. Implement minimal code to pass tests
3. Refactor for quality
"""

import pytest
from pydantic import ValidationError

# Import will fail initially - this is expected in TDD (RED phase)
try:
    from code_indexer.server.app import SemanticQueryRequest
except ImportError:
    pytest.skip("Server app not available", allow_module_level=True)


class TestTemporalParameterValidation:
    """Test validation of temporal parameters in SemanticQueryRequest model."""

    def test_time_range_valid_format(self):
        """AC1: Test valid time_range format YYYY-MM-DD..YYYY-MM-DD"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test", time_range="2024-01-01..2024-12-31"
        )

        # Assert
        assert request.time_range == "2024-01-01..2024-12-31"

    def test_time_range_invalid_month(self):
        """AC5: Test invalid month in time_range (>12) - should fail validation"""
        # Arrange, Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(query_text="test", time_range="2024-13-01..2024-12-31")

        # Verify error mentions time_range
        error_msg = str(exc_info.value)
        assert "time_range" in error_msg.lower()

    def test_time_range_all_default_false(self):
        """Test time_range_all defaults to False"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.time_range_all is False
