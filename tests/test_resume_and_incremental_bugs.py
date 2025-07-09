"""
Test for resume and incremental indexing bugs.

These tests should FAIL initially, demonstrating the bugs:
1. Second indexing operation after successful completion should NOT reindex (should be incremental)
2. Canceled indexing operation should be resumable, but it's not working
"""

import pytest

from .conftest import local_temporary_directory
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.config import Config
from code_indexer.services.branch_aware_indexer import BranchIndexingResult


@pytest.mark.slow
class TestResumeAndIncrementalBugs:
    """Test for resume and incremental indexing functionality bugs."""

    def test_second_index_should_not_reindex_completed_project(self):
        """
        Test that running index twice on same project should NOT reindex on second run.

        First run: Index project completely
        Second run: Should detect no changes and skip reindexing

        This test should FAIL initially, demonstrating that second run does full reindex.
        """
        with local_temporary_directory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.exclude_files = []
            config.file_extensions = ["py"]

            # Add missing config attributes
            config.qdrant = Mock()
            config.qdrant.vector_size = 768
            config.chunking = Mock()
            config.chunking.chunk_size = 1000
            config.chunking.overlap_size = 100

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"
            mock_embedding_provider.get_embedding.return_value = [0.1] * 768
            mock_embedding_provider.get_model_info.return_value = {"dimensions": 768}

            mock_qdrant_client = Mock()
            mock_qdrant_client.create_point.return_value = {"id": "test-id"}
            mock_qdrant_client.upsert_points.return_value = True
            mock_qdrant_client.scroll_points.return_value = ([], None)

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )

                # Create test files
                test_files = ["test1.py", "test2.py", "test3.py"]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello world')")

                first_run_calls = []
                second_run_calls = []

                def track_first_run(*args, **kwargs):
                    first_run_calls.append(kwargs)
                    return BranchIndexingResult(
                        content_points_created=10,
                        content_points_reused=0,
                        processing_time=1.0,
                        files_processed=len(test_files),
                    )

                def track_second_run(*args, **kwargs):
                    second_run_calls.append(kwargs)
                    return BranchIndexingResult(
                        content_points_created=10,  # BUG: Should be 0 for incremental with no changes
                        content_points_reused=0,
                        processing_time=1.0,
                        files_processed=len(
                            test_files
                        ),  # BUG: Should be 0 for incremental with no changes
                    )

                # First indexing run - should do full index
                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer,
                    "index_branch_changes",
                    side_effect=track_first_run,
                ):

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]
                    mock_file_finder.find_modified_files.return_value = (
                        []
                    )  # No modified files on first run

                    stats1 = indexer.smart_index(force_full=False)  # Not forcing full

                    assert stats1.files_processed == len(
                        test_files
                    ), "First run should process all files"
                    assert (
                        len(first_run_calls) == 1
                    ), "Should have called index_branch_changes once"
                    print(f"✅ First run processed {stats1.files_processed} files")

                # Wait a bit to ensure different timestamps
                time.sleep(0.1)

                # Second indexing run - should be incremental and find NO changes
                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer,
                    "index_branch_changes",
                    side_effect=track_second_run,
                ):

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]
                    mock_file_finder.find_modified_files.return_value = (
                        []
                    )  # No files modified since first run

                    stats2 = indexer.smart_index(force_full=False)  # Not forcing full

                    # EXPECTED behavior (should pass after fix):
                    # - stats2.files_processed should be 0 (no files to reprocess)
                    # - second_run_calls should be empty (no indexing needed)

                    # CURRENT behavior (demonstrates the bug):
                    if stats2.files_processed > 0 or len(second_run_calls) > 0:
                        pytest.fail(
                            f"BUG REPRODUCED: Second indexing run processed {stats2.files_processed} files "
                            f"and made {len(second_run_calls)} indexing calls. "
                            f"Should have processed 0 files and made 0 calls since no files changed."
                        )

                    print(
                        f"✅ Second run correctly processed {stats2.files_processed} files (incremental)"
                    )

            finally:
                metadata_path.unlink(missing_ok=True)

    def test_canceled_index_should_be_resumable(self):
        """
        Test that canceling an indexing operation mid-way should be resumable.

        First run: Start indexing, cancel mid-way (simulate with exception)
        Second run: Should resume from where it left off, not start from scratch

        This test should FAIL initially, demonstrating that resume doesn't work.
        """
        with local_temporary_directory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.exclude_files = []
            config.file_extensions = ["py"]

            # Add missing config attributes
            config.qdrant = Mock()
            config.qdrant.vector_size = 768
            config.chunking = Mock()
            config.chunking.chunk_size = 1000
            config.chunking.overlap_size = 100

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"
            mock_embedding_provider.get_embedding.return_value = [0.1] * 768
            mock_embedding_provider.get_model_info.return_value = {"dimensions": 768}

            mock_qdrant_client = Mock()
            mock_qdrant_client.create_point.return_value = {"id": "test-id"}
            mock_qdrant_client.upsert_points.return_value = True
            mock_qdrant_client.scroll_points.return_value = ([], None)

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )

                # Create test files
                test_files = [
                    "test1.py",
                    "test2.py",
                    "test3.py",
                    "test4.py",
                    "test5.py",
                ]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello world')")

                cancelled_run_calls = []
                resume_run_calls = []

                def simulate_cancel_midway(*args, **kwargs):
                    """Simulate cancellation after processing some files."""
                    cancelled_run_calls.append(kwargs)

                    # First, simulate that we actually started indexing and processed some files
                    # (this would normally happen in the real BranchAwareIndexer)
                    # We need to call mark_file_completed for some files to simulate partial progress
                    test_file_paths = [
                        Path(tmpdir) / f for f in test_files[:2]
                    ]  # Process first 2 files
                    for file_path in test_file_paths:
                        indexer.progressive_metadata.mark_file_completed(
                            str(file_path), chunks_count=2
                        )

                    # Now simulate cancellation
                    raise KeyboardInterrupt("Simulated user cancellation")

                def track_resume_run(*args, **kwargs):
                    """Track the resume run."""
                    resume_run_calls.append(kwargs)

                    # Check how many files we're actually being asked to process
                    changed_files = kwargs.get("changed_files", [])
                    actual_files_to_process = len(changed_files)

                    # Should only process remaining files, not all files
                    return BranchIndexingResult(
                        content_points_created=actual_files_to_process * 2,
                        content_points_reused=0,
                        processing_time=1.0,
                        files_processed=actual_files_to_process,
                    )

                # First run - simulate cancellation
                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer,
                    "index_branch_changes",
                    side_effect=simulate_cancel_midway,
                ):

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]
                    mock_file_finder.find_modified_files.return_value = []

                    # This should raise KeyboardInterrupt
                    with pytest.raises(KeyboardInterrupt):
                        indexer.smart_index(force_full=False)

                    assert (
                        len(cancelled_run_calls) == 1
                    ), "Should have attempted indexing before cancellation"
                    print("✅ First run was cancelled as expected")

                # Check metadata state after cancellation
                metadata_stats = indexer.get_indexing_status()
                print(
                    f"Metadata after cancellation: status={metadata_stats.get('status')}, can_resume={metadata_stats.get('can_resume')}"
                )

                # Second run - should resume, not start from scratch
                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer,
                    "index_branch_changes",
                    side_effect=track_resume_run,
                ):

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]
                    mock_file_finder.find_modified_files.return_value = []

                    stats = indexer.smart_index(force_full=False)

                    # EXPECTED behavior (should pass after fix):
                    # - Should resume and only process remaining files
                    # - stats.files_processed should be < len(test_files)

                    # CURRENT behavior (demonstrates the bug):
                    if stats.files_processed == len(test_files):
                        pytest.fail(
                            f"BUG REPRODUCED: Resume run processed {stats.files_processed} files "
                            f"(all {len(test_files)} files). Should have resumed and processed fewer files. "
                            f"This indicates resume functionality is not working - it's starting from scratch."
                        )

                    print(
                        f"✅ Resume run correctly processed {stats.files_processed} remaining files"
                    )

            finally:
                metadata_path.unlink(missing_ok=True)

    def test_metadata_state_after_cancellation(self):
        """
        Test that metadata correctly tracks the cancellation state for resume.

        This test verifies that the progressive metadata correctly stores the
        interrupted state and provides the right information for resuming.
        """
        with local_temporary_directory() as tmpdir:
            config = Mock(spec=Config)
            config.codebase_dir = Path(tmpdir)
            config.exclude_dirs = ["node_modules", ".git"]
            config.exclude_files = []
            config.file_extensions = ["py"]

            # Add missing config attributes
            config.qdrant = Mock()
            config.qdrant.vector_size = 768
            config.chunking = Mock()
            config.chunking.chunk_size = 1000
            config.chunking.overlap_size = 100

            indexing_config = Mock()
            indexing_config.chunk_size = 1000
            indexing_config.chunk_overlap = 100
            indexing_config.max_file_size = 1000000
            config.indexing = indexing_config

            mock_embedding_provider = Mock()
            mock_embedding_provider.get_provider_name.return_value = "test-provider"
            mock_embedding_provider.get_current_model.return_value = "test-model"
            mock_embedding_provider.get_embedding.return_value = [0.1] * 768
            mock_embedding_provider.get_model_info.return_value = {"dimensions": 768}

            mock_qdrant_client = Mock()
            mock_qdrant_client.create_point.return_value = {"id": "test-id"}
            mock_qdrant_client.upsert_points.return_value = True
            mock_qdrant_client.scroll_points.return_value = ([], None)

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
                metadata_path = Path(f.name)

            try:
                indexer = SmartIndexer(
                    config, mock_embedding_provider, mock_qdrant_client, metadata_path
                )

                # Create test files
                test_files = ["test1.py", "test2.py", "test3.py"]
                for file_name in test_files:
                    (Path(tmpdir) / file_name).write_text("print('hello world')")

                def simulate_cancel_after_setup(*args, **kwargs):
                    """Simulate cancellation after setup but before processing."""
                    raise KeyboardInterrupt("Simulated cancellation")

                # Simulate cancellation during indexing
                with patch.object(
                    indexer, "get_git_status"
                ) as mock_git_status, patch.object(
                    indexer, "file_finder"
                ) as mock_file_finder, patch.object(
                    indexer.branch_aware_indexer,
                    "index_branch_changes",
                    side_effect=simulate_cancel_after_setup,
                ):

                    mock_git_status.return_value = {"git_available": False}
                    mock_file_finder.find_files.return_value = [
                        Path(tmpdir) / f for f in test_files
                    ]

                    with pytest.raises(KeyboardInterrupt):
                        indexer.smart_index(force_full=False)

                # Check metadata state
                stats = indexer.get_indexing_status()
                can_resume = indexer.can_resume()

                print(
                    f"After cancellation - Status: {stats.get('status')}, Can resume: {can_resume}"
                )
                print(f"Files to index: {len(stats.get('files_to_index', []))}")
                print(f"Files processed: {stats.get('files_processed', 0)}")

                # EXPECTED behavior:
                # - status should be "failed" or "in_progress"
                # - can_resume should be True
                # - files_to_index should contain the test files

                if not can_resume:
                    pytest.fail(
                        f"BUG REPRODUCED: can_resume is False after cancellation. "
                        f"Status: {stats.get('status')}, should allow resuming. "
                        f"This indicates the metadata is not properly tracking interrupted operations."
                    )

                if stats.get("status") == "completed":
                    pytest.fail(
                        "BUG REPRODUCED: Status is 'completed' after cancellation. "
                        "Should be 'failed' or 'in_progress' to indicate interrupted state."
                    )

                print("✅ Metadata correctly tracks cancellation state for resume")

            finally:
                metadata_path.unlink(missing_ok=True)
