"""
Unit tests for Phase 3 REST API temporal filtering parameters (Story #503).

Tests for:
- diff_type parameter validation (single string and array)
- author parameter validation
- chunk_type parameter validation (commit_message/commit_diff enum)
- Parameter combinations
- Parameter defaults
"""

from code_indexer.server.app import SemanticQueryRequest


class TestDiffTypeParameter:
    """Test diff_type parameter."""

    def test_diff_type_accepts_single_string(self):
        """Test diff_type accepts single string value."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type="added",
        )
        assert request.diff_type == "added"

    def test_diff_type_accepts_list_of_strings(self):
        """Test diff_type accepts list of strings."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added", "modified"],
        )
        assert request.diff_type == ["added", "modified"]

    def test_diff_type_accepts_all_valid_values(self):
        """Test diff_type accepts all valid values (added/modified/deleted/renamed/binary)."""
        valid_values = ["added", "modified", "deleted", "renamed", "binary"]
        for value in valid_values:
            request = SemanticQueryRequest(
                query_text="test",
                time_range="2024-01-01..2024-12-31",
                diff_type=value,
            )
            assert request.diff_type == value

    def test_diff_type_accepts_combination_of_valid_values(self):
        """Test diff_type accepts array with multiple valid values."""
        request = SemanticQueryRequest(
            query_text="test",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added", "modified", "deleted"],
        )
        assert request.diff_type == ["added", "modified", "deleted"]

    def test_diff_type_optional_default_none(self):
        """Test diff_type is optional and defaults to None."""
        request = SemanticQueryRequest(
            query_text="test", time_range="2024-01-01..2024-12-31"
        )
        assert request.diff_type is None


class TestAuthorParameter:
    """Test author parameter."""

    def test_author_accepts_email(self):
        """Test author accepts email address."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            author="dev@example.com",
        )
        assert request.author == "dev@example.com"

    def test_author_accepts_name(self):
        """Test author accepts developer name."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            author="John Doe",
        )
        assert request.author == "John Doe"

    def test_author_accepts_partial_name(self):
        """Test author accepts partial name match."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            author="John",
        )
        assert request.author == "John"

    def test_author_optional_default_none(self):
        """Test author is optional and defaults to None."""
        request = SemanticQueryRequest(
            query_text="test", time_range="2024-01-01..2024-12-31"
        )
        assert request.author is None


class TestChunkTypeParameter:
    """Test chunk_type parameter."""

    def test_chunk_type_accepts_commit_message(self):
        """Test chunk_type accepts 'commit_message' value."""
        request = SemanticQueryRequest(
            query_text="fix bug",
            time_range="2024-01-01..2024-12-31",
            chunk_type="commit_message",
        )
        assert request.chunk_type == "commit_message"

    def test_chunk_type_accepts_commit_diff(self):
        """Test chunk_type accepts 'commit_diff' value."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            chunk_type="commit_diff",
        )
        assert request.chunk_type == "commit_diff"

    def test_chunk_type_optional_default_none(self):
        """Test chunk_type is optional and defaults to None."""
        request = SemanticQueryRequest(
            query_text="test", time_range="2024-01-01..2024-12-31"
        )
        assert request.chunk_type is None


class TestParameterCombinations:
    """Test combinations of Phase 3 temporal parameters."""

    def test_all_phase3_parameters_together(self):
        """Test all Phase 3 temporal parameters can be used together."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added", "modified"],
            author="dev@example.com",
            chunk_type="commit_diff",
        )
        assert request.diff_type == ["added", "modified"]
        assert request.author == "dev@example.com"
        assert request.chunk_type == "commit_diff"

    def test_phase3_with_phase1_and_phase2_parameters(self):
        """Test Phase 3 parameters work alongside Phase 1 and Phase 2 parameters."""
        request = SemanticQueryRequest(
            query_text="authentication",
            # Phase 1 parameters
            language="python",
            exclude_path="*/tests/*",
            accuracy="high",
            # Temporal parameters (Story #446)
            time_range="2024-01-01..2024-12-31",
            # Phase 2 FTS parameters
            search_mode="fts",
            case_sensitive=True,
            snippet_lines=10,
            # Phase 3 temporal filtering parameters
            diff_type="modified",
            author="dev@example.com",
            chunk_type="commit_diff",
        )
        # Phase 1
        assert request.language == "python"
        assert request.exclude_path == "*/tests/*"
        assert request.accuracy == "high"
        # Temporal base
        assert request.time_range == "2024-01-01..2024-12-31"
        # Phase 2
        assert request.search_mode == "fts"
        assert request.case_sensitive is True
        assert request.snippet_lines == 10
        # Phase 3
        assert request.diff_type == "modified"
        assert request.author == "dev@example.com"
        assert request.chunk_type == "commit_diff"

    def test_diff_type_array_with_single_value(self):
        """Test diff_type array with single value is accepted."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added"],
        )
        assert request.diff_type == ["added"]

    def test_diff_type_with_chunk_type_commit_message(self):
        """Test diff_type can be combined with chunk_type='commit_message'."""
        request = SemanticQueryRequest(
            query_text="fix bug",
            time_range="2024-01-01..2024-12-31",
            diff_type="added",
            chunk_type="commit_message",
        )
        assert request.diff_type == "added"
        assert request.chunk_type == "commit_message"

    def test_all_diff_types_with_author_filter(self):
        """Test all diff types can be filtered by author."""
        request = SemanticQueryRequest(
            query_text="authentication",
            time_range="2024-01-01..2024-12-31",
            diff_type=["added", "modified", "deleted", "renamed", "binary"],
            author="dev@example.com",
        )
        assert len(request.diff_type) == 5
        assert request.author == "dev@example.com"
