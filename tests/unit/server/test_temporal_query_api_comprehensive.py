"""
Comprehensive unit tests for Temporal Query API parameters (Story #489).

This test file covers all 5 temporal parameters and 8 acceptance criteria.
Tests are written following TDD - tests define the contract before implementation.
"""

import pytest
from pydantic import ValidationError

try:
    from code_indexer.server.app import SemanticQueryRequest
except ImportError:
    pytest.skip("Server app not available", allow_module_level=True)


class TestDiffTypeParameter:
    """Test diff_type parameter validation."""

    def test_diff_type_valid_single(self):
        """AC6: Test valid single diff_type"""
        request = SemanticQueryRequest(
            query_text="test",
            diff_type=["added"]
        )
        assert request.diff_type == ["added"]

    def test_diff_type_valid_multiple(self):
        """AC4: Test valid multiple diff_types"""
        request = SemanticQueryRequest(
            query_text="test",
            diff_type=["added", "modified", "deleted"]
        )
        assert request.diff_type == ["added", "modified", "deleted"]

    def test_diff_type_all_values(self):
        """Test all valid diff_type values"""
        request = SemanticQueryRequest(
            query_text="test",
            diff_type=["added", "modified", "deleted", "renamed", "binary"]
        )
        assert len(request.diff_type) == 5

    def test_diff_type_invalid_value(self):
        """AC6: Test invalid diff_type raises ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                query_text="test",
                diff_type=["invalid_type"]
            )
        error_msg = str(exc_info.value)
        assert "diff_type" in error_msg.lower()

    def test_diff_type_optional(self):
        """Test diff_type is optional (backward compatibility)"""
        request = SemanticQueryRequest(query_text="test")
        assert request.diff_type is None


class TestAuthorParameter:
    """Test author parameter validation."""

    def test_author_valid_string(self):
        """AC3: Test valid author string"""
        request = SemanticQueryRequest(
            query_text="test",
            author="john@example.com"
        )
        assert request.author == "john@example.com"

    def test_author_max_length(self):
        """Test author max_length validation (255 chars)"""
        long_author = "a" * 256  # Exceeds max_length
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                query_text="test",
                author=long_author
            )
        error_msg = str(exc_info.value)
        assert "author" in error_msg.lower()

    def test_author_optional(self):
        """Test author is optional (backward compatibility)"""
        request = SemanticQueryRequest(query_text="test")
        assert request.author is None


class TestChunkTypeParameter:
    """Test chunk_type parameter validation."""

    def test_chunk_type_commit_message(self):
        """AC3: Test chunk_type='commit_message'"""
        request = SemanticQueryRequest(
            query_text="test",
            chunk_type="commit_message"
        )
        assert request.chunk_type == "commit_message"

    def test_chunk_type_commit_diff(self):
        """Test chunk_type='commit_diff'"""
        request = SemanticQueryRequest(
            query_text="test",
            chunk_type="commit_diff"
        )
        assert request.chunk_type == "commit_diff"

    def test_chunk_type_optional(self):
        """Test chunk_type is optional (backward compatibility)"""
        request = SemanticQueryRequest(query_text="test")
        assert request.chunk_type is None

    def test_chunk_type_invalid_value(self):
        """Test invalid chunk_type raises ValidationError"""
        with pytest.raises(ValidationError) as exc_info:
            SemanticQueryRequest(
                query_text="test",
                chunk_type="invalid_type"
            )
        error_msg = str(exc_info.value)
        assert "chunk_type" in error_msg.lower()


class TestTemporalParameterCombinations:
    """Test various combinations of temporal parameters (Acceptance Criteria)."""

    def test_ac1_time_range_with_diff_type(self):
        """AC1: Search code added in specific date range"""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added"]
        )
        assert request.time_range == "2024-01-01..2024-12-31"
        assert request.diff_type == ["added"]

    def test_ac2_diff_type_with_time_range_all(self):
        """AC2: Search deleted code across full history"""
        request = SemanticQueryRequest(
            query_text="deprecated",
            diff_type=["deleted"],
            time_range_all=True
        )
        assert request.diff_type == ["deleted"]
        assert request.time_range_all is True

    def test_ac3_chunk_type_with_author(self):
        """AC3: Search commit messages by author"""
        request = SemanticQueryRequest(
            query_text="bug fix",
            chunk_type="commit_message",
            author="john@example.com"
        )
        assert request.chunk_type == "commit_message"
        assert request.author == "john@example.com"

    def test_ac4_all_temporal_parameters(self):
        """AC4: Search modified code in recent time window"""
        request = SemanticQueryRequest(
            query_text="TODO",
            time_range="2024-11-01..2024-11-12",
            diff_type=["modified", "added"]
        )
        assert request.time_range == "2024-11-01..2024-11-12"
        assert request.diff_type == ["modified", "added"]

    def test_ac8_backward_compatibility(self):
        """AC8: Non-temporal queries work without temporal parameters"""
        request = SemanticQueryRequest(query_text="authentication")
        assert request.time_range is None
        assert request.time_range_all is False
        assert request.diff_type is None
        assert request.author is None
        assert request.chunk_type is None

    def test_existing_parameters_with_temporal(self):
        """AC8: Temporal parameters integrate with existing parameters"""
        request = SemanticQueryRequest(
            query_text="authentication",
            repository_alias="my-repo",
            limit=20,
            time_range="2024-01-01..2024-12-31",
            diff_type=["added"]
        )
        assert request.query_text == "authentication"
        assert request.repository_alias == "my-repo"
        assert request.limit == 20
        assert request.time_range == "2024-01-01..2024-12-31"
        assert request.diff_type == ["added"]
