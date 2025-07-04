"""
Test to reproduce and fix the branch transition logic issue.

This test demonstrates that files are being incorrectly hidden during branch transitions
and provides the fix to ensure files remain visible in branches where they exist.
"""

import pytest
from pathlib import Path
import tempfile
import subprocess

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.smart_indexer import SmartIndexer
from .test_suite_setup import register_test_collection


def test_branch_transition_file_visibility():
    """Test that files remain visible in branches where they exist during transitions."""

    # Skip if no VoyageAI key
    import os

    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required")

    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Create git repository with initial file
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create shared file that exists in both branches
        shared_file = repo_path / "shared.py"
        shared_file.write_text("def shared_function(): return 'shared code'")

        subprocess.run(["git", "add", "shared.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add shared file"], cwd=repo_path, check=True
        )

        # Create test config
        config = Config(
            codebase_dir=str(repo_path),
            embedding_provider="voyage-ai",
            voyage_ai={
                "model": "voyage-code-3",
                "api_endpoint": "https://api.voyageai.com/v1/embeddings",
                "timeout": 30,
                "parallel_requests": 2,
                "batch_size": 8,
                "max_retries": 3,
            },
            qdrant={
                "host": "http://localhost:6333",
                "collection": "test_branch_transition",
                "vector_size": 1024,
                "use_provider_aware_collections": True,
                "collection_base_name": "test_branch_transition",
            },
            indexing={
                "chunk_size": 200,
                "chunk_overlap": 20,
                "file_extensions": [".py"],
            },
        )

        # Initialize services
        embedding_provider = EmbeddingProviderFactory.create(config)
        qdrant_client = QdrantClient(config.qdrant)
        collection_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )
        qdrant_client.clear_collection(collection_name)

        # Register collection for cleanup
        register_test_collection(collection_name)

        # Create indexer
        metadata_path = repo_path / "metadata.json"
        indexer = SmartIndexer(config, embedding_provider, qdrant_client, metadata_path)

        # Step 1: Index on master branch
        print("=== Step 1: Index on master branch ===")
        master_stats = indexer.smart_index(force_full=True)
        print(f"Master indexing: {master_stats.files_processed} files")

        # Verify shared file is visible on master
        query = embedding_provider.get_embedding("shared code")
        master_results = qdrant_client.search_with_branch_topology(
            query_vector=query,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )

        shared_visible_master = any(
            "shared.py" in result.get("payload", {}).get("path", "")
            for result in master_results
        )
        print(f"Shared file visible on master: {shared_visible_master}")
        assert shared_visible_master, "Shared file should be visible on master"

        # Step 2: Create feature branch from master (shared file exists in both)
        print("\n=== Step 2: Create feature branch ===")
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=repo_path, check=True)

        # Add a new file unique to feature branch
        feature_file = repo_path / "feature.py"
        feature_file.write_text("def feature_function(): return 'feature code'")
        subprocess.run(["git", "add", "feature.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add feature file"], cwd=repo_path, check=True
        )

        # Step 3: Index on feature branch (this triggers branch transition logic)
        print("\n=== Step 3: Index on feature branch ===")
        feature_stats = indexer.smart_index()
        print(f"Feature indexing: {feature_stats.files_processed} files")

        # Step 4: Test shared file visibility on feature branch
        print("\n=== Step 4: Test shared file visibility on feature branch ===")
        feature_results = qdrant_client.search_with_branch_topology(
            query_vector=query,
            current_branch="feature",
            limit=10,
            collection_name=collection_name,
        )

        shared_visible_feature = any(
            "shared.py" in result.get("payload", {}).get("path", "")
            for result in feature_results
        )
        print(f"Shared file visible on feature: {shared_visible_feature}")

        # Check the hidden_branches of shared file points
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "content"}},
                    {"key": "path", "match": {"value": "shared.py"}},
                ]
            },
            collection_name=collection_name,
            limit=10,
        )

        print(f"Shared file content points: {len(content_points)}")
        for point in content_points:
            payload = point.get("payload", {})
            hidden_branches = payload.get("hidden_branches", [])
            print(f"  hidden_branches: {hidden_branches}")

        # THIS IS THE KEY TEST: shared file should be visible on feature branch
        # because it exists in both master and feature branches
        assert (
            shared_visible_feature
        ), "Shared file should be visible on feature branch (exists in both branches)"

        # Step 5: Test feature file visibility
        print("\n=== Step 5: Test feature file visibility ===")
        feature_query = embedding_provider.get_embedding("feature code")
        feature_file_results = qdrant_client.search_with_branch_topology(
            query_vector=feature_query,
            current_branch="feature",
            limit=10,
            collection_name=collection_name,
        )

        feature_file_visible = any(
            "feature.py" in result.get("payload", {}).get("path", "")
            for result in feature_file_results
        )
        print(f"Feature file visible on feature: {feature_file_visible}")
        assert feature_file_visible, "Feature file should be visible on feature branch"

        # Step 6: Test isolation - feature file should not be visible on master
        print("\n=== Step 6: Test branch isolation ===")
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)

        # Index on master to trigger branch transition back
        master_stats2 = indexer.smart_index()
        print(f"Master re-indexing: {master_stats2.files_processed} files")

        # Feature file should not be visible on master
        feature_file_on_master = qdrant_client.search_with_branch_topology(
            query_vector=feature_query,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )

        feature_visible_master = any(
            "feature.py" in result.get("payload", {}).get("path", "")
            for result in feature_file_on_master
        )
        print(f"Feature file visible on master: {feature_visible_master}")
        assert (
            not feature_visible_master
        ), "Feature file should NOT be visible on master"

        # But shared file should still be visible on master
        shared_results_master2 = qdrant_client.search_with_branch_topology(
            query_vector=query,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )

        shared_visible_master2 = any(
            "shared.py" in result.get("payload", {}).get("path", "")
            for result in shared_results_master2
        )
        print(f"Shared file still visible on master: {shared_visible_master2}")
        assert shared_visible_master2, "Shared file should still be visible on master"

        print("\n✅ Branch transition logic working correctly!")


if __name__ == "__main__":
    test_branch_transition_file_visibility()
