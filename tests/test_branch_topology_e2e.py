"""
Comprehensive E2E test for branch topology-aware smart indexing.

This test suite validates the new BranchAwareIndexer architecture that separates
content storage from branch visibility through:
1. Content Points: Immutable, contain file content, no branch information
2. Visibility Points: Mutable, map branches to content, control what's visible per branch
3. Search: Returns content points filtered by branch visibility
4. Cleanup: Hides visibility points, preserves content points

The tests validate:
- Branch indexing creates both content and visibility points
- Search respects branch visibility filtering
- Branch cleanup properly hides visibility without data loss
- Content points are reused when files haven't changed
- Branch isolation works correctly
"""

import os
import subprocess
import time

import pytest

from code_indexer.config import Config
from code_indexer.services.embedding_factory import EmbeddingProviderFactory
from code_indexer.services.qdrant import QdrantClient
from code_indexer.services.smart_indexer import SmartIndexer

# Import new test infrastructure
from .test_infrastructure import (
    create_fast_e2e_setup,
    EmbeddingProvider,
)


@pytest.mark.skipif(
    not os.getenv("VOYAGE_API_KEY"),
    reason="VoyageAI API key required for E2E tests (set VOYAGE_API_KEY environment variable)",
)
class TestBranchTopologyE2E:
    """End-to-end test for branch topology-aware indexing with new architecture."""

    @pytest.fixture
    def test_config(self, e2e_temp_repo):
        """Create test configuration using new infrastructure."""
        # Use the e2e_temp_repo as the codebase directory to fix the mismatch
        temp_dir = e2e_temp_repo

        # Set up services using new infrastructure
        service_manager, cli_helper, dir_manager = create_fast_e2e_setup(
            EmbeddingProvider.VOYAGE_AI
        )

        # Ensure services are ready
        if not service_manager.ensure_services_ready(working_dir=temp_dir):
            pytest.skip("Could not start required services for E2E testing")

        return Config(
            codebase_dir=str(temp_dir),
            embedding_provider="voyage-ai",  # Use VoyageAI for CI stability
            voyage_ai={
                "model": "voyage-code-3",
                "api_endpoint": "https://api.voyageai.com/v1/embeddings",
                "timeout": 30,
                "parallel_requests": 4,  # Reduced for testing
                "batch_size": 16,  # Smaller batches for testing
                "max_retries": 3,
            },
            qdrant={
                "host": "http://localhost:6333",
                "collection": "test_branch_topology",
                "vector_size": 1024,  # VoyageAI voyage-code-3 dimensions
                "use_provider_aware_collections": True,
                "collection_base_name": "test_branch_topology",
            },
            indexing={
                "chunk_size": 500,
                "chunk_overlap": 50,
                "file_extensions": [".py", ".md", ".txt"],
            },
        )

    @pytest.fixture
    def smart_indexer(self, test_config, tmp_path):
        """Create SmartIndexer instance following NEW STRATEGY."""
        # Initialize embedding provider
        embedding_provider = EmbeddingProviderFactory.create(test_config)

        # Initialize Qdrant client
        qdrant_client = QdrantClient(test_config.qdrant)

        # NEW STRATEGY: Ensure collection exists but don't delete all data
        qdrant_client.resolve_collection_name(test_config, embedding_provider)

        # Only ensure collection exists, don't delete existing data
        try:
            # Use the indexer's own collection creation logic instead of direct deletion
            pass  # SmartIndexer will create collection as needed
        except Exception as e:
            print(f"Collection setup warning: {e}")

        # Create metadata path
        metadata_path = tmp_path / "metadata.json"

        # Create SmartIndexer
        indexer = SmartIndexer(
            test_config, embedding_provider, qdrant_client, metadata_path
        )

        yield indexer

        # NEW STRATEGY: Only clean up this test's specific data, not entire collection
        try:
            # Clean only points created by this test if needed
            # This could be implemented by filtering on metadata or project info
            pass  # For now, leave data for next test (faster execution)
        except Exception:
            pass  # Ignore cleanup errors

    def test_branch_topology_full_workflow(
        self, e2e_temp_repo, smart_indexer, test_config
    ):
        """Test complete branch topology workflow with content/visibility separation."""

        # Step 1: Initial indexing on master branch
        print("Step 1: Initial indexing on master branch")

        initial_stats = smart_indexer.smart_index(force_full=True)
        assert initial_stats.files_processed >= 2  # README.md and main.py
        assert initial_stats.chunks_created > 0

        # Verify initial index structure
        embedding_provider = smart_indexer.embedding_provider
        qdrant_client = smart_indexer.qdrant_client
        collection_name = qdrant_client.resolve_collection_name(
            test_config, embedding_provider
        )

        initial_count = qdrant_client.count_points(collection_name)
        assert initial_count > 0
        print(f"Initial index: {initial_count} points")

        # Step 2: Create test branch and add new file
        print("Step 2: Creating test branch and adding new file")

        test_branch = "feature/test-branch-topology"
        subprocess.run(
            ["git", "checkout", "-b", test_branch], cwd=e2e_temp_repo, check=True
        )

        # Add new file to the branch
        new_file_content = """
# New Feature Module

This is a new file added specifically for branch topology testing.

def new_feature():
    '''Implementation of new feature.'''
    return "This is a new feature implemented in the test branch"

def helper_function():
    '''Helper function for the new feature.'''
    return "Helper functionality"
"""
        new_file_path = e2e_temp_repo / "new_feature.py"
        new_file_path.write_text(new_file_content)

        subprocess.run(["git", "add", "new_feature.py"], cwd=e2e_temp_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add new feature module"],
            cwd=e2e_temp_repo,
            check=True,
        )

        # Step 3: Run smart indexing on the new branch
        print("Step 3: Running smart indexing on feature branch")

        branch_stats = smart_indexer.smart_index()

        # Verify only new content was processed
        print(
            f"Branch indexing stats: {branch_stats.files_processed} files, {branch_stats.chunks_created} chunks"
        )

        # Get total points after branch indexing
        after_branch_count = qdrant_client.count_points(collection_name)
        new_points_added = after_branch_count - initial_count
        print(
            f"Points after branch indexing: {after_branch_count} (added: {new_points_added})"
        )

        assert new_points_added > 0, "New points should be added for the new file"

        # Step 4: Validate content and visibility point structure
        print("Step 4: Validating content and visibility point architecture")

        # Count content points
        content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=1000,
        )
        content_count = len(content_points)
        print(f"Content points: {content_count}")

        # Count visibility points
        visibility_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "visibility"}}]
            },
            collection_name=collection_name,
            limit=1000,
        )
        visibility_count = len(visibility_points)
        print(f"Visibility points: {visibility_count}")

        # Verify architecture principles
        assert content_count > 0, "Should have content points"
        assert visibility_count > 0, "Should have visibility points"

        # Verify content points don't have branch information
        for point in content_points:
            payload = point.get("payload", {})
            assert payload.get("type") == "content"
            assert (
                "branch" not in payload
            ), "Content points should not contain branch info"
            assert "git_commit" in payload, "Content points should have git commit"
            assert "path" in payload, "Content points should have file path"

        # Verify visibility points have branch mapping
        for point in visibility_points:
            payload = point.get("payload", {})
            assert payload.get("type") == "visibility"
            assert "branch" in payload, "Visibility points should have branch info"
            assert "content_id" in payload, "Visibility points should reference content"
            assert (
                payload.get("status") == "visible"
            ), "Visibility points should be visible"

        # Step 5: Query for new file content and verify it's visible
        print("Step 5: Querying for new file content visibility")

        query_vector = embedding_provider.get_embedding("new feature implementation")
        search_results = qdrant_client.search_with_branch_topology(
            query_vector=query_vector,
            current_branch=test_branch,
            limit=10,
            collection_name=collection_name,
        )

        # Verify new file content is found and is a content point
        new_file_found = False
        for result in search_results:
            payload = result.get("payload", {})
            if payload.get("path", "").endswith("new_feature.py"):
                new_file_found = True
                assert (
                    payload.get("type") == "content"
                ), "Search should return content points"
                assert (
                    "branch" not in payload
                ), "Content points should not have branch field"
                print(f"Found new file content with score: {result.get('score', 0)}")
                break

        assert new_file_found, "New file content should be searchable"

        # Step 6: Query for existing file to ensure it's still visible
        print("Step 6: Verifying existing files are still accessible")

        existing_query_vector = embedding_provider.get_embedding(
            "Hello World main function"
        )
        existing_results = qdrant_client.search_with_branch_topology(
            query_vector=existing_query_vector,
            current_branch=test_branch,
            include_ancestry=True,
            limit=10,
            collection_name=collection_name,
        )

        # Verify existing content is still accessible
        main_py_found = False
        for result in existing_results:
            payload = result.get("payload", {})
            if payload.get("path", "").endswith("main.py"):
                main_py_found = True
                assert (
                    payload.get("type") == "content"
                ), "Search should return content points"
                print(
                    f"Found existing file content with score: {result.get('score', 0)}"
                )
                break

        assert (
            main_py_found
        ), "Existing files should remain accessible in feature branch"

        # Step 7: Switch back to master branch
        print("Step 7: Switching back to master branch")

        subprocess.run(["git", "checkout", "master"], cwd=e2e_temp_repo, check=True)

        # Run smart indexing to handle branch switch
        master_stats = smart_indexer.smart_index()
        print(
            f"Master branch switch stats: {master_stats.files_processed} files processed"
        )

        # Step 8: Delete the test branch and cleanup
        print("Step 8: Deleting test branch and cleaning up")

        subprocess.run(
            ["git", "branch", "-D", test_branch], cwd=e2e_temp_repo, check=True
        )

        # Clean up branch data from index
        cleanup_success = smart_indexer.cleanup_branch_data(test_branch)
        assert cleanup_success, "Branch data cleanup should succeed"

        # Step 9: Verify cleanup - visibility points should be hidden, content preserved
        print("Step 9: Verifying cleanup preserves content but hides visibility")

        # Check that visibility points for the branch are hidden
        visible_points_after_cleanup, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": test_branch}},
                    {"key": "status", "match": {"value": "visible"}},
                ]
            },
            collection_name=collection_name,
            limit=1000,
        )

        assert (
            len(visible_points_after_cleanup) == 0
        ), "No visibility points should be visible after cleanup"

        # Check that content points are still there
        content_points_after_cleanup, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=1000,
        )

        assert (
            len(content_points_after_cleanup) >= content_count
        ), "Content points should be preserved"

        # Step 10: Query again - new file content should not be visible
        print("Step 10: Verifying new file content is no longer accessible")

        final_query_vector = embedding_provider.get_embedding(
            "new feature implementation"
        )
        final_results = qdrant_client.search_with_branch_topology(
            query_vector=final_query_vector,
            current_branch="master",
            include_ancestry=True,
            limit=10,
            collection_name=collection_name,
        )

        # Verify new file content is no longer found
        new_file_still_found = False
        for result in final_results:
            payload = result.get("payload", {})
            if payload.get("path", "").endswith("new_feature.py"):
                new_file_still_found = True
                break

        assert (
            not new_file_still_found
        ), "New file content should not be accessible after branch deletion"

        # Step 11: Verify existing files are still accessible on master
        print("Step 11: Verifying existing files remain accessible on master")

        master_query_vector = embedding_provider.get_embedding(
            "Hello World main function"
        )
        master_results = qdrant_client.search_with_branch_topology(
            query_vector=master_query_vector,
            current_branch="master",
            limit=10,
            collection_name=collection_name,
        )

        # Verify existing content is still accessible
        main_py_still_found = False
        for result in master_results:
            payload = result.get("payload", {})
            if payload.get("path", "").endswith("main.py"):
                main_py_still_found = True
                break

        assert main_py_still_found, "Existing files should remain accessible on master"

        print("✅ Branch topology E2E test completed successfully!")

    def test_content_point_reuse_across_branches(
        self, e2e_temp_repo, smart_indexer, test_config
    ):
        """Test that content points are reused when files haven't changed across branches."""

        # Initial indexing on master
        smart_indexer.smart_index(force_full=True)

        embedding_provider = smart_indexer.embedding_provider
        qdrant_client = smart_indexer.qdrant_client
        collection_name = qdrant_client.resolve_collection_name(
            test_config, embedding_provider
        )

        # Count initial content points
        initial_content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=1000,
        )
        initial_content_count = len(initial_content_points)

        # Create new branch without changing files
        test_branch = "feature/no-changes"
        subprocess.run(
            ["git", "checkout", "-b", test_branch], cwd=e2e_temp_repo, check=True
        )

        # Run indexing on new branch
        smart_indexer.smart_index()

        # Count content points after branch indexing
        after_branch_content_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [{"key": "type", "match": {"value": "content"}}]
            },
            collection_name=collection_name,
            limit=1000,
        )
        after_branch_content_count = len(after_branch_content_points)

        # Verify no new content points were created
        assert (
            after_branch_content_count == initial_content_count
        ), "No new content points should be created for unchanged files"

        # Verify visibility points were created
        visibility_points, _ = qdrant_client.scroll_points(
            filter_conditions={
                "must": [
                    {"key": "type", "match": {"value": "visibility"}},
                    {"key": "branch", "match": {"value": test_branch}},
                ]
            },
            collection_name=collection_name,
            limit=1000,
        )

        assert (
            len(visibility_points) > 0
        ), "Visibility points should be created for new branch"

        # Verify files are still searchable
        query_vector = embedding_provider.get_embedding("Hello World")
        search_results = qdrant_client.search_with_branch_topology(
            query_vector=query_vector,
            current_branch=test_branch,
            limit=10,
            collection_name=collection_name,
        )

        assert len(search_results) > 0, "Files should be searchable in new branch"

        print("✅ Content point reuse test completed successfully!")

    def test_branch_visibility_isolation(
        self, e2e_temp_repo, smart_indexer, test_config
    ):
        """Test that branch visibility isolation works correctly."""

        # Initial indexing on master
        smart_indexer.smart_index(force_full=True)

        embedding_provider = smart_indexer.embedding_provider
        qdrant_client = smart_indexer.qdrant_client
        collection_name = qdrant_client.resolve_collection_name(
            test_config, embedding_provider
        )

        # Create branch A with a unique file
        branch_a = "feature/branch-a"
        subprocess.run(
            ["git", "checkout", "-b", branch_a], cwd=e2e_temp_repo, check=True
        )

        file_a_content = "def branch_a_function(): return 'unique to branch A'"
        file_a_path = e2e_temp_repo / "branch_a_file.py"
        file_a_path.write_text(file_a_content)

        subprocess.run(
            ["git", "add", "branch_a_file.py"], cwd=e2e_temp_repo, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add branch A file"], cwd=e2e_temp_repo, check=True
        )

        smart_indexer.smart_index()

        # Create branch B with a unique file
        subprocess.run(["git", "checkout", "master"], cwd=e2e_temp_repo, check=True)
        branch_b = "feature/branch-b"
        subprocess.run(
            ["git", "checkout", "-b", branch_b], cwd=e2e_temp_repo, check=True
        )

        file_b_content = "def branch_b_function(): return 'unique to branch B'"
        file_b_path = e2e_temp_repo / "branch_b_file.py"
        file_b_path.write_text(file_b_content)

        subprocess.run(
            ["git", "add", "branch_b_file.py"], cwd=e2e_temp_repo, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "Add branch B file"], cwd=e2e_temp_repo, check=True
        )

        smart_indexer.smart_index()

        # Test visibility isolation

        # From branch A, should see branch A file but not branch B file
        subprocess.run(["git", "checkout", branch_a], cwd=e2e_temp_repo, check=True)

        # Search for branch A content
        query_a = embedding_provider.get_embedding("unique to branch A")
        results_a = qdrant_client.search_with_branch_topology(
            query_vector=query_a,
            current_branch=branch_a,
            limit=10,
            collection_name=collection_name,
        )

        # Should find branch A content
        found_a_in_a = any(
            result.get("payload", {}).get("path", "").endswith("branch_a_file.py")
            for result in results_a
        )
        assert found_a_in_a, "Branch A file should be visible from branch A"

        # Search for branch B content from branch A
        query_b = embedding_provider.get_embedding("unique to branch B")
        results_b_from_a = qdrant_client.search_with_branch_topology(
            query_vector=query_b,
            current_branch=branch_a,
            limit=10,
            collection_name=collection_name,
        )

        # Should not find branch B content
        found_b_in_a = any(
            result.get("payload", {}).get("path", "").endswith("branch_b_file.py")
            for result in results_b_from_a
        )
        assert not found_b_in_a, "Branch B file should not be visible from branch A"

        # From branch B, should see branch B file but not branch A file
        subprocess.run(["git", "checkout", branch_b], cwd=e2e_temp_repo, check=True)

        # Search for branch B content
        results_b_in_b = qdrant_client.search_with_branch_topology(
            query_vector=query_b,
            current_branch=branch_b,
            limit=10,
            collection_name=collection_name,
        )

        # Should find branch B content
        found_b_in_b = any(
            result.get("payload", {}).get("path", "").endswith("branch_b_file.py")
            for result in results_b_in_b
        )
        assert found_b_in_b, "Branch B file should be visible from branch B"

        # Search for branch A content from branch B
        results_a_from_b = qdrant_client.search_with_branch_topology(
            query_vector=query_a,
            current_branch=branch_b,
            limit=10,
            collection_name=collection_name,
        )

        # Should not find branch A content
        found_a_in_b = any(
            result.get("payload", {}).get("path", "").endswith("branch_a_file.py")
            for result in results_a_from_b
        )
        assert not found_a_in_b, "Branch A file should not be visible from branch B"

        print("✅ Branch visibility isolation test completed successfully!")

    def test_working_directory_indexing(self, e2e_temp_repo, smart_indexer):
        """Test indexing of staged and unstaged files with new architecture."""

        # Initial indexing
        smart_indexer.smart_index(force_full=True)

        # Create staged file
        staged_file = e2e_temp_repo / "staged_feature.py"
        staged_file.write_text(
            "def staged_function():\n    return 'This is staged content'"
        )
        subprocess.run(
            ["git", "add", "staged_feature.py"], cwd=e2e_temp_repo, check=True
        )

        # Create unstaged file
        unstaged_file = e2e_temp_repo / "unstaged_feature.py"
        unstaged_file.write_text(
            "def unstaged_function():\n    return 'This is unstaged content'"
        )

        # Run smart indexing to handle working directory files
        wd_stats = smart_indexer.smart_index()

        # Verify working directory files were processed
        assert wd_stats.files_processed >= 2  # At least staged and unstaged files

        # Query for staged content
        embedding_provider = smart_indexer.embedding_provider
        qdrant_client = smart_indexer.qdrant_client

        staged_query = embedding_provider.get_embedding("staged content")
        staged_results = qdrant_client.search(staged_query, limit=5)

        # In the new architecture, working directory status is still tracked in content points
        staged_found = any(
            result.get("payload", {}).get("working_directory_status") == "staged"
            for result in staged_results
        )
        assert staged_found, "Staged content should be indexable"

        # Query for unstaged content
        unstaged_query = embedding_provider.get_embedding("unstaged content")
        unstaged_results = qdrant_client.search(unstaged_query, limit=5)

        # Note: A new unstaged file is detected as "untracked", not "unstaged"
        # "unstaged" applies to files that exist in git but have uncommitted modifications
        unstaged_found = any(
            result.get("payload", {}).get("working_directory_status") == "untracked"
            for result in unstaged_results
        )
        assert unstaged_found, "Untracked content should be indexable"

        print("✅ Working directory indexing test completed successfully!")

    def test_branch_topology_performance(self, e2e_temp_repo, smart_indexer):
        """Test performance characteristics of branch topology indexing with new architecture."""

        # Create multiple files for performance testing
        for i in range(10):
            file_path = e2e_temp_repo / f"perf_test_{i}.py"
            file_path.write_text(
                f"def function_{i}():\n    return 'Performance test function {i}'"
            )

        subprocess.run(["git", "add", "."], cwd=e2e_temp_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add performance test files"],
            cwd=e2e_temp_repo,
            check=True,
        )

        # Initial full indexing
        start_time = time.time()
        full_stats = smart_indexer.smart_index(force_full=True)
        full_time = time.time() - start_time

        print(f"Full indexing: {full_stats.files_processed} files in {full_time:.3f}s")

        # Create branch and modify one file
        subprocess.run(
            ["git", "checkout", "-b", "perf-test"], cwd=e2e_temp_repo, check=True
        )

        # Modify only one file
        modified_file = e2e_temp_repo / "perf_test_5.py"
        modified_file.write_text(
            "def function_5():\n    return 'Modified performance test function 5'"
        )
        subprocess.run(["git", "add", "perf_test_5.py"], cwd=e2e_temp_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Modify one file"], cwd=e2e_temp_repo, check=True
        )

        # Smart incremental indexing with new architecture
        start_time = time.time()
        incremental_stats = smart_indexer.smart_index()
        incremental_time = time.time() - start_time

        print(
            f"Incremental indexing: {incremental_stats.files_processed} files in {incremental_time:.3f}s"
        )

        # With the new architecture, performance should be significantly better
        # Only the modified file should be processed for content
        assert (
            incremental_stats.files_processed <= 1
        ), "Only modified files should be processed for content"
        assert (
            incremental_time < full_time / 2
        ), "Incremental indexing should be at least 2x faster"

        print("✅ Branch topology performance test completed successfully!")
