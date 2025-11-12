"""Unit tests for temporal filter extensions (range, any, contains).

Tests the extended filter functionality for lazy loading optimization:
- Range filters for timestamps (gte, lte, gt, lt)
- Set membership filters (any)
- Substring matching filters (contains)
"""

from unittest.mock import Mock
import pytest
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_store(tmp_path):
    """Create temporary filesystem vector store."""
    store = FilesystemVectorStore(base_path=tmp_path / "vectors", project_root=tmp_path)
    return store


@pytest.fixture
def temporal_store(temp_store):
    """Create store with temporal test data."""
    collection_name = "test_temporal"
    temp_store.create_collection(collection_name, vector_size=4)

    # Add test vectors with temporal metadata
    points = [
        {
            "id": "commit1_file1",
            "vector": [1.0, 0.0, 0.0, 0.0],
            "payload": {
                "path": "src/main.py",
                "language": "python",
                "commit_hash": "abc123",
                "commit_timestamp": 1609459200,  # 2021-01-01
                "author_name": "John Doe",
                "author_email": "john@example.com",
                "diff_type": "added",
            },
        },
        {
            "id": "commit2_file1",
            "vector": [0.9, 0.1, 0.0, 0.0],
            "payload": {
                "path": "src/utils.py",
                "language": "python",
                "commit_hash": "def456",
                "commit_timestamp": 1612137600,  # 2021-02-01
                "author_name": "Jane Smith",
                "author_email": "jane@example.com",
                "diff_type": "modified",
            },
        },
        {
            "id": "commit3_file1",
            "vector": [0.8, 0.2, 0.0, 0.0],
            "payload": {
                "path": "src/test.py",
                "language": "python",
                "commit_hash": "ghi789",
                "commit_timestamp": 1614556800,  # 2021-03-01
                "author_name": "John Doe",
                "author_email": "john@example.com",
                "diff_type": "deleted",
            },
        },
        {
            "id": "commit4_file1",
            "vector": [0.7, 0.3, 0.0, 0.0],
            "payload": {
                "path": "README.md",
                "language": "markdown",
                "commit_hash": "jkl012",
                "commit_timestamp": 1617235200,  # 2021-04-01
                "author_name": "Bob Johnson",
                "author_email": "bob@example.com",
                "diff_type": "modified",
            },
        },
    ]

    temp_store.begin_indexing(collection_name)
    temp_store.upsert_points(collection_name, points)
    temp_store.end_indexing(collection_name)
    return temp_store, collection_name


# ====================================================================
# RANGE FILTER TESTS
# ====================================================================


def test_range_filter_gte_lte(temporal_store):
    """Test range filter with gte and lte (between dates)."""
    store, collection_name = temporal_store

    # Filter: 2021-02-01 <= commit_timestamp <= 2021-03-01
    filter_conditions = {
        "must": [
            {
                "key": "commit_timestamp",
                "range": {
                    "gte": 1612137600,  # 2021-02-01
                    "lte": 1614556800,  # 2021-03-01
                }
            }
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Should return 2 commits in range (Feb 1 and Mar 1)
    assert len(results) == 2
    timestamps = [r["payload"]["commit_timestamp"] for r in results]
    assert 1612137600 in timestamps  # 2021-02-01
    assert 1614556800 in timestamps  # 2021-03-01


# ====================================================================
# SET MEMBERSHIP (ANY) FILTER TESTS
# ====================================================================


def test_any_filter_multiple_matches(temporal_store):
    """Test 'any' filter with multiple matching values."""
    store, collection_name = temporal_store

    # Filter: diff_type in ["added", "modified"]
    filter_conditions = {
        "must": [
            {
                "key": "diff_type",
                "match": {
                    "any": ["added", "modified"]
                }
            }
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Should return 3 results (1 added + 2 modified)
    assert len(results) == 3
    diff_types = [r["payload"]["diff_type"] for r in results]
    assert "added" in diff_types
    assert "modified" in diff_types
    assert "deleted" not in diff_types


# ====================================================================
# SUBSTRING MATCHING (CONTAINS) FILTER TESTS
# ====================================================================


def test_contains_filter_case_insensitive(temporal_store):
    """Test 'contains' filter with case-insensitive substring match."""
    store, collection_name = temporal_store

    # Filter: author_name contains "john" (case-insensitive)
    filter_conditions = {
        "must": [
            {
                "key": "author_name",
                "match": {
                    "contains": "john"
                }
            }
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Should return 3 results (John Doe appears twice, Bob Johnson once)
    assert len(results) == 3
    for result in results:
        assert "john" in result["payload"]["author_name"].lower()
