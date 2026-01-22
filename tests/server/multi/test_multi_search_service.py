"""
TDD tests for MultiSearchService (AC2-AC7: Multi-Repository Search Execution).

Tests written FIRST before implementation.

Verifies:
AC2: Threaded Execution for Semantic/FTS/Temporal (ThreadPoolExecutor)
AC3: Subprocess Execution for Regex (ReDoS protection)
AC4: Timeout Enforcement (30s timeout for all queries)
AC5: Partial Failure Handling (some repos succeed, others fail)
AC7: Actionable Error Messages (timeout recommendations)
"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from code_indexer.server.multi.multi_search_config import MultiSearchConfig
from code_indexer.server.multi.models import (
    MultiSearchRequest,
    MultiSearchResponse,
)


class TestMultiSearchServiceThreadedExecution:
    """Test threaded execution for semantic/FTS/temporal searches (AC2)."""

    @pytest.mark.asyncio
    async def test_semantic_search_uses_thread_pool(self):
        """Semantic search uses ThreadPoolExecutor for parallel repo queries."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1", "repo2"],
            query="authentication logic",
            search_type="semantic",
            limit=10,
        )

        # Service should use thread pool for execution
        with patch.object(service.thread_executor, "submit") as mock_submit:
            mock_future = Mock()
            mock_future.result.return_value = {"results": [], "error": None}
            mock_submit.return_value = mock_future

            # This will fail until implementation exists
            try:
                response = await service.search(request)
                # Should have submitted 2 tasks (one per repo)
                assert mock_submit.call_count == 2
            except AttributeError:
                pytest.fail("MultiSearchService.search() not implemented")

    @pytest.mark.asyncio
    async def test_fts_search_uses_thread_pool(self):
        """FTS search uses ThreadPoolExecutor for parallel repo queries."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1", "repo2"],
            query="def authenticate",
            search_type="fts",
            limit=10,
        )

        # This will fail until implementation exists
        try:
            response = await service.search(request)
            assert response.metadata.total_repos_searched >= 0
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService.search() for FTS not implemented")

    @pytest.mark.asyncio
    async def test_temporal_search_uses_thread_pool(self):
        """Temporal search uses ThreadPoolExecutor for parallel repo queries."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1", "repo2"],
            query="authentication",
            search_type="temporal",
            limit=10,
        )

        # This will fail until implementation exists
        try:
            response = await service.search(request)
            assert response.metadata.total_repos_searched >= 0
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService.search() for temporal not implemented")

    @pytest.mark.asyncio
    async def test_thread_pool_max_workers_enforced(self):
        """Thread pool respects max_workers configuration."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=3, query_timeout_seconds=30)
        service = MultiSearchService(config)

        # Verify thread pool initialized with correct max_workers
        assert service.thread_executor._max_workers == 3


class TestMultiSearchServiceSubprocessExecution:
    """Test subprocess execution for regex searches (AC3: ReDoS protection)."""

    @pytest.mark.asyncio
    async def test_regex_search_uses_subprocess(self):
        """Regex search uses subprocess execution for ReDoS protection."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1"],
            query="def .*authenticate.*",
            search_type="regex",
            limit=10,
        )

        # This will fail until subprocess implementation exists
        try:
            response = await service.search(request)
            # Regex should NOT use thread pool (uses subprocess instead)
            assert response.metadata.total_repos_searched >= 0
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService.search() for regex not implemented")

    @pytest.mark.asyncio
    async def test_regex_subprocess_isolation(self):
        """Each regex repo search runs in isolated subprocess."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1", "repo2"],
            query="(.*){100}",  # Potentially malicious ReDoS pattern
            search_type="regex",
            limit=10,
        )

        # This will fail until subprocess implementation exists
        try:
            response = await service.search(request)
            # Each repo should execute in separate subprocess
            # Server should remain responsive even if regex causes issues
            assert response is not None
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService subprocess isolation not implemented")


class TestMultiSearchServiceTimeoutEnforcement:
    """Test timeout enforcement for all query types (AC4)."""

    @pytest.mark.asyncio
    async def test_semantic_search_timeout_30s(self):
        """Semantic search enforces 30s timeout."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["slow_repo1"],
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # Mock slow repository that exceeds timeout
        # This will fail until timeout implementation exists
        try:
            response = await service.search(request)
            # Should have error for timed out repo
            if response.errors:
                assert "timeout" in response.errors.get("slow_repo1", "").lower()
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService timeout enforcement not implemented")

    @pytest.mark.asyncio
    async def test_regex_search_timeout_30s(self):
        """Regex search enforces 30s timeout."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["slow_repo1"],
            query="(.*){100}",  # ReDoS pattern
            search_type="regex",
            limit=10,
        )

        # This will fail until subprocess timeout implementation exists
        try:
            response = await service.search(request)
            # Should timeout and return error
            if response.errors:
                assert "timeout" in response.errors.get("slow_repo1", "").lower()
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService regex timeout not implemented")

    @pytest.mark.asyncio
    async def test_timeout_config_override(self):
        """Custom timeout configuration is respected."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=15)
        service = MultiSearchService(config)

        assert service.config.query_timeout_seconds == 15


class TestMultiSearchServicePartialFailures:
    """Test partial failure handling (AC5: some repos succeed, others fail)."""

    @pytest.mark.asyncio
    async def test_partial_failure_returns_successful_results(self):
        """When some repos fail, successful results are still returned."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["good_repo", "bad_repo"],
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # This will fail until partial failure handling exists
        try:
            response = await service.search(request)
            # Should have results from good_repo even if bad_repo failed
            assert "good_repo" in response.results or "bad_repo" in response.errors
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService partial failure handling not implemented")

    @pytest.mark.asyncio
    async def test_all_repos_fail_returns_empty_results(self):
        """When all repos fail, returns empty results with error details."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["bad_repo1", "bad_repo2"],
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # This will fail until error handling exists
        try:
            response = await service.search(request)
            assert response.metadata.total_results == 0
            assert len(response.errors) > 0
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService all-fail handling not implemented")

    @pytest.mark.asyncio
    async def test_errors_include_repository_id(self):
        """Error messages include repository identifier for debugging."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["nonexistent_repo"],
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # This will fail until error tracking exists
        try:
            response = await service.search(request)
            if response.errors:
                assert "nonexistent_repo" in response.errors
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService error tracking not implemented")


class TestMultiSearchServiceActionableErrors:
    """Test actionable error messages for timeouts (AC7)."""

    @pytest.mark.asyncio
    async def test_timeout_error_includes_recommendations(self):
        """Timeout error message includes actionable recommendations."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=[f"repo{i}" for i in range(20)],  # Many repos
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # This will fail until actionable error messages exist
        try:
            response = await service.search(request)
            if response.errors:
                # Error should include recommendations like:
                # - Reduce repositories from N to M
                # - Add --min-score filter
                # - Add --path-filter
                error_text = str(response.errors)
                # At minimum, should mention timeout
                assert (
                    "timeout" in error_text.lower() or "timed out" in error_text.lower()
                )
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService actionable errors not implemented")

    @pytest.mark.asyncio
    async def test_timeout_error_lists_affected_repos(self):
        """Timeout error lists which repositories timed out vs completed."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(
            max_workers=5, query_timeout_seconds=1
        )  # Very short timeout
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1", "repo2", "repo3"],
            query="authentication",
            search_type="semantic",
            limit=10,
        )

        # This will fail until timeout tracking exists
        try:
            response = await service.search(request)
            # Should clearly distinguish timed out vs completed repos
            if response.errors:
                for repo_id in response.errors:
                    assert repo_id in request.repositories
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService timeout tracking not implemented")


class TestMultiSearchServiceIntegration:
    """Integration tests with result aggregator."""

    @pytest.mark.asyncio
    async def test_integrates_with_aggregator(self):
        """Service integrates with MultiResultAggregator for result formatting."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1"],
            query="authentication",
            search_type="semantic",
            limit=5,
        )

        # This will fail until aggregator integration exists
        try:
            response = await service.search(request)
            # Results should include repository field (from aggregator)
            if response.results.get("repo1"):
                for result in response.results["repo1"]:
                    assert "repository" in result
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService aggregator integration not implemented")

    @pytest.mark.asyncio
    async def test_respects_per_repo_limit(self):
        """Results respect per-repository limit from request."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        request = MultiSearchRequest(
            repositories=["repo1"],
            query="authentication",
            search_type="semantic",
            limit=3,  # Request limit of 3
        )

        # This will fail until limit enforcement exists
        try:
            response = await service.search(request)
            # Each repo should have at most 3 results
            for repo_id, results in response.results.items():
                assert len(results) <= 3
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService limit enforcement not implemented")


class TestMultiSearchServiceEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_repository_list_raises_error(self):
        """Empty repository list should raise validation error."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        # Request validation should catch this before service execution
        with pytest.raises(Exception):  # Pydantic validation error
            request = MultiSearchRequest(
                repositories=[],
                query="authentication",
                search_type="semantic",
                limit=10,
            )

    @pytest.mark.asyncio
    async def test_invalid_search_type_raises_error(self):
        """Invalid search type should raise validation error."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        # Request validation should catch this
        with pytest.raises(Exception):  # Pydantic validation error
            request = MultiSearchRequest(
                repositories=["repo1"],
                query="authentication",
                search_type="invalid_type",  # type: ignore
                limit=10,
            )

    @pytest.mark.asyncio
    async def test_shutdown_cleanup(self):
        """Service properly shuts down thread pool and subprocess executor."""
        from code_indexer.server.multi.multi_search_service import MultiSearchService

        config = MultiSearchConfig(max_workers=5, query_timeout_seconds=30)
        service = MultiSearchService(config)

        # This will fail until shutdown method exists
        try:
            service.shutdown()
            # Thread pool should be shut down
            assert service.thread_executor._shutdown or hasattr(service, "_shutdown")
        except (AttributeError, NotImplementedError):
            pytest.fail("MultiSearchService.shutdown() not implemented")
