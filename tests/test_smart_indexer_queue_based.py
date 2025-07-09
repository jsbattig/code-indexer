"""
Test SmartIndexer queue-based processing consolidation.

This test validates that SmartIndexer uses only queue-based high-throughput
processing for all code paths, eliminating single-threaded and per-file
threading approaches.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import pytest


from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services import QdrantClient
from tests.test_vector_calculation_manager import MockEmbeddingProvider


class TestSmartIndexerQueueBased:
    """Test cases for SmartIndexer queue-based processing."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        # Use shared test directory to avoid creating multiple container sets
        self.temp_dir = str(Path.home() / ".tmp" / "shared_test_containers")
        # Clean and recreate for test isolation
        temp_path = Path(self.temp_dir)
        if temp_path.exists():
            import shutil

            shutil.rmtree(temp_path, ignore_errors=True)
        temp_path.mkdir(parents=True, exist_ok=True)
        self.temp_path = Path(self.temp_dir)

        # Create test files
        self.test_files = []
        for i in range(5):
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with enough content to create meaningful chunks.'''
    return "This is function {i} with substantial content for testing purposes."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation with enough content to create a chunk"
    
    def method_2(self):
        return "Another method with content for chunking"
"""
            file_path.write_text(content)
            self.test_files.append(file_path)

        # Create metadata path
        self.metadata_path = self.temp_path / "metadata.json"

        # Create mock config
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.file_extensions = ["py"]  # Extensions without dots

        # Mock nested config attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 768

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_file_size = 1000000  # 1MB
        self.config.indexing.min_file_size = 1  # 1 byte

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200
        self.config.chunking.overlap_size = 50

        # Mock Qdrant client
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        self.mock_qdrant.ensure_provider_aware_collection.return_value = (
            "test_collection"
        )
        self.mock_qdrant.clear_collection.return_value = True
        self.mock_qdrant.resolve_collection_name.return_value = "test_collection"
        self.mock_qdrant.get_collection_info.return_value = {
            "points_count": 0,
            "collection_name": "test_collection",
        }

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_smart_indexer_uses_queue_based_processing(self):
        """Test that SmartIndexer uses queue-based processing, not per-file processing."""

        # Create SmartIndexer instance
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Mock BranchAwareIndexer to fail and force fallback to high-throughput processing
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer, "process_files_high_throughput"
        ) as mock_high_throughput:

            mock_high_throughput.return_value = Mock(
                files_processed=len(self.test_files), chunks_created=20, failed_files=0
            )

            # Call smart_index to trigger processing
            result = smart_indexer.smart_index(
                force_full=True,
                batch_size=10,
                files_count_to_process=len(self.test_files),
            )

            # Verify high-throughput processing was called
            assert mock_high_throughput.called
            call_args = mock_high_throughput.call_args

            # Verify it was called with files and proper parameters
            assert len(call_args[0][0]) > 0  # files list should not be empty
            assert "vector_thread_count" in call_args[1]
            assert "batch_size" in call_args[1]

            # Verify processing stats
            assert result.files_processed == len(self.test_files)
            assert result.chunks_created == 20
            assert result.failed_files == 0

    @pytest.mark.unit
    def test_smart_indexer_no_single_threaded_fallback(self):
        """Test that SmartIndexer never falls back to single-threaded processing."""

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Mock both old methods to ensure they're never called
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer,
            "process_file",
            side_effect=AssertionError("process_file should not be called"),
        ) as mock_process_file, patch.object(
            smart_indexer,
            "process_file_parallel",
            side_effect=AssertionError("process_file_parallel should not be called"),
        ) as mock_process_parallel, patch.object(
            smart_indexer, "process_files_high_throughput"
        ) as mock_high_throughput:

            mock_high_throughput.return_value = Mock(
                files_processed=len(self.test_files), chunks_created=15, failed_files=0
            )

            # Test with vector_thread_count=1 (should still use queue-based)
            smart_indexer.smart_index(
                force_full=True,
                batch_size=5,
                files_count_to_process=len(self.test_files),
            )

            # Verify old methods were never called
            assert not mock_process_file.called
            assert not mock_process_parallel.called

            # Verify high-throughput processing was called
            assert mock_high_throughput.called

    @pytest.mark.unit
    def test_smart_indexer_thread_count_handling(self):
        """Test that SmartIndexer properly handles thread count for different providers."""

        # Test with VoyageAI provider (should default to 8 threads)
        voyage_provider = MockEmbeddingProvider("voyage-ai", delay=0.01)

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=voyage_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer, "process_files_high_throughput"
        ) as mock_high_throughput:
            mock_high_throughput.return_value = Mock(
                files_processed=len(self.test_files), chunks_created=12, failed_files=0
            )

            smart_indexer.smart_index(force_full=True)

            # Verify high-throughput was called with proper thread count
            call_args = mock_high_throughput.call_args
            assert call_args[1]["vector_thread_count"] == 8  # VoyageAI default

        # Test with Ollama provider (should default to 1 thread)
        ollama_provider = MockEmbeddingProvider("ollama", delay=0.05)

        smart_indexer_ollama = SmartIndexer(
            config=self.config,
            embedding_provider=ollama_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        with patch.object(
            smart_indexer_ollama.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer_ollama, "process_files_high_throughput"
        ) as mock_high_throughput_ollama:
            mock_high_throughput_ollama.return_value = Mock(
                files_processed=len(self.test_files), chunks_created=10, failed_files=0
            )

            smart_indexer_ollama.smart_index(force_full=True)

            # Verify high-throughput was called with proper thread count
            call_args = mock_high_throughput_ollama.call_args
            assert call_args[1]["vector_thread_count"] == 1  # Ollama default

    @pytest.mark.unit
    def test_smart_indexer_progress_callback_integration(self):
        """Test that progress callbacks work with queue-based processing."""

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        progress_calls = []

        def progress_callback(current, total, file_path, info=None, error=None):
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": file_path,
                    "info": info,
                    "error": error,
                }
            )
            return None  # Continue processing

        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer, "process_files_high_throughput"
        ) as mock_high_throughput:
            mock_high_throughput.return_value = Mock(
                files_processed=len(self.test_files), chunks_created=18, failed_files=0
            )

            smart_indexer.smart_index(
                force_full=True, progress_callback=progress_callback
            )

            # Verify high-throughput processing was called with progress callback
            call_args = mock_high_throughput.call_args
            assert "progress_callback" in call_args[1]
            assert call_args[1]["progress_callback"] == progress_callback

    @pytest.mark.unit
    def test_smart_indexer_metadata_update_queue_based(self):
        """Test that metadata is properly updated after queue-based processing."""

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Setup expected processing results

        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ), patch.object(
            smart_indexer, "process_files_high_throughput"
        ) as mock_high_throughput:

            mock_high_throughput.return_value = Mock(
                files_processed=3, chunks_created=9, failed_files=2
            )

            result = smart_indexer.smart_index(force_full=True)

            # Verify that high-throughput stats were converted to ProcessingStats correctly
            assert result.files_processed == 3
            assert result.chunks_created == 9
            assert result.failed_files == 2

            # Verify high-throughput was called
            assert mock_high_throughput.called

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
