"""
Debug branch isolation logic to understand why files aren't visible in their own branches.
"""

import pytest

from .conftest import local_temporary_directory
from pathlib import Path
import subprocess
from typing import Dict, Any

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.smart_indexer import SmartIndexer
from .test_suite_setup import register_test_collection


def test_debug_branch_isolation():
    """Debug branch isolation to see what's happening with hidden_branches."""

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
                "collection": "test_debug_isolation",
                "vector_size": 1024,
                "use_provider_aware_collections": True,
                "collection_base_name": "test_debug_isolation",
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

        # Step 1: Index on master branch
        print("=== Step 1: Index on master branch ===")
        stats = indexer.smart_index(force_full=True)
        print(f"Master indexing: {stats.files_processed} files processed")

        # Check hidden_branches after master indexing
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=10,
        )
        print(f"After master indexing: {len(content_points)} content points")
        for point in content_points:
            payload = point.get("payload", {})
            if "main.py" in payload.get("path", ""):
                print(
                    f"  main.py hidden_branches: {payload.get('hidden_branches', 'MISSING')}"
                )

        # Step 2: Create branch A and add unique file
        print("\n=== Step 2: Create branch A and add unique file ===")
        branch_a = "feature/branch-a"
        subprocess.run(["git", "checkout", "-b", branch_a], cwd=repo_path, check=True)

        file_a_content = "def branch_a_function(): return 'unique to branch A'"
        file_a_path = repo_path / "branch_a_file.py"
        file_a_path.write_text(file_a_content)

        subprocess.run(["git", "add", "branch_a_file.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add branch A file"], cwd=repo_path, check=True
        )

        print(
            f"Current branch: {subprocess.run(['git', 'branch', '--show-current'], cwd=repo_path, capture_output=True, text=True).stdout.strip()}"
        )

        # Index on branch A
        stats_a = indexer.smart_index()
        print(f"Branch A indexing: {stats_a.files_processed} files processed")

        # Check all content points after branch A indexing
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=20,
        )
        print(f"After branch A indexing: {len(content_points)} content points")

        branch_a_points = []
        main_py_points = []
        for point in content_points:
            payload = point.get("payload", {})
            if "branch_a_file.py" in payload.get("path", ""):
                branch_a_points.append(point)
                print(
                    f"  branch_a_file.py hidden_branches: {payload.get('hidden_branches', 'MISSING')}"
                )
            elif "main.py" in payload.get("path", ""):
                main_py_points.append(point)
                print(
                    f"  main.py hidden_branches: {payload.get('hidden_branches', 'MISSING')}"
                )

        # Step 3: Test search from branch A
        print("\n=== Step 3: Test search from branch A ===")
        query_a = embedding_provider.get_embedding("unique to branch A")
        results_a = qdrant_client.search_with_branch_topology(
            query_vector=query_a,
            current_branch=branch_a,
            limit=10,
            collection_name=collection_name,
        )

        print(
            f"Search results for 'unique to branch A' from branch {branch_a}: {len(results_a)}"
        )
        found_branch_a_file = False
        for result in results_a:
            payload = result.get("payload", {})
            path = payload.get("path", "")
            hidden_branches = payload.get("hidden_branches", [])
            print(
                f"  - {path} (score: {result.get('score', 0):.3f}, hidden_branches: {hidden_branches})"
            )
            if "branch_a_file.py" in path:
                found_branch_a_file = True

        print(f"Found branch A file in search: {found_branch_a_file}")

        # Step 4: Create branch B to test isolation
        print("\n=== Step 4: Create branch B and test isolation ===")
        subprocess.run(["git", "checkout", "master"], cwd=repo_path, check=True)
        branch_b = "feature/branch-b"
        subprocess.run(["git", "checkout", "-b", branch_b], cwd=repo_path, check=True)

        file_b_content = "def branch_b_function(): return 'unique to branch B'"
        file_b_path = repo_path / "branch_b_file.py"
        file_b_path.write_text(file_b_content)

        subprocess.run(["git", "add", "branch_b_file.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add branch B file"], cwd=repo_path, check=True
        )

        # Index on branch B
        stats_b = indexer.smart_index()
        print(f"Branch B indexing: {stats_b.files_processed} files processed")

        # Check all content points after branch B indexing
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=30,
        )
        print(f"After branch B indexing: {len(content_points)} content points")

        # Show hidden_branches for all files
        file_states: Dict[str, Any] = {}
        for point in content_points:
            payload = point.get("payload", {})
            path = payload.get("path", "")
            hidden_branches = payload.get("hidden_branches", [])
            if path not in file_states:
                file_states[path] = []
            file_states[path].append(hidden_branches)

        for path, hidden_branches_list in file_states.items():
            if any(
                "branch" in path
                for branch_pattern in ["branch_a_file", "branch_b_file", "main.py"]
                if branch_pattern in path
            ):
                print(f"  {path}: hidden_branches variations: {hidden_branches_list}")

        # Step 5: Test visibility from both branches
        print("\n=== Step 5: Test visibility from both branches ===")

        # From branch A, search for branch A content
        subprocess.run(["git", "checkout", branch_a], cwd=repo_path, check=True)
        results_a_from_a = qdrant_client.search_with_branch_topology(
            query_vector=query_a,
            current_branch=branch_a,
            limit=10,
            collection_name=collection_name,
        )

        found_a_in_a = any(
            "branch_a_file.py" in result.get("payload", {}).get("path", "")
            for result in results_a_from_a
        )
        print(f"From branch A, found branch A file: {found_a_in_a}")

        # From branch A, search for branch B content (should not find)
        query_b = embedding_provider.get_embedding("unique to branch B")
        results_b_from_a = qdrant_client.search_with_branch_topology(
            query_vector=query_b,
            current_branch=branch_a,
            limit=10,
            collection_name=collection_name,
        )

        found_b_in_a = any(
            "branch_b_file.py" in result.get("payload", {}).get("path", "")
            for result in results_b_from_a
        )
        print(f"From branch A, found branch B file: {found_b_in_a} (should be False)")

        # This is the key test that's failing in the original test
        print("\n=== EXPECTED BEHAVIOR ===")
        print(
            f"Branch A file should be visible from branch A: {found_a_in_a} (should be True)"
        )
        print(
            f"Branch B file should NOT be visible from branch A: {not found_b_in_a} (should be True)"
        )

        if not found_a_in_a:
            print("\n🚨 PROBLEM: Branch A file is not visible from branch A!")
            print(
                "This suggests the hidden_branches logic is incorrectly hiding the file in its own branch"
            )

        if found_b_in_a:
            print("\n🚨 PROBLEM: Branch B file is visible from branch A!")
            print("This suggests branch isolation is not working")


if __name__ == "__main__":
    test_debug_branch_isolation()
