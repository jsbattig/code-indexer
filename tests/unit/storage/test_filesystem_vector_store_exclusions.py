"""
Test language exclusion filtering in FilesystemVectorStore.

These tests verify that the must_not filter conditions properly exclude
specified languages from search results in the filesystem backend.
"""

import pytest
import numpy as np
from unittest.mock import Mock

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def test_vectors():
    """Generate test vectors for search."""
    np.random.seed(42)
    return np.random.randn(10, 1536)


@pytest.fixture
def populated_store_with_languages(tmp_path, test_vectors):
    """Create a populated store with files from different languages."""
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_language_exclusion"
    store.create_collection(collection_name, vector_size=1536)

    # Add Python files
    points = []
    for i in range(3):
        points.append(
            {
                "id": f"python_{i}",
                "vector": test_vectors[i].tolist(),
                "payload": {
                    "path": f"src/auth_{i}.py",
                    "language": "py",
                    "type": "content",
                },
            }
        )

    # Add JavaScript files
    for i in range(3):
        points.append(
            {
                "id": f"javascript_{i}",
                "vector": test_vectors[i + 3].tolist(),
                "payload": {
                    "path": f"src/app_{i}.js",
                    "language": "js",
                    "type": "content",
                },
            }
        )

    # Add TypeScript files
    for i in range(2):
        points.append(
            {
                "id": f"typescript_{i}",
                "vector": test_vectors[i + 6].tolist(),
                "payload": {
                    "path": f"src/component_{i}.ts",
                    "language": "ts",
                    "type": "content",
                },
            }
        )

    # Add Java file
    points.append(
        {
            "id": "java_0",
            "vector": test_vectors[8].tolist(),
            "payload": {
                "path": "src/Main.java",
                "language": "java",
                "type": "content",
            },
        }
    )

    store.upsert_points(collection_name, points)
    return store, collection_name


def test_exclude_single_language_javascript(
    populated_store_with_languages, test_vectors
):
    """
    GIVEN a store with Python, JavaScript, TypeScript, and Java files
    WHEN searching with must_not filter excluding JavaScript
    THEN no JavaScript files are returned, only Python, TypeScript, and Java
    """
    store, collection_name = populated_store_with_languages

    # Build must_not filter for JavaScript (single extension)
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "js"}},
        ]
    }

    query_vector = test_vectors[0].tolist()
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Verify no JavaScript files in results
    assert len(results) > 0, "Should return some results"
    for result in results:
        assert (
            result["payload"]["language"] != "js"
        ), f"Should not return JavaScript files, got {result['id']}"

    # Verify we got Python, TypeScript, or Java files
    languages_found = {r["payload"]["language"] for r in results}
    assert languages_found.issubset(
        {"py", "ts", "java"}
    ), "Should only return non-JavaScript files"


def test_exclude_multiple_languages(populated_store_with_languages, test_vectors):
    """
    GIVEN a store with multiple language files
    WHEN searching with must_not filter excluding both JavaScript and TypeScript
    THEN only Python and Java files are returned
    """
    store, collection_name = populated_store_with_languages

    # Build must_not filter for JavaScript and TypeScript
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "js"}},
            {"key": "language", "match": {"value": "ts"}},
        ]
    }

    query_vector = test_vectors[0].tolist()
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Verify no JavaScript or TypeScript files in results
    assert len(results) > 0, "Should return some results"
    for result in results:
        language = result["payload"]["language"]
        assert language not in [
            "js",
            "ts",
        ], f"Should not return JS/TS files, got {result['id']} with language {language}"

    # Verify we only got Python and Java files
    languages_found = {r["payload"]["language"] for r in results}
    assert languages_found.issubset(
        {"py", "java"}
    ), "Should only return Python and Java files"


def test_exclude_with_must_conditions_combined(
    populated_store_with_languages, test_vectors
):
    """
    GIVEN a store with multiple language files
    WHEN searching with BOTH must (include) and must_not (exclude) filters
    THEN results match must conditions AND do not match must_not conditions
    """
    store, collection_name = populated_store_with_languages

    # Build filter: must be content type AND must not be JavaScript
    filter_conditions = {
        "must": [
            {"key": "type", "match": {"value": "content"}},
        ],
        "must_not": [
            {"key": "language", "match": {"value": "js"}},
        ],
    }

    query_vector = test_vectors[0].tolist()
    mock_embedding_provider = Mock()
    mock_embedding_provider.get_embedding.return_value = query_vector

    results = store.search(
        query="test query",
        embedding_provider=mock_embedding_provider,
        collection_name=collection_name,
        limit=10,
        filter_conditions=filter_conditions,
    )

    # Verify all results match must conditions
    assert len(results) > 0, "Should return some results"
    for result in results:
        assert (
            result["payload"]["type"] == "content"
        ), "All results should be content type"
        assert result["payload"]["language"] != "js", "No results should be JavaScript"

    # Verify we got non-JavaScript files
    languages_found = {r["payload"]["language"] for r in results}
    assert "js" not in languages_found, "JavaScript should be excluded"
    assert len(languages_found) > 0, "Should have some languages in results"
