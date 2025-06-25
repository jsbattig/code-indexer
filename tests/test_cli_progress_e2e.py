"""
End-to-end test for CLI progress behavior.

This test simulates the exact CLI execution path to identify where
individual progress messages are still being generated instead of
progress bar updates.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock
import pytest

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services import QdrantClient
from tests.test_vector_calculation_manager import MockEmbeddingProvider


class TestCLIProgressE2E:
    """End-to-end tests for CLI progress behavior."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Create test files (small enough to process quickly)
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
        self.config.qdrant.vector_size = 768

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
        self.mock_qdrant.get_collection_info.return_value = {
            "points_count": 0,
            "collection_name": "test_collection",
        }

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_old_processor_methods_progress_behavior(self):
        """Test that old processor methods also use correct progress callback format."""
        from code_indexer.indexing.processor import DocumentProcessor

        # Test the old process_files_parallel method directly
        processor = DocumentProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # CLI-style progress callback that detects problematic patterns
        progress_calls = []
        problematic_calls = []

        def cli_progress_callback(current, total, file_path, error=None, info=None):
            """Simulate the CLI progress callback behavior."""
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

            # CLI logic: Check for problematic patterns
            # Setup messages (total=0) are handled separately and file_path doesn't matter
            if str(file_path) != "." and info is not None and total > 0:
                # This pattern causes individual messages instead of progress bar updates
                problematic_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "file_path": str(file_path),
                        "info": info,
                        "message": f"ℹ️  {info}",  # What the CLI would print
                    }
                )

        # Call the old process_files_parallel method that was causing issues
        processor.process_files_parallel(
            self.test_files,
            batch_size=10,
            progress_callback=cli_progress_callback,
            vector_thread_count=2,
        )

        # Print analysis for debugging
        print(f"\nOld method - Total progress calls: {len(progress_calls)}")
        print(f"Old method - Problematic calls: {len(problematic_calls)}")

        if problematic_calls:
            print("\nProblematic calls from old method:")
            for i, call in enumerate(problematic_calls):
                print(f"  Problem {i}: {call['message']}")

        # Assert that we have no problematic calls
        assert len(problematic_calls) == 0, (
            f"Found {len(problematic_calls)} progress calls in old processor method that would cause "
            f"individual messages instead of progress bar updates. "
            f"Examples: {problematic_calls[:3]}"
        )

    @pytest.mark.unit
    def test_cli_clear_command_progress_behavior(self):
        """Test the exact progress behavior of 'cidx index --clear' command."""

        # Create SmartIndexer instance (same as CLI)
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # CLI-style progress callback that detects problematic patterns
        progress_calls = []
        problematic_calls = []

        def cli_progress_callback(current, total, file_path, error=None, info=None):
            """Simulate the CLI progress callback behavior."""
            progress_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                    "error": error,
                }
            )

            # CLI logic: Check for problematic patterns
            # Setup messages (total=0) are handled separately and file_path doesn't matter
            if str(file_path) != "." and info is not None and total > 0:
                # This pattern causes individual messages instead of progress bar updates
                problematic_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "file_path": str(file_path),
                        "info": info,
                        "message": f"ℹ️  {info}",  # What the CLI would print
                    }
                )

        # Call the exact same method as CLI: smart_index with force_full=True (--clear)
        stats = smart_indexer.smart_index(
            force_full=True,  # This is what --clear does
            reconcile_with_database=False,
            batch_size=50,
            progress_callback=cli_progress_callback,
            safety_buffer_seconds=60,
            files_count_to_process=None,
            vector_thread_count=8,
        )

        # Print analysis for debugging
        print(f"\nTotal progress calls: {len(progress_calls)}")
        print(
            f"Problematic calls (would show individual messages): {len(problematic_calls)}"
        )

        print("\nAll progress calls:")
        for i, call in enumerate(progress_calls):
            print(
                f"  Call {i}: current={call['current']}, total={call['total']}, "
                f"file_path='{call['file_path']}', info='{call['info']}'"
            )

        if problematic_calls:
            print("\nProblematic calls that would show individual messages:")
            for i, call in enumerate(problematic_calls):
                print(f"  Problem {i}: {call['message']}")

        # Assert that we have no problematic calls
        assert len(problematic_calls) == 0, (
            f"Found {len(problematic_calls)} progress calls that would cause "
            f"individual messages instead of progress bar updates. "
            f"These calls combine real file paths with info messages, triggering "
            f"CLI individual message display. Examples: {problematic_calls[:3]}"
        )

        # Verify that all progress calls with info use empty paths
        info_calls = [call for call in progress_calls if call["info"] is not None]
        assert len(info_calls) > 0, "Should have progress calls with info messages"

        for call in info_calls:
            assert call["file_path"] == ".", (
                f"Progress calls with info should use empty path (.), but got: '{call['file_path']}'. "
                f"Info: '{call['info']}'"
            )

        # Verify successful processing
        assert stats.files_processed >= len(
            self.test_files
        ), "Should process test files"

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__])
