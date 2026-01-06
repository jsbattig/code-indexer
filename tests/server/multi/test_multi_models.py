"""
TDD tests for multi-search request/response models.

Tests written FIRST before implementation.

Verifies:
- MultiSearchRequest validation
- MultiSearchResponse structure
- Search type constraints
- Repository array validation
"""

import pytest
from pydantic import ValidationError
from code_indexer.server.multi.models import (
    MultiSearchRequest,
    MultiSearchResponse,
    MultiSearchMetadata,
)


class TestMultiSearchRequest:
    """Test MultiSearchRequest validation."""

    def test_valid_semantic_request(self):
        """Valid semantic search request."""
        request = MultiSearchRequest(
            repositories=["repo1", "repo2"],
            query="authentication",
            search_type="semantic",
        )
        assert request.repositories == ["repo1", "repo2"]
        assert request.query == "authentication"
        assert request.search_type == "semantic"
        assert request.limit == 10  # default

    def test_valid_fts_request(self):
        """Valid FTS search request."""
        request = MultiSearchRequest(
            repositories=["repo1"],
            query="def authenticate",
            search_type="fts",
            limit=20,
        )
        assert request.search_type == "fts"
        assert request.limit == 20

    def test_valid_regex_request(self):
        """Valid regex search request."""
        request = MultiSearchRequest(
            repositories=["repo1"],
            query="test_.*",
            search_type="regex",
        )
        assert request.search_type == "regex"

    def test_valid_temporal_request(self):
        """Valid temporal search request."""
        request = MultiSearchRequest(
            repositories=["repo1"],
            query="refactoring",
            search_type="temporal",
        )
        assert request.search_type == "temporal"

    def test_empty_repositories_raises_error(self):
        """Empty repositories array raises ValidationError."""
        with pytest.raises(ValidationError, match="at least 1 item"):
            MultiSearchRequest(
                repositories=[],
                query="test",
                search_type="semantic",
            )

    def test_invalid_search_type_raises_error(self):
        """Invalid search_type raises ValidationError."""
        with pytest.raises(ValidationError):
            MultiSearchRequest(
                repositories=["repo1"],
                query="test",
                search_type="invalid",
            )

    def test_optional_filters(self):
        """Optional filters are properly handled."""
        request = MultiSearchRequest(
            repositories=["repo1"],
            query="test",
            search_type="semantic",
            min_score=0.8,
            language="python",
            path_filter="*/src/*",
        )
        assert request.min_score == 0.8
        assert request.language == "python"
        assert request.path_filter == "*/src/*"


class TestMultiSearchResponse:
    """Test MultiSearchResponse structure."""

    def test_successful_response_structure(self):
        """Successful response has correct structure."""
        response = MultiSearchResponse(
            results={
                "repo1": [{"file": "test.py", "score": 0.9}],
                "repo2": [{"file": "auth.py", "score": 0.85}],
            },
            metadata=MultiSearchMetadata(
                total_results=2,
                total_repos_searched=2,
                execution_time_ms=150,
            ),
            errors=None,
        )
        assert len(response.results) == 2
        assert "repo1" in response.results
        assert "repo2" in response.results
        assert response.metadata.total_results == 2
        assert response.metadata.total_repos_searched == 2
        assert response.errors is None

    def test_partial_failure_response(self):
        """Response with partial failures includes errors."""
        response = MultiSearchResponse(
            results={
                "repo1": [{"file": "test.py", "score": 0.9}],
            },
            metadata=MultiSearchMetadata(
                total_results=1,
                total_repos_searched=1,
                execution_time_ms=200,
            ),
            errors={"repo2": "Timeout after 30s"},
        )
        assert len(response.results) == 1
        assert response.errors is not None
        assert "repo2" in response.errors
        assert "Timeout" in response.errors["repo2"]

    def test_empty_results_response(self):
        """Response with no results is valid."""
        response = MultiSearchResponse(
            results={},
            metadata=MultiSearchMetadata(
                total_results=0,
                total_repos_searched=0,
                execution_time_ms=50,
            ),
            errors=None,
        )
        assert len(response.results) == 0
        assert response.metadata.total_results == 0


class TestMultiSearchMetadata:
    """Test MultiSearchMetadata structure."""

    def test_metadata_fields(self):
        """Metadata contains required fields."""
        metadata = MultiSearchMetadata(
            total_results=42,
            total_repos_searched=5,
            execution_time_ms=1500,
        )
        assert metadata.total_results == 42
        assert metadata.total_repos_searched == 5
        assert metadata.execution_time_ms == 1500
