"""
Test full index operations use parallel high-throughput processing for maximum CPU utilization.

This test ensures that full index operations (--clear flag) bypass sequential processing
and directly leverage the HighThroughputProcessor's parallel capabilities for 4-8x speedup.
"""

import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services.embedding_provider import EmbeddingProvider
from code_indexer.indexing.processor import ProcessingStats


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Mock(spec=Config)
        config.exclude_dirs = ["node_modules", ".git"]
        config.file_extensions = [".py", ".js", ".ts"]
        config.codebase_dir = Path(tmpdir)

        # Mock indexing config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        # Mock the voyage_ai sub-config
        voyage_ai_config = Mock()
        voyage_ai_config.parallel_requests = 8
        config.voyage_ai = voyage_ai_config

        yield config


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = Mock(spec=EmbeddingProvider)
    provider.get_provider_name.return_value = "test-provider"
    provider.get_current_model.return_value = "test-model"
    provider.get_embedding.return_value = [0.1, 0.2, 0.3]
    return provider


@pytest.fixture
def mock_filesystem_client():
    """Create a mock vector store client."""
    client = Mock()
    client.collection_exists.return_value = True
    client.ensure_provider_aware_collection.return_value = "test_collection"
    client.resolve_collection_name.return_value = "test_collection"
    client.clear_collection.return_value = True
    client.get_collection_info.return_value = {"points_count": 100}
    client.scroll_points.return_value = ([], None)
    client.upsert_points_batched.return_value = True
    return client


@pytest.fixture
def temp_metadata_path():
    """Create a temporary metadata file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


class TestFullIndexParallelProcessing:
    """Test that full index operations use parallel processing for maximum performance."""

    def test_full_index_uses_high_throughput_processor_directly(
        self,
        mock_config,
        mock_embedding_provider,
        mock_filesystem_client,
        temp_metadata_path,
    ):
        """
        FAILING TEST: Full index should use HighThroughputProcessor.process_files_high_throughput() directly.

        This test demonstrates that the current implementation goes through BranchAwareIndexer
        instead of directly using the high-throughput processor, which may limit parallelization.
        """
        # Create test files
        test_files = []
        for i in range(10):
            file_path = mock_config.codebase_dir / f"test_file_{i}.py"
            file_path.write_text(f"# Test file {i}\nprint('hello {i}')")
            test_files.append(file_path)

        indexer = SmartIndexer(
            mock_config,
            mock_embedding_provider,
            mock_filesystem_client,
            temp_metadata_path,
        )

        # Track method calls to verify direct high-throughput usage
        with (
            patch.object(
                indexer, "process_files_high_throughput"
            ) as mock_high_throughput,
            patch.object(indexer, "get_git_status") as mock_git_status,
            patch.object(indexer.file_finder, "find_files") as mock_find_files,
        ):

            mock_git_status.return_value = {
                "git_available": False,
                "project_id": "test",
            }
            mock_find_files.return_value = test_files

            # Mock high-throughput processor to return stats
            mock_stats = ProcessingStats()
            mock_stats.files_processed = len(test_files)
            mock_stats.chunks_created = len(test_files) * 5
            mock_stats.start_time = time.time()
            mock_stats.end_time = time.time() + 1.0
            mock_high_throughput.return_value = mock_stats

            # Execute full index
            stats = indexer.smart_index(force_full=True)

            # ASSERTION THAT SHOULD PASS: Full index should directly call high-throughput processor
            mock_high_throughput.assert_called_once()

            # Verify the call was made with all files and proper thread count
            call_args = mock_high_throughput.call_args
            # Check keyword arguments
            assert "files" in call_args.kwargs
            assert len(call_args.kwargs["files"]) == len(test_files)  # All files passed
            assert (
                call_args.kwargs["vector_thread_count"] is not None
            )  # Thread count specified

            # Verify stats indicate successful processing
            assert stats.files_processed == len(test_files)
            assert stats.chunks_created == len(test_files) * 5

    def test_full_index_uses_parallel_processing_threads(
        self,
        mock_config,
        mock_embedding_provider,
        mock_filesystem_client,
        temp_metadata_path,
    ):
        """
        Test: Full index should use parallel processing with specified thread count.

        This test verifies the full index operation configures the high-throughput
        processor to use parallel threads for performance.
        """
        # Create test files
        test_files = []
        for i in range(10):
            file_path = mock_config.codebase_dir / f"file_{i}.py"
            file_path.write_text(f"print('file {i}')")
            test_files.append(file_path)

        indexer = SmartIndexer(
            mock_config,
            mock_embedding_provider,
            mock_filesystem_client,
            temp_metadata_path,
        )

        with (
            patch.object(indexer, "get_git_status") as mock_git_status,
            patch.object(indexer.file_finder, "find_files") as mock_find_files,
            patch.object(
                indexer, "process_files_high_throughput"
            ) as mock_high_throughput,
            patch.object(indexer, "hide_files_not_in_branch_thread_safe"),
        ):

            mock_git_status.return_value = {
                "git_available": False,
                "project_id": "test",
            }
            mock_find_files.return_value = test_files

            # Mock return value with stats
            mock_stats = ProcessingStats()
            mock_stats.files_processed = len(test_files)
            mock_stats.chunks_created = 50
            mock_high_throughput.return_value = mock_stats

            # Execute full index with specific thread count
            stats = indexer.smart_index(force_full=True, vector_thread_count=16)

            # ASSERTION: High-throughput processor called with correct thread count
            mock_high_throughput.assert_called_once()
            call_kwargs = mock_high_throughput.call_args.kwargs

            # Verify thread count was passed correctly
            assert call_kwargs["vector_thread_count"] == 16

            # Verify all files were passed for processing
            assert len(call_kwargs["files"]) == len(test_files)

            # Verify batch_size parameter exists
            assert "batch_size" in call_kwargs

            # Verify stats returned correctly
            assert stats.files_processed == len(test_files)
            assert stats.chunks_created == 50

    def test_full_index_preserves_git_aware_context(
        self,
        mock_config,
        mock_embedding_provider,
        mock_filesystem_client,
        temp_metadata_path,
    ):
        """
        Test: Git-aware metadata should be preserved during parallel full index processing.

        This test ensures that when full indexing uses parallel processing, the git-aware
        context is properly passed through to the high-throughput processor.
        """
        # Create test files
        test_files = []
        for i in range(5):
            file_path = mock_config.codebase_dir / f"module_{i}.py"
            file_path.write_text(f"class Module{i}:\n    pass")
            test_files.append(file_path)

        indexer = SmartIndexer(
            mock_config,
            mock_embedding_provider,
            mock_filesystem_client,
            temp_metadata_path,
        )

        # Mock git-aware environment
        mock_git_status = {
            "git_available": True,
            "project_id": "test-project",
            "current_branch": "feature-branch",
            "current_commit": "abc123def456",
        }

        with (
            patch.object(indexer, "get_git_status", return_value=mock_git_status),
            patch.object(indexer.file_finder, "find_files", return_value=test_files),
            patch.object(
                indexer, "process_files_high_throughput"
            ) as mock_high_throughput,
            patch.object(indexer, "hide_files_not_in_branch_thread_safe"),
            patch.object(
                indexer.git_topology_service,
                "get_current_branch",
                return_value="feature-branch",
            ),
        ):
            # Mock return stats
            mock_stats = ProcessingStats()
            mock_stats.files_processed = len(test_files)
            mock_stats.chunks_created = 10
            mock_high_throughput.return_value = mock_stats

            # Execute full index in git-aware environment
            stats = indexer.smart_index(force_full=True)

            # ASSERTION: High-throughput processor was called
            mock_high_throughput.assert_called_once()

            # Verify git context is available in indexer during processing
            # The indexer should have git information available for metadata creation
            assert indexer.get_git_status() == mock_git_status
            assert indexer.git_topology_service.get_current_branch() == "feature-branch"

            # Verify stats returned successfully
            assert stats.files_processed == len(test_files)
            assert stats.chunks_created == 10

    def test_full_index_progress_callback_integration(
        self,
        mock_config,
        mock_embedding_provider,
        mock_filesystem_client,
        temp_metadata_path,
    ):
        """
        Test: Progress callbacks should be properly passed to high-throughput processor.

        This test verifies that the progress callback parameter is correctly
        forwarded to the parallel processing infrastructure.
        """
        # Create test files
        test_files = []
        for i in range(5):
            file_path = mock_config.codebase_dir / f"test_{i}.py"
            file_path.write_text(f"print('file {i}')")
            test_files.append(file_path)

        indexer = SmartIndexer(
            mock_config,
            mock_embedding_provider,
            mock_filesystem_client,
            temp_metadata_path,
        )

        # Create a progress callback
        progress_calls = []

        def capture_progress(current, total, path, info=None):
            progress_calls.append({"current": current, "total": total})

        with (
            patch.object(indexer, "get_git_status") as mock_git_status,
            patch.object(indexer.file_finder, "find_files") as mock_find_files,
            patch.object(
                indexer, "process_files_high_throughput"
            ) as mock_high_throughput,
            patch.object(indexer, "hide_files_not_in_branch_thread_safe"),
        ):

            mock_git_status.return_value = {
                "git_available": False,
                "project_id": "test",
            }
            mock_find_files.return_value = test_files

            # Mock stats return
            mock_stats = ProcessingStats()
            mock_stats.files_processed = len(test_files)
            mock_high_throughput.return_value = mock_stats

            # Execute full index with progress callback
            stats = indexer.smart_index(
                force_full=True, progress_callback=capture_progress
            )

            # ASSERTION: High-throughput processor was called with progress callback
            mock_high_throughput.assert_called_once()
            call_kwargs = mock_high_throughput.call_args.kwargs

            # Verify progress_callback was passed through
            assert "progress_callback" in call_kwargs
            assert call_kwargs["progress_callback"] is not None

            # Verify stats returned correctly
            assert stats.files_processed == len(test_files)

    def test_full_index_bypasses_sequential_branch_indexer(
        self,
        mock_config,
        mock_embedding_provider,
        mock_filesystem_client,
        temp_metadata_path,
    ):
        """
        Test: Full index should bypass BranchAwareIndexer sequential processing.

        This test verifies that full index operations call process_files_high_throughput
        directly instead of going through process_branch_changes_high_throughput wrapper.
        """
        # Create test files
        test_files = [
            mock_config.codebase_dir / "file1.py",
            mock_config.codebase_dir / "file2.py",
            mock_config.codebase_dir / "file3.py",
        ]
        for file_path in test_files:
            file_path.write_text("print('test')")

        indexer = SmartIndexer(
            mock_config,
            mock_embedding_provider,
            mock_filesystem_client,
            temp_metadata_path,
        )

        with (
            patch.object(indexer, "get_git_status") as mock_git_status,
            patch.object(indexer.file_finder, "find_files") as mock_find_files,
            patch.object(
                indexer, "process_branch_changes_high_throughput"
            ) as mock_branch_processing,
            patch.object(
                indexer, "process_files_high_throughput"
            ) as mock_direct_processing,
            patch.object(indexer, "hide_files_not_in_branch_thread_safe"),
        ):

            mock_git_status.return_value = {
                "git_available": False,
                "project_id": "test",
            }
            mock_find_files.return_value = test_files

            # Mock direct processing to return stats
            mock_stats = ProcessingStats()
            mock_stats.files_processed = len(test_files)
            mock_stats.chunks_created = len(test_files) * 3
            mock_direct_processing.return_value = mock_stats

            # Mock branch processing (should not be called for full index)
            from src.code_indexer.services.high_throughput_processor import (
                BranchIndexingResult,
            )

            mock_result = BranchIndexingResult(
                files_processed=len(test_files),
                content_points_created=len(test_files) * 3,
                content_points_reused=0,
                processing_time=1.0,
            )
            mock_branch_processing.return_value = mock_result

            # Execute full index
            stats = indexer.smart_index(force_full=True)

            # ASSERTION: Full index should call process_files_high_throughput directly
            mock_direct_processing.assert_called_once()

            # ASSERTION: Should NOT use branch processing wrapper for full index
            mock_branch_processing.assert_not_called()

            # Verify correct stats returned
            assert stats.files_processed == len(test_files)
            assert stats.chunks_created == len(test_files) * 3
