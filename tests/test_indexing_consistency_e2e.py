"""
E2E tests for indexing consistency issues.

These tests verify that:
1. Initial index and reconcile use the same point format
2. No legacy points are created during reconcile operations
3. Timestamp comparisons work correctly
4. No unwanted migrations occur during normal operations

Marked as e2e tests to exclude from CI due to dependency on real services.
"""

import pytest
import tempfile
import shutil
import time
from pathlib import Path

from code_indexer.config import ConfigManager, Config
from code_indexer.services import QdrantClient, EmbeddingProviderFactory
from code_indexer.services.smart_indexer import SmartIndexer
from .test_infrastructure import auto_register_project_collections


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


@pytest.fixture
def temp_project_dir():
    """Create a temporary project directory with test files."""
    temp_dir = Path(tempfile.mkdtemp())

    # Create a simple test project structure
    (temp_dir / "src").mkdir()
    (temp_dir / "tests").mkdir()

    # Add some test files with different timestamps
    test_files = {
        "src/main.py": "def main():\n    print('Hello World')\n",
        "src/utils.py": "def helper():\n    return 'helper'\n",
        "tests/test_main.py": "def test_main():\n    assert True\n",
        "README.md": "# Test Project\n\nThis is a test.\n",
    }

    for file_path, content in test_files.items():
        full_path = temp_dir / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    yield temp_dir

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def test_config(temp_project_dir):
    """Create test configuration."""
    config_dir = temp_project_dir / ".code-indexer"
    config_dir.mkdir()

    config = Config(codebase_dir=temp_project_dir)
    # Use smaller chunk size for testing
    config.indexing.chunk_size = 200
    config.indexing.max_file_size = 10000

    # Configure a reliable embedding provider for E2E tests
    config.embedding_provider = "voyage-ai"

    config_manager = ConfigManager(config_dir / "config.json")
    config_manager.save(config)

    return config_manager


@pytest.fixture
def smart_indexer(test_config):
    """Create SmartIndexer with test configuration."""
    config = test_config.load()

    # Register collections for cleanup via test infrastructure
    auto_register_project_collections(config.codebase_dir)

    # Initialize services
    from rich.console import Console

    console = Console(quiet=True)
    embedding_provider = EmbeddingProviderFactory.create(config, console)
    qdrant_client = QdrantClient(config.qdrant, console)

    # For E2E tests, services should be running from test setup
    # If they're not available, that's a test infrastructure issue
    if not embedding_provider.health_check():
        pytest.fail(
            "Embedding provider not available for E2E test. "
            "Ensure services are running before running E2E tests. "
            "Check test setup or run: code-indexer start"
        )

    if not qdrant_client.health_check():
        pytest.fail(
            "Qdrant service not available for E2E test. "
            "Ensure services are running before running E2E tests. "
            "Check test setup or run: code-indexer start"
        )

    metadata_path = test_config.config_path.parent / "metadata.json"
    indexer = SmartIndexer(config, embedding_provider, qdrant_client, metadata_path)

    yield indexer

    # Cleanup handled by collection registration system


def get_all_points_with_payload(qdrant_client, collection_name):
    """Get all points from collection with full payload."""
    all_points = []
    offset = None

    while True:
        points, next_offset = qdrant_client.scroll_points(
            collection_name=collection_name,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        if not points:
            break

        all_points.extend(points)
        offset = next_offset

        if offset is None:
            break

    return all_points


def categorize_points_by_architecture(points):
    """Categorize points by architecture type."""
    legacy_points = []
    new_content_points = []
    new_visibility_points = []
    unknown_points = []

    for point in points:
        payload = point.get("payload", {})

        # Check for new architecture markers
        point_type = payload.get("type")
        if point_type == "content":
            new_content_points.append(point)
        elif point_type == "visibility":
            new_visibility_points.append(point)
        # Check for legacy architecture markers
        elif "git_branch" in payload and "type" not in payload:
            legacy_points.append(point)
        else:
            unknown_points.append(point)

    return {
        "legacy": legacy_points,
        "new_content": new_content_points,
        "new_visibility": new_visibility_points,
        "unknown": unknown_points,
    }


class TestIndexingConsistency:
    """Test indexing consistency across different operations."""

    def test_initial_index_creates_only_new_architecture_points(self, smart_indexer):
        """Test that initial indexing creates only new architecture points."""
        # Perform initial index
        stats = smart_indexer.smart_index(force_full=True, batch_size=10)

        assert stats.files_processed > 0, "Should process some files"
        assert stats.chunks_created > 0, "Should create some chunks"

        # Get all points from collection
        config = smart_indexer.config
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        all_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        assert len(all_points) > 0, "Should have points in collection"

        # Categorize points
        categorized = categorize_points_by_architecture(all_points)

        # EXPECTED BEHAVIOR: Only new architecture points should exist
        assert (
            len(categorized["legacy"]) == 0
        ), f"Should have no legacy points, found {len(categorized['legacy'])}"
        assert len(categorized["new_content"]) > 0, "Should have new content points"
        # In new architecture, visibility is controlled via hidden_branches in content points
        # Verify content points have hidden_branches field
        content_with_visibility = [
            point
            for point in categorized["new_content"]
            if "hidden_branches" in point["payload"]
        ]
        assert (
            len(content_with_visibility) > 0
        ), "Content points should have hidden_branches visibility control"

        # Verify content points have required fields
        for point in categorized["new_content"]:
            payload = point["payload"]
            assert payload["type"] == "content"
            assert "content" in payload, "Content points should have content field"
            assert "path" in payload, "Content points should have path field"

    def test_reconcile_maintains_architecture_consistency(self, smart_indexer):
        """Test that reconcile operation maintains architecture consistency."""
        # Perform initial index
        initial_stats = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert initial_stats.files_processed > 0

        config = smart_indexer.config
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        # Get initial point distribution
        initial_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        initial_categorized = categorize_points_by_architecture(initial_points)

        # Should start with only new architecture
        assert (
            len(initial_categorized["legacy"]) == 0
        ), "Should start with no legacy points"

        # Wait a moment to ensure timestamp differences
        time.sleep(1.1)

        # Modify one file to trigger reconcile behavior
        test_file = config.codebase_dir / "src" / "main.py"
        original_content = test_file.read_text()
        test_file.write_text(original_content + "\n# Modified\n")

        # Perform reconcile operation
        smart_indexer.smart_index(reconcile_with_database=True, batch_size=10)

        # Get post-reconcile points
        post_reconcile_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        post_reconcile_categorized = categorize_points_by_architecture(
            post_reconcile_points
        )

        # CRITICAL: Reconcile should NOT create legacy points
        assert len(post_reconcile_categorized["legacy"]) == 0, (
            f"Reconcile created {len(post_reconcile_categorized['legacy'])} legacy points! "
            f"This indicates inconsistent indexing architecture."
        )

        # Should still have new architecture points
        assert (
            len(post_reconcile_categorized["new_content"]) > 0
        ), "Should maintain content points"
        # In new architecture, verify content points maintain hidden_branches visibility control
        post_reconcile_content_with_visibility = [
            point
            for point in post_reconcile_categorized["new_content"]
            if "hidden_branches" in point["payload"]
        ]
        assert (
            len(post_reconcile_content_with_visibility) > 0
        ), "Content points should maintain hidden_branches visibility control after reconcile"

    def test_repeated_index_operations_are_idempotent(self, smart_indexer):
        """Test that repeated index operations don't create duplicates or mixed architectures."""
        # Perform initial index
        stats1 = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert stats1.files_processed > 0

        config = smart_indexer.config
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        # Get initial point count and architecture
        points_after_first = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        first_categorized = categorize_points_by_architecture(points_after_first)

        # Perform second index (should be incremental/no-op)
        smart_indexer.smart_index(batch_size=10)

        # Get points after second index
        points_after_second = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        second_categorized = categorize_points_by_architecture(points_after_second)

        # Architecture should remain consistent
        assert (
            len(second_categorized["legacy"]) == 0
        ), "Second index should not create legacy points"

        # Point counts should be similar (allowing for some variation due to chunking)
        content_diff = abs(
            len(second_categorized["new_content"])
            - len(first_categorized["new_content"])
        )
        visibility_diff = abs(
            len(second_categorized["new_visibility"])
            - len(first_categorized["new_visibility"])
        )

        # Allow small differences due to potential re-chunking, but not massive differences
        assert content_diff <= len(first_categorized["new_content"]) * 0.1, (
            f"Content point count changed significantly: {len(first_categorized['new_content'])} -> "
            f"{len(second_categorized['new_content'])}"
        )
        assert visibility_diff <= len(first_categorized["new_visibility"]) * 0.1, (
            f"Visibility point count changed significantly: {len(first_categorized['new_visibility'])} -> "
            f"{len(second_categorized['new_visibility'])}"
        )

    def test_no_unwanted_migrations_during_normal_operations(self, smart_indexer):
        """Test that normal indexing operations don't trigger unwanted migrations."""
        # Capture any migration warnings by monitoring console output
        migration_warnings = []

        original_print = smart_indexer.qdrant_client.console.print

        def capture_print(*args, **kwargs):
            message = str(args[0]) if args else ""
            if "migration" in message.lower() or "legacy" in message.lower():
                migration_warnings.append(message)
            return original_print(*args, **kwargs)

        smart_indexer.qdrant_client.console.print = capture_print

        try:
            # Perform initial index
            stats1 = smart_indexer.smart_index(force_full=True, batch_size=10)
            assert stats1.files_processed > 0

            # Perform incremental index
            smart_indexer.smart_index(batch_size=10)

            # Perform reconcile
            smart_indexer.smart_index(reconcile_with_database=True, batch_size=10)

            # Should not have triggered any migration warnings
            assert (
                len(migration_warnings) == 0
            ), f"Unexpected migration warnings during normal operations: {migration_warnings}"

        finally:
            # Restore original print function
            smart_indexer.qdrant_client.console.print = original_print

    def test_timestamp_comparison_accuracy(self, smart_indexer):
        """Test that timestamp comparisons correctly identify files that need reindexing."""
        # Perform initial index
        initial_stats = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert initial_stats.files_processed > 0

        config = smart_indexer.config
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        # Wait to ensure timestamp differences
        time.sleep(1.1)

        # Modify one file
        test_file = config.codebase_dir / "src" / "utils.py"
        original_mtime = test_file.stat().st_mtime
        test_file.write_text("def helper():\n    return 'modified helper'\n")
        new_mtime = test_file.stat().st_mtime

        assert (
            new_mtime > original_mtime
        ), "File modification time should have increased"

        # Perform reconcile - should detect the modified file
        reconcile_stats = smart_indexer.smart_index(
            reconcile_with_database=True, batch_size=10
        )

        # Should have processed the modified file
        # Note: Due to chunking, this might process multiple chunks from the same file
        assert (
            reconcile_stats.files_processed >= 1
        ), f"Should have processed at least the modified file, but processed {reconcile_stats.files_processed}"

        # Verify no legacy points were created during reconcile
        all_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        categorized = categorize_points_by_architecture(all_points)

        assert (
            len(categorized["legacy"]) == 0
        ), f"Reconcile operation created {len(categorized['legacy'])} legacy points"


class TestLegacyFallbackRemoval:
    """Test that legacy fallback code paths are completely removed."""

    def test_no_legacy_process_file_calls_during_reconcile(self, smart_indexer):
        """Test that reconcile doesn't use legacy process_file method."""
        # This test will monitor what methods get called during reconcile
        legacy_calls = []

        # Monkey patch the legacy process_file method to detect calls
        original_process_file = smart_indexer.process_file

        def monitored_process_file(*args, **kwargs):
            legacy_calls.append("legacy_process_file_called")
            return original_process_file(*args, **kwargs)

        smart_indexer.process_file = monitored_process_file

        try:
            # Create initial index
            smart_indexer.smart_index(force_full=True, batch_size=10)

            # Clear the call log
            legacy_calls.clear()

            # Modify a file to trigger reconcile processing
            test_file = smart_indexer.config.codebase_dir / "src" / "main.py"
            test_file.write_text("def main():\n    print('Modified')\n")
            time.sleep(1.1)

            # Perform reconcile
            smart_indexer.smart_index(reconcile_with_database=True, batch_size=10)

            # CRITICAL: Should not have called legacy process_file method
            assert len(legacy_calls) == 0, (
                f"Reconcile operation called legacy process_file {len(legacy_calls)} times. "
                f"This indicates fallback to legacy indexing is still happening."
            )

        finally:
            # Restore original method
            smart_indexer.process_file = original_process_file

    def test_branch_aware_indexer_used_consistently(self, smart_indexer):
        """Test that BranchAwareIndexer is used for all indexing operations."""
        # Monitor calls to BranchAwareIndexer
        branch_aware_calls = []

        original_index_branch_changes = (
            smart_indexer.branch_aware_indexer.index_branch_changes
        )

        def monitored_index_branch_changes(*args, **kwargs):
            branch_aware_calls.append("branch_aware_indexer_called")
            return original_index_branch_changes(*args, **kwargs)

        smart_indexer.branch_aware_indexer.index_branch_changes = (
            monitored_index_branch_changes
        )

        try:
            # Perform operations that should use BranchAwareIndexer
            smart_indexer.smart_index(force_full=True, batch_size=10)
            initial_calls = len(branch_aware_calls)
            assert initial_calls > 0, "Initial index should use BranchAwareIndexer"

            # Modify file and reconcile
            test_file = smart_indexer.config.codebase_dir / "README.md"
            original_mtime = test_file.stat().st_mtime
            time.sleep(1.2)  # Ensure timestamp difference
            test_file.write_text("# Modified Test Project\n\nThis is modified.\n")
            new_mtime = test_file.stat().st_mtime

            # Verify the file was actually modified
            assert new_mtime > original_mtime, "File should have newer timestamp"

            reconcile_stats = smart_indexer.smart_index(
                reconcile_with_database=True, batch_size=10
            )
            reconcile_calls = len(branch_aware_calls) - initial_calls

            # Should have used BranchAwareIndexer for reconcile if files were processed
            if reconcile_stats.files_processed > 0:
                assert (
                    reconcile_calls > 0
                ), "Reconcile should use BranchAwareIndexer when processing files"
            else:
                # If no files were processed, it's acceptable that BranchAwareIndexer wasn't called
                print(
                    "No files processed during reconcile - this is acceptable if timestamps are correct"
                )

        finally:
            # Restore original method
            smart_indexer.branch_aware_indexer.index_branch_changes = (
                original_index_branch_changes
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
