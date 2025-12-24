"""
Integration tests for Story 02: Replace Sequential with Parallel Processing.

Tests validate that HighThroughputProcessor correctly uses FileChunkingManager
for parallel file processing instead of sequential chunking loops.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from concurrent.futures import Future

import pytest

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.file_chunking_manager import FileProcessingResult
from code_indexer.indexing.processor import ProcessingStats
from ...conftest import local_temporary_directory

# Mark all tests in this file as integration
pytestmark = pytest.mark.integration


class TestStory02ParallelFileProcessing:
    """Test Story 02: Complete sequential to parallel processing replacement."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Set up test environment."""
        # Create test config
        self.config = Config(
            codebase_dir="/tmp/test-project",
            file_extensions=["py", "js", "ts"],
            exclude_dirs=["node_modules", "__pycache__"],
        )

        # Create mock embedding provider
        self.embedding_provider = MagicMock()
        self.embedding_provider.get_embedding.return_value = [0.1] * 768
        self.embedding_provider.get_current_model.return_value = "test-model"

        # Create mock Filesystem client
        self.filesystem_client = MagicMock()
        self.filesystem_client.create_point.return_value = {"id": "test-point"}
        self.filesystem_client.upsert_points_batched.return_value = True

    def test_should_fail_uses_file_chunking_manager_for_parallel_processing(self):
        """FAILING TEST: Verify FileChunkingManager is used for parallel processing."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            vector_store_client=self.filesystem_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(3):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    return {i}\n")
                test_files.append(test_file)

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=mock_get_file_metadata,
            ):
                # Track FileChunkingManager usage
                file_manager_created = False
                submit_calls = []

                original_context_manager = None

                def track_file_manager(*args, **kwargs):
                    nonlocal file_manager_created, original_context_manager
                    file_manager_created = True

                    # Create a mock context manager
                    mock_manager = MagicMock()

                    def mock_submit(file_path, metadata, progress_callback):
                        submit_calls.append((file_path, metadata))
                        # Create mock future with FileProcessingResult
                        future = Future()
                        result = FileProcessingResult(
                            success=True,
                            file_path=file_path,
                            chunks_processed=2,
                            processing_time=0.1,
                        )
                        future.set_result(result)
                        return future

                    mock_manager.submit_file_for_processing = mock_submit
                    mock_manager.__enter__ = lambda x: x
                    mock_manager.__exit__ = lambda x, y, z, w: None

                    return mock_manager

                with patch(
                    "code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=track_file_manager,
                ):
                    # Process files
                    stats = processor.process_files_high_throughput(
                        files=test_files,
                        vector_thread_count=2,
                        batch_size=10,
                    )

                    # ASSERTIONS for Story 02 acceptance criteria

                    # Scenario: Complete Sequential Loop Replacement
                    assert (
                        file_manager_created
                    ), "FileChunkingManager should be instantiated"
                    assert len(submit_calls) == len(
                        test_files
                    ), "All files should be submitted to FileChunkingManager"

                    # Scenario: File-Level Result Collection
                    assert stats.files_processed == len(
                        test_files
                    ), "Should process all files at file-level"
                    assert (
                        stats.chunks_created > 0
                    ), "Should aggregate chunks from FileProcessingResult"

                    # Scenario: Method Interface Compatibility
                    assert isinstance(
                        stats, ProcessingStats
                    ), "Return type should be ProcessingStats"
                    assert hasattr(
                        stats, "files_processed"
                    ), "Stats should have files_processed"
                    assert hasattr(
                        stats, "chunks_created"
                    ), "Stats should have chunks_created"

    def test_should_fail_immediate_feedback_during_file_submission(self):
        """FAILING TEST: Verify immediate feedback during file submission."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            vector_store_client=self.filesystem_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(3):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    return {i}\n")
                test_files.append(test_file)

            # Track progress callbacks for immediate feedback
            progress_calls = []

            def progress_callback(
                current,
                total,
                path,
                info=None,
                slot_tracker=None,
                concurrent_files=None,
            ):
                progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "path": str(path),
                        "info": info,
                        "timestamp": time.time(),
                    }
                )

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=mock_get_file_metadata,
            ):
                # Mock FileChunkingManager to track submission timing
                def track_file_manager(*args, **kwargs):
                    mock_manager = MagicMock()

                    def mock_submit(file_path, metadata, progress_callback_inner):
                        # Call immediate feedback callback
                        if progress_callback_inner:
                            progress_callback_inner(
                                0, 0, file_path, info="📥 Queued for processing"
                            )

                        # Create delayed future to simulate processing
                        future = Future()

                        def complete_after_delay():
                            time.sleep(0.05)  # Simulate processing delay
                            result = FileProcessingResult(
                                success=True,
                                file_path=file_path,
                                chunks_processed=2,
                                processing_time=0.05,
                            )
                            future.set_result(result)

                        import threading

                        threading.Thread(target=complete_after_delay).start()
                        return future

                    mock_manager.submit_file_for_processing = mock_submit
                    mock_manager.__enter__ = lambda x: x
                    mock_manager.__exit__ = lambda x, y, z, w: None

                    return mock_manager

                with patch(
                    "code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=track_file_manager,
                ):
                    start_time = time.time()

                    # Process files with progress callback
                    processor.process_files_high_throughput(
                        files=test_files,
                        vector_thread_count=2,
                        batch_size=10,
                        progress_callback=progress_callback,  # Pass the callback
                    )

                    submission_time = time.time() - start_time

                    # ASSERTIONS for Story 02 acceptance criteria

                    # Scenario: Immediate Feedback During Submission
                    queued_callbacks = [
                        call
                        for call in progress_calls
                        if "📥 Queued" in str(call.get("info", ""))
                    ]
                    assert len(queued_callbacks) >= len(
                        test_files
                    ), "Should have immediate queuing feedback for all files"

                    # Verify submission completes immediately (non-blocking)
                    assert (
                        submission_time < 1.0
                    ), f"File submission should complete immediately, took {submission_time:.2f}s"

                    # Verify no silent periods during submission
                    if len(progress_calls) > 1:
                        time_gaps = []
                        for i in range(1, len(progress_calls)):
                            gap = (
                                progress_calls[i]["timestamp"]
                                - progress_calls[i - 1]["timestamp"]
                            )
                            time_gaps.append(gap)

                        # No gap should be longer than reasonable processing time
                        max_gap = max(time_gaps) if time_gaps else 0
                        assert (
                            max_gap < 2.0
                        ), f"Should have no silent periods, max gap was {max_gap:.2f}s"

    def test_should_fail_file_level_result_collection_replaces_chunk_level(self):
        """FAILING TEST: Verify file-level result collection replaces chunk-level processing."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            vector_store_client=self.filesystem_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(2):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(
                    f"def test{i}():\n    return {i}\n" * 10
                )  # Multi-chunk files
                test_files.append(test_file)

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 300,
                }

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=mock_get_file_metadata,
            ):
                # Track that file-level futures are used, not chunk-level
                file_futures_used = False
                file_results_collected = []

                def track_file_manager(*args, **kwargs):
                    nonlocal file_futures_used
                    file_futures_used = True
                    mock_manager = MagicMock()

                    def mock_submit(file_path, metadata, progress_callback):
                        # Return FileProcessingResult (file-level, not chunk-level)
                        future = Future()
                        result = FileProcessingResult(
                            success=True,
                            file_path=file_path,
                            chunks_processed=3,  # Multiple chunks per file
                            processing_time=0.1,
                        )
                        file_results_collected.append(result)
                        future.set_result(result)
                        return future

                    mock_manager.submit_file_for_processing = mock_submit
                    mock_manager.__enter__ = lambda x: x
                    mock_manager.__exit__ = lambda x, y, z, w: None

                    return mock_manager

                with patch(
                    "code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=track_file_manager,
                ):
                    # Process files
                    stats = processor.process_files_high_throughput(
                        files=test_files,
                        vector_thread_count=2,
                        batch_size=10,
                    )

                    # ASSERTIONS for Story 02 acceptance criteria

                    # Scenario: File-Level Result Collection
                    assert (
                        file_futures_used
                    ), "Should use file-level futures, not chunk futures"
                    assert len(file_results_collected) == len(
                        test_files
                    ), "Should collect one result per file"

                    # Verify statistics aggregated from FileProcessingResult objects
                    assert stats.files_processed == len(
                        test_files
                    ), "Files processed should equal number of files"
                    expected_chunks = sum(
                        result.chunks_processed for result in file_results_collected
                    )
                    assert (
                        stats.chunks_created == expected_chunks
                    ), "Chunks should be aggregated from FileProcessingResult"

    def test_should_fail_error_handling_and_cancellation_preservation(self):
        """FAILING TEST: Verify error handling and cancellation are preserved."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            vector_store_client=self.filesystem_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(5):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    return {i}\n")
                test_files.append(test_file)

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": f"hash-{file_path.name}",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=mock_get_file_metadata,
            ):
                cancellation_checked = False

                def track_file_manager(*args, **kwargs):
                    mock_manager = MagicMock()

                    def mock_submit(file_path, metadata, progress_callback):
                        # Create delayed future with some processing time
                        future = Future()

                        def complete_with_delay():
                            nonlocal cancellation_checked
                            time.sleep(0.1)  # Allow cancellation to occur

                            # Check if processor was cancelled during processing
                            if processor.cancelled:
                                cancellation_checked = True
                                result = FileProcessingResult(
                                    success=False,
                                    file_path=file_path,
                                    chunks_processed=0,
                                    processing_time=0.1,
                                    error="Cancelled",
                                )
                            else:
                                result = FileProcessingResult(
                                    success=True,
                                    file_path=file_path,
                                    chunks_processed=2,
                                    processing_time=0.1,
                                )
                            future.set_result(result)

                        import threading

                        threading.Thread(target=complete_with_delay).start()
                        return future

                    mock_manager.submit_file_for_processing = mock_submit
                    mock_manager.__enter__ = lambda x: x
                    mock_manager.__exit__ = lambda x, y, z, w: None

                    return mock_manager

                with patch(
                    "code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=track_file_manager,
                ):
                    # Start processing in separate thread
                    import threading

                    stats = None

                    def run_processing():
                        nonlocal stats
                        stats = processor.process_files_high_throughput(
                            files=test_files,
                            vector_thread_count=2,
                            batch_size=10,
                        )

                    processing_thread = threading.Thread(target=run_processing)
                    processing_thread.start()

                    # Cancel after brief delay
                    time.sleep(0.05)
                    processor.request_cancellation()

                    # Wait for processing to complete
                    processing_thread.join(timeout=3.0)

                    # ASSERTIONS for Story 02 acceptance criteria

                    # Scenario: Error Handling and Cancellation Integration
                    assert processor.cancelled, "Cancellation flag should be set"
                    assert stats is not None, "Should return stats even when cancelled"
                    assert hasattr(
                        stats, "cancelled"
                    ), "Stats should track cancellation"

                    # Should have stopped processing due to cancellation
                    assert stats.files_processed < len(
                        test_files
                    ), "Should process fewer files due to cancellation"

    def test_should_fail_backward_compatibility_with_existing_callers(self):
        """FAILING TEST: Verify backward compatibility is maintained."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            vector_store_client=self.filesystem_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_file = Path(temp_dir) / "test.py"
            test_file.write_text("def test():\n    pass\n")

            # Mock file identifier
            def mock_get_file_metadata(file_path):
                return {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 50,
                }

            with patch.object(
                processor.file_identifier,
                "get_file_metadata",
                side_effect=mock_get_file_metadata,
            ):
                # Mock FileChunkingManager
                def track_file_manager(*args, **kwargs):
                    mock_manager = MagicMock()
                    mock_manager.submit_file_for_processing.return_value = Future()
                    mock_manager.submit_file_for_processing.return_value.set_result(
                        FileProcessingResult(
                            success=True,
                            file_path=test_file,
                            chunks_processed=1,
                            processing_time=0.1,
                        )
                    )
                    mock_manager.__enter__ = lambda x: x
                    mock_manager.__exit__ = lambda x, y, z, w: None
                    return mock_manager

                with patch(
                    "code_indexer.services.high_throughput_processor.FileChunkingManager",
                    side_effect=track_file_manager,
                ):
                    # Test all existing method signature patterns

                    # Pattern 1: Basic call
                    stats1 = processor.process_files_high_throughput(
                        files=[test_file],
                        vector_thread_count=2,
                    )

                    # Pattern 2: With batch size
                    stats2 = processor.process_files_high_throughput(
                        files=[test_file],
                        vector_thread_count=4,
                        batch_size=25,
                    )

                    # Pattern 3: With progress callback
                    callback_calls = []

                    def progress_callback(
                        current,
                        total,
                        path,
                        info=None,
                        slot_tracker=None,
                        concurrent_files=None,
                    ):
                        callback_calls.append((current, total, str(path), info))

                    stats3 = processor.process_files_high_throughput(
                        files=[test_file],
                        vector_thread_count=2,
                        batch_size=50,
                        progress_callback=progress_callback,  # Pass the callback
                    )

                    # ASSERTIONS for Story 02 acceptance criteria

                    # Scenario: Maintain Method Interface Compatibility
                    assert isinstance(
                        stats1, ProcessingStats
                    ), "Should return ProcessingStats"
                    assert isinstance(
                        stats2, ProcessingStats
                    ), "Should return ProcessingStats"
                    assert isinstance(
                        stats3, ProcessingStats
                    ), "Should return ProcessingStats"

                    # All calls should work with same signature
                    for stats in [stats1, stats2, stats3]:
                        assert hasattr(
                            stats, "files_processed"
                        ), "Should have files_processed attribute"
                        assert hasattr(
                            stats, "chunks_created"
                        ), "Should have chunks_created attribute"
                        assert hasattr(
                            stats, "start_time"
                        ), "Should have start_time attribute"
                        assert hasattr(
                            stats, "end_time"
                        ), "Should have end_time attribute"

                    # Progress callback should have been called for stats3
                    assert len(callback_calls) > 0, "Progress callback should be called"
