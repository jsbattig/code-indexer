"""
TDD tests for CoW removal - Tests that should pass after CoW code is removed.
These tests define the expected behavior after CoW removal.
"""

import pytest
from unittest.mock import Mock, patch
from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestSimplifiedEnsureCollection:
    """Test that ensure_collection works without CoW complexity after removal."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock Qdrant configuration."""
        return QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
            hnsw_m=16,
            hnsw_ef_construct=100,
        )

    @pytest.fixture
    def qdrant_client(self, mock_config):
        """Create a QdrantClient instance for testing."""
        return QdrantClient(config=mock_config, console=Mock())

    def test_ensure_collection_should_not_call_cow_methods(self, qdrant_client):
        """Test that ensure_collection doesn't call any CoW methods after removal."""
        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "_create_collection_direct") as mock_direct,
        ):
            mock_exists.return_value = False
            mock_direct.return_value = True

            result = qdrant_client.ensure_collection("test_collection", 1536)

            # After CoW removal, should go straight to direct creation
            assert result is True
            mock_exists.assert_called_once_with("test_collection")
            mock_direct.assert_called_once_with("test_collection", 1536)

    def test_ensure_collection_should_not_have_cow_fallback(self, qdrant_client):
        """Test that ensure_collection doesn't have CoW fallback logic after removal."""
        # This test will initially fail because CoW methods still exist
        # After removal, it should pass

        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "_create_collection_direct") as mock_direct,
        ):
            mock_exists.return_value = False
            mock_direct.return_value = True

            # After CoW removal, ensure_collection should only call _create_collection_direct
            # No CoW methods should be called
            result = qdrant_client.ensure_collection("test_collection", 1536)

            assert result is True
            # Verify only direct creation was called
            mock_direct.assert_called_once_with("test_collection", 1536)

    def test_ensure_collection_simplified_when_collection_exists(self, qdrant_client):
        """Test simplified behavior when collection already exists."""
        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "get_collection_info") as mock_get_info,
        ):
            mock_exists.return_value = True
            mock_get_info.return_value = {
                "config": {"params": {"vectors": {"size": 1536}}}
            }

            result = qdrant_client.ensure_collection("test_collection", 1536)

            # Should return True immediately without creating anything
            assert result is True
            mock_exists.assert_called_once_with("test_collection")


class TestCoWMethodsRemoval:
    """Test that CoW methods are removed from QdrantClient."""

    @pytest.fixture
    def qdrant_client(self):
        """Create a QdrantClient instance for testing."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )
        return QdrantClient(config=config, console=Mock())

    def test_cow_methods_should_not_exist_after_removal(self, qdrant_client):
        """Test that CoW methods don't exist after removal."""
        # These tests will initially fail but should pass after CoW removal

        cow_methods = [
            "_create_collection_with_cow",
            "_copy_collection_data_via_container",
            "_get_container_runtime_and_name",
            "_get_cow_storage_path",
            "_cleanup_cow_storage_with_path",
            "_replace_with_symlink_via_container",
        ]

        for method_name in cow_methods:
            assert not hasattr(
                qdrant_client, method_name
            ), f"CoW method {method_name} should be removed but still exists"

    def test_delete_collection_should_not_call_cow_cleanup(self, qdrant_client):
        """Test that delete_collection doesn't call CoW cleanup after removal."""
        with patch.object(qdrant_client.client, "delete") as mock_delete:
            mock_delete.return_value.status_code = 200

            result = qdrant_client.delete_collection("test_collection")

            # Should succeed with simple deletion, no CoW cleanup
            assert result is True
            mock_delete.assert_called_once_with("/collections/test_collection")


class TestSimplifiedCollectionDeletion:
    """Test simplified collection deletion without CoW storage cleanup."""

    @pytest.fixture
    def qdrant_client(self):
        """Create a QdrantClient instance for testing."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )
        return QdrantClient(config=config, console=Mock())

    def test_delete_collection_simplified_approach(self, qdrant_client):
        """Test that delete_collection uses simplified approach without CoW storage cleanup."""
        with patch.object(qdrant_client.client, "delete") as mock_delete:
            mock_delete.return_value.status_code = 200

            result = qdrant_client.delete_collection("test_collection")

            # Should be a simple Qdrant API call without storage cleanup
            assert result is True
            mock_delete.assert_called_once_with("/collections/test_collection")

    def test_delete_collection_handles_errors_gracefully(self, qdrant_client):
        """Test that simplified delete_collection handles errors gracefully."""
        with patch.object(qdrant_client.client, "delete") as mock_delete:
            mock_delete.side_effect = Exception("Connection error")

            result = qdrant_client.delete_collection("test_collection")

            # Should handle errors gracefully and return False
            assert result is False


class TestPerformanceAfterCoWRemoval:
    """Test that performance is improved after CoW removal."""

    @pytest.fixture
    def qdrant_client(self):
        """Create a QdrantClient instance for testing."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )
        return QdrantClient(config=config, console=Mock())

    def test_collection_creation_includes_payload_indexes_after_cow_removal(
        self, qdrant_client
    ):
        """Test that collection creation includes automatic payload index creation after CoW removal."""
        with patch.object(qdrant_client.client, "put") as mock_put:
            mock_put.return_value.status_code = 200

            result = qdrant_client._create_collection_direct("test_collection", 1536)

            # Should create collection + 7 payload indexes (8 total calls)
            assert result is True
            assert mock_put.call_count == 8  # 1 collection + 7 indexes

            # Verify collection creation call is present
            collection_calls = [
                call
                for call in mock_put.call_args_list
                if "hnsw_config" in call[1]["json"]
            ]
            assert len(collection_calls) == 1

            # Verify index creation calls are present
            index_calls = [
                call
                for call in mock_put.call_args_list
                if "field_name" in call[1]["json"]
            ]
            assert len(index_calls) == 7

    def test_ensure_collection_no_cow_overhead(self, qdrant_client):
        """Test that ensure_collection has no CoW overhead after removal."""
        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "_create_collection_direct") as mock_direct,
        ):
            mock_exists.return_value = False
            mock_direct.return_value = True

            result = qdrant_client.ensure_collection("test_collection", 1536)

            # Should be minimal calls - existence check + direct creation
            assert result is True
            assert mock_exists.call_count == 1
            assert mock_direct.call_count == 1
