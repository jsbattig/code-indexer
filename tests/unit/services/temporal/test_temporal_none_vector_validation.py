"""
Test suite for None vector validation in temporal indexing.

This test suite validates the three-layer defense strategy against None vectors:
- Layer 3: API response validation (voyage_ai.py) - deepest layer
- Layer 2: Validation before matrix multiplication (filesystem_vector_store.py)
- Layer 1: Validation before point creation (temporal_indexer.py)

Critical requirement: Indexing must continue after skipping bad chunks, not blow up.
"""

import pytest
from unittest.mock import Mock, patch

from code_indexer.services.voyage_ai import VoyageAIClient


class TestLayer3APIValidation:
    """Test Layer 3: API response validation in voyage_ai.py"""

    def test_voyage_ai_detects_none_embedding_in_response(self):
        """Layer 3: VoyageAI should raise if API returns None embedding"""
        # Create mock config
        config = Mock()
        config.embedding_provider = "voyage-ai"
        config.model = "voyage-code-3"
        config.api_key = "test-key"

        embedder = VoyageAIClient(config)

        # Mock API response with None embedding
        mock_response = {
            "data": [
                {"embedding": [1.0, 2.0, 3.0]},
                {"embedding": None},  # API returned None
                {"embedding": [4.0, 5.0, 6.0]},
            ],
            "usage": {"total_tokens": 100},
        }

        with patch.object(embedder, "_make_sync_request", return_value=mock_response):
            with pytest.raises(
                RuntimeError,
                match=r"VoyageAI returned None embedding at index 1 in batch",
            ):
                embedder.get_embeddings_batch(["text1", "text2", "text3"])

    def test_voyage_ai_detects_none_embedding_in_multi_batch_response(self):
        """Layer 3: VoyageAI should raise if API returns None embedding in split batches"""
        # Create mock config
        config = Mock()
        config.embedding_provider = "voyage-ai"
        config.model = "voyage-code-3"
        config.api_key = "test-key"

        embedder = VoyageAIClient(config)

        # Mock responses - first batch OK, second batch has None
        mock_response_1 = {
            "data": [
                {"embedding": [1.0, 2.0, 3.0]},
            ],
            "usage": {"total_tokens": 50},
        }
        mock_response_2 = {
            "data": [
                {"embedding": None},  # API returned None in second batch
            ],
            "usage": {"total_tokens": 50},
        }

        # Mock token counting to force batch split
        with patch.object(
            embedder, "_count_tokens_accurately", side_effect=[120000, 1000]
        ):
            with patch.object(
                embedder,
                "_make_sync_request",
                side_effect=[mock_response_1, mock_response_2],
            ):
                with pytest.raises(
                    RuntimeError,
                    match=r"VoyageAI returned None embedding at index 0 in batch",
                ):
                    # Large first text forces batch split
                    embedder.get_embeddings_batch(["text1" * 10000, "text2"])

    def test_voyage_ai_detects_none_embedding_in_first_batch_of_split(self):
        """Layer 3: VoyageAI should raise if API returns None embedding in first batch of split"""
        # Create mock config
        config = Mock()
        config.embedding_provider = "voyage-ai"
        config.model = "voyage-code-3"
        config.api_key = "test-key"

        embedder = VoyageAIClient(config)

        # Mock responses - first batch has None, second batch OK
        mock_response_1 = {
            "data": [
                {"embedding": None},  # API returned None in first batch (split path)
            ],
            "usage": {"total_tokens": 50},
        }
        mock_response_2 = {
            "data": [
                {"embedding": [1.0, 2.0, 3.0]},
            ],
            "usage": {"total_tokens": 50},
        }

        # Mock token counting to force batch split
        with patch.object(
            embedder, "_count_tokens_accurately", side_effect=[120000, 1000]
        ):
            with patch.object(
                embedder,
                "_make_sync_request",
                side_effect=[mock_response_1, mock_response_2],
            ):
                with pytest.raises(
                    RuntimeError,
                    match=r"VoyageAI returned None embedding at index 0 in batch",
                ):
                    # Large first text forces batch split, None is in FIRST batch (split path)
                    embedder.get_embeddings_batch(["text1" * 10000, "text2"])


class TestLayer2StorageValidation:
    """Test Layer 2: Vector validation before matrix multiplication"""

    def test_filesystem_store_rejects_object_dtype_vector(self, tmp_path):
        """Layer 2: FilesystemVectorStore should reject object dtype vectors"""
        from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore

        base_path = tmp_path / ".code-indexer" / "index"
        project_root = tmp_path
        store = FilesystemVectorStore(base_path=base_path, project_root=project_root)

        collection = "test_collection"
        store.create_collection(collection, vector_size=1024)

        # Create point with None inside 1024-dim vector (becomes object dtype)
        vector_with_none = [float(i) if i != 500 else None for i in range(1024)]
        point = {
            "id": "point_1",
            "vector": vector_with_none,  # This becomes object dtype in numpy
            "payload": {"path": "test.py"},
            "chunk_text": "test content",
        }

        with pytest.raises(
            ValueError,
            match=r"Point point_1 has invalid vector with dtype=object.*Vector contains non-numeric values",
        ):
            store.upsert_points(collection_name=collection, points=[point])
