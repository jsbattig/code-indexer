"""
Test cancellation handling in indexing operations.
"""

from pathlib import Path
import uuid
from unittest.mock import Mock
import pytest

from ...conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from code_indexer.services import QdrantClient
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestCancellationHandling:
    """Test cancellation behavior in indexing operations."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_files = []
        for i in range(10):  # Create 10 files for testing
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with content for chunking.'''
    return "This is function {i} with content for testing."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation"
    
    def method_2(self):
        return "Another method"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Create mock config
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.file_extensions = ["py"]

        # Mock nested config attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 768

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_file_size = 1000000
        self.config.indexing.min_file_size = 1

        # Mock Qdrant client
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_high_throughput_processor_cancellation(self):
        """Test that HighThroughputProcessor handles cancellation correctly."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls and simulate cancellation after processing 3 files
        progress_calls = []
        cancelled_after_files = 3

        def progress_callback_with_cancellation(
            current, total, file_path, error=None, info=None, concurrent_files=None
        ):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

            # Simulate user cancellation after processing some files
            if current >= cancelled_after_files:
                return "INTERRUPT"
            return None

        # Process files with cancellation
        stats = processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=2,
            batch_size=10,
            progress_callback=progress_callback_with_cancellation,
        )

        # Verify cancellation was handled correctly
        assert stats.files_processed == cancelled_after_files, (
            f"Expected files_processed={cancelled_after_files} after cancellation, "
            f"but got {stats.files_processed}. This indicates cancellation is not properly "
            f"stopping the processing and reporting accurate file counts."
        )

        # Verify we don't report processing all files when cancelled
        assert stats.files_processed < len(self.test_files), (
            f"Cancellation should result in fewer files processed ({stats.files_processed}) "
            f"than total files ({len(self.test_files)}), but they are equal or greater."
        )

        # Verify that progress callbacks were made before cancellation
        assert len(progress_calls) >= cancelled_after_files, (
            f"Should have at least {cancelled_after_files} progress calls before cancellation, "
            f"but got {len(progress_calls)}"
        )

        print("✅ Cancellation test passed:")
        print(f"   Files to process: {len(self.test_files)}")
        print(f"   Cancelled after: {cancelled_after_files} files")
        print(f"   Reported processed: {stats.files_processed} files")
        print(f"   Progress calls made: {len(progress_calls)}")

    @pytest.mark.unit
    def test_high_throughput_processor_complete_processing(self):
        """Test that HighThroughputProcessor reports correct counts when completed normally."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls without cancellation
        progress_calls = []

        def progress_callback_no_cancellation(
            current, total, file_path, error=None, info=None
        ):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "info": info,
                }
            )
            # No cancellation
            return None

        # Process files without cancellation
        stats = processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=2,
            batch_size=10,
            progress_callback=progress_callback_no_cancellation,
        )

        # Verify all files were processed when not cancelled
        assert stats.files_processed == len(self.test_files), (
            f"Expected files_processed={len(self.test_files)} when completed normally, "
            f"but got {stats.files_processed}."
        )

        # Verify chunks were created
        assert stats.chunks_created > 0, "Should have created some chunks"

        print("✅ Complete processing test passed:")
        print(f"   Files to process: {len(self.test_files)}")
        print(f"   Reported processed: {stats.files_processed} files")
        print(f"   Chunks created: {stats.chunks_created}")
        print(f"   Progress calls made: {len(progress_calls)}")

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
