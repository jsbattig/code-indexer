"""
Test to reproduce and fix the search_with_branch_topology method issue.

This test demonstrates that search_with_branch_topology is using the wrong architecture
and needs to be fixed to use the hidden_branches approach instead of visibility points.
"""

import pytest
from pathlib import Path
import tempfile
import subprocess

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.smart_indexer import SmartIndexer


def test_search_with_branch_topology_hidden_branches_architecture():
    """Test that search_with_branch_topology works with hidden_branches architecture."""

    # Skip if no VoyageAI key
    import os

    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required")

    with tempfile.TemporaryDirectory() as temp_dir:
        repo_path = Path(temp_dir)

        # Create a simple git repository
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create initial file
        main_file = repo_path / "main.py"
        main_file.write_text("def hello(): return 'Hello World'")

        subprocess.run(["git", "add", "main.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
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
                "collection": "test_search_fix",
                "vector_size": 1024,
                "use_provider_aware_collections": True,
                "collection_base_name": "test_search_fix",
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

        # Clear collection to start fresh
        collection_name = qdrant_client.resolve_collection_name(
            config, embedding_provider
        )
        qdrant_client.clear_collection(collection_name)

        # Create indexer
        metadata_path = repo_path / "metadata.json"
        indexer = SmartIndexer(config, embedding_provider, qdrant_client, metadata_path)

        # Index on master branch
        print("Indexing on master branch...")
        stats = indexer.smart_index(force_full=True)
        assert stats.files_processed > 0

        # Verify content exists
        total_points = qdrant_client.count_points(collection_name)
        print(f"Total points after indexing: {total_points}")
        assert total_points > 0

        # Check the structure of content points
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=10,
        )

        print(f"Found {len(content_points)} content points")
        assert len(content_points) > 0

        # Verify content points have hidden_branches architecture
        for point in content_points:
            payload = point.get("payload", {})
            print(f"Content point structure: {list(payload.keys())}")
            assert payload.get("type") == "content"
            assert (
                "hidden_branches" in payload
            ), "Content points must have hidden_branches field"
            assert isinstance(
                payload["hidden_branches"], list
            ), "hidden_branches must be a list"
            assert (
                "master" not in payload["hidden_branches"]
            ), "Content should be visible in master branch"

        # Test search_with_branch_topology method
        print("Testing search_with_branch_topology method...")

        query_vector = embedding_provider.get_embedding("Hello World")

        # This should work with the fixed implementation
        search_results = qdrant_client.search_with_branch_topology(
            query_vector=query_vector,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )

        print(f"Search results: {len(search_results)}")
        for result in search_results:
            payload = result.get("payload", {})
            print(
                f"Found result: {payload.get('path', 'unknown')} (score: {result.get('score', 0)})"
            )

        # This should find the content
        assert (
            len(search_results) > 0
        ), "search_with_branch_topology should find content in master branch"

        # Verify the returned content is correct
        main_py_found = any(
            result.get("payload", {}).get("path", "").endswith("main.py")
            for result in search_results
        )
        assert main_py_found, "Should find main.py content"

        print(
            "✅ Test passed - search_with_branch_topology works with hidden_branches architecture"
        )


if __name__ == "__main__":
    test_search_with_branch_topology_hidden_branches_architecture()
