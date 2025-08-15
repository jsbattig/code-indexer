"""
Test for the QdrantClient clear_collection bug.

This test reproduces the issue where clean-data fails because clear_collection
uses the wrong HTTP method and endpoint for clearing collection points.
"""

import os
import subprocess
import pytest
from unittest.mock import Mock, patch

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig
from ...conftest import local_temporary_directory
from ..infrastructure.test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


@pytest.fixture
def qdrant_test_repo():
    """Create a test repository for Qdrant testing."""
    with local_temporary_directory() as temp_dir:
        # Auto-register collections for cleanup
        create_test_project_with_inventory(
            temp_dir, TestProjectInventory.QDRANT_CLEAR_COLLECTION_BUG
        )

        # Preserve .code-indexer directory if it exists
        config_dir = temp_dir / ".code-indexer"
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

        yield temp_dir


# Removed create_qdrant_config function - tests should use shared infrastructure only


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
@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
def test_clear_collection_integration_with_real_qdrant(qdrant_test_repo):
    """
    Integration test that reproduces the actual failure with real Qdrant.

    This test creates a collection, adds some points, then tries to clear it.
    With the bug, clear_collection returns False. After the fix, it should return True.
    """
    test_dir = qdrant_test_repo

    # DO NOT manually create config - use shared test infrastructure only
    # The inventory system already created proper config with dynamic ports

    # Initialize project with VoyageAI to match shared container setup
    init_result = subprocess.run(
        ["code-indexer", "init", "--embedding-provider", "voyage-ai", "--force"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert init_result.returncode == 0, f"Init failed: {init_result.stderr}"

    # Start services - be idempotent if they're already running
    start_result = subprocess.run(
        ["code-indexer", "start"],
        cwd=test_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # If start fails, check if services are already running
    if start_result.returncode != 0:
        # Check status to see if services are healthy
        status_result = subprocess.run(
            ["code-indexer", "status"],
            cwd=test_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )

        # If services are not running, skip the test
        if status_result.returncode != 0 or "✅" not in status_result.stdout:
            # Check for various infrastructure issues that require skipping
            if (
                "Failed to create/validate collection" in start_result.stdout
                or "Collection creation failed" in start_result.stdout
                or "Can't create directory for collection" in start_result.stdout
                or "Connection refused" in start_result.stderr
                or "Port already in use" in start_result.stderr
                or "Address already in use" in start_result.stderr
                or "No such container" in start_result.stderr
                or "resource temporarily unavailable" in start_result.stderr.lower()
                or "Cannot allocate memory" in start_result.stderr
                or "Container failed to start" in start_result.stdout
                or "Cannot connect to the Docker daemon" in start_result.stderr
                or "podman" in start_result.stderr.lower()
                and "not found" in start_result.stderr.lower()
            ):
                pytest.skip(
                    f"Infrastructure issue: Resource contention or container conflict during full-automation - {start_result.stdout[:200]}...{start_result.stderr[:200]}"
                )
            pytest.skip(
                f"Could not start services: {start_result.stdout} | {start_result.stderr}"
            )

    # Additional validation - ensure we can actually connect to Qdrant
    # before attempting collection operations
    from code_indexer.config import ConfigManager

    config_manager = ConfigManager()
    config_manager.project_root = test_dir
    app_config = config_manager.load()

    # Quick connectivity test
    import httpx

    try:
        response = httpx.get(f"{app_config.qdrant.host}/collections", timeout=5.0)
        if response.status_code != 200:
            pytest.skip(
                f"Qdrant service not responding properly: HTTP {response.status_code}"
            )
    except Exception as e:
        pytest.skip(
            f"Cannot connect to Qdrant service at {app_config.qdrant.host}: {e}"
        )

    # Give services a moment to stabilize
    import time

    time.sleep(2)

    # Setup - read actual config to get the correct port
    from code_indexer.config import ConfigManager

    config_manager = ConfigManager()
    config_manager.project_root = test_dir
    app_config = config_manager.load()

    # Create QdrantClient using the actual configuration
    print(f"DEBUG: Qdrant config host: {app_config.qdrant.host}")
    print(f"DEBUG: Qdrant config: {app_config.qdrant}")
    client = QdrantClient(app_config.qdrant, project_root=test_dir)
    collection_name = "test_clear_bug_collection"

    try:
        # Clean up any existing collection first
        try:
            client.client.delete(f"/collections/{collection_name}")
        except Exception:
            pass  # Collection might not exist

        # Create a test collection with retry logic for resource contention
        max_retries = 3
        create_result = False
        for attempt in range(max_retries):
            try:
                create_result = client.create_collection(
                    collection_name, vector_size=1024
                )
                if create_result:
                    break
            except Exception as e:
                if "Connection refused" in str(e) or "Connection reset" in str(e):
                    if attempt < max_retries - 1:
                        import time

                        time.sleep(2**attempt)  # Exponential backoff
                        continue
                    pytest.skip(
                        f"Infrastructure issue: Qdrant connection unavailable after {max_retries} attempts - {e}"
                    )
                raise

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

    with (
        patch.object(client.client, "get") as mock_get,
        patch.object(client, "clear_collection") as mock_clear,
    ):

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
