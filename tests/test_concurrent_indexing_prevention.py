"""
Test for preventing concurrent indexing operations on the same project.

This test should fail initially, demonstrating that multiple indexing operations
can run simultaneously, which could cause data corruption and resource conflicts.
"""

import pytest
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.config import Config


@pytest.mark.slow
class TestConcurrentIndexingPrevention:
    """Test prevention of concurrent indexing operations."""

    def test_concurrent_indexing_should_be_prevented(self):
        """
        Test that attempting to start a second indexing operation
        while one is already running should be prevented.

        This test should FAIL initially, demonstrating the bug.
        """
        # Setup two indexer instances for the same project
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.file_extensions = ["py"]

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"

            mock_qdrant_client = Mock()

            # Use same metadata path for both indexers (same project)
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer1 = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )
                indexer2 = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )

                # Create test files
                test_files = ["test1.py", "test2.py"]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello')")

                # Mock the methods to simulate slow indexing

                def slow_index_branch_changes(*args, **kwargs):
                    # Simulate slow indexing operation
                    time.sleep(2.0)  # 2 second delay
                    # Mock return value
                    from code_indexer.services.branch_aware_indexer import (
                        BranchIndexingResult,
                    )

                    return BranchIndexingResult(
                        content_points_created=1,
                        visibility_points_created=1,
                        visibility_points_updated=0,
                        content_points_reused=0,
                        processing_time=2.0,
                        files_processed=1,
                    )

                # Results tracking
                results = []
                errors = []

                def run_indexing(indexer, indexer_name):
                    """Run indexing and track results."""
                    try:
                        with patch.object(
                            indexer.branch_aware_indexer,
                            "index_branch_changes",
                            side_effect=slow_index_branch_changes,
                        ), patch.object(
                            indexer, "get_git_status"
                        ) as mock_git_status, patch.object(
                            indexer, "file_finder"
                        ) as mock_file_finder:

                            mock_git_status.return_value = {"git_available": False}
                            mock_file_finder.find_files.return_value = [
                                Path(tmpdir) / f for f in test_files
                            ]

                            start_time = time.time()
                            stats = indexer.smart_index(force_full=True)
                            end_time = time.time()

                            results.append(
                                {
                                    "indexer": indexer_name,
                                    "success": True,
                                    "start_time": start_time,
                                    "end_time": end_time,
                                    "duration": end_time - start_time,
                                    "stats": stats,
                                }
                            )

                    except Exception as e:
                        errors.append(
                            {
                                "indexer": indexer_name,
                                "error": str(e),
                                "error_type": type(e).__name__,
                            }
                        )

                # Start both indexing operations simultaneously
                thread1 = threading.Thread(
                    target=run_indexing, args=(indexer1, "indexer1")
                )
                thread2 = threading.Thread(
                    target=run_indexing, args=(indexer2, "indexer2")
                )

                # Start both threads at nearly the same time
                thread1.start()
                time.sleep(0.1)  # Small delay to ensure first one starts
                thread2.start()

                # Wait for both to complete
                thread1.join(timeout=10)
                thread2.join(timeout=10)

                print(f"Results: {results}")
                print(f"Errors: {errors}")

                # Current behavior: both indexing operations succeed (BUG!)
                # Expected behavior: second operation should be prevented

                if len(results) == 2 and len(errors) == 0:
                    pytest.fail(
                        "BUG REPRODUCED: Both indexing operations succeeded simultaneously! "
                        "This could cause data corruption. Second operation should have been prevented."
                    )

                # After fix: one should succeed, one should fail with appropriate error
                if len(results) == 1 and len(errors) == 1:
                    error = errors[0]
                    assert (
                        "already in progress" in error["error"].lower()
                        or "concurrent" in error["error"].lower()
                    ), f"Expected concurrent indexing error, got: {error['error']}"
                    print("✅ Concurrent indexing properly prevented!")
                else:
                    pytest.fail(
                        f"Unexpected result pattern: {len(results)} successes, {len(errors)} errors"
                    )

            finally:
                metadata_path.unlink(missing_ok=True)

    def test_heartbeat_cooloff_mechanism(self):
        """
        Test that crashed indexing operations are handled properly with heartbeat cooloff.

        When an indexing operation crashes, the heartbeat should expire after a timeout,
        allowing new operations to proceed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.file_extensions = ["py"]

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"

            mock_qdrant_client = Mock()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )

                # Simulate creating a stale heartbeat file (from crashed process)
                heartbeat_path = metadata_path.parent / "indexing_heartbeat.json"
                stale_time = time.time() - 300  # 5 minutes ago (stale)

                import json

                heartbeat_data = {
                    "pid": 99999,  # Non-existent process
                    "started_at": stale_time,
                    "last_heartbeat": stale_time,
                    "project_path": str(config.codebase_dir),
                }
                heartbeat_path.write_text(json.dumps(heartbeat_data))

                # Create test files
                test_files = ["test1.py", "test2.py"]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello')")

                # Should be able to start indexing since heartbeat is stale
                # This will fail initially since heartbeat mechanism doesn't exist yet

                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer, "index_branch_changes"
                ) as mock_index_branch:

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]

                    # Mock return value for branch aware indexer
                    from code_indexer.services.branch_aware_indexer import (
                        BranchIndexingResult,
                    )

                    mock_index_branch.return_value = BranchIndexingResult(
                        content_points_created=1,
                        visibility_points_created=1,
                        visibility_points_updated=0,
                        content_points_reused=0,
                        processing_time=0.1,
                        files_processed=len(test_files),
                    )

                    # This should succeed (stale heartbeat should be ignored)
                    try:
                        indexer.smart_index(force_full=True)
                        print("✅ Stale heartbeat properly handled - indexing allowed")
                    except Exception as e:
                        if "already in progress" in str(e).lower():
                            pytest.fail(
                                "Stale heartbeat not properly detected - should allow indexing"
                            )
                        else:
                            raise

            finally:
                metadata_path.unlink(missing_ok=True)
                heartbeat_path = metadata_path.parent / "indexing_heartbeat.json"
                heartbeat_path.unlink(missing_ok=True)

    def test_heartbeat_cleanup_on_completion(self):
        """
        Test that heartbeat file is properly cleaned up when indexing completes successfully.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.file_extensions = ["py"]

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"

            mock_qdrant_client = Mock()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )
                heartbeat_path = metadata_path.parent / "indexing_heartbeat.json"

                # Create test files
                test_files = ["test1.py", "test2.py"]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello')")

                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer, "index_branch_changes"
                ) as mock_index_branch:

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]

                    # Mock return value for branch aware indexer
                    from code_indexer.services.branch_aware_indexer import (
                        BranchIndexingResult,
                    )

                    mock_index_branch.return_value = BranchIndexingResult(
                        content_points_created=1,
                        visibility_points_created=1,
                        visibility_points_updated=0,
                        content_points_reused=0,
                        processing_time=0.1,
                        files_processed=len(test_files),
                    )

                    # Run indexing
                    indexer.smart_index(force_full=True)

                    # Heartbeat file should be cleaned up after completion
                    assert (
                        not heartbeat_path.exists()
                    ), "Heartbeat file should be cleaned up after successful indexing completion"

            finally:
                metadata_path.unlink(missing_ok=True)
