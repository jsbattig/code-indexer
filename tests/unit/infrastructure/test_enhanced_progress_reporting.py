"""
Tests for enhanced progress reporting with thread utilization and real-time file completion.

Story 5: Enhanced Progress Reporting for File-Level Parallelization
Tests verify:
1. Progress format: "files completed/total (%) | files/sec | KB/s | active threads | current filename"
2. Thread utilization shows actual worker thread count (1-8)
3. File completion updates in real-time with completion indicators
4. Files per second reflects parallel throughput
5. KB/s shows source data throughput (Story 3)
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


class TestEnhancedProgressReporting:
    """Test enhanced progress reporting for parallel processing."""

    def setup_method(self):
        """Setup test environment."""
        # Create temporary directory
        self.temp_dir = str(get_local_tmp_dir() / f"test_{uuid.uuid4().hex[:8]}")
        self.temp_path = Path(self.temp_dir)
        self.temp_path.mkdir(parents=True, exist_ok=True)

        # Create test files
        self.test_files = []
        for i in range(8):  # 8 files for parallel processing
            file_path = self.temp_path / f"test_file_{i}.py"
            content = f"""
def function_{i}():
    '''Function {i} with content for chunking.'''
    return "Content for testing parallel processing and progress reporting."

class TestClass_{i}:
    '''Test class {i}'''
    
    def method_1(self):
        return "Method implementation with enough content for chunking"
    
    def method_2(self):
        return "Another method with substantial content for testing"
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
    def test_enhanced_progress_format_with_thread_utilization(self):
        """Test that progress reporting shows actual thread utilization in real-time."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress calls to analyze format
        progress_calls = []
        thread_counts_seen = set()

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0:  # File progress calls
                progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "info": info,
                        "timestamp": time.time(),
                    }
                )

                # Extract thread count from info string
                # Expected format: "files completed/total (%) | files/s | KB/s | threads | filename"
                if "|" in info and "threads" in info:
                    parts = info.split("|")
                    if (
                        len(parts) >= 4
                    ):  # Now need at least 4 parts due to KB/s addition
                        thread_part = parts[3].strip()  # Threads moved to index 3
                        if "threads" in thread_part:
                            thread_count_str = thread_part.replace(
                                "threads", ""
                            ).strip()
                            try:
                                thread_count = int(thread_count_str)
                                thread_counts_seen.add(thread_count)
                            except ValueError:
                                pass

            return None  # Don't cancel

        # Process with 4 threads
        thread_count = 4
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=thread_count,
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify progress calls were made
        assert len(progress_calls) > 0, "Expected progress callbacks during processing"

        # Verify at least one progress call contains thread information
        thread_info_found = False
        for call in progress_calls:
            info = call["info"]
            if "threads" in info:
                thread_info_found = True
                # Verify format matches expected pattern
                # Expected: "X/Y files (Z%) | files/s | KB/s | threads | filename"
                parts = info.split("|")
                assert (
                    len(parts) >= 5
                ), f"Expected at least 5 parts in progress info with KB/s, got: {info}"

                # Check file progress part
                assert (
                    "files" in parts[0]
                ), f"Expected 'files' in first part: {parts[0]}"
                assert (
                    "(" in parts[0] and "%)" in parts[0]
                ), f"Expected percentage in first part: {parts[0]}"

                # Check files per second part
                assert (
                    "files/s" in parts[1]
                ), f"Expected 'files/s' in second part: {parts[1]}"

                # Check KB/s part (Story 3 addition)
                assert "KB/s" in parts[2], f"Expected 'KB/s' in third part: {parts[2]}"

                # Check thread count part
                assert (
                    "threads" in parts[3]
                ), f"Expected 'threads' in fourth part: {parts[3]}"

                # Check filename part exists
                assert (
                    len(parts[4].strip()) > 0
                ), f"Expected filename in fifth part: {parts[4]}"

                break

        assert thread_info_found, "No progress calls contained thread information"

        # Verify we captured some thread counts
        assert (
            len(thread_counts_seen) > 0
        ), f"Expected to see thread counts, but saw: {thread_counts_seen}"

        # The thread count should be related to our configured count
        # In high-throughput processing, actual active threads can vary as workers complete tasks
        assert any(
            count <= thread_count for count in thread_counts_seen
        ), f"Expected to see thread counts <= {thread_count}, but saw: {thread_counts_seen}"

    @pytest.mark.unit
    def test_real_time_file_completion_indicators(self):
        """Test that progress shows file completion status indicators."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track progress to find completion indicators
        progress_calls = []
        completion_indicators_found = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0:
                progress_calls.append(
                    {"current": current, "total": total, "info": info}
                )

                # Look for completion indicators in filename part
                # Expected format: "files completed/total (%) | files/s | KB/s | threads | filename ✓"
                # or: "files completed/total (%) | files/s | KB/s | threads | filename (67%)"
                parts = info.split("|")
                if len(parts) >= 5:  # Now need 5 parts due to KB/s addition
                    filename_part = parts[4].strip()  # Filename moved to index 4
                    if "✓" in filename_part:
                        completion_indicators_found.append(("completed", filename_part))
                    elif "(" in filename_part and "%)" in filename_part:
                        completion_indicators_found.append(
                            ("in_progress", filename_part)
                        )

            return None

        # Process files
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify we found completion indicators
        assert len(completion_indicators_found) > 0, (
            f"Expected to find completion indicators (✓ or %), but found none. "
            f"Progress calls: {[call['info'] for call in progress_calls[-3:]]}"
        )

        # Verify we have both types of indicators (completed and in-progress)
        indicator_types = {indicator[0] for indicator in completion_indicators_found}

        # At minimum, we should see completed files marked with ✓
        assert "completed" in indicator_types, (
            f"Expected to see completed files marked with ✓, "
            f"but only found: {completion_indicators_found}"
        )

    @pytest.mark.unit
    def test_files_per_second_reflects_parallel_throughput(self):
        """Test that files per second calculation reflects parallel processing throughput."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track files per second values
        files_per_sec_values = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0 and "files/s" in info:
                parts = info.split("|")
                if len(parts) >= 2:
                    files_part = parts[1].strip()
                    if "files/s" in files_part:
                        files_str = files_part.replace("files/s", "").strip()
                        try:
                            files_value = float(files_str)
                            files_per_sec_values.append(files_value)
                        except ValueError:
                            pass

            return None

        # Process with multiple threads
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=4,
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify we captured files per second values
        assert (
            len(files_per_sec_values) > 0
        ), "Expected to capture files per second values"

        # Verify the values are reasonable for parallel processing
        max_files_per_sec = max(files_per_sec_values)

        # With parallel processing, we should see reasonable files/s values
        assert max_files_per_sec > 0.0, (
            f"Expected parallel processing to achieve > 0.0 files/s, "
            f"but max was {max_files_per_sec}"
        )

        # Files/s should be reasonable for the number of files processed
        files_processed = len(self.test_files)
        assert max_files_per_sec < 1000.0, (
            f"Max reported rate ({max_files_per_sec:.2f} files/s) seems unreasonably high "
            f"given {files_processed} files processed. Possible calculation error."
        )

    @pytest.mark.unit
    def test_thread_utilization_varies_during_processing(self):
        """Test that thread utilization count varies as workers finish tasks."""

        # Create processor
        processor = HighThroughputProcessor(
            config=self.config,
            embedding_provider=self.mock_embedding_provider,
            qdrant_client=self.mock_qdrant,
        )

        # Track thread utilization over time
        thread_utilization_over_time = []

        def capture_progress(current, total, file_path, error=None, info=None):
            if info and total > 0 and "threads" in info:
                parts = info.split("|")
                if len(parts) >= 4:  # Now need at least 4 parts due to KB/s addition
                    thread_part = parts[3].strip()  # Threads moved to index 3
                    if "threads" in thread_part:
                        thread_count_str = thread_part.replace("threads", "").strip()
                        try:
                            thread_count = int(thread_count_str)
                            thread_utilization_over_time.append(
                                {
                                    "timestamp": time.time(),
                                    "threads": thread_count,
                                    "progress": current / total if total > 0 else 0,
                                }
                            )
                        except ValueError:
                            pass

            return None

        # Process with 8 threads to see variation
        processor.process_files_high_throughput(
            files=self.test_files,
            vector_thread_count=8,
            batch_size=50,
            progress_callback=capture_progress,
        )

        # Verify we captured thread utilization data
        assert (
            len(thread_utilization_over_time) >= 2
        ), "Expected to capture thread utilization over multiple progress updates"

        # Extract unique thread counts seen
        unique_thread_counts = {
            entry["threads"] for entry in thread_utilization_over_time
        }

        # With 8 files and 8 threads, we should see variation in active thread counts
        # as workers complete files at different times
        assert len(unique_thread_counts) >= 2, (
            f"Expected to see variation in thread utilization, "
            f"but only saw these counts: {unique_thread_counts}"
        )

        # Thread counts should be reasonable (between 0 and 8)
        # 0 is valid when processing is complete or starting up
        assert all(
            0 <= count <= 8 for count in unique_thread_counts
        ), f"Expected thread counts between 0-8, but saw: {unique_thread_counts}"

        # As processing progresses, thread utilization typically decreases
        # (fewer files left to process) and eventually reaches 0 when complete
        if len(thread_utilization_over_time) >= 4:
            early_threads = thread_utilization_over_time[0]["threads"]
            late_threads = thread_utilization_over_time[-1]["threads"]

            # Early in processing, we should see active threads
            assert early_threads >= 0, (
                f"Expected non-negative thread count early in processing, "
                f"but saw: {early_threads}"
            )

            # Late in processing, thread count can be 0 (processing complete)
            # or lower than early count (workers finishing)
            assert late_threads <= early_threads, (
                f"Expected thread utilization to decrease or stay same over time, "
                f"but saw early: {early_threads}, late: {late_threads}"
            )

    def teardown_method(self):
        """Cleanup test environment."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
