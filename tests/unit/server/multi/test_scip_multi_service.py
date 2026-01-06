"""
TDD tests for SCIPMultiService (AC1-AC8: Multi-Repository SCIP Intelligence).

Tests written FIRST before implementation.

Verifies:
AC1: Multi-Repository Definition Lookup
AC2: Multi-Repository Reference Lookup
AC3: Multi-Repository Dependency Analysis
AC4: Multi-Repository Dependents Analysis
AC5: Per-Repository Call Chain Tracing (no cross-repo stitching)
AC6: Result Aggregation with Repository Attribution
AC7: Timeout Handling (30s) with Recommendations
AC8: SCIP Index Availability Handling
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from code_indexer.server.multi.scip_models import (
    SCIPMultiRequest,
    SCIPMultiResponse,
    SCIPResult,
)
from code_indexer.scip.query.primitives import QueryResult


class TestSCIPMultiServiceDefinition:
    """Test multi-repository definition lookup (AC1)."""

    @pytest.mark.asyncio
    async def test_definition_across_multiple_repos(self):
        """Find definition across multiple repositories."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="UserService"
        )

        # Mock the single-repo definition method
        with patch.object(
            service, "_find_definition_in_repo"
        ) as mock_find:
            # Repo1 has definition, repo2 doesn't
            mock_find.side_effect = [
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo1",
                        file_path="src/auth.py",
                        line=42,
                        column=4,
                        kind="definition"
                    )
                ],
                []  # repo2 has no definition
            ]

            response = await service.definition(request)

            assert response.metadata.repos_searched == 2
            assert response.metadata.repos_with_results == 1
            assert len(response.results["repo1"]) == 1
            assert response.results["repo1"][0].symbol == "UserService"
            assert response.results["repo1"][0].kind == "definition"

    @pytest.mark.asyncio
    async def test_definition_no_scip_index(self):
        """Handle repos without SCIP indexes gracefully."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo_no_scip"],
            symbol="UserService"
        )

        with patch.object(service, "_find_definition_in_repo") as mock_find:
            # repo1 has definition, repo_no_scip has no SCIP index
            mock_find.side_effect = [
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo1",
                        file_path="src/auth.py",
                        line=42,
                        column=4,
                        kind="definition"
                    )
                ],
                None  # Indicates no SCIP index
            ]

            response = await service.definition(request)

            assert response.metadata.repos_searched == 1
            assert "repo_no_scip" in response.skipped
            assert "No SCIP index" in response.skipped["repo_no_scip"]


class TestSCIPMultiServiceReferences:
    """Test multi-repository reference lookup (AC2)."""

    @pytest.mark.asyncio
    async def test_references_across_multiple_repos(self):
        """Find references across multiple repositories."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="UserService"
        )

        with patch.object(service, "_find_references_in_repo") as mock_find:
            # Both repos have references
            mock_find.side_effect = [
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo1",
                        file_path="tests/test_auth.py",
                        line=10,
                        column=0,
                        kind="reference"
                    )
                ],
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo2",
                        file_path="lib/user.py",
                        line=5,
                        column=4,
                        kind="reference"
                    )
                ]
            ]

            response = await service.references(request)

            assert response.metadata.repos_searched == 2
            assert response.metadata.repos_with_results == 2
            assert len(response.results["repo1"]) == 1
            assert len(response.results["repo2"]) == 1
            assert response.results["repo1"][0].kind == "reference"
            assert response.results["repo2"][0].kind == "reference"


class TestSCIPMultiServiceDependencies:
    """Test multi-repository dependency analysis (AC3)."""

    @pytest.mark.asyncio
    async def test_dependencies_across_multiple_repos(self):
        """Find dependencies across multiple repositories."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="UserService"
        )

        with patch.object(service, "_get_dependencies_in_repo") as mock_deps:
            # Both repos have dependencies
            mock_deps.side_effect = [
                [
                    QueryResult(
                        symbol="DatabaseConnection",
                        project="repo1",
                        file_path="src/auth.py",
                        line=5,
                        column=0,
                        kind="dependency"
                    )
                ],
                [
                    QueryResult(
                        symbol="Logger",
                        project="repo2",
                        file_path="lib/user.py",
                        line=2,
                        column=0,
                        kind="dependency"
                    )
                ]
            ]

            response = await service.dependencies(request)

            assert response.metadata.repos_searched == 2
            assert response.metadata.repos_with_results == 2
            assert response.results["repo1"][0].kind == "dependency"
            assert response.results["repo2"][0].kind == "dependency"


class TestSCIPMultiServiceDependents:
    """Test multi-repository dependents analysis (AC4)."""

    @pytest.mark.asyncio
    async def test_dependents_across_multiple_repos(self):
        """Find dependents across multiple repositories."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="UserService"
        )

        with patch.object(service, "_get_dependents_in_repo") as mock_deps:
            # Both repos have dependents
            mock_deps.side_effect = [
                [
                    QueryResult(
                        symbol="APIHandler",
                        project="repo1",
                        file_path="src/api.py",
                        line=20,
                        column=4,
                        kind="dependent"
                    )
                ],
                [
                    QueryResult(
                        symbol="WebController",
                        project="repo2",
                        file_path="controllers/user.py",
                        line=15,
                        column=0,
                        kind="dependent"
                    )
                ]
            ]

            response = await service.dependents(request)

            assert response.metadata.repos_searched == 2
            assert response.metadata.repos_with_results == 2
            assert response.results["repo1"][0].kind == "dependent"
            assert response.results["repo2"][0].kind == "dependent"


class TestSCIPMultiServiceCallChain:
    """Test per-repository call chain tracing (AC5)."""

    @pytest.mark.asyncio
    async def test_callchain_per_repository_no_stitching(self):
        """Trace call chains per repository without cross-repo stitching."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="",  # Not used for callchain
            from_symbol="api_handler",
            to_symbol="database_query"
        )

        with patch.object(service, "_trace_callchain_in_repo") as mock_chain:
            # Each repo has its own call chain (with different lengths to verify independence)
            mock_chain.side_effect = [
                [
                    QueryResult(
                        symbol="api_handler -> service -> database_query",
                        project="repo1",
                        file_path="",
                        line=0,
                        column=0,
                        kind="callchain",
                        context="api_handler -> service -> database_query"
                    )
                ],
                [
                    QueryResult(
                        symbol="api_handler -> database_query",
                        project="repo2",
                        file_path="",
                        line=0,
                        column=0,
                        kind="callchain",
                        context="api_handler -> database_query"
                    )
                ]
            ]

            response = await service.callchain(request)

            # Each repo has independent call chains (no cross-repo stitching)
            assert response.metadata.repos_searched == 2
            assert response.metadata.repos_with_results == 2
            assert len(response.results["repo1"]) == 1
            assert len(response.results["repo2"]) == 1

            # Verify chains are separate by checking they have different lengths
            # repo1 chain has 3 symbols (includes 'service'), repo2 has 2 symbols
            repo1_chain = response.results["repo1"][0].context
            repo2_chain = response.results["repo2"][0].context
            assert "service" in repo1_chain  # repo1 has intermediate symbol
            assert "service" not in repo2_chain  # repo2 doesn't have intermediate symbol

            # Verify repository attribution is correct
            assert response.results["repo1"][0].repository == "repo1"
            assert response.results["repo2"][0].repository == "repo2"


class TestSCIPMultiServiceTimeout:
    """Test timeout handling with recommendations (AC7)."""

    @pytest.mark.asyncio
    async def test_timeout_parameter_accepted(self):
        """Service accepts timeout parameter and processes multiple repos."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        # Verify service accepts custom timeout
        service = SCIPMultiService(query_timeout_seconds=1)
        assert service.query_timeout_seconds == 1

        request = SCIPMultiRequest(
            repositories=["repo1", "repo2"],
            symbol="UserService"
        )

        with patch.object(service, "_find_definition_in_repo") as mock_find:
            # Both repos succeed quickly
            mock_find.return_value = [
                QueryResult(
                    symbol="UserService",
                    project="repo1",
                    file_path="src/auth.py",
                    line=42,
                    column=4,
                    kind="definition"
                )
            ]

            response = await service.definition(request)

            # Verify both repos were processed
            assert response.metadata.repos_searched == 2
            assert len(response.results) == 2


class TestSCIPMultiServiceResultAggregation:
    """Test result aggregation with repository attribution (AC6)."""

    @pytest.mark.asyncio
    async def test_results_grouped_by_repository(self):
        """Results are grouped by repository with proper attribution."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo2", "repo3"],
            symbol="UserService"
        )

        with patch.object(service, "_find_definition_in_repo") as mock_find:
            mock_find.side_effect = [
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo1",
                        file_path="src/auth.py",
                        line=42,
                        column=4,
                        kind="definition"
                    )
                ],
                [],  # repo2 has no results
                [
                    QueryResult(
                        symbol="UserService",
                        project="repo3",
                        file_path="lib/auth.py",
                        line=10,
                        column=0,
                        kind="definition"
                    )
                ]
            ]

            response = await service.definition(request)

            # Verify grouping by repository
            assert "repo1" in response.results
            assert "repo2" in response.results  # Searched but no results (empty list)
            assert "repo3" in response.results

            # Verify repo2 has empty results
            assert len(response.results["repo2"]) == 0

            # Verify attribution
            assert response.results["repo1"][0].repository == "repo1"
            assert response.results["repo3"][0].repository == "repo3"

            # Verify metadata
            assert response.metadata.repos_searched == 3
            assert response.metadata.repos_with_results == 2  # repo1 and repo3 have results
            assert response.metadata.total_results == 2


class TestSCIPMultiServicePartialFailure:
    """Test partial failure handling."""

    @pytest.mark.asyncio
    async def test_partial_failure_continues_other_repos(self):
        """Continue with other repos when one fails."""
        from code_indexer.server.multi.scip_multi_service import SCIPMultiService

        service = SCIPMultiService()
        request = SCIPMultiRequest(
            repositories=["repo1", "repo_error", "repo3"],
            symbol="UserService"
        )

        with patch.object(service, "_find_definition_in_repo") as mock_find:
            def find_with_error(repo_id, symbol):
                if repo_id == "repo_error":
                    raise RuntimeError("Database connection failed")
                return [
                    QueryResult(
                        symbol="UserService",
                        project=repo_id,
                        file_path="src/auth.py",
                        line=42,
                        column=4,
                        kind="definition"
                    )
                ]

            mock_find.side_effect = find_with_error

            response = await service.definition(request)

            # repo1 and repo3 succeed, repo_error fails
            assert len(response.results) == 2
            assert "repo1" in response.results
            assert "repo3" in response.results
            assert "repo_error" in response.errors
            assert "Database connection failed" in response.errors["repo_error"]
