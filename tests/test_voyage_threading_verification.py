"""
Test to verify that --clear command uses multi-threading with Voyage AI.
"""

from pathlib import Path
import uuid
from unittest.mock import Mock, patch
import pytest

from .conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services import QdrantClient
from tests.test_vector_calculation_manager import MockEmbeddingProvider


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

        # Mock embedding provider (simulating Voyage AI)
        self.mock_embedding_provider = MockEmbeddingProvider(
            provider_name="voyage-ai", delay=0.01, dimensions=1024
        )

    @pytest.mark.unit
    def test_voyage_ai_thread_count_calculation(self):
        """Test that Voyage AI gets the correct default thread count."""
        from code_indexer.services.vector_calculation_manager import (
            get_default_thread_count,
        )

        # Mock Voyage AI provider
        voyage_provider = Mock()
        voyage_provider.get_provider_name.return_value = "voyage-ai"

        # Test thread count calculation
        thread_count = get_default_thread_count(voyage_provider)

        # Voyage AI should get 8 threads by default
        assert (
            thread_count == 8
        ), f"Expected 8 threads for Voyage AI, got {thread_count}"

    @pytest.mark.unit
    def test_clear_command_threading_fallback(self):
        """Test that --clear command uses multi-threading in fallback scenario with Voyage AI."""

        # Create SmartIndexer with Voyage-like provider
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track vector thread count usage in fallback
        vector_thread_count_used = None

        def capture_vector_thread_count(files, vector_thread_count=None, **kwargs):
            nonlocal vector_thread_count_used
            vector_thread_count_used = vector_thread_count
            # Return mock stats
            from code_indexer.indexing.processor import ProcessingStats

            return ProcessingStats(
                files_processed=len(files),
                chunks_created=len(files) * 3,
                failed_files=0,
                total_size=1000,
            )

        # Force BranchAwareIndexer to fail so we test the fallback path
        with patch.object(
            smart_indexer.branch_aware_indexer, "index_branch_changes"
        ) as mock_branch_indexer:
            mock_branch_indexer.side_effect = Exception(
                "BranchAwareIndexer forced failure for testing"
            )

            # Mock the fallback high-throughput processing to capture thread count
            with patch.object(
                smart_indexer,
                "process_files_high_throughput",
                side_effect=capture_vector_thread_count,
            ):
                # Call smart_index with force_full=True (equivalent to --clear)
                stats = smart_indexer.smart_index(
                    force_full=True,  # This is what --clear does
                    reconcile_with_database=False,
                    batch_size=50,
                    progress_callback=None,
                    safety_buffer_seconds=60,
                    files_count_to_process=None,
                    vector_thread_count=8,  # Voyage AI typical thread count
                )

        # Verify that the fallback path preserved the vector thread count
        assert vector_thread_count_used == 8, (
            f"Expected fallback to preserve vector_thread_count=8 for Voyage AI, but got {vector_thread_count_used}. "
            f"This indicates that --clear fallback is not properly using multi-threading with Voyage AI."
        )

        # Verify successful processing in fallback
        assert stats.files_processed >= len(
            self.test_files
        ), "Should process test files in fallback"

    @pytest.mark.unit
    def test_branch_aware_indexer_receives_thread_count(self):
        """Test that BranchAwareIndexer receives vector_thread_count parameter."""

        # Create SmartIndexer
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track vector thread count passed to BranchAwareIndexer
        branch_indexer_thread_count = None

        def capture_branch_indexer_thread_count(
            old_branch,
            new_branch,
            changed_files,
            unchanged_files,
            collection_name,
            progress_callback=None,
            vector_thread_count=None,
        ):
            nonlocal branch_indexer_thread_count
            branch_indexer_thread_count = vector_thread_count
            # Return mock result
            from code_indexer.services.branch_aware_indexer import BranchIndexingResult

            return BranchIndexingResult(
                content_points_created=3,
                content_points_reused=0,
                processing_time=0.1,
                files_processed=3,
            )

        # Mock BranchAwareIndexer.index_branch_changes to capture thread count
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=capture_branch_indexer_thread_count,
        ):
            # Call with specific thread count
            smart_indexer.smart_index(
                force_full=True,
                reconcile_with_database=False,
                batch_size=50,
                progress_callback=None,
                safety_buffer_seconds=60,
                files_count_to_process=None,
                vector_thread_count=8,  # Voyage AI thread count
            )

        # Verify that BranchAwareIndexer received the thread count
        assert branch_indexer_thread_count == 8, (
            f"Expected BranchAwareIndexer to receive vector_thread_count=8, but got {branch_indexer_thread_count}. "
            f"This indicates that thread count is not being passed to BranchAwareIndexer."
        )

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
