"""
Test to debug the progress percentage calculation issue.
"""

from pathlib import Path
import uuid
from typing import List, Dict, Any
from unittest.mock import Mock
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

        # Call smart_index to see what happens
        print(f"\n=== Testing with {len(self.test_files)} files ===")
        stats = smart_indexer.smart_index(
            force_full=True,  # Force full indexing
            reconcile_with_database=False,
            batch_size=50,
            progress_callback=debug_progress_callback,
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
    def test_debug_high_throughput_fallback(self):
        """Debug progress when BranchAwareIndexer fails and falls back to HighThroughputProcessor."""

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

        # Force BranchAwareIndexer to fail so we hit the HighThroughputProcessor fallback
        from unittest.mock import patch

        with patch.object(
            smart_indexer.branch_aware_indexer, "index_branch_changes"
        ) as mock_branch_indexer:
            mock_branch_indexer.side_effect = Exception(
                "Forced BranchAwareIndexer failure to test fallback"
            )

            print(
                f"\n=== Testing HighThroughputProcessor fallback with {len(self.test_files)} files ==="
            )
            # Should raise RuntimeError due to disabled fallbacks
            with pytest.raises(
                RuntimeError,
                match="Git-aware indexing failed and fallbacks are disabled",
            ):
                smart_indexer.smart_index(
                    force_full=True,  # Force full indexing (same as --clear)
                    reconcile_with_database=False,
                    batch_size=50,
                    progress_callback=debug_progress_callback,
                    safety_buffer_seconds=60,
                    files_count_to_process=None,
                    vector_thread_count=2,
                )

        # Test passes if RuntimeError is raised due to disabled fallbacks
        print("\n=== FALLBACK DISABLED ANALYSIS ===")
        print(f"Expected total files: {len(self.test_files)}")
        print("✅ Git-aware indexing correctly fails fast without fallbacks")

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])  # -s to show print statements
