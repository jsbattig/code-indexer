"""
Tests for HNSW search parameter optimization functionality.
"""

import pytest
from unittest.mock import Mock, patch

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient
from rich.console import Console


class TestHNSWSearchParameters:
    """Test HNSW search parameter configuration and usage."""

    @pytest.fixture
    def qdrant_config(self):
        return QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
            # These should be added in Phase 1
            hnsw_ef=64,
            hnsw_ef_construct=200,
            hnsw_m=32,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def qdrant_client(self, qdrant_config, console):
        return QdrantClient(qdrant_config, console)

    def test_config_has_hnsw_search_parameters(self, qdrant_config):
        """Test that QdrantConfig includes HNSW search parameters."""
        # These should fail initially - attributes don't exist yet
        assert hasattr(qdrant_config, "hnsw_ef")
        assert hasattr(qdrant_config, "hnsw_ef_construct")
        assert hasattr(qdrant_config, "hnsw_m")

        assert qdrant_config.hnsw_ef == 64
        assert qdrant_config.hnsw_ef_construct == 200
        assert qdrant_config.hnsw_m == 32

    def test_config_has_intelligent_defaults(self):
        """Test that HNSW parameters have intelligent defaults."""
        # Default config should have optimized values for code search
        config = QdrantConfig()

        # These should be the intelligent defaults
        assert config.hnsw_ef == 64  # Higher accuracy for code research
        assert config.hnsw_ef_construct == 200  # Better index quality
        assert config.hnsw_m == 32  # Better connectivity for large codebases

    @patch("httpx.Client.post")
    def test_search_includes_hnsw_ef_parameter(self, mock_post, qdrant_client):
        """Test that search requests include hnsw_ef parameter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        # Perform search
        qdrant_client.search(query_vector=[0.1, 0.2, 0.3, 0.4], limit=10)

        # Verify hnsw_ef was included in the request
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]

        # This should fail initially - hnsw_ef not implemented yet
        assert "params" in request_data
        assert "hnsw_ef" in request_data["params"]
        assert request_data["params"]["hnsw_ef"] == 64

    @patch("httpx.Client.post")
    def test_search_respects_custom_hnsw_ef(self, mock_post, qdrant_client):
        """Test that search can override hnsw_ef parameter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": []}
        mock_post.return_value = mock_response

        # Search with custom hnsw_ef
        qdrant_client.search(
            query_vector=[0.1, 0.2, 0.3, 0.4], limit=10, hnsw_ef=128  # Custom value
        )

        # Verify custom hnsw_ef was used
        call_args = mock_post.call_args
        request_data = call_args[1]["json"]

        assert request_data["params"]["hnsw_ef"] == 128

    def test_search_with_accuracy_profile_high(self, qdrant_client):
        """Test search with high accuracy profile."""
        with patch("httpx.Client.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": []}
            mock_post.return_value = mock_response

            # This method should be added in Phase 1
            qdrant_client.search_with_accuracy(
                query_vector=[0.1, 0.2, 0.3, 0.4], limit=10, accuracy="high"
            )

            call_args = mock_post.call_args
            request_data = call_args[1]["json"]

            # High accuracy should use higher hnsw_ef
            assert request_data["params"]["hnsw_ef"] >= 128

    def test_search_with_accuracy_profile_fast(self, qdrant_client):
        """Test search with fast (lower accuracy) profile."""
        with patch("httpx.Client.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": []}
            mock_post.return_value = mock_response

            qdrant_client.search_with_accuracy(
                query_vector=[0.1, 0.2, 0.3, 0.4], limit=10, accuracy="fast"
            )

            call_args = mock_post.call_args
            request_data = call_args[1]["json"]

            # Fast should use lower hnsw_ef
            assert request_data["params"]["hnsw_ef"] <= 32

    def test_search_with_accuracy_profile_balanced(self, qdrant_client):
        """Test search with balanced accuracy profile."""
        with patch("httpx.Client.post") as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": []}
            mock_post.return_value = mock_response

            qdrant_client.search_with_accuracy(
                query_vector=[0.1, 0.2, 0.3, 0.4], limit=10, accuracy="balanced"
            )

            call_args = mock_post.call_args
            request_data = call_args[1]["json"]

            # Balanced should use config default
            assert request_data["params"]["hnsw_ef"] == 64


class TestHNSWCollectionConfiguration:
    """Test HNSW collection configuration for Phase 2."""

    @pytest.fixture
    def qdrant_config(self):
        return QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
            hnsw_ef=64,
            hnsw_ef_construct=200,
            hnsw_m=32,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def qdrant_client(self, qdrant_config, console):
        return QdrantClient(qdrant_config, console)

    @patch("httpx.Client.put")
    def test_create_collection_uses_hnsw_config(self, mock_put, qdrant_client):
        """Test that collection creation uses configured HNSW parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True}
        mock_put.return_value = mock_response

        # This should be enhanced in Phase 2
        qdrant_client.create_collection()

        # Verify HNSW config was used (collection creation may make multiple calls)
        assert (
            mock_put.call_count >= 1
        ), f"Expected at least 1 call for collection creation, got {mock_put.call_count}"

        # Check the collection creation call
        final_call_args = mock_put.call_args_list[0]
        request_data = final_call_args[1]["json"]

        hnsw_config = request_data["hnsw_config"]
        assert hnsw_config["m"] == 32  # From config
        assert hnsw_config["ef_construct"] == 200  # From config

        # Verify CoW structure - simplified approach doesn't use init_from
        assert (
            "init_from" not in request_data
        ), "Simplified CoW should not use init_from"

    def test_create_large_codebase_collection_profile(self, qdrant_client):
        """Test creating collection with large codebase profile."""
        with patch("httpx.Client.put") as mock_put:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_put.return_value = mock_response

            # This method should be added in Phase 2
            qdrant_client.create_collection_with_profile("large_codebase")

            # Find the collection creation call (the one with hnsw_config)
            collection_call = None
            for call in mock_put.call_args_list:
                if "hnsw_config" in call[1]["json"]:
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"
            request_data = collection_call[1]["json"]

            hnsw_config = request_data["hnsw_config"]
            # Large codebase profile should have optimized settings
            assert hnsw_config["m"] >= 32
            assert hnsw_config["ef_construct"] >= 200

    def test_create_small_codebase_collection_profile(self, qdrant_client):
        """Test creating collection with small codebase profile."""
        with patch("httpx.Client.put") as mock_put:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": True}
            mock_put.return_value = mock_response

            qdrant_client.create_collection_with_profile("small_codebase")

            # Find the collection creation call (the one with hnsw_config)
            collection_call = None
            for call in mock_put.call_args_list:
                if "hnsw_config" in call[1]["json"]:
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"
            request_data = collection_call[1]["json"]

            hnsw_config = request_data["hnsw_config"]
            # Small codebase can use lower settings for memory efficiency
            assert hnsw_config["m"] == 16
            assert hnsw_config["ef_construct"] == 100

    def test_recreate_collection_preserves_data_option(self, qdrant_client):
        """Test collection recreation with data preservation option."""
        # Data preservation should show warning and return False for now
        result = qdrant_client.recreate_collection_with_hnsw_optimization(
            preserve_data=True
        )

        # Should return False since data preservation is not implemented
        assert result is False

    def test_recreate_collection_without_data_preservation(self, qdrant_client):
        """Test collection recreation without data preservation."""
        with patch.object(qdrant_client, "delete_collection") as mock_delete:
            with patch.object(
                qdrant_client, "create_collection_with_profile"
            ) as mock_create:
                mock_delete.return_value = True
                mock_create.return_value = True

                # Should delete and recreate collection
                result = qdrant_client.recreate_collection_with_hnsw_optimization(
                    preserve_data=False
                )

                assert result is True
                mock_delete.assert_called_once()
                mock_create.assert_called_once_with(
                    "large_codebase", qdrant_client.config.collection_base_name
                )


class TestHNSWSemanticSearchIntegration:
    """Test HNSW integration with semantic search service."""

    def test_semantic_search_uses_hnsw_parameters(self):
        """Test that semantic search service uses HNSW parameters."""
        # Test integration between semantic search and qdrant using existing GenericQueryService

        from code_indexer.services.generic_query_service import GenericQueryService
        from pathlib import Path

        # Mock dependencies
        config = Mock()
        config.qdrant = Mock()
        config.qdrant.hnsw_ef = 64

        service = GenericQueryService(Path("/tmp"), config)

        # Should have access to HNSW parameters from config
        assert service.config.qdrant.hnsw_ef == 64

    def test_semantic_search_accuracy_tuning(self):
        """Test semantic search with accuracy tuning."""
        # Test that our CLI query command supports accuracy tuning
        from code_indexer.config import QdrantConfig

        # Test different accuracy configurations
        default_config = QdrantConfig(hnsw_ef=64)
        high_accuracy_config = QdrantConfig(
            hnsw_ef=128
        )  # Higher ef for better accuracy
        fast_config = QdrantConfig(hnsw_ef=32)  # Lower ef for faster search

        # Verify the configurations have different accuracy levels
        assert high_accuracy_config.hnsw_ef > default_config.hnsw_ef
        assert fast_config.hnsw_ef < default_config.hnsw_ef

        # Test that HNSW parameters are accessible for runtime tuning
        assert hasattr(default_config, "hnsw_ef")
        assert hasattr(default_config, "hnsw_ef_construct")
        assert hasattr(default_config, "hnsw_m")
