"""Test that lazy_load parameter reduces JSON file loads via early exit.

This test verifies Phase 2 - Lazy Loading with Early Exit is properly implemented.
We measure the number of JSON loads for eager vs lazy loading and assert that
lazy loading loads fewer files when early exit is triggered.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class JSONLoadCounter:
    """Context manager to count JSON loads during search."""

    def __init__(self):
        self.load_count = 0
        self.original_open = None

    def __enter__(self):
        """Wrap open() to count JSON loads."""
        import builtins

        self.original_open = builtins.open
        counter = self

        def counting_open(*args, **kwargs):
            # Count BEFORE calling original open (in case it fails)
            if len(args) > 0:
                path_str = str(args[0])
                # Match vector files: vector_point_*.json (but not collection_meta.json)
                if "vector_point_" in path_str and path_str.endswith(".json"):
                    counter.load_count += 1
            result = counter.original_open(*args, **kwargs)
            return result

        builtins.open = counting_open
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore original open()."""
        import builtins

        builtins.open = self.original_open


@pytest.fixture
def store_with_many_vectors():
    """Create a store with 100 indexed vectors for testing lazy loading."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_path = Path(tmpdir)
        store = FilesystemVectorStore(base_path=base_path)

        collection_name = "test_collection"
        store.create_collection(collection_name=collection_name, vector_size=768)

        # Add 100 vectors with different languages
        points = []
        for i in range(100):
            vector = np.random.rand(768).tolist()
            # First 50 are Python, next 50 are JavaScript
            language = "python" if i < 50 else "javascript"

            points.append(
                {
                    "id": f"point_{i}",
                    "vector": vector,
                    "payload": {
                        "file_path": f"/test/file_{i}.{language}",
                        "language": language,
                        "chunk_text": f"Test content {i}",
                        "blob_hash": f"hash_{i}",
                    },
                }
            )

        store.upsert_points(collection_name=collection_name, points=points)

        # Build HNSW index
        from code_indexer.storage.hnsw_index_manager import HNSWIndexManager

        collection_path = base_path / collection_name
        hnsw_manager = HNSWIndexManager(vector_dim=768, space="cosine")
        hnsw_manager.rebuild_from_vectors(
            collection_path=collection_path, progress_callback=None
        )

        yield store, collection_name


def test_lazy_load_reduces_json_loads(store_with_many_vectors):
    """Test that lazy_load=True loads fewer JSON files than lazy_load=False.

    Phase 2 - Lazy Loading with Early Exit Implementation Test.

    This test proves that lazy loading with early exit actually reduces I/O:
    1. Search with lazy_load=False (eager) -> loads many JSONs
    2. Search with lazy_load=True (lazy) -> loads fewer JSONs due to early exit
    3. Assert lazy loading loads fewer files

    The early exit should trigger when we have enough results (limit=5),
    so we shouldn't need to load all 100 vector files.
    """
    store, collection_name = store_with_many_vectors

    # Create mock embedding provider with deterministic query vector
    mock_provider = MagicMock()
    # Use a query vector that will match some results
    query_vector = np.random.rand(768).tolist()
    mock_provider.get_embedding.return_value = query_vector

    limit = 5  # We only need 5 results

    # === TEST 1: Eager loading (lazy_load=False) ===
    with JSONLoadCounter() as eager_counter:
        results_eager = store.search(
            query="test query",
            embedding_provider=mock_provider,
            collection_name=collection_name,
            limit=limit,
            lazy_load=False,  # Eager loading
        )

    eager_json_loads = eager_counter.load_count

    # === TEST 2: Lazy loading (lazy_load=True) ===
    with JSONLoadCounter() as lazy_counter:
        results_lazy = store.search(
            query="test query",
            embedding_provider=mock_provider,
            collection_name=collection_name,
            limit=limit,
            lazy_load=True,  # Lazy loading with early exit
            prefetch_limit=50,  # Prefetch 50 candidates
        )

    lazy_json_loads = lazy_counter.load_count

    # === ASSERTIONS ===
    # Both should return the same number of results
    assert len(results_eager) == limit
    assert len(results_lazy) == limit

    # CRITICAL: Lazy loading should load FEWER JSON files than eager loading
    # Eager loading loads all candidates (50 from prefetch with limit*2)
    # Lazy loading should early exit after finding 5 results
    assert (
        lazy_json_loads < eager_json_loads
    ), f"Lazy loading should reduce JSON loads: lazy={lazy_json_loads}, eager={eager_json_loads}"

    # Lazy loading should load at most slightly more than limit (due to prefetch ordering)
    # With good HNSW ordering, we should hit limit quickly
    assert (
        lazy_json_loads <= limit * 2
    ), f"Lazy loading should early exit near limit: loaded {lazy_json_loads}, limit={limit}"

    print(f"✓ Eager loading: {eager_json_loads} JSON files loaded")
    print(f"✓ Lazy loading: {lazy_json_loads} JSON files loaded")
    print(f"✓ Reduction: {eager_json_loads - lazy_json_loads} fewer JSON loads")
    print(f"✓ Lazy loading reduces I/O by {100 * (1 - lazy_json_loads / eager_json_loads):.1f}%")
