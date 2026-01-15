"""
TDD tests for SCIP Multi-Repository Models.

Tests written FIRST before implementation.

Verifies:
- SCIPMultiRequest model validation
- SCIPResult model structure
- SCIPMultiMetadata model structure
- SCIPMultiResponse model structure
"""

import pytest
from pydantic import ValidationError


class TestSCIPMultiRequest:
    """Test SCIP multi-repository request model."""

    def test_valid_request_definition(self):
        """Valid definition request with repositories and symbol."""
        from code_indexer.server.multi.scip_models import SCIPMultiRequest

        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"], symbol="UserService"
        )

        assert request.repositories == ["repo1", "repo2"]
        assert request.symbol == "UserService"
        assert request.from_symbol is None
        assert request.to_symbol is None

    def test_valid_request_callchain(self):
        """Valid callchain request with from_symbol and to_symbol."""
        from code_indexer.server.multi.scip_models import SCIPMultiRequest

        request = SCIPMultiRequest(
            repositories=["repo1"],
            symbol="",  # Not used for callchain
            from_symbol="api_handler",
            to_symbol="database_query",
        )

        assert request.repositories == ["repo1"]
        assert request.from_symbol == "api_handler"
        assert request.to_symbol == "database_query"

    def test_empty_repositories_rejected(self):
        """Request with empty repositories list is rejected."""
        from code_indexer.server.multi.scip_models import SCIPMultiRequest

        with pytest.raises(ValidationError):
            SCIPMultiRequest(repositories=[], symbol="UserService")

    def test_missing_symbol_rejected(self):
        """Request without symbol is rejected."""
        from code_indexer.server.multi.scip_models import SCIPMultiRequest

        with pytest.raises(ValidationError):
            SCIPMultiRequest(repositories=["repo1"])


class TestSCIPResult:
    """Test SCIP result item model."""

    def test_valid_definition_result(self):
        """Valid definition result with all required fields."""
        from code_indexer.server.multi.scip_models import SCIPResult

        result = SCIPResult(
            repository="repo1",
            file_path="src/auth.py",
            line=42,
            column=4,
            symbol="UserService",
            kind="definition",
        )

        assert result.repository == "repo1"
        assert result.file_path == "src/auth.py"
        assert result.line == 42
        assert result.column == 4
        assert result.symbol == "UserService"
        assert result.kind == "definition"
        assert result.context is None

    def test_valid_reference_result_with_context(self):
        """Valid reference result with optional context."""
        from code_indexer.server.multi.scip_models import SCIPResult

        result = SCIPResult(
            repository="repo2",
            file_path="tests/test_auth.py",
            line=10,
            column=0,
            symbol="UserService",
            kind="reference",
            context="    user = UserService()",
        )

        assert result.kind == "reference"
        assert result.context == "    user = UserService()"

    def test_dependency_result(self):
        """Valid dependency result."""
        from code_indexer.server.multi.scip_models import SCIPResult

        result = SCIPResult(
            repository="repo1",
            file_path="src/auth.py",
            line=5,
            column=0,
            symbol="DatabaseConnection",
            kind="dependency",
        )

        assert result.kind == "dependency"

    def test_dependent_result(self):
        """Valid dependent result."""
        from code_indexer.server.multi.scip_models import SCIPResult

        result = SCIPResult(
            repository="repo1",
            file_path="src/api.py",
            line=20,
            column=4,
            symbol="APIHandler",
            kind="dependent",
        )

        assert result.kind == "dependent"


class TestSCIPMultiMetadata:
    """Test SCIP multi-repository metadata model."""

    def test_valid_metadata(self):
        """Valid metadata with all fields."""
        from code_indexer.server.multi.scip_models import SCIPMultiMetadata

        metadata = SCIPMultiMetadata(
            total_results=25,
            repos_searched=3,
            repos_with_results=2,
            execution_time_ms=450,
        )

        assert metadata.total_results == 25
        assert metadata.repos_searched == 3
        assert metadata.repos_with_results == 2
        assert metadata.execution_time_ms == 450

    def test_zero_results_metadata(self):
        """Valid metadata with zero results."""
        from code_indexer.server.multi.scip_models import SCIPMultiMetadata

        metadata = SCIPMultiMetadata(
            total_results=0,
            repos_searched=2,
            repos_with_results=0,
            execution_time_ms=100,
        )

        assert metadata.total_results == 0
        assert metadata.repos_with_results == 0


class TestSCIPMultiResponse:
    """Test SCIP multi-repository response model."""

    def test_valid_response_with_results(self):
        """Valid response with results from multiple repos."""
        from code_indexer.server.multi.scip_models import (
            SCIPMultiResponse,
            SCIPResult,
            SCIPMultiMetadata,
        )

        results = {
            "repo1": [
                SCIPResult(
                    repository="repo1",
                    file_path="src/auth.py",
                    line=42,
                    column=4,
                    symbol="UserService",
                    kind="definition",
                )
            ],
            "repo2": [
                SCIPResult(
                    repository="repo2",
                    file_path="lib/user.py",
                    line=10,
                    column=0,
                    symbol="UserService",
                    kind="reference",
                )
            ],
        }

        metadata = SCIPMultiMetadata(
            total_results=2,
            repos_searched=2,
            repos_with_results=2,
            execution_time_ms=300,
        )

        response = SCIPMultiResponse(results=results, metadata=metadata, skipped={})

        assert len(response.results) == 2
        assert "repo1" in response.results
        assert "repo2" in response.results
        assert response.metadata.total_results == 2
        assert response.errors is None

    def test_valid_response_with_skipped_repos(self):
        """Valid response with some repos skipped (no SCIP index)."""
        from code_indexer.server.multi.scip_models import (
            SCIPMultiResponse,
            SCIPResult,
            SCIPMultiMetadata,
        )

        results = {
            "repo1": [
                SCIPResult(
                    repository="repo1",
                    file_path="src/auth.py",
                    line=42,
                    column=4,
                    symbol="UserService",
                    kind="definition",
                )
            ]
        }

        metadata = SCIPMultiMetadata(
            total_results=1,
            repos_searched=1,
            repos_with_results=1,
            execution_time_ms=200,
        )

        response = SCIPMultiResponse(
            results=results,
            metadata=metadata,
            skipped={"repo2": "No SCIP index available"},
        )

        assert len(response.results) == 1
        assert len(response.skipped) == 1
        assert response.skipped["repo2"] == "No SCIP index available"

    def test_valid_response_with_errors(self):
        """Valid response with errors from some repos."""
        from code_indexer.server.multi.scip_models import (
            SCIPMultiResponse,
            SCIPMultiMetadata,
        )

        metadata = SCIPMultiMetadata(
            total_results=0,
            repos_searched=0,
            repos_with_results=0,
            execution_time_ms=150,
        )

        response = SCIPMultiResponse(
            results={},
            metadata=metadata,
            skipped={},
            errors={"repo1": "Database connection failed"},
        )

        assert len(response.results) == 0
        assert response.errors is not None
        assert response.errors["repo1"] == "Database connection failed"

    def test_empty_response(self):
        """Valid empty response (no results, no errors)."""
        from code_indexer.server.multi.scip_models import (
            SCIPMultiResponse,
            SCIPMultiMetadata,
        )

        metadata = SCIPMultiMetadata(
            total_results=0,
            repos_searched=1,
            repos_with_results=0,
            execution_time_ms=50,
        )

        response = SCIPMultiResponse(results={}, metadata=metadata, skipped={})

        assert len(response.results) == 0
        assert len(response.skipped) == 0
        assert response.errors is None
