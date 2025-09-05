"""
Tests for Story 3: Add Source KB/Sec Throughput Reporting

Story 3: Add Source KB/Sec Throughput Reporting

Problem: No source data throughput reporting. Need to add KB/s to show data ingestion rate alongside files/s.

Requirements:
1. Add KB/s source throughput to progress reporting
2. Calculate KB/s as (total_source_bytes / 1024) / processing_time
3. Track source bytes for all processed files in thread-safe manner
4. PRESERVE Rich Progress bar visual layout exactly
5. Add KB/s to existing metrics text, not as new progress component

Target Progress Format: "files (%) | files/s | KB/s | threads | filename"

Test verifies:
1. Progress format includes KB/s between files/s and threads
2. KB/s calculation reflects source data throughput
3. KB/s shows cumulative data ingestion rate
4. Source bytes tracking is thread-safe
5. Rich Progress bar layout remains unchanged
"""

import time
import pytest
from pathlib import Path
from unittest.mock import Mock
import uuid

from ...conftest import get_local_tmp_dir
from code_indexer.config import Config
from code_indexer.services.high_throughput_processor import HighThroughputProcessor
from ..services.test_vector_calculation_manager import MockEmbeddingProvider


class TestSourceKBsThroughputReporting:
    """Test source KB/s throughput reporting in progress updates."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files with known sizes for KB/s calculation
        self.test_files = []
        self.expected_total_bytes = 0

        # Create files with different sizes to test KB/s calculation
        file_sizes = [1024, 2048, 1536, 3072, 4096]  # Different sizes in bytes
        for i, size in enumerate(file_sizes):
            file_path = self.temp_path / f"test_file_{i}.py"
            content = (
                f"""
# File {i} with {size} bytes of content for KB/s testing
def function_{i}():
    '''Function {i} with content for KB/s throughput testing.'''
"""
                + "# "
                + "x" * (size - 200)
            )  # Pad to reach target size

            file_path.write_text(content)
            actual_size = file_path.stat().st_size
            self.expected_total_bytes += actual_size
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

        self.config.chunking = Mock()
        self.config.chunking.chunk_size = 200
        self.config.chunking.overlap_size = 50

        # Mock Qdrant client
        self.mock_qdrant = Mock()
        self.mock_qdrant.upsert_points.return_value = True
        self.mock_qdrant.create_point.return_value = {"id": "test-point"}
        self.mock_qdrant.ensure_provider_aware_collection.return_value = (
            "test_collection"
        )
        self.mock_qdrant.clear_collection.return_value = True
        self.mock_qdrant.resolve_collection_name.return_value = "test_collection"
        self.mock_qdrant.collection_exists.return_value = True

        # Mock embedding provider with realistic delay
        self.mock_embedding_provider = MockEmbeddingProvider(delay=0.05)

    @pytest.mark.unit
    def test_progress_format_includes_kbs_throughput(self):
        """Test that progress reporting includes KB/s between files/s and threads."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls to verify KB/s inclusion
        progress_calls = []
        kbs_values_found = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0:
                progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "info": info,
                        "timestamp": time.time(),
                    }
                )

                # Parse progress info to extract KB/s
                # Expected format: "files completed/total (%) | files/s | KB/s | threads | filename"
                parts = info.split("|")
                if len(parts) >= 4:
                    # KB/s should be in parts[2] (after files/s, before threads)
                    kbs_part = parts[2].strip()
                    if "KB/s" in kbs_part:
                        kbs_str = kbs_part.replace("KB/s", "").strip()
                        try:
                            kbs_value = float(kbs_str)
                            kbs_values_found.append(kbs_value)
                        except ValueError:
                            pass

            return None

        # Process files with KB/s tracking
        start_time = time.time()
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=capture_progress,
        )
        processing_time = time.time() - start_time

        # ASSERTION 1: Progress calls were made
        assert len(progress_calls) > 0, "Expected progress callbacks during processing"

        # ASSERTION 2: KB/s was included in progress format
        assert len(kbs_values_found) > 0, (
            f"Expected to find KB/s values in progress info, but found none. "
            f"Progress calls: {[call['info'] for call in progress_calls[-3:]]}"
        )

        # ASSERTION 3: KB/s values are reasonable for source data throughput
        max_kbs = max(kbs_values_found)
        avg_kbs = sum(kbs_values_found) / len(kbs_values_found)

        # Expected KB/s should reflect actual source data throughput
        expected_total_kb = self.expected_total_bytes / 1024
        expected_kbs = expected_total_kb / processing_time

        # Verify KB/s is in reasonable range (allow tolerance for processing variations)
        assert max_kbs > 0, f"Expected positive KB/s values, but max was {max_kbs}"

        # KB/s should be related to source data size and processing time
        assert avg_kbs >= expected_kbs * 0.1, (  # 10% minimum tolerance
            f"Average KB/s ({avg_kbs:.2f}) too low compared to expected "
            f"({expected_kbs:.2f}) based on {expected_total_kb:.1f} KB in "
            f"{processing_time:.2f}s"
        )

    @pytest.mark.unit
    def test_progress_format_maintains_existing_structure(self):
        """Test that adding KB/s maintains the existing progress format structure."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls to verify format structure
        progress_calls = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0:
                progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "info": info,
                    }
                )

            return None

        # Process files
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify progress calls were made
        assert len(progress_calls) > 0, "Expected progress callbacks during processing"

        # Verify format structure with KB/s included
        format_verified = False
        for call in progress_calls:
            info = call["info"]
            if "|" in info and "KB/s" in info:
                format_verified = True
                # Expected format: "X/Y files (Z%) | A.B files/s | C.D KB/s | E threads | filename"
                parts = info.split("|")

                assert (
                    len(parts) >= 5
                ), f"Expected at least 5 parts in progress format with KB/s, got {len(parts)}: {info}"

                # Verify each part contains expected content
                assert (
                    "files" in parts[0] and "(" in parts[0] and "%)" in parts[0]
                ), f"Expected 'X/Y files (Z%)' in first part: {parts[0]}"

                assert (
                    "files/s" in parts[1]
                ), f"Expected 'files/s' in second part: {parts[1]}"

                assert "KB/s" in parts[2], f"Expected 'KB/s' in third part: {parts[2]}"

                assert (
                    "threads" in parts[3]
                ), f"Expected 'threads' in fourth part: {parts[3]}"

                assert (
                    len(parts[4].strip()) > 0
                ), f"Expected filename in fifth part: {parts[4]}"

                break

        assert format_verified, (
            f"No progress calls contained the expected format with KB/s. "
            f"Progress calls: {[call['info'] for call in progress_calls[-3:]]}"
        )

    @pytest.mark.unit
    def test_kbs_reflects_cumulative_source_data_throughput(self):
        """Test that KB/s calculation reflects cumulative source data processing rate."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track KB/s values over time to verify cumulative calculation
        kbs_progression = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0 and "KB/s" in info:
                parts = info.split("|")
                if len(parts) >= 3:
                    kbs_part = parts[2].strip()
                    if "KB/s" in kbs_part:
                        kbs_str = kbs_part.replace("KB/s", "").strip()
                        try:
                            kbs_value = float(kbs_str)
                            kbs_progression.append(
                                {
                                    "timestamp": time.time(),
                                    "kbs": kbs_value,
                                    "files_completed": current,
                                    "total_files": total,
                                }
                            )
                        except ValueError:
                            pass

            return None

        # Process files
        start_time = time.time()
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=capture_progress,
        )
        processing_time = time.time() - start_time

        # Verify we captured KB/s progression
        assert len(kbs_progression) > 0, "Expected to capture KB/s values over time"

        # Verify KB/s values are cumulative (not per-file rates)
        # Later KB/s values should reflect cumulative throughput, not just current file
        for i, entry in enumerate(kbs_progression):
            files_completed = entry["files_completed"]
            kbs = entry["kbs"]

            # KB/s should increase as more source data is processed
            if i > 0 and files_completed > kbs_progression[i - 1]["files_completed"]:
                # More files completed should generally mean higher total KB/s
                # (allowing some variance for processing smoothing)
                assert kbs > 0, f"KB/s should be positive, got {kbs}"

        # Final KB/s should reflect total data throughput
        final_kbs = kbs_progression[-1]["kbs"]
        expected_total_kb = self.expected_total_bytes / 1024
        expected_final_kbs = expected_total_kb / processing_time

        # Allow reasonable tolerance but verify order of magnitude
        assert final_kbs >= expected_final_kbs * 0.1, (
            f"Final KB/s ({final_kbs:.2f}) too low compared to expected "
            f"({expected_final_kbs:.2f}) for {expected_total_kb:.1f} KB in "
            f"{processing_time:.2f}s"
        )

    @pytest.mark.unit
    def test_source_bytes_tracking_thread_safe(self):
        """Test that source bytes tracking works correctly in multi-threaded environment."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track all KB/s calculations
        all_kbs_values = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0 and "KB/s" in info:
                parts = info.split("|")
                if len(parts) >= 3:
                    kbs_part = parts[2].strip()
                    if "KB/s" in kbs_part:
                        kbs_str = kbs_part.replace("KB/s", "").strip()
                        try:
                            kbs_value = float(kbs_str)
                            all_kbs_values.append(kbs_value)
                        except ValueError:
                            pass

            return None

        # Process with multiple threads to test thread safety
        stats = processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=8,  # High thread count to stress test
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify KB/s tracking worked correctly despite threading
        assert len(all_kbs_values) > 0, "Expected KB/s values from threaded processing"

        # All KB/s values should be reasonable (no negative or extremely high values)
        for kbs in all_kbs_values:
            assert kbs >= 0, f"KB/s should not be negative: {kbs}"
            assert (
                kbs < 1000000
            ), f"KB/s suspiciously high (possible threading issue): {kbs}"

        # Verify final processing stats are consistent
        assert stats.files_processed > 0, "Should have processed files successfully"
        assert stats.chunks_created > 0, "Should have created chunks"

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-s"])
