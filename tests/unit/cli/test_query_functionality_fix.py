#!/usr/bin/env python3
"""
Test suite for the cidx query functionality fix.

This test validates that the query system works correctly after fixing
the git-aware filtering that was broken during BranchAwareIndexer removal.
"""

import pytest
from pathlib import Path
from typing import Any
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from code_indexer.config import ConfigManager
from code_indexer.services import QdrantClient, EmbeddingProviderFactory


@pytest.fixture
def query_services():
    """Initialize query services for testing."""
    # Load config
    config_manager = ConfigManager()
    config = config_manager.load()

    # Initialize services
    qdrant_client = QdrantClient(config.qdrant, None, Path(config.codebase_dir))
    embedding_provider = EmbeddingProviderFactory.create(config, None)

    return config, qdrant_client, embedding_provider


def test_basic_query_functionality(query_services):
    """Test that basic query without filters returns results."""
    config, qdrant_client, embedding_provider = query_services

    # Get collection name
    collection_name = qdrant_client.resolve_collection_name(config, embedding_provider)

    # Verify collection has data
    collection_info = qdrant_client.get_collection_info(collection_name)
    points_count = collection_info.get("points_count", 0)
    assert points_count > 0, f"Expected indexed data but found {points_count} points"

    # Test basic search without filters
    query_embedding = embedding_provider.get_embedding("test query")
    basic_filter: dict[str, Any] = {}  # No filtering

    results = qdrant_client.search(
        query_vector=query_embedding,
        filter_conditions=basic_filter,
        limit=5,
        collection_name=collection_name,
    )

    # Should return results
    assert len(results) > 0, "Basic search should return results"

    # Verify result structure
    result = results[0]
    assert "payload" in result
    assert "score" in result
    payload = result["payload"]

    # Verify expected payload fields exist
    expected_fields = ["path", "content", "git_available", "git_branch"]
    for field in expected_fields:
        assert field in payload, f"Expected field '{field}' in payload"


def test_git_aware_filtering_works(query_services):
    """Test that git-aware filtering returns results (the main fix)."""
    config, qdrant_client, embedding_provider = query_services

    # Get collection name
    collection_name = qdrant_client.resolve_collection_name(config, embedding_provider)

    # Test git-aware filter - this was broken before the fix
    current_branch = "master"
    git_filter_conditions = {
        "must": [
            # Match content from the current branch
            {"key": "git_branch", "match": {"value": current_branch}},
            # Ensure git is available (exclude non-git content)
            {"key": "git_available", "match": {"value": True}},
        ],
    }

    query_embedding = embedding_provider.get_embedding("test")

    results = qdrant_client.search(
        query_vector=query_embedding,
        filter_conditions=git_filter_conditions,
        limit=5,
        collection_name=collection_name,
    )

    # This should return results now (it was returning 0 before the fix)
    assert len(results) > 0, "Git-aware filtering should return results"

    # Verify all results are from the correct branch
    for result in results:
        payload = result["payload"]
        assert payload.get("git_branch") == current_branch
        assert payload.get("git_available") is True


def test_language_filtering_works(query_services):
    """Test that language filtering works correctly."""
    config, qdrant_client, embedding_provider = query_services

    # Get collection name
    collection_name = qdrant_client.resolve_collection_name(config, embedding_provider)

    # Test language filter
    current_branch = "master"
    language_filter_conditions = {
        "must": [
            {"key": "git_branch", "match": {"value": current_branch}},
            {"key": "git_available", "match": {"value": True}},
            {"key": "language", "match": {"value": "py"}},  # Python files only
        ],
    }

    query_embedding = embedding_provider.get_embedding("test")

    results = qdrant_client.search(
        query_vector=query_embedding,
        filter_conditions=language_filter_conditions,
        limit=5,
        collection_name=collection_name,
    )

    # Should return Python files only
    assert len(results) > 0, "Language filtering should return Python results"

    # Verify all results are Python files
    for result in results:
        payload = result["payload"]
        assert payload.get("language") == "py"


def test_old_filter_conditions_fail(query_services):
    """Test that the old (broken) filter conditions return no results."""
    config, qdrant_client, embedding_provider = query_services

    # Get collection name
    collection_name = qdrant_client.resolve_collection_name(config, embedding_provider)

    # Test the OLD broken filter conditions
    current_branch = "master"
    old_broken_filter = {
        "must": [
            {"key": "type", "match": {"value": "content"}},  # This field doesn't exist
        ],
        "must_not": [
            {
                "key": "hidden_branches",
                "match": {"any": [current_branch]},
            },  # This field doesn't exist
        ],
    }

    query_embedding = embedding_provider.get_embedding("test")

    results = qdrant_client.search(
        query_vector=query_embedding,
        filter_conditions=old_broken_filter,
        limit=5,
        collection_name=collection_name,
    )

    # The old filter should return 0 results because the fields don't exist
    assert len(results) == 0, "Old broken filter conditions should return no results"


def test_data_schema_validation(query_services):
    """Test that the actual data schema matches expectations."""
    config, qdrant_client, embedding_provider = query_services

    # Get collection name
    collection_name = qdrant_client.resolve_collection_name(config, embedding_provider)

    # Get sample results to check schema
    query_embedding = embedding_provider.get_embedding("test")
    basic_filter: dict[str, Any] = {}

    results = qdrant_client.search(
        query_vector=query_embedding,
        filter_conditions=basic_filter,
        limit=3,
        collection_name=collection_name,
    )

    assert len(results) > 0
    payload = results[0]["payload"]

    # Verify the data schema is as expected (not the old schema)
    assert "type" not in payload, "Old 'type' field should not exist in data"
    assert (
        "hidden_branches" not in payload
    ), "Old 'hidden_branches' field should not exist"

    # Verify the new schema fields exist
    assert "git_branch" in payload, "New 'git_branch' field should exist"
    assert "git_available" in payload, "New 'git_available' field should exist"
    assert "path" in payload, "Path field should exist"
    assert "content" in payload, "Content field should exist"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
