"""
Test for the QdrantClient clear_collection bug.

This test reproduces the issue where clean-data fails because clear_collection
uses the wrong HTTP method and endpoint for clearing collection points.
"""

import os
import json
import subprocess
import pytest
from unittest.mock import Mock, patch

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig
from .conftest import local_temporary_directory
from .test_infrastructure import auto_register_project_collections


@pytest.fixture
def qdrant_test_repo():
    """Create a test repository for Qdrant testing."""
    with local_temporary_directory() as temp_dir:
        # Auto-register collections for cleanup
        auto_register_project_collections(temp_dir)

        # Preserve .code-indexer directory if it exists
        config_dir = temp_dir / ".code-indexer"
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

        yield temp_dir


def create_qdrant_config(test_dir):
    """Create configuration for Qdrant test."""
    config_dir = test_dir / ".code-indexer"
    config_file = config_dir / "config.json"

    # Load existing config if it exists (preserves container ports)
    if config_file.exists():
        with open(config_file, "r") as f:
            config = json.load(f)
    else:
        config = {
            "codebase_dir": str(test_dir),
            "qdrant": {
                "host": "http://localhost:6333",
                "collection": "test_collection",
                "vector_size": 1024,
            },
        }

    # Only modify test-specific settings, preserve container configuration
    config["embedding_provider"] = "ollama"
    config["ollama"] = {
        "host": "http://localhost:11434",
        "model": "nomic-embed-text",
        "timeout": 30,
    }

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    return config_file


@pytest.mark.slow
@pytest.mark.qdrant
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_clear_collection_uses_correct_http_method():
    """
    Test that clear_collection uses the correct HTTP method and endpoint.

    This test reproduces the bug where clear_collection fails because it uses:
    - DELETE /collections/{collection}/points?filter={}

    Instead of the correct Qdrant API:
    - POST /collections/{collection}/points/delete with JSON body {"filter": {}}
    """
    # Setup
    config = QdrantConfig(
        host="http://localhost:6333", collection="test_collection", vector_size=1024
    )
    client = QdrantClient(config)

    # Mock the HTTP client to capture the actual calls being made
    with patch.object(client, "client") as mock_http_client:
        # Setup mock responses
        mock_response = Mock()
        mock_response.status_code = 200
        mock_http_client.delete.return_value = mock_response
        mock_http_client.post.return_value = mock_response

        # Call clear_collection
        result = client.clear_collection("test_collection")

        # Verify the result
        assert result is True, "clear_collection should return True on success"

        # The bug: verify what HTTP method was actually called
        # Currently, clear_collection incorrectly uses DELETE with params
        if mock_http_client.delete.called:
            # This is the buggy behavior - using DELETE
            args, kwargs = mock_http_client.delete.call_args
            assert args[0] == "/collections/test_collection/points"
            assert kwargs.get("params") == {"filter": "{}"}
            pytest.fail(
                "BUG REPRODUCED: clear_collection uses DELETE method with query params. "
                "Should use POST to /collections/{collection}/points/delete with JSON body."
            )

        # This is what should happen (correct behavior)
        if mock_http_client.post.called:
            args, kwargs = mock_http_client.post.call_args
            assert args[0] == "/collections/test_collection/points/delete"
            assert kwargs.get("json") == {"filter": {}}
            # If we get here, the bug is fixed


@pytest.mark.slow
@pytest.mark.qdrant
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_clear_collection_integration_with_real_qdrant(qdrant_test_repo):
    """
    Integration test that reproduces the actual failure with real Qdrant.

    This test creates a collection, adds some points, then tries to clear it.
    With the bug, clear_collection returns False. After the fix, it should return True.
    """
    test_dir = qdrant_test_repo

    # Create configuration
    create_qdrant_config(test_dir)

    # Initialize project
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "ollama", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Start services if needed
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # Allow start to fail if services are already running
    if start_result.returncode != 0:
        if (
            "already in use" not in start_result.stdout
            and "already running" not in start_result.stdout
        ):
            assert False, f"Start failed: {start_result.stderr}"

    # Setup
    config = QdrantConfig(
        host="http://localhost:6333",
        collection="test_clear_bug_collection",
        vector_size=1024,
    )
    client = QdrantClient(config)
    collection_name = "test_clear_bug_collection"

    try:
        # Clean up any existing collection first
        try:
            client.client.delete(f"/collections/{collection_name}")
        except Exception:
            pass  # Collection might not exist

        # Create a test collection
        create_result = client.create_collection(collection_name, vector_size=1024)
        assert create_result is True, "Should be able to create test collection"

        # Add a test point to the collection
        test_point = {
            "id": 1,  # Use integer ID as required by Qdrant
            "vector": [0.1] * 1024,
            "payload": {"test": "data"},
        }

        # Use direct HTTP call to add point (to avoid other potential bugs)
        response = client.client.put(
            f"/collections/{collection_name}/points", json={"points": [test_point]}
        )
        assert response.status_code == 200, f"Failed to add test point: {response.text}"

        # Verify the point was added
        info_response = client.client.get(f"/collections/{collection_name}")
        assert info_response.status_code == 200
        points_count = info_response.json()["result"]["points_count"]
        assert points_count > 0, "Collection should have points before clearing"

        # Now test clear_collection - this is where the bug manifests
        clear_result = client.clear_collection(collection_name)

        # With the bug, this assertion will fail
        assert clear_result is True, (
            "clear_collection should return True when successfully clearing points. "
            "If this fails, the bug is reproduced - clear_collection is using wrong HTTP method."
        )

        # Verify the collection is actually empty
        info_response = client.client.get(f"/collections/{collection_name}")
        assert info_response.status_code == 200
        points_count = info_response.json()["result"]["points_count"]
        assert points_count == 0, "Collection should be empty after clearing"

    finally:
        # Clean up test collection
        try:
            client.client.delete(f"/collections/{collection_name}")
        except Exception:
            pass  # Best effort cleanup

        # Clean up project data
        try:
            subprocess.run(
                ["code-indexer", "clean-data"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception:
            pass  # Best effort cleanup


@pytest.mark.slow
@pytest.mark.qdrant
@pytest.mark.skipif(
    os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true",
    reason="E2E tests require Docker services which are not available in CI",
)
def test_clean_data_failure_scenario():
    """
    Test that reproduces the exact scenario that causes clean-data to fail.

    This test simulates having multiple collections (like from tests) and shows
    that clear_all_collections fails when any single collection fails to clear.
    """
    # Setup
    config = QdrantConfig(
        host="http://localhost:6333", collection="test_collection", vector_size=1024
    )
    client = QdrantClient(config)

    # Mock collections list with one that exists and one that doesn't
    collections_response = {
        "result": {
            "collections": [
                {"name": "existing_collection"},
                {"name": "nonexistent_collection"},
            ]
        }
    }

    with patch.object(client.client, "get") as mock_get, patch.object(
        client, "clear_collection"
    ) as mock_clear:

        # Mock the collections list call
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = collections_response
        mock_get.return_value = mock_response

        # Mock clear_collection to fail for nonexistent collection (reproducing the bug)
        def mock_clear_side_effect(collection_name):
            if collection_name == "nonexistent_collection":
                return False  # This is what happens with the bug
            return True

        mock_clear.side_effect = mock_clear_side_effect

        # Call clear_all_collections
        result = client.clear_all_collections()

        # With the bug, this fails because one collection can't be cleared
        assert result is False, (
            "clear_all_collections should fail when any collection fails to clear. "
            "This reproduces the clean-data issue."
        )

        # Verify that clear_collection was called for both collections
        assert mock_clear.call_count == 2
        mock_clear.assert_any_call("existing_collection")
        mock_clear.assert_any_call("nonexistent_collection")
