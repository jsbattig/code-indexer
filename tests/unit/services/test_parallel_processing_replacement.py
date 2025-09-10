"""
Integration tests for Story 02: Replace Sequential with Parallel Processing.

Tests verify that the sequential processing loop in high_throughput_processor.py
is replaced with parallel processing using FileChunkingManager.

These are TDD integration tests that define the expected behavior:
1. FileChunkingManager is used instead of sequential chunking
2. File-level result collection replaces chunk-level
3. Method signature and behavior compatibility preserved
4. Immediate feedback during submission
5. Parallel processing improves throughput
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from concurrent.futures import Future
from typing import Any

from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services.file_chunking_manager import FileProcessingResult
from code_indexer.indexing.processor import ProcessingStats


def create_test_config():
    """Create a properly configured mock for testing."""
    config = Mock()
    # Use a temporary directory that actually exists and is writable
    temp_dir = Path(tempfile.gettempdir()) / "test_code_indexer"
    temp_dir.mkdir(exist_ok=True)
    config.codebase_dir = temp_dir
    config.exclude_dirs = []  # Fix for FileFinder initialization
    config.max_file_size_mb = 10
    config.exclude_patterns = []
    return config


class TestParallelProcessingReplacement:
    """Test suite for sequential to parallel processing replacement."""

    def test_file_chunking_manager_import_exists(self):
        """Test that FileChunkingManager can be imported from high_throughput_processor."""
        # This test will FAIL initially - we need to add the import
        try:
            from code_indexer.services.high_throughput_processor import (
                FileChunkingManager,
                FileProcessingResult,
            )

            assert FileChunkingManager is not None
            assert FileProcessingResult is not None
        except ImportError as e:
            pytest.fail(
                f"FileChunkingManager import missing from high_throughput_processor.py: {e}"
            )

    @patch("code_indexer.services.high_throughput_processor.FileChunkingManager")
    @patch("code_indexer.services.high_throughput_processor.VectorCalculationManager")
    def test_uses_file_chunking_manager_instead_of_sequential_chunking(
        self, mock_vector_manager, mock_file_chunking_manager
    ):
        """Test that process_files_high_throughput uses FileChunkingManager instead of sequential chunking."""
        # Setup with proper constructor arguments
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)
        processor.file_identifier = Mock()
        processor.fixed_size_chunker = Mock()

        # Mock file metadata
        test_files = [Path("/test/file1.py"), Path("/test/file2.py")]
        processor.file_identifier.get_file_metadata.return_value = {
            "project_id": "test",
            "file_hash": "hash123",
            "git_available": False,
        }

        # Setup FileChunkingManager mock
        mock_file_manager_instance = Mock()
        mock_file_chunking_manager.return_value.__enter__.return_value = (
            mock_file_manager_instance
        )

        # Setup file futures with results
        file_result1 = FileProcessingResult(
            success=True,
            file_path=test_files[0],
            chunks_processed=3,
            processing_time=1.0,
        )
        file_result2 = FileProcessingResult(
            success=True,
            file_path=test_files[1],
            chunks_processed=2,
            processing_time=0.8,
        )

        future1 = Future()
        future1.set_result(file_result1)
        future2 = Future()
        future2.set_result(file_result2)

        mock_file_manager_instance.submit_file_for_processing.side_effect = [
            future1,
            future2,
        ]

        # Setup VectorCalculationManager mock
        mock_vector_manager_instance = Mock()
        mock_vector_manager.return_value.__enter__.return_value = (
            mock_vector_manager_instance
        )

        # Execute
        result = processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            batch_size=50,
        )

        # Verify FileChunkingManager was instantiated with correct parameters
        # Note: slot_tracker is automatically created by HighThroughputProcessor
        mock_file_chunking_manager.assert_called_once()
        call_args = mock_file_chunking_manager.call_args
        assert call_args[1]["vector_manager"] == mock_vector_manager_instance
        assert call_args[1]["chunker"] == processor.fixed_size_chunker
        assert call_args[1]["qdrant_client"] == qdrant_client
        assert call_args[1]["thread_count"] == 4
        assert "slot_tracker" in call_args[1]  # Verify slot_tracker is included

        # Verify files were submitted for processing (not sequential chunking)
        assert mock_file_manager_instance.submit_file_for_processing.call_count == 2
        calls = mock_file_manager_instance.submit_file_for_processing.call_args_list
        assert calls[0][0][0] == test_files[0]  # First file path
        assert calls[1][0][0] == test_files[1]  # Second file path

        # Verify sequential chunking is NOT used (should not call chunker directly in main thread)
        processor.fixed_size_chunker.chunk_file.assert_not_called()

        # Verify results aggregated correctly
        assert isinstance(result, ProcessingStats)
        assert result.files_processed == 2
        assert result.chunks_created == 5  # 3 + 2 from FileProcessingResult objects

    @patch("code_indexer.services.high_throughput_processor.FileChunkingManager")
    @patch("code_indexer.services.high_throughput_processor.VectorCalculationManager")
    def test_file_level_result_collection_not_chunk_level(
        self, mock_vector_manager, mock_file_chunking_manager
    ):
        """Test that results are collected at file level, not chunk level."""
        # Setup with proper constructor arguments
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)
        processor.file_identifier = Mock()
        processor.fixed_size_chunker = Mock()

        test_files = [Path("/test/file1.py")]
        processor.file_identifier.get_file_metadata.return_value = {
            "project_id": "test",
            "file_hash": "hash123",
            "git_available": False,
        }

        # Setup FileChunkingManager mock
        mock_file_manager_instance = Mock()
        mock_file_chunking_manager.return_value.__enter__.return_value = (
            mock_file_manager_instance
        )

        # File result contains aggregated chunk information
        file_result = FileProcessingResult(
            success=True,
            file_path=test_files[0],
            chunks_processed=5,
            processing_time=2.0,
        )
        future: Future[Any] = Future()
        future.set_result(file_result)
        mock_file_manager_instance.submit_file_for_processing.return_value = future

        # Setup VectorCalculationManager mock
        mock_vector_manager_instance = Mock()
        mock_vector_manager.return_value.__enter__.return_value = (
            mock_vector_manager_instance
        )

        # Execute
        result = processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            batch_size=50,
        )

        # Verify file-level result aggregation
        assert result.files_processed == 1  # 1 file processed
        assert result.chunks_created == 5  # Chunks from FileProcessingResult

        # Should NOT call vector_manager directly for chunk submission in main thread
        # (FileChunkingManager handles this internally)
        mock_vector_manager_instance.submit_chunk.assert_not_called()

    def test_method_signature_preserved(self):
        """Test that process_files_high_throughput method signature is unchanged."""
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()
        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)

        # Verify method exists with correct signature
        method = getattr(processor, "process_files_high_throughput", None)
        assert method is not None, "process_files_high_throughput method not found"

        # Check method signature using inspect
        import inspect

        sig = inspect.signature(method)
        expected_params = [
            "files",
            "vector_thread_count",
            "batch_size",
            "progress_callback",
        ]
        actual_params = list(sig.parameters.keys())

        assert (
            actual_params == expected_params
        ), f"Method signature changed: expected {expected_params}, got {actual_params}"

        # Check return type annotation if present
        # The method should return ProcessingStats
        if sig.return_annotation != inspect.Signature.empty:
            assert sig.return_annotation == ProcessingStats

    @patch("code_indexer.services.high_throughput_processor.FileChunkingManager")
    @patch("code_indexer.services.high_throughput_processor.VectorCalculationManager")
    def test_immediate_feedback_during_submission(
        self, mock_vector_manager, mock_file_chunking_manager
    ):
        """Test that immediate feedback is provided during file submission."""
        # Setup with proper constructor arguments
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)
        processor.file_identifier = Mock()
        processor.fixed_size_chunker = Mock()

        test_files = [Path("/test/file1.py"), Path("/test/file2.py")]
        processor.file_identifier.get_file_metadata.return_value = {
            "project_id": "test",
            "file_hash": "hash123",
            "git_available": False,
        }

        # Setup FileChunkingManager mock
        mock_file_manager_instance = Mock()
        mock_file_chunking_manager.return_value.__enter__.return_value = (
            mock_file_manager_instance
        )

        # Create futures that complete immediately
        futures = []
        for file_path in test_files:
            file_result = FileProcessingResult(
                success=True,
                file_path=file_path,
                chunks_processed=2,
                processing_time=1.0,
            )
            future: Future[Any] = Future()
            future.set_result(file_result)
            futures.append(future)

        mock_file_manager_instance.submit_file_for_processing.side_effect = futures

        # Setup VectorCalculationManager mock
        mock_vector_manager_instance = Mock()
        mock_vector_manager.return_value.__enter__.return_value = (
            mock_vector_manager_instance
        )

        # Setup progress callback to capture immediate feedback
        progress_callback = Mock()

        # Execute
        processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=progress_callback,
        )

        # Verify each file was submitted individually (parallel submission)
        assert mock_file_manager_instance.submit_file_for_processing.call_count == 2

        # FileChunkingManager should provide immediate "Queued for processing" feedback
        # This happens inside FileChunkingManager.submit_file_for_processing
        submit_calls = (
            mock_file_manager_instance.submit_file_for_processing.call_args_list
        )
        for i, call_args in enumerate(submit_calls):
            args, kwargs = call_args
            assert args[0] == test_files[i]  # File path
            assert args[2] == progress_callback  # Progress callback passed through

    @patch("code_indexer.services.high_throughput_processor.FileChunkingManager")
    @patch("code_indexer.services.high_throughput_processor.VectorCalculationManager")
    def test_error_handling_preserved(
        self, mock_vector_manager, mock_file_chunking_manager
    ):
        """Test that error handling and cancellation behavior is preserved."""
        # Setup with proper constructor arguments
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)
        processor.file_identifier = Mock()
        processor.fixed_size_chunker = Mock()

        # Create actual test files that exist
        test_files = []
        for i, filename in enumerate(["file1.py", "file2.py"]):
            test_file = config.codebase_dir / filename
            test_file.write_text(f"# Test file {i+1}\nprint('hello')")
            test_files.append(test_file)

        processor.file_identifier.get_file_metadata.return_value = {
            "project_id": "test",
            "file_hash": "hash123",
            "git_available": False,
        }

        # Setup FileChunkingManager mock
        mock_file_manager_instance = Mock()
        mock_file_chunking_manager.return_value.__enter__.return_value = (
            mock_file_manager_instance
        )

        # First file succeeds, second fails
        success_result = FileProcessingResult(
            success=True,
            file_path=test_files[0],
            chunks_processed=2,
            processing_time=1.0,
        )
        failure_result = FileProcessingResult(
            success=False,
            file_path=test_files[1],
            chunks_processed=0,
            processing_time=0.5,
            error="Processing failed",
        )

        future1 = Future()
        future1.set_result(success_result)
        future2 = Future()
        future2.set_result(failure_result)

        mock_file_manager_instance.submit_file_for_processing.side_effect = [
            future1,
            future2,
        ]

        # Setup VectorCalculationManager mock
        mock_vector_manager_instance = Mock()
        mock_vector_manager.return_value.__enter__.return_value = (
            mock_vector_manager_instance
        )

        # Execute
        result = processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            batch_size=50,
        )

        # Verify error handling: one success, one failure
        assert result.files_processed == 1  # Only successful file counted
        assert result.failed_files == 1  # Failed file tracked
        assert result.chunks_created == 2  # Only chunks from successful file

    def test_cancellation_integration_preserved(self):
        """Test that cancellation behavior is preserved with new implementation."""
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()
        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)

        # Verify cancellation flag exists and works
        assert not processor.cancelled
        processor.request_cancellation()
        assert processor.cancelled

        # The implementation should check self.cancelled in the as_completed loop
        # This test ensures the interface exists

    @patch("code_indexer.services.high_throughput_processor.FileChunkingManager")
    @patch("code_indexer.services.high_throughput_processor.VectorCalculationManager")
    def test_no_sequential_chunking_phase_exists(
        self, mock_vector_manager, mock_file_chunking_manager
    ):
        """Test that sequential chunking phase (lines 388-450) is completely removed."""
        # This test verifies that the sequential "for file_path in files:" loop is gone

        # Setup with proper constructor arguments
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()

        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)
        processor.file_identifier = Mock()
        processor.fixed_size_chunker = Mock()

        test_files = [Path("/test/file1.py")]
        processor.file_identifier.get_file_metadata.return_value = {
            "project_id": "test",
            "file_hash": "hash123",
            "git_available": False,
        }

        # Setup mocks
        mock_file_manager_instance = Mock()
        mock_file_chunking_manager.return_value.__enter__.return_value = (
            mock_file_manager_instance
        )

        file_result = FileProcessingResult(
            success=True,
            file_path=test_files[0],
            chunks_processed=2,
            processing_time=1.0,
        )
        future: Future[Any] = Future()
        future.set_result(file_result)
        mock_file_manager_instance.submit_file_for_processing.return_value = future

        mock_vector_manager_instance = Mock()
        mock_vector_manager.return_value.__enter__.return_value = (
            mock_vector_manager_instance
        )

        # Execute
        processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            batch_size=50,
        )

        # Verify NO sequential chunking happens in main thread
        # The chunker should NOT be called directly in process_files_high_throughput
        processor.fixed_size_chunker.chunk_file.assert_not_called()

        # Verify FileChunkingManager is used instead
        mock_file_chunking_manager.assert_called_once()
        mock_file_manager_instance.submit_file_for_processing.assert_called_once()

    def test_processing_stats_return_type_preserved(self):
        """Test that ProcessingStats return type is preserved."""
        config = create_test_config()
        embedding_provider = Mock()
        qdrant_client = Mock()
        processor = HighThroughputProcessor(config, embedding_provider, qdrant_client)

        # Import should work (tests the import exists)
        from code_indexer.indexing.processor import ProcessingStats

        # Verify method signature indicates it returns ProcessingStats
        import inspect

        sig = inspect.signature(processor.process_files_high_throughput)

        # If return annotation exists, it should be ProcessingStats
        if sig.return_annotation != inspect.Signature.empty:
            assert (
                sig.return_annotation == ProcessingStats
                or str(sig.return_annotation) == "ProcessingStats"
            )
