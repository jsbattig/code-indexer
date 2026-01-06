"""Integration tests for temporal search with metadata store (Story #669).

Tests that search operations correctly integrate with temporal metadata store:
- search() returns results with correct point_ids from v2 hash-based format
- Payloads are loaded correctly using metadata mappings
- Hash prefix → point_id resolution works during search

Code Review P0 Violation Fix: Integration gap - search_vectors() integration not tested.
"""

import tempfile
from pathlib import Path
import pytest

from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from src.code_indexer.storage.temporal_metadata_store import TemporalMetadataStore
from src.code_indexer.storage.hnsw_index_manager import HNSWIndexManager
from tests.shared.mock_providers import MockEmbeddingProvider


class TestTemporalSearchMetadataIntegration:
    """Integration tests for search with temporal metadata store."""

    def test_search_returns_results_from_v2_temporal_collection(self):
        """Search returns results with correct point_ids from v2 format temporal collection."""
        # Given: A temporal collection with v2 format vectors
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # Upsert temporal points (triggers v2 format)
            points = [
                {
                    "id": "project:diff:abc123:auth.py:0",
                    "vector": [0.1] * 1024,
                    "payload": {
                        "path": "auth.py",
                        "commit_hash": "abc123",
                        "chunk_index": 0,
                    },
                    "chunk_text": "authentication logic for user login",
                },
                {
                    "id": "project:diff:def456:database.py:0",
                    "vector": [0.2] * 1024,
                    "payload": {
                        "path": "database.py",
                        "commit_hash": "def456",
                        "chunk_index": 0,
                    },
                    "chunk_text": "database query execution",
                },
            ]
            store.upsert_points("code-indexer-temporal", points)

            # Verify v2 format is used
            temporal_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_db_path = temporal_path / "temporal_metadata.db"
            assert metadata_db_path.exists(), "temporal_metadata.db should exist"

            # Verify metadata entries exist
            metadata_store = TemporalMetadataStore(temporal_path)
            assert metadata_store.count_entries() == 2

            # Rebuild HNSW index for search
            hnsw_manager = HNSWIndexManager(vector_dim=1024, space="cosine")
            hnsw_manager.rebuild_from_vectors(temporal_path, progress_callback=None)

            # When: Searching temporal collection
            mock_provider = MockEmbeddingProvider(dimensions=1024)
            results = store.search(
                query="authentication",
                embedding_provider=mock_provider,
                collection_name="code-indexer-temporal",
                limit=10,
            )

            # Then: Results should contain correct point_ids (resolved from hash prefixes)
            assert len(results) > 0, "Search should return results"

            # Verify at least one result has the expected point_id
            point_ids = {r["id"] for r in results}
            assert (
                "project:diff:abc123:auth.py:0" in point_ids
                or "project:diff:def456:database.py:0" in point_ids
            )

            # Verify payloads are loaded correctly
            for result in results:
                assert "payload" in result
                assert "path" in result["payload"]
                assert len(result["payload"]["path"]) > 0

    def test_search_with_long_point_ids_uses_metadata_mapping(self):
        """Search with long point_ids correctly uses metadata mapping (v2 format necessity)."""
        # Given: Temporal collection with extremely long point_ids
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # Create point with long path that would exceed 255 chars in v1 format
            long_path = "deeply/nested/" + "directory/" * 20 + "VeryLongFileName.py"
            long_point_id = f"project:diff:longcommithash:{long_path}:0"

            assert (
                len(long_point_id) > 255
            ), "point_id should exceed 255 chars for this test"

            point = {
                "id": long_point_id,
                "vector": [0.3] * 1024,
                "payload": {
                    "path": long_path,
                    "commit_hash": "longcommithash",
                    "chunk_index": 0,
                },
                "chunk_text": "test content for long path file",
            }
            store.upsert_points("code-indexer-temporal", [point])

            # Verify v2 format and metadata exist
            temporal_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(temporal_path)
            assert metadata_store.count_entries() == 1

            # Get hash prefix from metadata
            vector_files = list(temporal_path.rglob("vector_*.json"))
            assert len(vector_files) == 1
            filename = vector_files[0].stem
            hash_prefix = filename[len("vector_") :]

            # Verify mapping exists
            retrieved_point_id = metadata_store.get_point_id(hash_prefix)
            assert retrieved_point_id == long_point_id

            # Rebuild HNSW index for search
            hnsw_manager = HNSWIndexManager(vector_dim=1024, space="cosine")
            hnsw_manager.rebuild_from_vectors(temporal_path, progress_callback=None)

            # When: Searching (should use metadata mapping internally)
            mock_provider = MockEmbeddingProvider(dimensions=1024)
            results = store.search(
                query="test content",
                embedding_provider=mock_provider,
                collection_name="code-indexer-temporal",
                limit=10,
            )

            # Then: Should return result with correct point_id (resolved via metadata)
            assert len(results) > 0
            assert results[0]["id"] == long_point_id
            assert results[0]["payload"]["path"] == long_path

    def test_search_metadata_integration_preserves_commit_info(self):
        """Search results include commit information from metadata store."""
        # Given: Temporal collection with commit metadata
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            point = {
                "id": "project:diff:commit789:file.py:0",
                "vector": [0.4] * 1024,
                "payload": {
                    "path": "file.py",
                    "commit_hash": "commit789",
                    "chunk_index": 0,
                    "commit_message": "Add new feature",
                },
                "chunk_text": "feature implementation",
            }
            store.upsert_points("code-indexer-temporal", [point])

            # Rebuild HNSW index for search
            temporal_path = Path(tmpdir) / "code-indexer-temporal"
            hnsw_manager = HNSWIndexManager(vector_dim=1024, space="cosine")
            hnsw_manager.rebuild_from_vectors(temporal_path, progress_callback=None)

            # When: Searching
            mock_provider = MockEmbeddingProvider(dimensions=1024)
            results = store.search(
                query="feature",
                embedding_provider=mock_provider,
                collection_name="code-indexer-temporal",
                limit=10,
            )

            # Then: Results should include commit information
            assert len(results) > 0
            result = results[0]
            assert result["id"] == "project:diff:commit789:file.py:0"
            assert result["payload"]["commit_hash"] == "commit789"
            assert result["payload"]["path"] == "file.py"

    def test_search_empty_temporal_collection_returns_empty_results(self):
        """Search on empty temporal collection (with metadata db) returns empty results."""
        # Given: Empty temporal collection with v2 format initialized
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # Initialize metadata store (creates temporal_metadata.db)
            temporal_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(temporal_path)
            assert metadata_store.count_entries() == 0

            # When: Searching empty collection (no HNSW index exists yet, will error)
            mock_provider = MockEmbeddingProvider(dimensions=1024)

            # Expect RuntimeError for missing HNSW index on empty collection
            with pytest.raises(RuntimeError, match="HNSW index not found"):
                store.search(
                    query="anything",
                    embedding_provider=mock_provider,
                    collection_name="code-indexer-temporal",
                    limit=10,
                )

    def test_search_with_multiple_chunks_same_file_resolves_correctly(self):
        """Search with multiple chunks from same file resolves all point_ids correctly."""
        # Given: Multiple chunks from same file in temporal collection
        with tempfile.TemporaryDirectory() as tmpdir:
            store = FilesystemVectorStore(base_path=Path(tmpdir))
            store.create_collection("code-indexer-temporal", vector_size=1024)

            # Create 3 chunks from same file
            points = [
                {
                    "id": f"project:diff:xyz:module.py:{i}",
                    "vector": [0.1 * (i + 1)] * 1024,
                    "payload": {
                        "path": "module.py",
                        "commit_hash": "xyz",
                        "chunk_index": i,
                    },
                    "chunk_text": f"chunk content {i}",
                }
                for i in range(3)
            ]
            store.upsert_points("code-indexer-temporal", points)

            # Verify metadata has 3 entries
            temporal_path = Path(tmpdir) / "code-indexer-temporal"
            metadata_store = TemporalMetadataStore(temporal_path)
            assert metadata_store.count_entries() == 3

            # Rebuild HNSW index for search
            hnsw_manager = HNSWIndexManager(vector_dim=1024, space="cosine")
            hnsw_manager.rebuild_from_vectors(temporal_path, progress_callback=None)

            # When: Searching
            mock_provider = MockEmbeddingProvider(dimensions=1024)
            results = store.search(
                query="chunk",
                embedding_provider=mock_provider,
                collection_name="code-indexer-temporal",
                limit=10,
            )

            # Then: All chunks should be returned with correct point_ids
            assert len(results) == 3

            expected_ids = {f"project:diff:xyz:module.py:{i}" for i in range(3)}
            actual_ids = {r["id"] for r in results}
            assert actual_ids == expected_ids

            # All should have same file path and commit hash
            for result in results:
                assert result["payload"]["path"] == "module.py"
                assert result["payload"]["commit_hash"] == "xyz"
