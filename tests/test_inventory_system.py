"""
Test to validate the TestProjectInventory system works correctly.
"""

import json
import tempfile
from pathlib import Path


from .test_infrastructure import (
    TestProjectInventory,
    create_test_project_with_inventory,
)


def test_inventory_creates_isolated_configs():
    """Test that inventory system creates isolated configurations."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create reconcile project
        reconcile_dir = temp_path / "reconcile_test"
        reconcile_dir.mkdir()
        config_file1 = create_test_project_with_inventory(
            reconcile_dir, TestProjectInventory.RECONCILE
        )

        # Create branch topology project
        branch_dir = temp_path / "branch_test"
        branch_dir.mkdir()
        config_file2 = create_test_project_with_inventory(
            branch_dir, TestProjectInventory.BRANCH_TOPOLOGY
        )

        # Verify both configs exist
        assert config_file1.exists()
        assert config_file2.exists()

        # Verify they have different collection names
        with open(config_file1) as f:
            config1 = json.load(f)
        with open(config_file2) as f:
            config2 = json.load(f)

        collection1 = config1["qdrant"]["collection_base_name"]
        collection2 = config2["qdrant"]["collection_base_name"]

        assert collection1 != collection2
        assert collection1 == "reconcile_test_collection"
        assert collection2 == "test_branch_topology_clean"

        # Verify both use voyage-ai
        assert config1["embedding_provider"] == "voyage-ai"
        assert config2["embedding_provider"] == "voyage-ai"

        # Verify they have different codebase_dir
        assert config1["codebase_dir"] == str(reconcile_dir)
        assert config2["codebase_dir"] == str(branch_dir)


def test_inventory_includes_all_collections():
    """Test that all test collections are included for cleanup."""
    collections = TestProjectInventory.get_all_test_collections()

    expected_collections = [
        "test_branch_topology_clean",
        "reconcile_test_collection",
        "test_timestamp_comparison",
        "test_cli_progress",
        "test_watch",
        "test_deletion",
        "test_claude",
        "test_e2e_complete",
        "start_stop_test_collection",
        "test_default",
    ]

    for expected in expected_collections:
        assert expected in collections, f"Missing collection: {expected}"


def test_inventory_config_structure():
    """Test that inventory configs have required structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        config_file = create_test_project_with_inventory(
            temp_path, TestProjectInventory.BRANCH_TOPOLOGY
        )

        with open(config_file) as f:
            config = json.load(f)

        # Verify required sections exist
        assert "codebase_dir" in config
        assert "embedding_provider" in config
        assert "qdrant" in config
        assert "voyage_ai" in config
        assert "indexing" in config

        # Verify qdrant section
        qdrant_config = config["qdrant"]
        assert "vector_size" in qdrant_config
        assert "collection_base_name" in qdrant_config

        # Verify values
        assert config["embedding_provider"] == "voyage-ai"
        assert qdrant_config["vector_size"] == 1024
