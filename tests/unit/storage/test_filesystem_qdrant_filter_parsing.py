"""Unit tests for Qdrant filter parsing in FilesystemVectorStore.

Tests that FilesystemVectorStore correctly parses Qdrant-style filter conditions
to be a true drop-in replacement for QdrantClient.
"""

import json
from pathlib import Path
import pytest
import numpy as np
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_store(tmp_path):
    """Create temporary filesystem vector store."""
    store = FilesystemVectorStore(base_path=tmp_path / "vectors", project_root=tmp_path)
    return store


@pytest.fixture
def populated_store(temp_store):
    """Create store with test data."""
    # Create collection
    collection_name = "test_collection"
    temp_store.create_collection(collection_name, vector_size=4)

    # Add test vectors with different payloads
    points = [
        {
            'id': 'python_file1',
            'vector': [1.0, 0.0, 0.0, 0.0],
            'payload': {
                'path': 'src/test.py',
                'language': 'python',
                'git_available': True,
                'type': 'content'
            }
        },
        {
            'id': 'python_file2',
            'vector': [0.9, 0.1, 0.0, 0.0],
            'payload': {
                'path': 'src/main.py',
                'language': 'python',
                'git_available': True,
                'type': 'content'
            }
        },
        {
            'id': 'js_file',
            'vector': [0.8, 0.2, 0.0, 0.0],
            'payload': {
                'path': 'app.js',
                'language': 'javascript',
                'git_available': False,
                'type': 'content'
            }
        },
        {
            'id': 'python_test',
            'vector': [0.7, 0.3, 0.0, 0.0],
            'payload': {
                'path': 'tests/test_foo.py',
                'language': 'python',
                'git_available': False,
                'type': 'test'
            }
        }
    ]

    temp_store.upsert_points(collection_name, points)
    return temp_store, collection_name


def test_qdrant_filter_single_must_condition(populated_store):
    """Test Qdrant-style filter with single must condition."""
    store, collection_name = populated_store

    # Qdrant-style filter: language = python
    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "python"}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 3 python files
    assert len(results) == 3
    for result in results:
        assert result['payload']['language'] == 'python'


def test_qdrant_filter_multiple_must_conditions(populated_store):
    """Test Qdrant-style filter with multiple must conditions (AND)."""
    store, collection_name = populated_store

    # Qdrant-style filter: language = python AND git_available = True
    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "python"}},
            {"key": "git_available", "match": {"value": True}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 2 python files with git_available=True
    assert len(results) == 2
    for result in results:
        assert result['payload']['language'] == 'python'
        assert result['payload']['git_available'] is True


def test_qdrant_filter_should_conditions(populated_store):
    """Test Qdrant-style filter with should conditions (OR)."""
    store, collection_name = populated_store

    # Qdrant-style filter: language = python OR language = javascript
    filter_conditions = {
        "should": [
            {"key": "language", "match": {"value": "python"}},
            {"key": "language", "match": {"value": "javascript"}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return all 4 files (3 python + 1 javascript)
    assert len(results) == 4


def test_qdrant_filter_must_not_conditions(populated_store):
    """Test Qdrant-style filter with must_not conditions (NOT)."""
    store, collection_name = populated_store

    # Qdrant-style filter: NOT git_available = False
    filter_conditions = {
        "must_not": [
            {"key": "git_available", "match": {"value": False}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 2 files with git_available=True
    assert len(results) == 2
    for result in results:
        assert result['payload']['git_available'] is True


def test_qdrant_filter_combined_conditions(populated_store):
    """Test Qdrant-style filter with combined must and should."""
    store, collection_name = populated_store

    # Qdrant-style filter: git_available = True AND (language = python OR language = javascript)
    filter_conditions = {
        "must": [
            {"key": "git_available", "match": {"value": True}}
        ],
        "should": [
            {"key": "language", "match": {"value": "python"}},
            {"key": "language", "match": {"value": "javascript"}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 2 python files with git_available=True
    assert len(results) == 2
    for result in results:
        assert result['payload']['git_available'] is True
        assert result['payload']['language'] == 'python'


def test_qdrant_filter_no_filter(populated_store):
    """Test that search works without filters."""
    store, collection_name = populated_store

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=None
    )

    # Should return all 4 files
    assert len(results) == 4


def test_qdrant_filter_empty_filter(populated_store):
    """Test that empty filter returns all results."""
    store, collection_name = populated_store

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions={}
    )

    # Should return all 4 files
    assert len(results) == 4


def test_qdrant_filter_no_matches(populated_store):
    """Test filter that matches nothing."""
    store, collection_name = populated_store

    # Filter for non-existent language
    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "rust"}}
        ]
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 0 results
    assert len(results) == 0


def test_parse_qdrant_filter_method_exists():
    """Test that _parse_qdrant_filter method exists."""
    store = FilesystemVectorStore(base_path=Path("/tmp/test"), project_root=Path("/tmp"))
    assert hasattr(store, '_parse_qdrant_filter')


def test_parse_qdrant_filter_returns_callable():
    """Test that _parse_qdrant_filter returns a callable."""
    store = FilesystemVectorStore(base_path=Path("/tmp/test"), project_root=Path("/tmp"))

    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "python"}}
        ]
    }

    filter_func = store._parse_qdrant_filter(filter_conditions)
    assert callable(filter_func)


def test_parse_qdrant_filter_evaluates_correctly():
    """Test that parsed filter evaluates payloads correctly."""
    store = FilesystemVectorStore(base_path=Path("/tmp/test"), project_root=Path("/tmp"))

    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "python"}},
            {"key": "git_available", "match": {"value": True}}
        ]
    }

    filter_func = store._parse_qdrant_filter(filter_conditions)

    # Matching payload
    payload1 = {"language": "python", "git_available": True}
    assert filter_func(payload1) is True

    # Non-matching payload (wrong language)
    payload2 = {"language": "javascript", "git_available": True}
    assert filter_func(payload2) is False

    # Non-matching payload (wrong git_available)
    payload3 = {"language": "python", "git_available": False}
    assert filter_func(payload3) is False


def test_scroll_points_with_qdrant_filters(populated_store):
    """Test that scroll_points also works with Qdrant filters."""
    store, collection_name = populated_store

    # This should also use Qdrant filter parser
    filter_conditions = {
        "must": [
            {"key": "language", "match": {"value": "python"}}
        ]
    }

    points, next_offset = store.scroll_points(
        collection_name=collection_name,
        limit=100,
        filter_conditions=filter_conditions
    )

    # Should return 3 python files
    assert len(points) == 3
    for point in points:
        assert point['payload']['language'] == 'python'


def test_flat_dict_filter_format_backward_compatibility(populated_store):
    """Test that flat dict filters still work for backward compatibility."""
    store, collection_name = populated_store

    # Flat dict filter (legacy format)
    filter_conditions = {
        "language": "python"
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 3 python files
    assert len(results) == 3
    for result in results:
        assert result['payload']['language'] == 'python'


def test_flat_dict_filter_multiple_conditions(populated_store):
    """Test flat dict filter with multiple conditions (AND logic)."""
    store, collection_name = populated_store

    # Flat dict filter: language = python AND git_available = True
    filter_conditions = {
        "language": "python",
        "git_available": True
    }

    query_vector = [1.0, 0.0, 0.0, 0.0]
    results = store.search(
        query_vector=query_vector,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions
    )

    # Should return 2 python files with git_available=True
    assert len(results) == 2
    for result in results:
        assert result['payload']['language'] == 'python'
        assert result['payload']['git_available'] is True
