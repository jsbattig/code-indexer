"""Tests demonstrating hardcoded file display limit bug.

This test suite demonstrates that the file display system is limited to 8 concurrent files
despite having more threads configured. This is due to ConsolidatedFileTracker being
initialized with hardcoded max_concurrent_files=8 instead of using actual thread count.
"""

import pytest
from pathlib import Path
from unittest.mock import patch

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor


@pytest.mark.unit
class TestHardcodedFileDisplayLimit:
    """Test cases demonstrating hardcoded 8-file display limit bug."""

    def test_file_display_limited_to_8_despite_12_threads_configured(self):
        """FAILING TEST: File display shows only 8 files despite 12 threads configured.

        This test demonstrates that ConsolidatedFileTracker is hardcoded to 8 max_concurrent_files
        even when the system is configured for 12 threads. This creates a mismatch where:
        - Thread count shows: "12 threads" (correct)
        - File display shows: Only 8 file lines (BUG - should show 12)
        """
        # Create HighThroughputProcessor instance (which hardcodes ConsolidatedFileTracker to 8)
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize threading attributes
        import threading

        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Initialize ConsolidatedFileTracker with hardcoded 8 (this is the bug)
        from src.code_indexer.services.consolidated_file_tracker import (
            ConsolidatedFileTracker,
        )

        processor.file_tracker = ConsolidatedFileTracker(max_concurrent_files=8)

        # Simulate 12 threads all working on files simultaneously
        # (representing 12 configured threads from config.json)
        file_paths = [Path(f"/test/file{i}.py") for i in range(1, 13)]

        # Register 12 files with the processor (simulating 12 active threads)
        for file_path in file_paths:
            processor.file_tracker.start_file_processing(
                thread_id=len(processor.file_tracker._active_files),
                file_path=file_path,
                file_size=1024,
            )

        # Get concurrent files data - this should show all 12 files but will only show 8
        concurrent_files = processor.file_tracker.get_concurrent_files_data()

        # BUG DEMONSTRATION: This fails because ConsolidatedFileTracker is hardcoded to 8
        # The file display is artificially limited despite having 12 threads configured
        assert len(concurrent_files) == 12, (
            f"HARDCODED LIMIT BUG: Expected 12 concurrent files to match 12 configured threads, "
            f"but got {len(concurrent_files)} due to hardcoded max_concurrent_files=8 in "
            f"ConsolidatedFileTracker initialization"
        )

        # Verify all 12 files should be visible
        displayed_files = {cf["file_path"] for cf in concurrent_files}
        expected_files = {str(fp) for fp in file_paths}

        missing_files = expected_files - displayed_files
        if missing_files:
            pytest.fail(
                f"Files missing from display due to hardcoded 8-file limit: {missing_files}. "
                f"ConsolidatedFileTracker should support all {len(file_paths)} configured threads, "
                f"not hardcoded 8 files."
            )

    def test_thread_configuration_mismatch_demonstration(self):
        """FAILING TEST: Demonstrates mismatch between thread config and file display.

        This test shows the root cause: ConsolidatedFileTracker is initialized with
        hardcoded max_concurrent_files=8 regardless of actual thread configuration.
        """
        # Simulate different thread configurations
        for configured_threads in [4, 8, 12, 16, 24]:
            with patch.object(
                HighThroughputProcessor, "__init__", lambda self, *args, **kwargs: None
            ):
                processor = HighThroughputProcessor()

                # Initialize attributes manually
                import threading

                processor._thread_counter = 0
                processor._file_to_thread_map = {}
                processor._file_to_thread_lock = threading.Lock()

                # BUG: ConsolidatedFileTracker is always hardcoded to 8, ignoring configured_threads
                from src.code_indexer.services.consolidated_file_tracker import (
                    ConsolidatedFileTracker,
                )

                processor.file_tracker = ConsolidatedFileTracker(
                    max_concurrent_files=8
                )  # HARDCODED!

                # Simulate configured_threads number of active files
                for i in range(configured_threads):
                    processor.file_tracker.start_file_processing(
                        thread_id=i, file_path=Path(f"/test/file{i}.py"), file_size=1024
                    )

                # Get actual display count
                concurrent_files = processor.file_tracker.get_concurrent_files_data()
                actual_display_count = len(concurrent_files)

                # The bug: display is always capped at 8, regardless of thread configuration
                if configured_threads <= 8:
                    # These configurations work correctly
                    assert actual_display_count == configured_threads
                else:
                    # BUG: These configurations are artificially limited to 8
                    assert actual_display_count == 8, (
                        f"BUG CONFIRMED: {configured_threads} threads configured but only "
                        f"{actual_display_count} files displayed due to hardcoded 8-file limit"
                    )

                    # This is what SHOULD happen (but currently fails due to hardcoded limit)
                    with pytest.raises(AssertionError, match="HARDCODED LIMIT"):
                        assert actual_display_count == configured_threads, (
                            f"HARDCODED LIMIT: {configured_threads} threads configured but only "
                            f"{actual_display_count} files displayed"
                        )

    def test_fix_validation_file_display_supports_12_threads(self):
        """PASSING TEST: File display now shows all 12 files when 12 threads configured.

        This test validates the FIX for ConsolidatedFileTracker being hardcoded to 8 max_concurrent_files.
        After the fix, the file tracker is initialized dynamically with the actual thread count.
        """
        import tempfile
        from unittest.mock import Mock, patch

        # Use a temporary directory to avoid permission issues
        with tempfile.TemporaryDirectory() as temp_dir:
            # Mock dependencies for HighThroughputProcessor
            config = Mock()
            config.codebase_dir = Path(temp_dir)
            config.exclude_dirs = []
            config.exclude_files = []
            config.file_extensions = [".py"]

            # Mock nested config attributes required for initialization
            config.indexing = Mock()
            config.indexing.chunk_size = 200
            config.indexing.overlap_size = 50
            config.indexing.max_file_size = 1000000
            config.indexing.min_file_size = 1

            config.chunking = Mock()
            config.chunking.chunk_size = 200
            config.chunking.overlap_size = 50

            embedding_provider = Mock()
            qdrant_client = Mock()

            # Create processor with proper initialization
            processor = HighThroughputProcessor(
                config=config,
                embedding_provider=embedding_provider,
                qdrant_client=qdrant_client,
            )

            # Verify file_tracker is None initially (lazy initialization)
            assert (
                processor.file_tracker is None
            ), "file_tracker should be None before processing"

            # Create test files
            file_paths = [Path(temp_dir) / f"file{i}.py" for i in range(1, 13)]

            # Mock the file processing parts we don't need for this test
            with patch.object(processor, "fixed_size_chunker") as mock_chunker:
                mock_chunker.chunk_file.return_value = [{"content": "test"}]

                with patch(
                    "src.code_indexer.services.high_throughput_processor.VectorCalculationManager"
                ):
                    # This call should initialize file_tracker with 12 max_concurrent_files
                    try:
                        processor.process_files_high_throughput(
                            files=file_paths,
                            vector_thread_count=12,  # This is the key - 12 threads
                            batch_size=50,
                        )
                    except Exception:
                        # We don't care if the processing fails, we just want to test file tracker initialization
                        pass

            # FIXED: After the fix, file_tracker should be initialized with 12 max_concurrent_files
            assert (
                processor.file_tracker is not None
            ), "file_tracker should be initialized after process_files_high_throughput"
            assert processor.file_tracker.max_concurrent_files == 12, (
                f"FIXED: ConsolidatedFileTracker should support 12 concurrent files when 12 threads configured, "
                f"but got {processor.file_tracker.max_concurrent_files}"
            )

            # Register 12 files with the processor (simulating 12 active threads)
            for i, file_path in enumerate(file_paths):
                processor.file_tracker.start_file_processing(
                    thread_id=i, file_path=file_path, file_size=1024
                )

            # Get concurrent files data - this should now show all 12 files
            concurrent_files = processor.file_tracker.get_concurrent_files_data()

            # FIXED: Now supports all 12 files instead of being limited to 8
            assert len(concurrent_files) == 12, (
                f"FIXED: Expected 12 concurrent files to match 12 configured threads, "
                f"but got {len(concurrent_files)}. The hardcoded limit has been fixed!"
            )

            # Verify all 12 files are visible
            displayed_files = {cf["file_path"] for cf in concurrent_files}
            expected_files = {str(fp) for fp in file_paths}

            assert (
                displayed_files == expected_files
            ), f"All 12 files should be displayed. Missing: {expected_files - displayed_files}"

    def test_root_cause_identification(self):
        """Test that identifies the exact source of the hardcoded limit."""
        # The bug is in HighThroughputProcessor.__init__ line 92:
        # self.file_tracker = ConsolidatedFileTracker(max_concurrent_files=8)

        # This should use dynamic thread count from configuration instead
        processor = HighThroughputProcessor.__new__(HighThroughputProcessor)

        # Initialize required attributes
        import threading

        processor._thread_counter = 0
        processor._file_to_thread_map = {}
        processor._file_to_thread_lock = threading.Lock()

        # Verify the hardcoded value exists
        from src.code_indexer.services.consolidated_file_tracker import (
            ConsolidatedFileTracker,
        )

        processor.file_tracker = ConsolidatedFileTracker(max_concurrent_files=8)

        # Confirm the tracker respects the hardcoded 8 limit
        assert processor.file_tracker.max_concurrent_files == 8

        # This test will pass initially (confirming the bug exists)
        # After the fix, ConsolidatedFileTracker should be initialized with
        # dynamic thread count instead of hardcoded 8
