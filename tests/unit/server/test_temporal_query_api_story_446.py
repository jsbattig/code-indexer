"""
Unit tests for Temporal Query API parameters (Story #446).

Tests the REST API integration of temporal parameters:
- time_range: Time range filter (YYYY-MM-DD..YYYY-MM-DD)
- at_commit: Query at specific commit
- include_removed: Include deleted files
- show_evolution: Show code evolution timeline
- evolution_limit: Limit evolution entries

TDD Cycle:
1. Write failing tests for each acceptance criterion
2. Implement minimal code to pass tests
3. Refactor for quality
"""

import pytest
from pydantic import ValidationError

try:
    from code_indexer.server.app import SemanticQueryRequest
except ImportError:
    pytest.skip("Server app not available", allow_module_level=True)


class TestTemporalParametersStory446:
    """Test temporal parameters added in Story #446 for REST API."""

    def test_time_range_parameter_exists(self):
        """AC1: Test time_range parameter exists on SemanticQueryRequest"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            time_range="2024-01-01..2024-12-31"
        )

        # Assert
        assert hasattr(request, 'time_range')
        assert request.time_range == "2024-01-01..2024-12-31"

    def test_time_range_parameter_optional(self):
        """AC1: Test time_range is optional (defaults to None)"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.time_range is None

    def test_at_commit_parameter_exists(self):
        """AC2: Test at_commit parameter exists on SemanticQueryRequest"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            at_commit="abc123def456"
        )

        # Assert
        assert hasattr(request, 'at_commit')
        assert request.at_commit == "abc123def456"

    def test_at_commit_parameter_optional(self):
        """AC2: Test at_commit is optional (defaults to None)"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.at_commit is None

    def test_include_removed_parameter_exists(self):
        """AC3: Test include_removed parameter exists on SemanticQueryRequest"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            include_removed=True
        )

        # Assert
        assert hasattr(request, 'include_removed')
        assert request.include_removed is True

    def test_include_removed_parameter_defaults_false(self):
        """AC3: Test include_removed defaults to False"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.include_removed is False

    def test_show_evolution_parameter_exists(self):
        """AC4: Test show_evolution parameter exists on SemanticQueryRequest"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            show_evolution=True
        )

        # Assert
        assert hasattr(request, 'show_evolution')
        assert request.show_evolution is True

    def test_show_evolution_parameter_defaults_false(self):
        """AC4: Test show_evolution defaults to False"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.show_evolution is False

    def test_evolution_limit_parameter_exists(self):
        """AC5: Test evolution_limit parameter exists on SemanticQueryRequest"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            evolution_limit=10
        )

        # Assert
        assert hasattr(request, 'evolution_limit')
        assert request.evolution_limit == 10

    def test_evolution_limit_parameter_optional(self):
        """AC5: Test evolution_limit is optional (defaults to None)"""
        # Arrange & Act
        request = SemanticQueryRequest(query_text="test")

        # Assert
        assert request.evolution_limit is None

    def test_evolution_limit_validation_positive(self):
        """AC5: Test evolution_limit must be >= 1"""
        # Arrange, Act & Assert - valid value
        request = SemanticQueryRequest(
            query_text="test",
            evolution_limit=1
        )
        assert request.evolution_limit == 1

    def test_evolution_limit_validation_rejects_zero(self):
        """AC5: Test evolution_limit rejects 0"""
        # Arrange, Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                query_text="test",
                evolution_limit=0
            )
        error_msg = str(exc_info.value)
        assert "evolution_limit" in error_msg.lower()

    def test_evolution_limit_validation_rejects_negative(self):
        """AC5: Test evolution_limit rejects negative values"""
        # Arrange, Act & Assert
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                query_text="test",
                evolution_limit=-5
            )
        error_msg = str(exc_info.value)
        assert "evolution_limit" in error_msg.lower()

    def test_all_temporal_parameters_combined(self):
        """AC6: Test all 5 temporal parameters can be used together"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="authentication logic",
            time_range="2024-01-01..2024-12-31",
            at_commit="main",
            include_removed=True,
            show_evolution=True,
            evolution_limit=5
        )

        # Assert
        assert request.time_range == "2024-01-01..2024-12-31"
        assert request.at_commit == "main"
        assert request.include_removed is True
        assert request.show_evolution is True
        assert request.evolution_limit == 5

    def test_temporal_parameters_backward_compatible(self):
        """AC7: Test backward compatibility - existing queries work without temporal params"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test query",
            limit=10,
            min_score=0.7,
            file_extensions=[".py", ".js"]
        )

        # Assert - temporal parameters use defaults
        assert request.time_range is None
        assert request.at_commit is None
        assert request.include_removed is False
        assert request.show_evolution is False
        assert request.evolution_limit is None

    def test_temporal_parameters_with_fts_mode(self):
        """AC8: Test temporal parameters work with FTS search mode"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test",
            search_mode="fts",
            time_range="2024-01-01..2024-12-31"
        )

        # Assert
        assert request.search_mode == "fts"
        assert request.time_range == "2024-01-01..2024-12-31"

    def test_temporal_parameters_with_hybrid_mode(self):
        """AC8: Test temporal parameters work with hybrid search mode"""
        # Arrange & Act
        request = SemanticQueryRequest(
            query_text="test",
            search_mode="hybrid",
            show_evolution=True,
            evolution_limit=3
        )

        # Assert
        assert request.search_mode == "hybrid"
        assert request.show_evolution is True
        assert request.evolution_limit == 3


class TestTemporalParameterDescriptions:
    """Test that temporal parameters have proper descriptions for API docs."""

    def test_time_range_has_description(self):
        """Test time_range parameter has description"""
        from code_indexer.server.app import SemanticQueryRequest
        field = SemanticQueryRequest.model_fields.get('time_range')
        assert field is not None
        assert field.description is not None
        assert 'time range' in field.description.lower()

    def test_at_commit_has_description(self):
        """Test at_commit parameter has description"""
        from code_indexer.server.app import SemanticQueryRequest
        field = SemanticQueryRequest.model_fields.get('at_commit')
        assert field is not None
        assert field.description is not None
        assert 'commit' in field.description.lower()

    def test_include_removed_has_description(self):
        """Test include_removed parameter has description"""
        from code_indexer.server.app import SemanticQueryRequest
        field = SemanticQueryRequest.model_fields.get('include_removed')
        assert field is not None
        assert field.description is not None
        assert 'removed' in field.description.lower()

    def test_show_evolution_has_description(self):
        """Test show_evolution parameter has description"""
        from code_indexer.server.app import SemanticQueryRequest
        field = SemanticQueryRequest.model_fields.get('show_evolution')
        assert field is not None
        assert field.description is not None
        assert 'evolution' in field.description.lower()

    def test_evolution_limit_has_description(self):
        """Test evolution_limit parameter has description"""
        from code_indexer.server.app import SemanticQueryRequest
        field = SemanticQueryRequest.model_fields.get('evolution_limit')
        assert field is not None
        assert field.description is not None
        assert 'evolution' in field.description.lower() or 'limit' in field.description.lower()
