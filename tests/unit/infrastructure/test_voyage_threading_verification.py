"""
Test to verify that --clear command uses multi-threading with Voyage AI.
"""

from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import pytest

from ...conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services import QdrantClient
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestVoyageThreadingVerification:
    """Test multi-threading behavior with Voyage AI provider."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_files = []
        for i in range(3):
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

        # Create metadata path
        self.metadata_path = self.temp_path / "metadata.json"

        # Create mock config
        self.config = Mock(spec=Config)
        self.config.codebase_dir = self.temp_path
        self.config.exclude_dirs = []
        self.config.exclude_files = []
        self.config.file_extensions = ["py"]

        # Mock nested config attributes
        self.config.qdrant = Mock()
        self.config.qdrant.vector_size = 1024  # Voyage AI typical size

        self.config.indexing = Mock()
        self.config.indexing.chunk_size = 200
        self.config.indexing.overlap_size = 50
        self.config.indexing.max_file_size = 1000000
        self.config.indexing.min_file_size = 1

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200
        self.config.chunking.overlap_size = 50

        # Mock VoyageAI config for thread testing
        self.config.voyage_ai = Mock()
        self.config.voyage_ai.parallel_requests = 8  # Standard config.json setting

        # Mock Qdrant client
        self.mock_qdrant = Mock(spec=QdrantClient)
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        self.mock_qdrant.ensure_provider_aware_collection.return_value = (
            "test_collection"
        )
        self.mock_qdrant.clear_collection.return_value = True
        self.mock_qdrant.resolve_collection_name.return_value = "test_collection"
        self.mock_qdrant.collection_exists.return_value = True
        self.mock_qdrant.scroll_points.return_value = ([], None)

        # Mock embedding provider (simulating Voyage AI)
        self.mock_embedding_provider = MockEmbeddingProvider(
            provider_name="voyage-ai", delay=0.01, dimensions=1024
        )

    @pytest.mark.unit
    def test_voyage_ai_thread_count_from_config(self):
        """Test that thread count comes from config.json setting."""
        # Thread count now comes from config.json, not provider defaults
        assert (
            self.config.voyage_ai.parallel_requests == 8
        ), f"Expected 8 from config.json, got {self.config.voyage_ai.parallel_requests}"

    @pytest.mark.unit
    def test_clear_command_uses_high_throughput_processor(self):
        """Test that --clear command (force_full) uses high-throughput processor with proper threading."""

        # Create SmartIndexer with Voyage-like provider
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track that high-throughput processor is called with correct thread count
        vector_thread_count_used = None
        high_throughput_called = False

        def capture_high_throughput_call(files, vector_thread_count=None, **kwargs):
            nonlocal vector_thread_count_used, high_throughput_called
            high_throughput_called = True
            vector_thread_count_used = vector_thread_count
            # Return mock stats
            from code_indexer.indexing.processor import ProcessingStats

            return ProcessingStats(
                files_processed=len(files),
                chunks_created=len(files) * 3,
                failed_files=0,
                total_size=1000,
            )

        # Mock the high-throughput processor
        with patch.object(
            smart_indexer,
            "process_files_high_throughput",
            side_effect=capture_high_throughput_call,
        ):
            smart_indexer.smart_index(
                force_full=True,  # This is what --clear does
                reconcile_with_database=False,
                batch_size=50,
                safety_buffer_seconds=60,
                files_count_to_process=None,
                vector_thread_count=8,  # Voyage AI typical thread count
            )

        # Verify high-throughput processor was called directly
        assert (
            high_throughput_called
        ), "High-throughput processor should be called for full index"
        assert (
            vector_thread_count_used == 8
        ), f"Expected thread count of 8, got {vector_thread_count_used}"

    @pytest.mark.unit
    def test_high_throughput_processor_receives_thread_count_for_full_index(self):
        """Test that full index passes vector_thread_count to high-throughput processor."""

        # Create SmartIndexer
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track vector thread count passed to high-throughput processor
        high_throughput_thread_count = None

        def capture_high_throughput_thread_count(
            files,
            vector_thread_count=None,
            batch_size=50,
            progress_callback=None,
        ):
            nonlocal high_throughput_thread_count
            high_throughput_thread_count = vector_thread_count
            # Return mock result
            from code_indexer.indexing.processor import ProcessingStats

            stats = ProcessingStats()
            stats.files_processed = 3
            stats.chunks_created = 10
            return stats

        # Mock process_files_high_throughput to capture thread count
        with patch.object(
            smart_indexer,
            "process_files_high_throughput",
            side_effect=capture_high_throughput_thread_count,
        ):
            # Call with specific thread count for full index
            smart_indexer.smart_index(
                force_full=True,
                reconcile_with_database=False,
                batch_size=50,
                safety_buffer_seconds=60,
                files_count_to_process=None,
                vector_thread_count=8,  # Voyage AI thread count
            )

        # Verify that high-throughput processor received the thread count
        assert high_throughput_thread_count == 8, (
            f"Expected high-throughput processor to receive vector_thread_count=8, but got {high_throughput_thread_count}. "
            f"This indicates that thread count is not being passed to the parallel processor for full index."
        )

    @pytest.mark.unit
    def test_branch_processor_method_signature_includes_thread_count(self):
        """Test that process_branch_changes_high_throughput accepts vector_thread_count parameter."""

        # Create SmartIndexer
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Check that process_branch_changes_high_throughput has the right signature
        import inspect

        sig = inspect.signature(smart_indexer.process_branch_changes_high_throughput)
        params = sig.parameters

        # Verify vector_thread_count parameter exists
        assert (
            "vector_thread_count" in params
        ), "process_branch_changes_high_throughput should have vector_thread_count parameter"

        # Verify it has a default value
        assert (
            params["vector_thread_count"].default is not inspect.Parameter.empty
        ), "vector_thread_count should have a default value"

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
