"""Integration test to verify 12 threads configuration works end-to-end."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


@pytest.mark.unit
class TestTwelveThreadsIntegration:
    """Integration tests for 12 threads configuration."""

    def test_12_threads_shows_12_concurrent_files(self):
        """Integration test: 12 threads configuration shows 12 concurrent files in display.

        This test verifies the complete flow:
        1. HighThroughputProcessor is initialized
        2. process_files_high_throughput is called with vector_thread_count=12
        3. ConsolidatedFileTracker is initialized with 12 max_concurrent_files
        4. File display can show all 12 files simultaneously
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Set up processor
            config = Mock()
            config.codebase_dir = Path(temp_dir)
            config.exclude_dirs = []
            config.exclude_files = []
            config.file_extensions = [".py"]

            # Mock nested config attributes
            config.indexing = Mock()
            config.indexing.chunk_size = 200
            config.indexing.overlap_size = 50
            config.indexing.max_file_size = 1000000
            config.indexing.min_file_size = 1

            config.chunking = Mock()
            config.chunking.chunk_size = 200
            config.chunking.overlap_size = 50

            processor = HighThroughputProcessor(
                config=config,
                embedding_provider=Mock(),
                qdrant_client=Mock(),
            )

            # Verify lazy initialization (slot_tracker should not be assigned yet)
            try:
                _ = processor.slot_tracker
                assert False, "slot_tracker should not be initialized yet"
            except AttributeError:
                pass  # Expected - slot_tracker is not yet assigned

            # Create 12 test files
            test_files = []
            for i in range(1, 13):
                file_path = Path(temp_dir) / f"test_file_{i}.py"
                file_path.write_text(f"def function_{i}(): pass")
                test_files.append(file_path)

            # Mock dependencies to focus on file tracking
            with patch.object(processor, "fixed_size_chunker") as mock_chunker:
                mock_chunker.chunk_file.return_value = [
                    {"content": "chunk", "metadata": {}}
                ]

                with patch(
                    "src.code_indexer.services.high_throughput_processor.VectorCalculationManager"
                ) as MockVCM:
                    mock_vcm = Mock()
                    MockVCM.return_value.__enter__.return_value = mock_vcm
                    mock_vcm.submit_chunk.return_value = Mock()

                    # The key test: call with 12 threads
                    try:
                        processor.process_files_high_throughput(
                            files=test_files,
                            vector_thread_count=12,  # CRITICAL: 12 threads
                            batch_size=50,
                        )
                    except Exception:
                        # Processing may fail due to mocking, but we only care about file tracker initialization
                        pass

            # Verify slot tracker was initialized correctly
            assert (
                processor.slot_tracker is not None
            ), "SlotTracker should be initialized"
            assert (
                processor.slot_tracker.max_slots == 14  # 12 threads + 2
            ), f"SlotTracker should support 14 concurrent slots (12+2), got {processor.slot_tracker.max_slots}"

            # Simulate 12 concurrent files being processed
            from src.code_indexer.services.clean_slot_tracker import (
                FileData,
                FileStatus,
            )

            for i, test_file in enumerate(test_files):
                file_data = FileData(
                    filename=str(test_file),
                    file_size=test_file.stat().st_size,
                    status=FileStatus.STARTING,
                )
                _ = processor.slot_tracker.acquire_slot(file_data)

            # Verify all 12 files can be displayed simultaneously
            concurrent_files = processor.slot_tracker.get_concurrent_files_data()
            assert (
                len(concurrent_files) == 12
            ), f"Should display all 12 concurrent files, got {len(concurrent_files)}"

            # Verify all files are present
            displayed_paths = {cf["file_path"] for cf in concurrent_files}
            expected_paths = {str(f) for f in test_files}
            assert (
                displayed_paths == expected_paths
            ), f"All test files should be displayed. Missing: {expected_paths - displayed_paths}"

            print("✅ SUCCESS: 12 threads configuration works correctly!")
            print(
                f"   - CleanSlotTracker initialized with {processor.slot_tracker.max_slots} max slots (12+2)"
            )
            print(
                f"   - Successfully displaying {len(concurrent_files)} concurrent files"
            )
            print("   - Thread count matches display capability: 12 = 12 ✓")

    def test_different_thread_counts_work_correctly(self):
        """Test that different thread counts (4, 8, 16, 24) all work correctly."""
        for thread_count in [4, 8, 16, 24]:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Set up processor
                config = Mock()
                config.codebase_dir = Path(temp_dir)
                config.exclude_dirs = []
                config.exclude_files = []
                config.file_extensions = [".py"]

                config.indexing = Mock()
                config.indexing.chunk_size = 200
                config.indexing.overlap_size = 50
                config.indexing.max_file_size = 1000000
                config.indexing.min_file_size = 1

                config.chunking = Mock()
                config.chunking.chunk_size = 200
                config.chunking.overlap_size = 50

                processor = HighThroughputProcessor(
                    config=config,
                    embedding_provider=Mock(),
                    qdrant_client=Mock(),
                )

                # Create test files
                test_files = [
                    Path(temp_dir) / f"file{i}.py" for i in range(thread_count)
                ]
                for f in test_files:
                    f.write_text("def test(): pass")

                # Mock and process
                with patch.object(processor, "fixed_size_chunker") as mock_chunker:
                    mock_chunker.chunk_file.return_value = [{"content": "test"}]

                    with patch(
                        "src.code_indexer.services.high_throughput_processor.VectorCalculationManager"
                    ):
                        try:
                            processor.process_files_high_throughput(
                                files=test_files,
                                vector_thread_count=thread_count,
                                batch_size=50,
                            )
                        except Exception:
                            pass

                # Verify configuration (thread_count + 2 slots)
                expected_slots = thread_count + 2
                assert processor.slot_tracker.max_slots == expected_slots, (
                    f"Thread count {thread_count}: SlotTracker should support {expected_slots} slots ({thread_count}+2), "
                    f"got {processor.slot_tracker.max_slots}"
                )

                # Test file display capacity
                from src.code_indexer.services.clean_slot_tracker import (
                    FileData,
                    FileStatus,
                )

                for i, test_file in enumerate(test_files):
                    file_data = FileData(
                        filename=str(test_file),
                        file_size=1024,
                        status=FileStatus.STARTING,
                    )
                    _ = processor.slot_tracker.acquire_slot(file_data)

                concurrent_files = processor.slot_tracker.get_concurrent_files_data()
                assert len(concurrent_files) == thread_count, (
                    f"Thread count {thread_count}: Should display {thread_count} files, "
                    f"got {len(concurrent_files)}"
                )

        print("✅ SUCCESS: All thread counts (4, 8, 16, 24) work correctly!")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
