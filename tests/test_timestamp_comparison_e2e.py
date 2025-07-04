"""
E2E tests for timestamp comparison accuracy in reconcile operations.

These tests verify that:
1. Reconcile correctly identifies files that need reindexing based on timestamps
2. Reconcile doesn't reindex files that are already up-to-date
3. New architecture points have proper timestamp fields for comparison

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

    # Add test files
    test_files = {
        "src/unchanged.py": "def unchanged():\n    return 'unchanged'\n",
        "src/modified.py": "def original():\n    return 'original'\n",
        "src/new_file.py": "def new_function():\n    return 'new'\n",
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

    # Initialize services using test infrastructure
    from rich.console import Console
    from .test_infrastructure import ServiceManager, EmbeddingProvider

    console = Console(quiet=True)

    # Use ServiceManager to ensure services are running with proper setup
    service_manager = ServiceManager()

    # Ensure services are ready for E2E test - no skipping allowed
    services_ready = service_manager.ensure_services_ready(
        embedding_provider=EmbeddingProvider.VOYAGE_AI, working_dir=config.codebase_dir
    )

    if not services_ready:
        # Try force recreation if first attempt failed
        print("First attempt failed, trying force recreation...")
        services_ready = service_manager.ensure_services_ready(
            embedding_provider=EmbeddingProvider.VOYAGE_AI,
            working_dir=config.codebase_dir,
            force_recreate=True,
        )

    assert (
        services_ready
    ), "Failed to ensure services are ready for E2E test after all attempts"

    embedding_provider = EmbeddingProviderFactory.create(config, console)
    qdrant_client = QdrantClient(config.qdrant, console)

    # Wait a moment for services to be fully ready
    import time

    time.sleep(2)

    # Verify services are actually running after ServiceManager setup
    if not embedding_provider.health_check():
        # Try one more time after a brief wait
        time.sleep(3)
        if not embedding_provider.health_check():
            # Try force recreation as last resort
            print(
                "Embedding provider health check failed, attempting force recreation..."
            )
            services_ready = service_manager.ensure_services_ready(
                embedding_provider=EmbeddingProvider.VOYAGE_AI,
                working_dir=config.codebase_dir,
                force_recreate=True,
            )
            assert (
                services_ready
            ), "Failed to ensure embedding provider is ready even after force recreation"

            # Reinitialize the embedding provider after force recreation
            embedding_provider = EmbeddingProviderFactory.create(config, console)
            assert (
                embedding_provider.health_check()
            ), "Embedding provider still not healthy after force recreation"

    if not qdrant_client.health_check():
        # Try one more time after a brief wait
        time.sleep(3)
        if not qdrant_client.health_check():
            # Try force recreation as last resort
            print("Qdrant health check failed, attempting force recreation...")
            services_ready = service_manager.ensure_services_ready(
                embedding_provider=EmbeddingProvider.VOYAGE_AI,
                working_dir=config.codebase_dir,
                force_recreate=True,
            )
            assert (
                services_ready
            ), "Failed to ensure Qdrant is ready even after force recreation"

            # Reinitialize the qdrant client after force recreation
            qdrant_client = QdrantClient(config.qdrant, console)
            assert (
                qdrant_client.health_check()
            ), "Qdrant still not healthy after force recreation"

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


class TestTimestampComparison:
    """Test timestamp comparison accuracy in reconcile operations."""

    def test_reconcile_correctly_identifies_modified_files(self, smart_indexer):
        """Test that reconcile identifies files that have been modified since indexing."""
        config = smart_indexer.config

        # Perform initial index
        initial_stats = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert initial_stats.files_processed > 0, "Should process some files initially"

        # Wait to ensure timestamp differences
        time.sleep(1.2)

        # Modify one file
        modified_file = config.codebase_dir / "src" / "modified.py"
        original_mtime = modified_file.stat().st_mtime

        modified_file.write_text("def modified():\n    return 'modified content'\n")
        new_mtime = modified_file.stat().st_mtime

        assert new_mtime > original_mtime, "File modification time should increase"

        # Add a completely new file
        new_file = config.codebase_dir / "src" / "brand_new.py"
        new_file.write_text("def brand_new():\n    return 'brand new'\n")

        # Perform reconcile
        reconcile_stats = smart_indexer.smart_index(
            reconcile_with_database=True, batch_size=10
        )

        # Should have processed at least the modified and new files
        # Note: chunk count might be higher due to file chunking
        assert reconcile_stats.files_processed >= 2, (
            f"Should have processed at least 2 files (modified + new), "
            f"but processed {reconcile_stats.files_processed}"
        )

    def test_reconcile_skips_unchanged_files(self, smart_indexer):
        """Test that reconcile skips files that haven't been modified."""
        # Perform initial index
        initial_stats = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert initial_stats.files_processed > 0

        # Wait to ensure timestamp differences
        time.sleep(1.2)

        # Don't modify any files, just perform reconcile
        reconcile_stats = smart_indexer.smart_index(
            reconcile_with_database=True, batch_size=10
        )

        # Should not process any files since nothing changed
        assert reconcile_stats.files_processed == 0, (
            f"Should have processed 0 files since nothing changed, "
            f"but processed {reconcile_stats.files_processed}"
        )

    def test_reconcile_handles_timestamp_edge_cases(self, smart_indexer):
        """Test reconcile handles edge cases in timestamp comparison."""
        config = smart_indexer.config

        # Perform initial index
        initial_stats = smart_indexer.smart_index(force_full=True, batch_size=10)
        assert initial_stats.files_processed > 0

        # Get the collection name and check point timestamps
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        all_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        assert len(all_points) > 0, "Should have points in collection"

        # Check that points have timestamps for comparison
        timestamp_fields = ["filesystem_mtime", "created_at", "indexed_at"]
        points_with_timestamps = 0

        for point in all_points:
            payload = point.get("payload", {})
            has_timestamp = any(field in payload for field in timestamp_fields)
            if has_timestamp:
                points_with_timestamps += 1

        assert points_with_timestamps > 0, (
            f"No points found with timestamp fields {timestamp_fields}. "
            f"This will cause reconcile to fail."
        )

        # Wait a short time
        time.sleep(1.2)

        # Modify a file with a very recent timestamp (edge case)
        test_file = config.codebase_dir / "src" / "unchanged.py"
        test_file.write_text("def unchanged():\n    return 'slightly changed'\n")

        # Perform reconcile
        reconcile_stats = smart_indexer.smart_index(
            reconcile_with_database=True, batch_size=10
        )

        # Should detect the change despite small time difference
        assert (
            reconcile_stats.files_processed >= 1
        ), "Should have detected the modified file despite small timestamp difference"

    def test_new_architecture_points_have_comparable_timestamps(self, smart_indexer):
        """Test that new architecture points have timestamps that can be compared."""
        config = smart_indexer.config

        # Perform initial index
        smart_indexer.smart_index(force_full=True, batch_size=10)

        # Get all points and check their timestamp fields
        collection_name = smart_indexer.qdrant_client.resolve_collection_name(
            config, smart_indexer.embedding_provider
        )

        all_points = get_all_points_with_payload(
            smart_indexer.qdrant_client, collection_name
        )
        assert len(all_points) > 0, "Should have points in collection"

        # Check that new architecture points have usable timestamps
        new_architecture_points = [
            point
            for point in all_points
            if point.get("payload", {}).get("type") in ["content", "visibility"]
        ]

        assert len(new_architecture_points) > 0, "Should have new architecture points"

        usable_timestamp_count = 0
        for point in new_architecture_points:
            payload = point["payload"]

            # Check for any usable timestamp field
            has_filesystem_mtime = "filesystem_mtime" in payload
            has_created_at = "created_at" in payload
            has_indexed_at = "indexed_at" in payload

            if has_filesystem_mtime or has_created_at or has_indexed_at:
                usable_timestamp_count += 1

                # Verify timestamp is a reasonable value
                if has_created_at:
                    created_at = payload["created_at"]
                    assert isinstance(
                        created_at, (int, float)
                    ), "created_at should be numeric"
                    assert created_at > 0, "created_at should be positive"

                if has_filesystem_mtime:
                    fs_mtime = payload["filesystem_mtime"]
                    assert isinstance(
                        fs_mtime, (int, float)
                    ), "filesystem_mtime should be numeric"
                    assert fs_mtime > 0, "filesystem_mtime should be positive"

        # All new architecture points should have usable timestamps
        assert usable_timestamp_count == len(new_architecture_points), (
            f"Only {usable_timestamp_count} of {len(new_architecture_points)} new architecture points "
            f"have usable timestamps. This will cause reconcile issues."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
