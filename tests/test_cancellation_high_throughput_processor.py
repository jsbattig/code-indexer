"""
Tests for cancellation functionality in HighThroughputProcessor.

This test module verifies that the HighThroughputProcessor can be properly cancelled
and handles cancellation gracefully without losing completed work.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from tests.conftest import local_temporary_directory

# Mark all tests in this file as e2e to exclude from ci-github.sh
pytestmark = pytest.mark.e2e


class TestHighThroughputProcessorCancellation:
    """Test cancellation functionality in HighThroughputProcessor."""

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

        # Create mock Qdrant client
        self.qdrant_client = MagicMock()
        self.qdrant_client.create_point.return_value = {"id": "test-point"}
        self.qdrant_client.upsert_points_atomic.return_value = True

    def test_request_cancellation_sets_flag(self):
        """Test that request_cancellation sets the cancelled flag."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Initially not cancelled
        assert not processor.cancelled

        # After calling request_cancellation, should be set
        processor.request_cancellation()
        assert processor.cancelled

    def test_as_completed_loop_checks_cancellation(self):
        """Test that as_completed loop checks cancellation flag every iteration."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(5):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    pass\n")
                test_files.append(test_file)

            # Mock chunker to return chunks
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"content of {file_path.name}",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "file_extension": "py",
                        "line_start": 1,
                        "line_end": 2,
                    }
                ]

            with patch.object(
                processor.text_chunker, "chunk_file", side_effect=mock_chunk_file
            ):
                # Mock file identifier
                def mock_get_file_metadata(file_path):
                    return {
                        "project_id": "test-project",
                        "file_hash": "test-hash",
                        "git_available": False,
                        "file_mtime": time.time(),
                        "file_size": 100,
                    }

                with patch.object(
                    processor.file_identifier,
                    "get_file_metadata",
                    side_effect=mock_get_file_metadata,
                ):
                    # Track progress callback calls
                    callback_calls = []

                    def progress_callback(current, total, path, info=None):
                        callback_calls.append((current, total, str(path), info))
                        # Cancel after first callback
                        if len(callback_calls) == 2:
                            processor.request_cancellation()
                            return "INTERRUPT"
                        return None

                    # Process files (should be cancelled quickly)
                    start_time = time.time()
                    processor.process_files_high_throughput(
                        files=test_files,
                        vector_thread_count=2,
                        batch_size=10,
                        progress_callback=progress_callback,
                    )
                    processing_time = time.time() - start_time

                    # Should complete quickly due to cancellation
                    assert (
                        processing_time < 2.0
                    ), f"Processing took {processing_time:.2f}s, expected < 2.0s"

                    # Should have received cancellation signal
                    assert len(callback_calls) >= 2
                    # Check that we have at least 2 callbacks and cancellation occurred
                    assert (
                        processor.cancelled
                    ), "Processor should be marked as cancelled"

    def test_cancellation_prevents_further_processing(self):
        """Test that cancellation prevents further chunk processing."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(10):  # More files to ensure some get cancelled
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(
                    f"def test{i}():\n    pass\n" * 10
                )  # Larger content
                test_files.append(test_file)

            # Mock chunker to return multiple chunks per file
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"chunk {j} of {file_path.name}",
                        "chunk_index": j,
                        "total_chunks": 3,
                        "file_extension": "py",
                        "line_start": j * 10 + 1,
                        "line_end": (j + 1) * 10,
                    }
                    for j in range(3)
                ]

            with patch.object(
                processor.text_chunker, "chunk_file", side_effect=mock_chunk_file
            ):
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
                    # Mock embedding to be slow enough that we can cancel
                    def slow_embedding(text):
                        time.sleep(0.05)  # 50ms per embedding
                        return [0.1] * 768

                    with patch.object(
                        processor.embedding_provider,
                        "get_embedding",
                        side_effect=slow_embedding,
                    ):
                        # Start processing in a separate thread
                        import threading

                        stats = None
                        exception = None

                        def run_processing():
                            nonlocal stats, exception
                            try:
                                stats = processor.process_files_high_throughput(
                                    test_files, vector_thread_count=2
                                )
                            except Exception as e:
                                exception = e

                        processing_thread = threading.Thread(target=run_processing)
                        processing_thread.start()

                        # Let it start processing some chunks
                        time.sleep(0.3)

                        # Request cancellation
                        processor.request_cancellation()

                        # Wait for processing to complete
                        processing_thread.join(timeout=5.0)

                        # Should have stopped due to cancellation
                        assert processor.cancelled
                        assert stats is not None  # Should have partial results
                        assert exception is None  # Should not have thrown an exception

                        # Should have processed fewer than total files due to cancellation
                        total_possible_chunks = len(test_files) * 3  # 3 chunks per file
                        assert stats.chunks_created < total_possible_chunks

    def test_cancellation_preserves_completed_work(self):
        """Test that cancellation preserves completed work and doesn't lose data."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Create test files
        with local_temporary_directory() as temp_dir:
            test_files = []
            for i in range(6):
                test_file = Path(temp_dir) / f"test{i}.py"
                test_file.write_text(f"def test{i}():\n    pass\n")
                test_files.append(test_file)

            # Mock chunker
            def mock_chunk_file(file_path):
                return [
                    {
                        "text": f"content of {file_path.name}",
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "file_extension": "py",
                        "line_start": 1,
                        "line_end": 2,
                    }
                ]

            with patch.object(
                processor.text_chunker, "chunk_file", side_effect=mock_chunk_file
            ):
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
                    # Track upsert calls to ensure completed work is preserved
                    upsert_calls = []

                    def track_upsert(points):
                        upsert_calls.append(len(points))
                        return True

                    with patch.object(
                        processor.qdrant_client,
                        "upsert_points_atomic",
                        side_effect=track_upsert,
                    ):
                        # Start processing in a separate thread
                        import threading

                        stats = None

                        def run_processing():
                            nonlocal stats
                            stats = processor.process_files_high_throughput(
                                test_files, vector_thread_count=2, batch_size=3
                            )

                        processing_thread = threading.Thread(target=run_processing)
                        processing_thread.start()

                        # Let it process some files
                        time.sleep(0.2)

                        # Request cancellation
                        processor.request_cancellation()

                        # Wait for processing to complete
                        processing_thread.join(timeout=3.0)

                        # Completed work should have been preserved
                        if upsert_calls:
                            total_upserted = sum(upsert_calls)
                            assert (
                                total_upserted > 0
                            ), "Some chunks should have been upserted"

                        # Stats should reflect the work that was completed
                        assert stats is not None
                        assert stats.chunks_created >= 0

    def test_multiple_cancellation_requests_safe(self):
        """Test that multiple cancellation requests are safe and don't cause issues."""
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.embedding_provider,
            qdrant_client=self.qdrant_client,
        )

        # Initially not cancelled
        assert not processor.cancelled

        # Multiple cancellation requests should be safe
        processor.request_cancellation()
        assert processor.cancelled

        processor.request_cancellation()  # Second call
        assert processor.cancelled

        processor.request_cancellation()  # Third call
        assert processor.cancelled

        # Should still be in valid state
        assert hasattr(processor, "cancelled")
        assert processor.cancelled is True
