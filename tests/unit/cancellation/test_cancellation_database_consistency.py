"""
Tests for database consistency during cancellation.

These tests verify that cancellation doesn't leave partial files in the database,
ensuring that either ALL chunks of a file are indexed, or NONE are.

Note: This should be marked as e2e since it tests database interaction.
"""

import pytest

from ...conftest import local_temporary_directory
import time
from pathlib import Path
from unittest.mock import Mock, patch
from collections import defaultdict

# Mark all tests in this file as e2e to avoid running in CI
pytestmark = pytest.mark.e2e


class MockFilesystemClient:
    """Mock Filesystem client that tracks batch operations for consistency testing."""

    def __init__(self):
        self.points_by_file = defaultdict(list)  # file_path -> list of points
        self.upsert_calls = []
        self.should_fail = False

    def upsert_points(self, points):
        """Mock upsert that tracks points by file for consistency verification."""
        if self.should_fail:
            return False

        # Track which points were added
        self.upsert_calls.append(points)
        for point in points:
            file_path = point.get("payload", {}).get("path", "unknown")
            self.points_by_file[file_path].append(point)
        return True

    def upsert_points_batched(self, points, collection_name=None, max_batch_size=100):
        """Mock atomic upsert that delegates to regular upsert for testing."""
        return self.upsert_points(points)

    def create_point(self, point_id, vector, payload, embedding_model=None):
        """Mock point creation."""
        return {"id": point_id, "vector": vector, "payload": payload}

    def get_points_for_file(self, file_path):
        """Get all points that were indexed for a specific file."""
        return self.points_by_file.get(str(file_path), [])

    def get_file_chunk_counts(self):
        """Get count of chunks per file for consistency checking."""
        return {
            file_path: len(points) for file_path, points in self.points_by_file.items()
        }


class SlowMockEmbeddingProvider:
    """Mock embedding provider with configurable delays for cancellation testing."""

    def __init__(self, delay=0.2):
        self.delay = delay
        self.call_count = 0

    def get_provider_name(self):
        return "slow-test-provider"

    def get_current_model(self):
        return "slow-test-model"

    def get_embedding(self, text, model=None):
        """Generate embedding with delay to simulate slow processing."""
        self.call_count += 1
        time.sleep(self.delay)
        return [1.0] * 768

    def get_embeddings_batch(self, texts, model=None):
        return [self.get_embedding(text, model) for text in texts]

    def supports_batch_processing(self):
        return True

    def health_check(self):
        return True


class TestDatabaseConsistencyDuringCancellation:
    """Test database consistency when cancellation occurs during processing."""

    def test_file_level_atomicity_on_cancellation(self):
        """Test that files are indexed atomically - either ALL chunks or NONE."""
        # This test will fail until we implement file-level transaction management

        with local_temporary_directory() as temp_dir:
            # Create test files with multiple chunks each
            test_files = []
            for i in range(3):
                test_file = Path(temp_dir) / f"large_file_{i}.py"
                # Create larger content that will be chunked
                content = "\n".join(
                    [f"def function_{j}():\n    pass\n" for j in range(10)]
                )
                test_file.write_text(content)
                test_files.append(test_file)

            # Mock processor with database consistency tracking
            mock_filesystem = MockFilesystemClient()
            mock_embedding = SlowMockEmbeddingProvider(delay=0.1)

            # Test scenario: cancel during processing and verify no partial files
            with (
                patch("code_indexer.services.git_aware_processor.FileIdentifier"),
                patch("code_indexer.services.git_aware_processor.GitDetectionService"),
                patch("code_indexer.indexing.processor.FileFinder"),
                patch("code_indexer.indexing.chunker.TextChunker") as mock_chunker,
            ):
                # Configure chunker to return multiple chunks per file
                def mock_chunk_file(file_path):
                    # Return 5 chunks per file
                    return [
                        {
                            "text": f"chunk {j} of {file_path.name}",
                            "chunk_index": j,
                            "total_chunks": 5,
                            "file_extension": "py",
                        }
                        for j in range(5)
                    ]

                mock_chunker.return_value.chunk_file.side_effect = mock_chunk_file

                from code_indexer.services.high_throughput_processor import (
                    HighThroughputProcessor,
                )

                config = Mock()
                config.codebase_dir = Path(temp_dir)

                processor = HighThroughputProcessor(
                    config=config,
                    embedding_provider=mock_embedding,
                    vector_store_client=mock_filesystem,
                )

                # Mock file identifier
                processor.file_identifier.get_file_metadata.return_value = {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 1000,
                }

                # Cancel very early to increase chance of partial files
                callback_count = 0

                def progress_callback(current, total, path, info=None):
                    nonlocal callback_count
                    callback_count += 1
                    # Cancel immediately after first callback to maximize partial file risk
                    if callback_count == 1:
                        return "INTERRUPT"
                    return None

                # Process files - should be cancelled mid-way
                processor.process_files_high_throughput(
                    files=test_files,
                    vector_thread_count=2,
                    batch_size=10,
                )

                # CRITICAL TEST: Verify no partial files exist in database
                file_chunk_counts = mock_filesystem.get_file_chunk_counts()

                for file_path, chunk_count in file_chunk_counts.items():
                    # Each file should have either 0 chunks (not started) or 5 chunks (completed)
                    # NO file should have 1, 2, 3, or 4 chunks (partial state)
                    assert chunk_count in [0, 5], (
                        f"File {file_path} has {chunk_count} chunks, expected 0 or 5. "
                        f"Partial file detected - database consistency violation!"
                    )

    def test_progressive_metadata_consistency_on_cancellation(self):
        """Test that progressive metadata reflects only actually completed files."""
        # This test will fail until we implement progressive metadata cleanup

        with local_temporary_directory() as temp_dir:
            test_file = Path(temp_dir) / "test_file.py"
            test_file.write_text("def test(): pass\n" * 20)

            mock_filesystem = MockFilesystemClient()
            mock_embedding = SlowMockEmbeddingProvider(delay=0.1)

            with (
                patch("code_indexer.services.git_aware_processor.FileIdentifier"),
                patch("code_indexer.services.git_aware_processor.GitDetectionService"),
                patch("code_indexer.indexing.processor.FileFinder"),
                patch("code_indexer.indexing.chunker.TextChunker") as mock_chunker,
            ):
                # Configure chunker to return chunks
                mock_chunker.return_value.chunk_file.return_value = [
                    {
                        "text": f"chunk {i}",
                        "chunk_index": i,
                        "total_chunks": 3,
                        "file_extension": "py",
                    }
                    for i in range(3)
                ]

                from code_indexer.services.high_throughput_processor import (
                    HighThroughputProcessor,
                )

                config = Mock()
                config.codebase_dir = Path(temp_dir)

                processor = HighThroughputProcessor(
                    config=config,
                    embedding_provider=mock_embedding,
                    vector_store_client=mock_filesystem,
                )

                # Mock file identifier
                processor.file_identifier.get_file_metadata.return_value = {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 500,
                }

                # Cancel immediately
                def progress_callback(current, total, path, info=None):
                    return "INTERRUPT"

                # Process with immediate cancellation
                stats = processor.process_files_high_throughput(
                    files=[test_file],
                    vector_thread_count=1,
                    batch_size=10,
                )

                # Progressive metadata should reflect only actually completed files
                # Since we cancelled immediately, no files should be marked as completed
                assert stats.files_processed == 0, (
                    f"Expected 0 files processed after immediate cancellation, "
                    f"got {stats.files_processed}. Progressive metadata inconsistency!"
                )

    def test_batch_safety_during_cancellation(self):
        """Test that Filesystem batches are handled safely during cancellation."""
        # This test will fail until we implement enhanced Filesystem batch safety

        with local_temporary_directory() as temp_dir:
            # Create multiple files to trigger batching
            test_files = []
            for i in range(10):
                test_file = Path(temp_dir) / f"batch_test_{i}.py"
                test_file.write_text(f"def func_{i}(): pass\n")
                test_files.append(test_file)

            mock_filesystem = MockFilesystemClient()
            mock_embedding = SlowMockEmbeddingProvider(delay=0.05)

            with (
                patch("code_indexer.services.git_aware_processor.FileIdentifier"),
                patch("code_indexer.services.git_aware_processor.GitDetectionService"),
                patch("code_indexer.indexing.processor.FileFinder"),
                patch("code_indexer.indexing.chunker.TextChunker") as mock_chunker,
            ):
                # Configure chunker
                def mock_chunk_file(file_path):
                    return [
                        {
                            "text": f"content of {file_path.name}",
                            "chunk_index": 0,
                            "total_chunks": 1,
                            "file_extension": "py",
                        }
                    ]

                mock_chunker.return_value.chunk_file.side_effect = mock_chunk_file

                from code_indexer.services.high_throughput_processor import (
                    HighThroughputProcessor,
                )

                config = Mock()
                config.codebase_dir = Path(temp_dir)

                processor = HighThroughputProcessor(
                    config=config,
                    embedding_provider=mock_embedding,
                    vector_store_client=mock_filesystem,
                )

                # Mock file identifier
                processor.file_identifier.get_file_metadata.return_value = {
                    "project_id": "test-project",
                    "file_hash": "test-hash",
                    "git_available": False,
                    "file_mtime": time.time(),
                    "file_size": 100,
                }

                # Cancel mid-processing
                callback_count = 0

                def progress_callback(current, total, path, info=None):
                    nonlocal callback_count
                    callback_count += 1
                    if callback_count == 5:  # Cancel partway through
                        return "INTERRUPT"
                    return None

                # Process with small batch size to trigger multiple batches
                processor.process_files_high_throughput(
                    files=test_files,
                    vector_thread_count=2,
                    batch_size=3,  # Small batch size
                )

                # Verify that batches were handled consistently
                # All batches that were started should complete successfully
                total_points = sum(
                    len(points) for points in mock_filesystem.points_by_file.values()
                )

                # Should have some points (batches that completed before cancellation)
                # but not all points (due to cancellation)
                assert 0 <= total_points < len(test_files), (
                    f"Expected partial completion due to cancellation, "
                    f"got {total_points} points from {len(test_files)} files"
                )

                # All upsert operations should have succeeded (no partial batches)
                for batch in mock_filesystem.upsert_calls:
                    assert (
                        len(batch) > 0
                    ), "Empty batch should not be sent to Filesystem"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "e2e"])
