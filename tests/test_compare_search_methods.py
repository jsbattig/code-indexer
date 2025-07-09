"""
Test to compare search_with_branch_topology and search_with_branch_context methods.
"""

import pytest

from .conftest import local_temporary_directory
from pathlib import Path
import subprocess

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.smart_indexer import SmartIndexer
from .test_suite_setup import register_test_collection


def test_compare_search_methods():
    """Compare search_with_branch_topology and search_with_branch_context methods."""

    # Skip if no VoyageAI key
    import os

    if not os.getenv("VOYAGE_API_KEY"):
        pytest.skip("VoyageAI API key required")

    with local_temporary_directory() as temp_dir:
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
                "collection": "test_compare_search",
                "vector_size": 1024,
                "use_provider_aware_collections": True,
                "collection_base_name": "test_compare_search",
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

        # Register collection for cleanup
        register_test_collection(collection_name)

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

        # Check a content point's hidden_branches
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=3,
        )

        print(f"Found {len(content_points)} content points")
        for i, point in enumerate(content_points):
            payload = point.get("payload", {})
            print(
                f"Point {i}: hidden_branches = {payload.get('hidden_branches', 'MISSING')}"
            )
            print(f"Point {i}: path = {payload.get('path', 'MISSING')}")

        # Get embedding for search
        query_vector = embedding_provider.get_embedding("Hello World")

        # Test 1: search_with_branch_context from BranchAwareIndexer
        print("\n=== Testing search_with_branch_context ===")
        branch_indexer = indexer.branch_aware_indexer
        if branch_indexer:
            context_results = branch_indexer.search_with_branch_context(
                query_vector=query_vector,
                branch="master",
                limit=10,
                collection_name=collection_name,
            )
            print(f"search_with_branch_context results: {len(context_results)}")
            for result in context_results[:3]:
                payload = result.get("payload", {})
                print(
                    f"  - {payload.get('path', 'unknown')} (score: {result.get('score', 0)})"
                )
        else:
            print("No branch_aware_indexer available")
            context_results = []

        # Test 2: search_with_branch_topology from QdrantClient
        print("\n=== Testing search_with_branch_topology ===")
        topology_results = qdrant_client.search_with_branch_topology(
            query_vector=query_vector,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )
        print(f"search_with_branch_topology results: {len(topology_results)}")
        for result in topology_results[:3]:
            payload = result.get("payload", {})
            print(
                f"  - {payload.get('path', 'unknown')} (score: {result.get('score', 0)})"
            )

        # Test 3: basic search without branch filtering for comparison
        print("\n=== Testing basic search (no branch filtering) ===")
        basic_results = qdrant_client.search(
            query_vector=query_vector,
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            limit=10,
            collection_name=collection_name,
        )
        print(f"basic search results: {len(basic_results)}")
        for result in basic_results[:3]:
            payload = result.get("payload", {})
            print(
                f"  - {payload.get('path', 'unknown')} (score: {result.get('score', 0)})"
            )

        # The basic search should always work
        assert len(basic_results) > 0, "Basic search should find content"

        # If we have branch_indexer, its search should also work
        if branch_indexer:
            assert (
                len(context_results) > 0
            ), "search_with_branch_context should find content"

        # Our fixed method should also work
        assert (
            len(topology_results) > 0
        ), "search_with_branch_topology should find content"

        print("\n✅ All search methods working correctly!")


if __name__ == "__main__":
    test_compare_search_methods()
