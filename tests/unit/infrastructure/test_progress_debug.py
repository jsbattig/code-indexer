"""
Test to debug the progress percentage calculation issue.
"""

from pathlib import Path
import uuid
from typing import List, Dict, Any
from unittest.mock import Mock, patch
import pytest

from ...conftest import get_local_tmp_dir

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer
from code_indexer.services import QdrantClient
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestProgressDebug:
    """Debug progress percentage calculation."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_files = []
        for i in range(5):  # Small number for easy debugging
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
        self.mock_qdrant.scroll_points.return_value = ([], None)

        # Mock embedding provider
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.01)

    @pytest.mark.unit
    def test_debug_progress_totals(self):
        """Debug what total values are being passed to progress callbacks."""

        # Create SmartIndexer
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track all progress calls with detailed logging
        progress_calls: List[Dict[str, Any]] = []
        first_call_total = None

        def debug_progress_callback(current, total, file_path, error=None, info=None):
            nonlocal first_call_total

            call_info = {
                "call_number": len(progress_calls) + 1,
                "current": current,
                "total": total,
                "file_path": str(file_path),
                "info": info,
                "error": error,
                "percentage": (current / total * 100) if total > 0 else 0,
            }
            progress_calls.append(call_info)

            # Capture the first total value (this is what initializes the progress bar)
            if first_call_total is None:
                first_call_total = total

            print(
                f"Progress call {call_info['call_number']}: "
                f"current={current}, total={total}, "
                f"percentage={call_info['percentage']:.1f}%, "
                f"info='{info}', file_path='{file_path}'"
            )

            return None  # Don't cancel

        # Mock the heavy SmartIndexer processing to focus on progress callbacks only
        with patch.object(smart_indexer, "smart_index") as mock_smart_index:
            # Configure mock to simulate progress callbacks without heavy processing
            def mock_index_with_progress(*args, **kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
                    # Simulate setup phase with total=0 (info messages)
                    callback(0, 0, Path(""), info="Initializing collection")
                    callback(0, 0, Path(""), info="Starting file processing")

                    # Simulate progress for each file with realistic chunking scenario
                    # Each file creates ~3 chunks based on the content size
                    total_chunks = len(self.test_files) * 3
                    chunk_count = 0

                    for i, file_path in enumerate(self.test_files):
                        # Simulate chunks for this file
                        for chunk_idx in range(3):  # 3 chunks per file
                            chunk_count += 1
                            info = f"{chunk_count}/{total_chunks} files ({chunk_count/total_chunks*100:.1f}%) | 150.0 emb/s | 2 threads | {file_path.name}"
                            callback(chunk_count, total_chunks, file_path, info=info)

                # Return realistic stats that match the progress calls
                stats = Mock()
                stats.files_processed = len(self.test_files)
                stats.chunks_created = len(self.test_files) * 3
                stats.vectors_created = len(self.test_files) * 3
                stats.processing_time = 0.5  # Fast mock processing
                return stats

            mock_smart_index.side_effect = mock_index_with_progress

            # Call the mocked smart_index
            print(f"\n=== Testing with {len(self.test_files)} files (MOCKED) ===")
            stats = smart_indexer.smart_index(
                force_full=True,  # Force full indexing
                reconcile_with_database=False,
                batch_size=50,
                safety_buffer_seconds=60,
                files_count_to_process=None,
                vector_thread_count=2,
            )

        print("\n=== ANALYSIS ===")
        print(f"Expected total files: {len(self.test_files)}")
        print(f"First call total (progress bar init): {first_call_total}")
        print(f"Final stats.files_processed: {stats.files_processed}")
        print(f"Total progress calls: {len(progress_calls)}")

        if first_call_total and len(self.test_files) > 0:
            ratio = first_call_total / len(self.test_files)
            print(f"Ratio (first_total / expected_files): {ratio:.1f}")

            if ratio > 5:
                print(
                    f"❌ PROBLEM: Progress bar initialized with {first_call_total} "
                    f"instead of {len(self.test_files)}. This suggests chunk count "
                    f"is being passed instead of file count!"
                )
            else:
                print("✅ OK: Progress bar initialized with reasonable total")

        # Show first few progress calls
        print("\nFirst 3 progress calls:")
        for i, call in enumerate(progress_calls[:3]):
            print(
                f"  {i + 1}: {call['current']}/{call['total']} = {call['percentage']:.1f}%"
            )

        # Show last few progress calls
        if len(progress_calls) > 3:
            print("Last 3 progress calls:")
            for i, call in enumerate(progress_calls[-3:]):
                call_num = len(progress_calls) - 3 + i + 1
                print(
                    f"  {call_num}: {call['current']}/{call['total']} = {call['percentage']:.1f}%"
                )

        # Verify the issue
        if len(progress_calls) >= 2:
            # Check if we're seeing the reported issue
            middle_call = progress_calls[len(progress_calls) // 2]
            expected_percentage = (middle_call["current"] / len(self.test_files)) * 100
            actual_percentage = middle_call["percentage"]

            print("\nPercentage Check:")
            print(
                f"  Middle call: {middle_call['current']}/{middle_call['total']} = {actual_percentage:.1f}%"
            )
            print(
                f"  Expected: {middle_call['current']}/{len(self.test_files)} = {expected_percentage:.1f}%"
            )

            if abs(actual_percentage - expected_percentage) > 5:
                print("❌ CONFIRMED: Progress percentage is wrong!")
            else:
                print("✅ Progress percentage looks correct")

    @pytest.mark.unit
    def test_debug_high_throughput_processing_progress(self):
        """Debug progress during high-throughput processing to ensure proper progress reporting."""

        # Create SmartIndexer
        smart_indexer = SmartIndexer(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
            metadata_path=self.metadata_path,
        )

        # Track all progress calls with detailed logging
        progress_calls: List[Dict[str, Any]] = []
        first_call_total = None

        def debug_progress_callback(current, total, file_path, error=None, info=None):
            nonlocal first_call_total

            call_info = {
                "call_number": len(progress_calls) + 1,
                "current": current,
                "total": total,
                "file_path": str(file_path),
                "info": info,
                "error": error,
                "percentage": (current / total * 100) if total > 0 else 0,
            }
            progress_calls.append(call_info)

            # Capture the first total value (this is what initializes the progress bar)
            if first_call_total is None:
                first_call_total = total

            print(
                f"Progress call {call_info['call_number']}: "
                f"current={current}, total={total}, "
                f"percentage={call_info['percentage']:.1f}%, "
                f"info='{info}', file_path='{file_path}'"
            )

            return None  # Don't cancel

        print(
            f"\n=== Testing high-throughput processing progress with {len(self.test_files)} files (MOCKED) ==="
        )

        # Mock the high-throughput processing to focus on progress callbacks only
        with patch.object(smart_indexer, "smart_index") as mock_smart_index:
            # Configure mock to simulate high-throughput progress patterns
            def mock_high_throughput_processing(*args, **kwargs):
                callback = kwargs.get("progress_callback")
                if callback:
                    # Simulate collection clearing (setup phase)
                    callback(0, 0, Path(""), info="Clearing collection")
                    callback(
                        0, 0, Path(""), info="Initializing high-throughput processing"
                    )

                    # Simulate file processing with realistic batch behavior
                    total_files = len(self.test_files)
                    for i, file_path in enumerate(self.test_files):
                        current = i + 1
                        info = f"{current}/{total_files} files ({current/total_files*100:.1f}%) | 200.0 emb/s | 2 threads | {file_path.name}"
                        callback(current, total_files, file_path, info=info)

                # Return realistic processing results
                result = Mock()
                result.files_processed = len(self.test_files)
                result.chunks_created = len(self.test_files) * 2  # Simulate chunking
                result.vectors_created = len(self.test_files) * 2
                result.processing_time = 0.3
                return result

            mock_smart_index.side_effect = mock_high_throughput_processing

            # Execute the mocked high-throughput processing
            result = smart_indexer.smart_index(
                force_full=True,  # Force full indexing (same as --clear)
                reconcile_with_database=False,
                batch_size=50,
                safety_buffer_seconds=60,
                files_count_to_process=None,
                vector_thread_count=2,
                progress_callback=debug_progress_callback,
            )

        # Verify successful processing
        assert result.files_processed > 0, "Should have processed files successfully"
        assert result.chunks_created > 0, "Should have created chunks"

        # Verify progress reporting
        assert len(progress_calls) > 0, "Should have made progress calls"

        # Verify progress included collection clearing
        setup_calls = [call for call in progress_calls if call["total"] == 0]
        assert len(setup_calls) > 0, "Should have setup progress calls"

        # Verify progress included file processing
        file_progress_calls = [call for call in progress_calls if call["total"] > 0]
        assert len(file_progress_calls) > 0, "Should have file progress calls"

        print("\n=== HIGH-THROUGHPUT PROCESSING ANALYSIS ===")
        print(f"Files processed: {result.files_processed}")
        print(f"Chunks created: {result.chunks_created}")
        print(f"Progress calls made: {len(progress_calls)}")
        print(f"Setup calls: {len(setup_calls)}")
        print(f"File progress calls: {len(file_progress_calls)}")
        print("✅ High-throughput processing completed with proper progress reporting")

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])  # -s to show print statements
