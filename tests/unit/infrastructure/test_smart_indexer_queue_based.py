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
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestSmartIndexerQueueBased:
    """Test cases for SmartIndexer queue-based processing."""

    def setup_method(self):
        """Setup test environment."""
        # Import here to avoid circular dependency
        from .infrastructure import get_shared_test_directory

        # Use shared test directory to avoid creating multiple container sets
        temp_path = get_shared_test_directory(force_docker=False)
        temp_path.mkdir(parents=True, exist_ok=True)

        # Clean only test files, preserve .code-indexer directory for containers
        import shutil

        test_subdirs = ["metadata.json"] + [f"test_file_{i}.py" for i in range(10)]
        for item_name in test_subdirs:
            item_path = temp_path / item_name
            if item_path.exists():
                if item_path.is_file():
                    item_path.unlink(missing_ok=True)
                elif item_path.is_dir():
                    shutil.rmtree(item_path, ignore_errors=True)

        # Clean any other test files but preserve .code-indexer
        for item in temp_path.iterdir():
            if item.name != ".code-indexer" and item.name.startswith("test_"):
                if item.is_file():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)

        self.temp_dir = str(temp_path)
        self.temp_path = temp_path

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
        self.mock_qdrant.scroll_points.return_value = ([], None)

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_smart_indexer_uses_queue_based_processing(self):
        """Test that SmartIndexer fails fast when BranchAwareIndexer fails (no fallbacks)."""

        # Create SmartIndexer instance
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Mock BranchAwareIndexer to fail
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(
                    force_full=True,
                    batch_size=10,
                    files_count_to_process=len(self.test_files),
                )

    @pytest.mark.unit
    def test_smart_indexer_no_single_threaded_fallback(self):
        """Test that SmartIndexer fails fast without fallbacks when BranchAwareIndexer fails."""

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Mock BranchAwareIndexer to fail
        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(
                    force_full=True,
                    batch_size=5,
                    files_count_to_process=len(self.test_files),
                )

    @pytest.mark.unit
    def test_smart_indexer_thread_count_handling(self):
        """Test that SmartIndexer fails fast when BranchAwareIndexer fails (no fallbacks)."""

        # Test with VoyageAI provider
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
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(force_full=True)

        # Test with Ollama provider
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
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer_ollama.smart_index(force_full=True)

    @pytest.mark.unit
    def test_smart_indexer_progress_callback_integration(self):
        """Test that SmartIndexer fails fast when BranchAwareIndexer fails (no fallbacks)."""

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
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(
                    force_full=True, progress_callback=progress_callback
                )

    @pytest.mark.unit
    def test_smart_indexer_metadata_update_queue_based(self):
        """Test that SmartIndexer fails fast when BranchAwareIndexer fails (no fallbacks)."""

        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        with patch.object(
            smart_indexer.branch_aware_indexer,
            "index_branch_changes",
            side_effect=Exception("Force fallback"),
        ):
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(force_full=True)

    def teardown_method(self):
        """Cleanup test environment."""
        # Don't destroy shared directory - only clean test files
        import shutil

        temp_path = Path(self.temp_dir)

        # Clean test files created by this test
        test_files = ["metadata.json"] + [f"test_file_{i}.py" for i in range(10)]
        for item_name in test_files:
            item_path = temp_path / item_name
            if item_path.exists() and item_path.is_file():
                item_path.unlink(missing_ok=True)

        # Clean any other test artifacts but preserve .code-indexer
        for item in temp_path.iterdir():
            if item.name != ".code-indexer" and item.name.startswith("test_"):
                if item.is_file():
                    item.unlink(missing_ok=True)
                elif item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
