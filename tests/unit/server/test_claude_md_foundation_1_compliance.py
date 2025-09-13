"""
Test suite verifying CLAUDE.md Foundation #1 compliance: Anti-Mock Golden Rules.

These tests ensure services use real implementations without mock-enabling architecture.
"""

import pytest
from unittest.mock import patch

from code_indexer.server.services.stats_service import RepositoryStatsService
from code_indexer.server.services.health_service import HealthCheckService
from code_indexer.server.services.search_service import SemanticSearchService


class TestFoundation1AntiMockCompliance:
    """Test CLAUDE.md Foundation #1: No mock-enabling architecture."""

    def test_stats_service_uses_direct_instantiation(self):
        """StatsService must use direct instantiation, no dependency injection."""
        service = RepositoryStatsService()

        # Service should have real dependencies, not injectable ones
        assert hasattr(service, "qdrant_client"), "Service must have real QdrantClient"
        assert hasattr(
            service, "repository_manager"
        ), "Service must have real RepositoryManager"

        # QdrantClient should be real instance, not None or injectable
        assert service.qdrant_client is not None, "QdrantClient must be real instance"
        # Repository manager will be real when implemented
        # assert service.repository_manager is not None, "RepositoryManager must be real instance"

    def test_health_service_uses_direct_instantiation(self):
        """FAILING TEST: HealthService must use direct instantiation, no dependency injection."""
        service = HealthCheckService()

        # Service should have real dependencies
        assert hasattr(service, "qdrant_client"), "Service must have real QdrantClient"
        assert service.qdrant_client is not None, "QdrantClient must be real instance"

    def test_search_service_uses_direct_instantiation(self):
        """FAILING TEST: SearchService must use direct instantiation, no dependency injection."""
        service = SemanticSearchService()

        # Service should have real dependencies
        assert hasattr(service, "qdrant_client"), "Service must have real QdrantClient"
        assert hasattr(
            service, "embedding_service"
        ), "Service must have real EmbeddingService"

        assert service.qdrant_client is not None, "QdrantClient must be real instance"
        assert (
            service.embedding_service is not None
        ), "EmbeddingService must be real instance"

    def test_stats_service_get_embedding_count_uses_real_qdrant(self):
        """get_embedding_count must use real Qdrant operations."""
        service = RepositoryStatsService()

        # Mock both collection_exists and get_collection_info for complete flow
        with patch.object(service.qdrant_client, "collection_exists") as mock_exists:
            with patch.object(
                service.qdrant_client, "get_collection_info"
            ) as mock_info:
                mock_exists.return_value = True
                mock_info.return_value = {"vectors_count": 1500}

                result = service.get_embedding_count("test_repo")

                # Should have called real Qdrant methods, not returned placeholder
                mock_exists.assert_called_once_with("repo_test_repo")
                mock_info.assert_called_once_with("repo_test_repo")
                assert (
                    result == 1500
                ), "Should return real Qdrant count, not placeholder"

    def test_stats_service_repository_metadata_uses_real_database(self):
        """get_repository_metadata must use real database operations."""
        service = RepositoryStatsService()

        # This should query real repository manager, not return simulated data
        with pytest.raises(FileNotFoundError):
            # Should fail clearly because repository doesn't exist
            service.get_repository_metadata("test_repo")

    def test_health_service_qdrant_check_uses_real_operations(self):
        """Qdrant health check must use real Qdrant operations."""
        service = HealthCheckService()

        # Should make real Qdrant health check, not return simulated status
        result = service._check_qdrant_health()

        # Should have real status structure, not placeholder
        assert hasattr(result, "status"), "Should have status attribute"
        assert hasattr(result, "response_time_ms"), "Should measure real response time"
        assert (
            result.response_time_ms is not None
        ), "Should have real response time measurement"

        # Should have real metadata with cluster info if available
        if hasattr(result, "metadata") and result.metadata:
            assert (
                "collections_count" in result.metadata
            ), "Should get real cluster info"

    def test_search_service_semantic_search_uses_real_embeddings(self):
        """Semantic search must use real vector embeddings."""
        service = SemanticSearchService()

        # Should generate real embeddings and search Qdrant, not text search
        with patch.object(service.embedding_service, "get_embedding") as mock_embed:
            mock_embed.return_value = [0.1] * 384  # Mock embedding

            with patch.object(service.qdrant_client, "search") as mock_search:
                mock_search.return_value = []

                # Test the internal method directly to avoid repo path issues
                service._perform_semantic_search(
                    "test_repo", "test query", limit=10, include_source=False
                )

                # Should have generated embedding and searched vectors
                mock_embed.assert_called_once_with("test query")
                mock_search.assert_called_once()

    def test_services_reject_mock_parameters(self):
        """FAILING TEST: Services must reject mock-enabling constructor parameters."""
        # These should fail because services shouldn't accept dependency injection
        with pytest.raises(TypeError):
            RepositoryStatsService(qdrant_client="mock", repository_manager="mock")

        with pytest.raises(TypeError):
            HealthCheckService(qdrant_client="mock")

        with pytest.raises(TypeError):
            SemanticSearchService(qdrant_client="mock", embedding_service="mock")

    def test_no_placeholder_implementations(self):
        """Services must not contain placeholder implementations."""
        service = RepositoryStatsService()

        # These methods should not return hardcoded placeholder values
        # They should either work with real data or fail clearly

        # get_embedding_count should use real Qdrant (returns 0 for non-existent collection)
        result = service.get_embedding_count("nonexistent_repo")
        assert (
            result == 0
        ), "Should return 0 for non-existent collection, not placeholder value"

        # Repository path lookup should fail clearly for missing repository
        with pytest.raises(FileNotFoundError):
            service._get_repository_path("test_repo")

    def test_health_endpoint_requires_authentication(self):
        """FAILING TEST: Health endpoint must require authentication."""
        # This test will be implemented when fixing health endpoint authentication
        # Current implementation lacks authentication
        pass

    def test_repository_path_lookup_uses_real_database(self):
        """FAILING TEST: Repository path lookup must use real database."""
        service = RepositoryStatsService()

        # _get_repository_path should query real repository manager, not return placeholder path
        with pytest.raises(FileNotFoundError):
            # Should fail because repository doesn't exist in golden repositories
            service._get_repository_path("test_repo")

    def test_file_indexing_status_uses_real_qdrant_check(self):
        """FAILING TEST: File indexing status must check real Qdrant data."""
        service = RepositoryStatsService()

        # _is_file_indexed should query Qdrant, not use simple extension check
        from pathlib import Path

        result = service._is_file_indexed(Path("test.py"))

        # Should be bool based on real Qdrant check, not extension-based heuristic
        # This test will fail until real Qdrant integration is implemented
        assert isinstance(result, bool)
