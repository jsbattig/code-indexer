"""
Unit tests for FileChunkingManager.

Tests the complete parallel file processing lifecycle with file atomicity
and immediate progress feedback.
"""

import pytest
import tempfile
import time
import threading
from unittest.mock import Mock
from pathlib import Path
from concurrent.futures import Future
from typing import Dict, List

from code_indexer.services.file_chunking_manager import (
    FileChunkingManager,
    FileProcessingResult,
)


class MockVectorCalculationManager:
    """Mock VectorCalculationManager for testing."""

    def __init__(self):
        self.submitted_chunks = []
        self.submit_delay = 0.01  # Small delay to simulate processing
        self.cancellation_event = threading.Event()  # Add required cancellation_event

    def submit_chunk(self, chunk_text: str, metadata: Dict) -> Future:
        """Mock submit_chunk that returns a future."""
        future = Future()

        # Simulate async processing
        def complete_future():
            time.sleep(self.submit_delay)
            from code_indexer.services.vector_calculation_manager import VectorResult

            result = VectorResult(
                task_id=f"task_{len(self.submitted_chunks)}",
                embedding=[0.1] * 768,  # Mock embedding
                metadata=metadata.copy(),
                processing_time=self.submit_delay,
                error=None,
            )
            future.set_result(result)

        # Execute in background thread
        thread = threading.Thread(target=complete_future)
        thread.start()

        # Track submitted chunks for verification
        self.submitted_chunks.append(
            {"text": chunk_text, "metadata": metadata, "future": future}
        )

        return future


class MockFixedSizeChunker:
    """Mock FixedSizeChunker for testing."""

    def __init__(self):
        self.chunk_calls = []

    def chunk_file(self, file_path: Path) -> List[Dict]:
        """Mock chunk_file method."""
        self.chunk_calls.append(file_path)

        # Simulate chunking based on file content
        try:
            with open(file_path, "r") as f:
                content = f.read()
        except (IOError, OSError):
            content = "mock content"

        # Return mock chunks
        return (
            [
                {
                    "text": content[:500] if len(content) > 500 else content,
                    "chunk_index": 0,
                    "total_chunks": 2 if len(content) > 500 else 1,
                    "size": min(500, len(content)),
                    "file_path": str(file_path),
                    "file_extension": file_path.suffix.lstrip("."),
                    "line_start": 1,
                    "line_end": 10,
                },
                {
                    "text": content[400:] if len(content) > 500 else "",
                    "chunk_index": 1,
                    "total_chunks": 2 if len(content) > 500 else 1,
                    "size": max(0, len(content) - 400),
                    "file_path": str(file_path),
                    "file_extension": file_path.suffix.lstrip("."),
                    "line_start": 8,
                    "line_end": 20,
                },
            ]
            if len(content) > 500
            else [
                {
                    "text": content,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "size": len(content),
                    "file_path": str(file_path),
                    "file_extension": file_path.suffix.lstrip("."),
                    "line_start": 1,
                    "line_end": 5,
                }
            ]
        )


class MockQdrantClient:
    """Mock QdrantClient for testing."""

    def __init__(self):
        self.upserted_points = []
        self.upsert_calls = []
        self.should_fail = False

    def upsert_points_atomic(self, points: List[Dict], collection_name=None) -> bool:
        """Mock atomic upsert method."""
        self.upsert_calls.append(
            {
                "points": points.copy(),
                "collection_name": collection_name,
                "point_count": len(points),
            }
        )

        if self.should_fail:
            return False

        self.upserted_points.extend(points)
        return True


class TestFileChunkingManagerAcceptanceCriteria:
    """Test all acceptance criteria from the story specification."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_vector_manager = MockVectorCalculationManager()
        self.mock_chunker = MockFixedSizeChunker()
        self.mock_qdrant_client = MockQdrantClient()

        # Create temporary test file
        self.test_file = tempfile.NamedTemporaryFile(
            mode="w", delete=False, suffix=".py"
        )
        self.test_file.write("print('Hello, World!')\n" * 100)  # 2000+ characters
        self.test_file.close()
        self.test_file_path = Path(self.test_file.name)

    def teardown_method(self):
        """Cleanup test environment."""
        if self.test_file_path.exists():
            self.test_file_path.unlink()

    def test_complete_functional_implementation_initialization(self):
        """Test FileChunkingManager complete initialization per acceptance criteria."""
        # Given FileChunkingManager class with complete implementation
        # When initialized with vector_manager, chunker, and thread_count
        thread_count = 4
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=thread_count,
        )

        # Then creates ThreadPoolExecutor with (thread_count + 2) workers per user specs
        with manager:
            # This should NOT raise an error and should create proper thread pool
            assert hasattr(manager, "executor")
            assert manager.executor is not None
            # ThreadPoolExecutor should be configured for thread_count + 2
            # (We'll verify this in the implementation)

        # And provides submit_file_for_processing() method that returns Future
        assert hasattr(manager, "submit_file_for_processing")
        assert callable(getattr(manager, "submit_file_for_processing"))

    def test_submit_file_returns_future(self):
        """Test that submit_file_for_processing returns Future."""
        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}
            progress_callback = Mock()

            # When submitting file for processing
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, progress_callback
            )

            # Then returns Future
            assert isinstance(future, Future)

    def test_immediate_queuing_feedback(self):
        """Test that individual progress callbacks are correctly removed.

        SURGICAL FIX: This test validates that individual file callbacks
        are no longer sent to prevent spam in the fixed N-line display.
        The ConsolidatedFileTracker now handles all display updates.
        """
        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}
            progress_callback = Mock()

            # When submit_file_for_processing() is called
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, progress_callback
            )

            # SURGICAL FIX VALIDATION: No immediate individual callbacks
            # Progress is now handled by ConsolidatedFileTracker
            progress_callback.assert_not_called()

            # Verify the future was returned for async processing
            assert isinstance(future, Future)

    def test_worker_thread_complete_file_processing_lifecycle(self):
        """Test complete file lifecycle in worker thread."""
        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}
            progress_callback = Mock()

            # When worker thread processes file using _process_file_complete_lifecycle()
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, progress_callback
            )

            # Wait for completion
            result = future.result(timeout=10.0)

            # Then MOVE chunking logic from main thread to worker thread
            # And chunks = self.fixed_size_chunker.chunk_file(file_path) executes in worker
            assert len(self.mock_chunker.chunk_calls) == 1
            assert self.mock_chunker.chunk_calls[0] == self.test_file_path

            # And ALL chunks submitted to existing VectorCalculationManager (unchanged)
            assert len(self.mock_vector_manager.submitted_chunks) > 0

            # And MOVE qdrant_client.upsert_points_atomic() from main thread to worker thread
            assert len(self.mock_qdrant_client.upsert_calls) == 1

            # And FileProcessingResult returned with success/failure status
            assert isinstance(result, FileProcessingResult)
            assert result.success is True
            assert result.chunks_processed > 0

    def test_file_atomicity_within_worker_threads(self):
        """Test that file atomicity is maintained within worker threads."""
        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}

            # Submit file for processing
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            future.result(timeout=10.0)

            # Verify atomicity: all chunks from one file written together
            assert len(self.mock_qdrant_client.upsert_calls) == 1
            upsert_call = self.mock_qdrant_client.upsert_calls[0]

            # All points in single atomic operation
            assert upsert_call["point_count"] > 0

            # All points should be from same file
            for point in upsert_call["points"]:
                assert str(self.test_file_path) in str(
                    point.get("payload", {}).get("path", "")
                )

    def test_error_handling_chunking_failure(self):
        """Test error handling when chunking fails."""
        # Mock chunker to raise exception
        failing_chunker = Mock()
        failing_chunker.chunk_file.side_effect = ValueError("Chunking failed")

        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=failing_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}

            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            result = future.result(timeout=5.0)

            # Then errors logged with specific file context
            # And FileProcessingResult indicates failure with error details
            assert isinstance(result, FileProcessingResult)
            assert result.success is False
            assert result.error is not None
            assert "Chunking failed" in str(result.error)

    def test_error_handling_vector_processing_failure(self):
        """Test error handling when vector processing fails."""
        # Mock vector manager to fail
        failing_vector_manager = Mock()
        failing_future = Future()
        failing_future.set_exception(RuntimeError("Vector processing failed"))
        failing_vector_manager.submit_chunk.return_value = failing_future

        with FileChunkingManager(
            vector_manager=failing_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}

            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            result = future.result(timeout=5.0)

            # FileProcessingResult should indicate failure
            assert result.success is False
            assert result.error is not None

    def test_error_handling_qdrant_write_failure(self):
        """Test error handling when Qdrant writing fails."""
        # Mock Qdrant client to fail
        self.mock_qdrant_client.should_fail = True

        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}

            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            result = future.result(timeout=10.0)

            # FileProcessingResult should indicate failure
            assert result.success is False
            assert result.error is not None
            assert "Qdrant write failed" in str(result.error)

    def test_thread_pool_management(self):
        """Test ThreadPoolExecutor lifecycle management."""
        manager = FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=3,
        )

        # Context manager should start thread pool
        with manager:
            assert hasattr(manager, "executor")
            assert manager.executor is not None

            # Should be able to submit work
            metadata = {"project_id": "test", "file_hash": "abc123"}
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            result = future.result(timeout=5.0)
            assert isinstance(result, FileProcessingResult)

        # After context exit, thread pool should be shut down
        # (Implementation will handle this)

    def test_parallel_file_processing_efficiency(self):
        """Test that parallel processing improves efficiency for multiple files."""
        # Create multiple test files
        test_files = []
        for i in range(3):
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=f"_test_{i}.py"
            )
            temp_file.write(f"# File {i}\n" + "print('test')\n" * 50)
            temp_file.close()
            test_files.append(Path(temp_file.name))

        try:
            with FileChunkingManager(
                vector_manager=self.mock_vector_manager,
                chunker=self.mock_chunker,
                qdrant_client=self.mock_qdrant_client,
                thread_count=2,
            ) as manager:

                start_time = time.time()
                futures = []

                # Submit multiple files
                for file_path in test_files:
                    metadata = {
                        "project_id": "test",
                        "file_hash": f"hash_{file_path.name}",
                    }
                    future = manager.submit_file_for_processing(
                        file_path, metadata, Mock()
                    )
                    futures.append(future)

                # Wait for all to complete
                results = []
                for future in futures:
                    result = future.result(timeout=10.0)
                    results.append(result)

                processing_time = time.time() - start_time

                # All files should be processed successfully
                assert len(results) == 3
                for result in results:
                    assert result.success is True
                    assert result.chunks_processed > 0

                # Should be faster than sequential processing
                # (This is more of a performance test)
                assert processing_time < 5.0  # Reasonable timeout

        finally:
            # Cleanup test files
            for file_path in test_files:
                if file_path.exists():
                    file_path.unlink()

    def test_integration_with_existing_system_compatibility(self):
        """Test integration with existing VectorCalculationManager and FixedSizeChunker."""
        # This test ensures FileChunkingManager works with real components
        # (when available) without breaking existing interfaces

        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {
                "project_id": "test_project",
                "file_hash": "test_hash_123",
                "git_available": False,
                "commit_hash": None,
                "branch": None,
                "file_mtime": 1640995200,
                "file_size": 1000,
            }

            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, Mock()
            )

            result = future.result(timeout=5.0)

            # Should work with existing metadata structure
            assert result.success is True

            # Should call existing chunker interface
            assert len(self.mock_chunker.chunk_calls) == 1

            # Should call existing vector manager interface
            assert len(self.mock_vector_manager.submitted_chunks) > 0

            # Should call existing Qdrant client interface
            assert len(self.mock_qdrant_client.upsert_calls) == 1

    def test_addresses_user_problems_efficiency_and_feedback(self):
        """Test that FileChunkingManager addresses the specific user problems.

        SURGICAL FIX UPDATE: Progress callbacks are now handled by
        ConsolidatedFileTracker at the system level, not individual files.
        This test validates the efficient parallel processing architecture.
        """
        with FileChunkingManager(
            vector_manager=self.mock_vector_manager,
            chunker=self.mock_chunker,
            qdrant_client=self.mock_qdrant_client,
            thread_count=2,
        ) as manager:

            metadata = {"project_id": "test", "file_hash": "abc123"}

            # Submit small file
            future = manager.submit_file_for_processing(
                self.test_file_path, metadata, None  # No individual callbacks
            )

            result = future.result(timeout=5.0)

            # ADDRESSES user problem: "not efficient for very small files" via parallel processing
            assert result.success is True
            assert result.processing_time < 5.0  # Should be reasonable

            # ADDRESSES user problem: "no feedback when chunking files"
            # NOW HANDLED BY: ConsolidatedFileTracker provides fixed N-line display
            # Individual file callbacks removed to prevent spam
            # Feedback is provided at the system level, not per-file level


class TestFileChunkingManagerValidation:
    """Test parameter validation and edge cases."""

    def test_invalid_thread_count_validation(self):
        """Test that invalid thread counts raise ValueError."""
        mock_vector_manager = MockVectorCalculationManager()
        mock_chunker = MockFixedSizeChunker()
        mock_qdrant_client = MockQdrantClient()

        with pytest.raises(ValueError, match="thread_count must be positive"):
            FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=0,
            )

        with pytest.raises(ValueError, match="thread_count must be positive"):
            FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=-1,
            )

    def test_none_dependencies_validation(self):
        """Test that None dependencies raise ValueError."""
        mock_vector_manager = MockVectorCalculationManager()
        mock_chunker = MockFixedSizeChunker()
        mock_qdrant_client = MockQdrantClient()

        with pytest.raises(ValueError, match="vector_manager cannot be None"):
            FileChunkingManager(
                vector_manager=None,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            )

        with pytest.raises(ValueError, match="chunker cannot be None"):
            FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=None,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            )

        with pytest.raises(ValueError, match="qdrant_client cannot be None"):
            FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=None,
                thread_count=2,
            )

    def test_submit_without_context_manager_raises_error(self):
        """Test that submitting without context manager raises RuntimeError."""
        manager = FileChunkingManager(
            vector_manager=MockVectorCalculationManager(),
            chunker=MockFixedSizeChunker(),
            qdrant_client=MockQdrantClient(),
            thread_count=2,
        )

        metadata = {"project_id": "test", "file_hash": "abc123"}

        with pytest.raises(RuntimeError, match="FileChunkingManager not started"):
            manager.submit_file_for_processing(Path("/tmp/test.py"), metadata, Mock())

    def test_empty_chunks_handling(self):
        """Test handling when chunker returns empty chunks."""
        # Create chunker that returns empty chunks
        empty_chunker = Mock()
        empty_chunker.chunk_file.return_value = []

        with FileChunkingManager(
            vector_manager=MockVectorCalculationManager(),
            chunker=empty_chunker,
            qdrant_client=MockQdrantClient(),
            thread_count=2,
        ) as manager:

            test_file = tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".py"
            )
            test_file.write("# Empty file")
            test_file.close()
            test_file_path = Path(test_file.name)

            try:
                metadata = {"project_id": "test", "file_hash": "abc123"}
                future = manager.submit_file_for_processing(
                    test_file_path, metadata, Mock()
                )

                result = future.result(timeout=5.0)

                assert result.success is False
                assert result.error == "No chunks generated"
                assert result.chunks_processed == 0

            finally:
                if test_file_path.exists():
                    test_file_path.unlink()
