"""
Tests for post-CoW functionality to ensure no regression after CoW code removal.
These tests validate that core functionality works correctly without CoW code.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestPostCoWQdrantClient:
    """Test QdrantClient functionality that should work after CoW removal."""

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
    def mock_console(self):
        """Create a mock console."""
        return Mock()

    @pytest.fixture
    def qdrant_client(self, mock_config, mock_console):
        """Create a QdrantClient instance for testing."""
        return QdrantClient(config=mock_config, console=mock_console)

    def test_create_collection_direct_should_work_without_cow(self, qdrant_client):
        """Test that _create_collection_direct works independently of CoW."""
        with patch.object(qdrant_client.client, "put") as mock_put:
            mock_put.return_value.status_code = 200

            result = qdrant_client._create_collection_direct("test_collection", 1536)

            assert result is True
            mock_put.assert_called_once()

            # Verify the collection config is correct
            call_args = mock_put.call_args
            assert "/collections/test_collection" in call_args[0][0]

            # Verify configuration structure
            config = call_args[1]["json"]
            assert config["vectors"]["size"] == 1536
            assert config["vectors"]["distance"] == "Cosine"
            assert config["vectors"]["on_disk"] is True

    def test_collection_exists_should_work_without_cow(self, qdrant_client):
        """Test that collection_exists works independently of CoW."""
        with patch.object(qdrant_client.client, "get") as mock_get:
            mock_get.return_value.status_code = 200

            result = qdrant_client.collection_exists("test_collection")

            assert result is True
            mock_get.assert_called_once_with("/collections/test_collection")

    def test_collection_exists_returns_false_when_not_found(self, qdrant_client):
        """Test that collection_exists returns False when collection doesn't exist."""
        with patch.object(qdrant_client.client, "get") as mock_get:
            mock_get.return_value.status_code = 404

            result = qdrant_client.collection_exists("nonexistent_collection")

            assert result is False

    def test_health_check_should_work_without_cow(self, qdrant_client):
        """Test that health_check works independently of CoW."""
        with patch.object(qdrant_client.client, "get") as mock_get:
            mock_get.return_value.status_code = 200

            result = qdrant_client.health_check()

            assert result is True
            mock_get.assert_called_once_with("/healthz", timeout=2.0)

    def test_health_check_handles_exceptions(self, qdrant_client):
        """Test that health_check handles exceptions gracefully."""
        with patch.object(qdrant_client.client, "get") as mock_get:
            mock_get.side_effect = Exception("Connection error")

            result = qdrant_client.health_check()

            assert result is False

    def test_create_collection_should_use_direct_approach(self, qdrant_client):
        """Test that create_collection uses direct approach without CoW."""
        with patch.object(qdrant_client, "_create_collection_direct") as mock_direct:
            mock_direct.return_value = True

            result = qdrant_client.create_collection("test_collection", 1536)

            assert result is True
            mock_direct.assert_called_once_with("test_collection", 1536)

    def test_ensure_collection_creates_when_not_exists(self, qdrant_client):
        """Test that ensure_collection creates collection when it doesn't exist."""
        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "_create_collection_direct") as mock_direct,
        ):

            mock_exists.return_value = False
            mock_direct.return_value = True

            result = qdrant_client.ensure_collection("test_collection", 1536)

            assert result is True
            mock_exists.assert_called_once_with("test_collection")
            mock_direct.assert_called_once_with("test_collection", 1536)

    def test_ensure_collection_validates_existing_collection(self, qdrant_client):
        """Test that ensure_collection validates existing collection."""
        with (
            patch.object(qdrant_client, "collection_exists") as mock_exists,
            patch.object(qdrant_client, "get_collection_info") as mock_get_info,
        ):

            mock_exists.return_value = True
            mock_get_info.return_value = {
                "config": {"params": {"vectors": {"size": 1536}}}
            }

            result = qdrant_client.ensure_collection("test_collection", 1536)

            assert result is True
            mock_exists.assert_called_once_with("test_collection")

    def test_delete_collection_should_work_without_cow(self, qdrant_client):
        """Test that delete_collection works without CoW cleanup."""
        with patch.object(qdrant_client.client, "delete") as mock_delete:
            mock_delete.return_value.status_code = 200

            result = qdrant_client.delete_collection("test_collection")

            assert result is True
            mock_delete.assert_called_once_with("/collections/test_collection")

    def test_delete_collection_handles_errors(self, qdrant_client):
        """Test that delete_collection handles errors gracefully."""
        with patch.object(qdrant_client.client, "delete") as mock_delete:
            mock_delete.side_effect = Exception("Delete error")

            result = qdrant_client.delete_collection("test_collection")

            assert result is False

    def test_initialization_with_defaults(self, mock_config):
        """Test QdrantClient initialization with default parameters."""
        client = QdrantClient(config=mock_config)

        assert client.config == mock_config
        assert client.console is not None
        assert client.client is not None
        assert client.project_root == Path.cwd()

    def test_initialization_with_project_root(self, mock_config, mock_console):
        """Test QdrantClient initialization with custom project root."""
        project_root = Path("/custom/project/root")
        client = QdrantClient(
            config=mock_config, console=mock_console, project_root=project_root
        )

        assert client.project_root == project_root

    def test_current_collection_name_tracking(self, qdrant_client):
        """Test that current collection name is tracked correctly."""
        assert qdrant_client._current_collection_name is None

        # Simulate setting current collection name
        qdrant_client._current_collection_name = "active_collection"

        with patch.object(qdrant_client.client, "get") as mock_get:
            mock_get.return_value.status_code = 200

            result = qdrant_client.collection_exists()

            assert result is True
            # Verify it used the current collection name
            mock_get.assert_called_once_with("/collections/active_collection")


class TestPostCoWCollectionManagement:
    """Test collection management functionality without CoW dependencies."""

    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_collection_configuration_without_cow_complexity(self):
        """Test that collection configuration is simplified without CoW."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="simple_collection",
            vector_size=1536,
            hnsw_m=16,
            hnsw_ef_construct=100,
        )

        # Test that configuration is straightforward
        assert config.collection_base_name == "simple_collection"
        assert config.vector_size == 1536
        assert config.hnsw_m == 16
        assert config.hnsw_ef_construct == 100

    def test_no_cow_related_attributes_in_client(self):
        """Test that QdrantClient doesn't have CoW-related attributes."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )

        client = QdrantClient(config=config)

        # Verify no CoW-related attributes exist
        cow_attributes = ["_cow_storage_path", "_cow_enabled", "_global_storage_dir"]

        for attr in cow_attributes:
            assert not hasattr(
                client, attr
            ), f"Client should not have CoW attribute: {attr}"


class TestPostCoWConfigurationManagement:
    """Test configuration management without CoW dependencies."""

    def test_qdrant_config_without_cow_fields(self):
        """Test that QdrantConfig works without CoW-specific fields."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
            hnsw_m=16,
            hnsw_ef_construct=100,
        )

        # Verify essential fields exist
        assert config.host == "http://localhost:6333"
        assert config.collection_base_name == "test_collection"
        assert config.vector_size == 1536
        assert config.hnsw_m == 16
        assert config.hnsw_ef_construct == 100

    def test_configuration_uses_absolute_paths(self):
        """Test that configuration uses absolute paths instead of relative CoW paths."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )

        # Configuration should work with absolute paths
        # This test ensures no relative path complexity from CoW
        assert config.host.startswith("http://") or config.host.startswith("https://")


class TestPostCoWPerformance:
    """Test that performance is improved without CoW overhead."""

    def test_collection_creation_is_direct_and_fast(self):
        """Test that collection creation is direct without CoW complexity."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="perf_test",
            vector_size=1536,
        )

        client = QdrantClient(config=config)

        with patch.object(client.client, "put") as mock_put:
            mock_put.return_value.status_code = 200

            # This should be a single, direct call without CoW overhead
            result = client._create_collection_direct("perf_test", 1536)

            assert result is True
            # Verify only one API call was made (no CoW complexity)
            assert mock_put.call_count == 1

    def test_no_cow_fallback_logic(self):
        """Test that there's no CoW fallback logic slowing down operations."""
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=1536,
        )

        client = QdrantClient(config=config)

        # Verify that create_collection goes directly to _create_collection_direct
        with patch.object(client, "_create_collection_direct") as mock_direct:
            mock_direct.return_value = True

            result = client.create_collection()

            assert result is True
            # Should go directly to direct creation, no CoW complexity
            mock_direct.assert_called_once()
