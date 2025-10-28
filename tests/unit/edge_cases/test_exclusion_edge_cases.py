"""
Edge case tests for language exclusion feature.

These tests verify that language exclusion handles unusual or boundary
conditions correctly.
"""

import pytest
import numpy as np
from unittest.mock import Mock
from click.testing import CliRunner
from pathlib import Path

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.cli import cli


@pytest.fixture
def test_vectors():
    """Generate test vectors."""
    np.random.seed(42)
    return np.random.randn(10, 1536)


def test_exclude_all_languages_returns_empty_results(tmp_path, test_vectors):
    """
    GIVEN a store with only Python and JavaScript files
    WHEN excluding both Python and JavaScript
    THEN no results are returned
    """
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_exclude_all"
    store.create_collection(collection_name, vector_size=1536)

    # Add only Python and JavaScript files
    points = [
        {
            "id": "python_0",
            "vector": test_vectors[0].tolist(),
            "payload": {"path": "test.py", "language": "py", "type": "content"},
        },
        {
            "id": "javascript_0",
            "vector": test_vectors[1].tolist(),
            "payload": {"path": "app.js", "language": "js", "type": "content"},
        },
    ]
    store.upsert_points(collection_name, points)

    # Exclude both languages
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "py"}},
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

    # Should return no results
    assert len(results) == 0, "Should return empty results when all languages excluded"


def test_exclude_unknown_language_has_no_effect(tmp_path, test_vectors):
    """
    GIVEN a store with Python files
    WHEN excluding a language that doesn't exist (e.g., "unknown")
    THEN all Python files are still returned
    """
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_unknown_exclusion"
    store.create_collection(collection_name, vector_size=1536)

    # Add Python files
    points = [
        {
            "id": f"python_{i}",
            "vector": test_vectors[i].tolist(),
            "payload": {"path": f"test_{i}.py", "language": "py", "type": "content"},
        }
        for i in range(3)
    ]
    store.upsert_points(collection_name, points)

    # Exclude non-existent language
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "unknownlang"}},
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

    # Should return all Python files
    assert len(results) == 3, "Should return all files when excluding unknown language"
    for result in results:
        assert result["payload"]["language"] == "py", "Should only contain Python files"


def test_exclude_language_with_multiple_extensions(tmp_path, test_vectors):
    """
    GIVEN a store with Python files (.py, .pyw, .pyi extensions)
    WHEN excluding python language
    THEN all Python extension files are excluded
    """
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_multi_ext"
    store.create_collection(collection_name, vector_size=1536)

    # Add Python files with different extensions + JavaScript
    points = [
        {"id": "python_py", "vector": test_vectors[0].tolist(), "payload": {"path": "main.py", "language": "py", "type": "content"}},
        {"id": "python_pyw", "vector": test_vectors[1].tolist(), "payload": {"path": "gui.pyw", "language": "pyw", "type": "content"}},
        {"id": "python_pyi", "vector": test_vectors[2].tolist(), "payload": {"path": "types.pyi", "language": "pyi", "type": "content"}},
        {"id": "javascript", "vector": test_vectors[3].tolist(), "payload": {"path": "app.js", "language": "js", "type": "content"}},
    ]
    store.upsert_points(collection_name, points)

    # Exclude all Python extensions
    filter_conditions = {
        "must_not": [
            {"key": "language", "match": {"value": "py"}},
            {"key": "language", "match": {"value": "pyw"}},
            {"key": "language", "match": {"value": "pyi"}},
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

    # Should only return JavaScript
    assert len(results) == 1, "Should exclude all Python extensions"
    assert results[0]["id"] == "javascript", "Should only return JavaScript file"
    assert results[0]["payload"]["language"] == "js", "Result should be JavaScript"


def test_exclude_language_case_insensitive_cli(tmp_path):
    """
    GIVEN a query with --exclude-language in mixed case
    WHEN the CLI processes the query
    THEN it correctly handles case-insensitive language names
    """
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Setup minimal config
        Path(".code-indexer").mkdir(exist_ok=True)
        config_path = Path(".code-indexer/config.json")
        config_path.write_text('{"codebase_dir": ".", "embedding_provider": {"provider": "voyageai"}}')

        # Test various case variations
        test_cases = [
            ["query", "test", "--exclude-language", "JavaScript"],
            ["query", "test", "--exclude-language", "PYTHON"],
            ["query", "test", "--exclude-language", "TypeScript"],
        ]

        for args in test_cases:
            # Should not raise validation errors for case variations
            # (This is a smoke test - actual functionality tested elsewhere)
            result = runner.invoke(cli, args, catch_exceptions=False)
            # We don't check exit code here because services may not be running
            # The important thing is it doesn't crash on case variation
            assert "Invalid language" not in result.output, f"Should handle case variation: {args}"


def test_empty_exclusion_list_behaves_like_no_filter(tmp_path, test_vectors):
    """
    GIVEN a store with multiple files
    WHEN searching with empty must_not filter
    THEN all files are returned (no exclusion)
    """
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_empty_exclusion"
    store.create_collection(collection_name, vector_size=1536)

    # Add files
    points = [
        {"id": "python_0", "vector": test_vectors[0].tolist(), "payload": {"path": "test.py", "language": "py"}},
        {"id": "javascript_0", "vector": test_vectors[1].tolist(), "payload": {"path": "app.js", "language": "js"}},
    ]
    store.upsert_points(collection_name, points)

    # Search with empty must_not
    filter_conditions = {"must_not": []}

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

    # Should return all files
    assert len(results) == 2, "Empty must_not should not filter any results"


def test_exclude_same_language_as_include_returns_empty(tmp_path, test_vectors):
    """
    GIVEN a store with Python and JavaScript files
    WHEN including Python AND excluding Python in same query
    THEN no results are returned (contradiction)
    """
    store = FilesystemVectorStore(base_path=tmp_path)
    collection_name = "test_contradiction"
    store.create_collection(collection_name, vector_size=1536)

    # Add files
    points = [
        {"id": "python_0", "vector": test_vectors[0].tolist(), "payload": {"path": "test.py", "language": "py"}},
        {"id": "javascript_0", "vector": test_vectors[1].tolist(), "payload": {"path": "app.js", "language": "js"}},
    ]
    store.upsert_points(collection_name, points)

    # Contradictory filter: must be Python AND must not be Python
    filter_conditions = {
        "must": [{"key": "language", "match": {"value": "py"}}],
        "must_not": [{"key": "language", "match": {"value": "py"}}],
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

    # Should return no results due to contradiction
    assert len(results) == 0, "Contradictory filters should return empty results"
