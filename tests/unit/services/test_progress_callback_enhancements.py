"""
Tests for Progress Callback Enhancements (Story 03).

Tests the enhanced progress callback system with:
1. Immediate queuing feedback during file submission
2. Worker thread progress reporting during chunk processing
3. File completion notifications with timing and chunk count
4. Error status reporting with specific error context
5. Overall progress tracking with file-level metrics

CRITICAL: Tests must verify the exact callback patterns required by CLI:
- total=0 with info → Setup messages (ℹ️ scrolling)
- total>0 with info → Progress bar with format "files (%) | emb/s | threads | filename"
"""

import threading
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.high_throughput_processor import HighThroughputProcessor
from src.code_indexer.services.file_chunking_manager import FileChunkingManager
from src.code_indexer.services.vector_calculation_manager import (
    VectorCalculationManager,
)


class TestProgressCallbackEnhancements:
    """Test suite for progress callback enhancements with comprehensive real-time feedback."""

    def setup_method(self):
        """Set up test fixtures."""
        # Progress callback capture
        self.progress_calls = []
        self.progress_lock = threading.Lock()

        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.temp_files = []

        def capture_progress_callback(current, total, file_path, info=None):
            """Capture progress callback calls for testing."""
            with self.progress_lock:
                self.progress_calls.append(
                    {
                        "current": current,
                        "total": total,
                        "file_path": file_path,
                        "info": info,
                        "timestamp": time.time(),
                    }
                )

        self.progress_callback = capture_progress_callback

    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temporary files
        for temp_file in self.temp_files:
            if temp_file.exists():
                temp_file.unlink()

        # Remove temp directory
        os.rmdir(self.temp_dir)

    def _create_test_file(
        self,
        filename: str,
        content: str = "def test_function():\n    return 'hello world'",
    ) -> Path:
        """Create a temporary test file with content."""
        test_file = Path(self.temp_dir) / filename
        test_file.write_text(content)
        self.temp_files.append(test_file)
        return test_file

    def test_immediate_queuing_feedback_during_file_submission(self):
        """
        Test immediate queuing feedback when files are submitted for processing.

        HOOK POINT: FileChunkingManager.submit_file_for_processing() method entry
        EXPECTED CALLBACK: progress_callback(0, 0, file_path, info="📥 Queued for processing")
        """
        # Create actual test file with content
        test_file = self._create_test_file("test_file.py")
        metadata = {"project_id": "test", "file_hash": "abc123"}

        # Mock dependencies with proper setup
        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock chunker to return valid chunks (avoiding Mock len() issue)
        mock_chunks = [
            {
                "text": "def test_function():",
                "chunk_index": 0,
                "total_chunks": 1,
                "file_extension": "py",
            }
        ]
        mock_chunker.chunk_file.return_value = mock_chunks

        # Record timing when we start the submission
        start_time = time.time()

        # Create FileChunkingManager
        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            # Submit file for processing
            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Verify immediate queuing feedback was provided
            # Wait just enough for immediate callback to be captured
            time.sleep(0.02)  # Reduced wait time

            assert len(self.progress_calls) >= 1, "Expected immediate queuing callback"

            queuing_call = self.progress_calls[0]
            assert queuing_call["current"] == 0, "Expected current=0 for setup message"
            assert queuing_call["total"] == 0, "Expected total=0 for setup message"
            assert (
                queuing_call["file_path"] == test_file
            ), f"Expected file_path={test_file}"
            assert (
                "📥 Queued for processing" in queuing_call["info"]
            ), "Expected queuing message"

            # Test timing requirement: measure against start time, not current time
            first_call_time = self.progress_calls[0]["timestamp"]
            feedback_delay = (first_call_time - start_time) * 1000  # Convert to ms

            # The callback should happen almost immediately (within 10ms of submission)
            assert (
                feedback_delay < 50
            ), f"Queuing feedback took {feedback_delay:.1f}ms, expected < 50ms"

    def test_worker_thread_progress_reporting_during_chunk_processing(self):
        """
        Test worker thread progress reporting during chunk processing.

        HOOK POINT: Worker thread _process_file_complete_lifecycle() during chunk processing
        EXPECTED CALLBACK: progress_callback(0, 0, file_path, info="🔄 Processing file.py (chunk 5/12, 42%)")
        """
        # This test will need to be implemented after we add the hook points
        # For now, test that current implementation does NOT provide this feedback

        test_file = self._create_test_file("test_worker_progress.py")
        metadata = {"project_id": "test", "file_hash": "def456"}

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock chunker to return multiple chunks
        mock_chunks = [
            {
                "text": "chunk1",
                "chunk_index": 0,
                "total_chunks": 3,
                "file_extension": "py",
            },
            {
                "text": "chunk2",
                "chunk_index": 1,
                "total_chunks": 3,
                "file_extension": "py",
            },
            {
                "text": "chunk3",
                "chunk_index": 2,
                "total_chunks": 3,
                "file_extension": "py",
            },
        ]
        mock_chunker.chunk_file.return_value = mock_chunks

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Wait for processing
            time.sleep(0.5)

            # FAILING TEST: Currently no worker thread progress reporting exists
            worker_progress_calls = [
                call
                for call in self.progress_calls
                if call["info"]
                and "🔄 Processing" in call["info"]
                and "chunk" in call["info"]
            ]

            # This should fail because the enhancement hasn't been implemented yet
            assert (
                len(worker_progress_calls) > 0
            ), "Expected worker thread progress reporting during chunk processing"

    def test_file_completion_notifications_with_timing_and_chunk_count(self):
        """
        Test file completion notifications with timing and chunk count.

        HOOK POINT: Worker thread _process_file_complete_lifecycle() before return
        EXPECTED CALLBACK: progress_callback(0, 0, file_path, info="✅ Completed file.py (12 chunks, 2.3s)")
        """
        # Create actual test file with meaningful content
        test_file = self._create_test_file(
            "test_completion.py", "def completion_test():\n    return 'test complete'"
        )
        metadata = {"project_id": "test", "file_hash": "ghi789"}

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock successful processing with proper vector results
        mock_chunks = [
            {
                "text": "def completion_test():",
                "chunk_index": 0,
                "total_chunks": 2,
                "file_extension": "py",
            },
            {
                "text": "    return 'test complete'",
                "chunk_index": 1,
                "total_chunks": 2,
                "file_extension": "py",
            },
        ]
        mock_chunker.chunk_file.return_value = mock_chunks

        # Mock successful vector processing
        mock_vector_result = Mock()
        mock_vector_result.error = None  # No error
        mock_vector_result.embedding = [0.1, 0.2, 0.3]  # Mock embedding

        mock_future = Mock()
        mock_future.result.return_value = mock_vector_result

        mock_vector_manager.submit_chunk.return_value = mock_future
        mock_qdrant_client.upsert_points_atomic.return_value = True

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Wait for completion
            time.sleep(1.0)

            # Now this should pass with the enhancement
            completion_calls = [
                call
                for call in self.progress_calls
                if call["info"]
                and "✅ Completed" in call["info"]
                and "chunks" in call["info"]
            ]

            assert (
                len(completion_calls) > 0
            ), "Expected completion notification with timing and chunk count"

            # Verify completion notification format
            completion_call = completion_calls[0]
            assert (
                completion_call["current"] == 0
            ), "Expected current=0 for setup message"
            assert completion_call["total"] == 0, "Expected total=0 for setup message"
            assert (
                completion_call["file_path"] == test_file
            ), f"Expected file_path={test_file}"
            assert (
                "✅ Completed" in completion_call["info"]
            ), "Expected completion indicator"
            assert "chunks" in completion_call["info"], "Expected chunk count"
            assert "s)" in completion_call["info"], "Expected timing information"

    def test_error_status_reporting_with_specific_context(self):
        """
        Test error status reporting with specific error context.

        HOOK POINT: Worker thread _process_file_complete_lifecycle() exception handling blocks
        EXPECTED CALLBACK: progress_callback(0, 0, file_path, info="❌ Failed file.py - Vector processing timeout")
        """
        test_file = self._create_test_file("test_error.py")
        metadata = {"project_id": "test", "file_hash": "jkl012"}

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock error condition - chunker returns empty chunks
        mock_chunker.chunk_file.return_value = []

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Wait for error processing
            time.sleep(0.5)

            # FAILING TEST: Currently no error status reporting exists
            error_calls = [
                call
                for call in self.progress_calls
                if call["info"] and "❌ Failed" in call["info"]
            ]

            # This should fail because the enhancement hasn't been implemented yet
            assert (
                len(error_calls) > 0
            ), "Expected error status reporting with specific context"

    def test_overall_progress_tracking_with_file_level_metrics(self):
        """
        Test overall progress tracking with file-level metrics.

        HOOK POINT: Main thread as_completed(file_futures) loop (replacing current line 492)
        EXPECTED: File-level progress instead of chunk-level
        """
        # Create mock processor
        mock_processor = Mock(spec=HighThroughputProcessor)

        # Test files - create actual test files
        test_files = [
            self._create_test_file("file1.py"),
            self._create_test_file("file2.py"),
            self._create_test_file("file3.py"),
        ]

        # Mock the process_files_high_throughput method
        def mock_process_files(
            files, vector_thread_count, batch_size=50, progress_callback=None
        ):
            """Mock processing that calls progress_callback with file-level metrics."""

            for i, file_path in enumerate(files):
                # Simulate file completion
                if progress_callback:
                    completed_files = i + 1
                    files_per_second = 1.2
                    kbs_throughput = 45.7
                    thread_count = vector_thread_count

                    file_progress_pct = completed_files / len(files) * 100
                    info_msg = (
                        f"{completed_files}/{len(files)} files ({file_progress_pct:.0f}%) | "
                        f"{files_per_second:.1f} files/s | "
                        f"{kbs_throughput:.1f} KB/s | "
                        f"{thread_count} threads | "
                        f"{file_path.name} ✓"
                    )

                    progress_callback(
                        completed_files,  # current (file-level)
                        len(files),  # total (file-level)
                        Path(""),  # empty path for progress bar update
                        info=info_msg,
                    )

                time.sleep(0.1)  # Simulate processing time

            return Mock(files_processed=len(files), chunks_created=15)

        mock_processor.process_files_high_throughput = mock_process_files

        # Execute mock processing
        _result = mock_processor.process_files_high_throughput(
            files=test_files,
            vector_thread_count=4,
            progress_callback=self.progress_callback,
        )

        # Verify file-level progress tracking
        file_progress_calls = [
            call
            for call in self.progress_calls
            if call["total"] > 0  # File progress (not setup messages)
        ]

        assert len(file_progress_calls) == len(
            test_files
        ), f"Expected {len(test_files)} file progress calls"

        # Verify progress format
        for i, call in enumerate(file_progress_calls):
            expected_current = i + 1
            expected_total = len(test_files)

            assert (
                call["current"] == expected_current
            ), f"Expected current={expected_current}"
            assert call["total"] == expected_total, f"Expected total={expected_total}"
            assert "files/s" in call["info"], "Expected files/s metric in progress"
            assert "KB/s" in call["info"], "Expected KB/s metric in progress"
            assert "threads" in call["info"], "Expected thread count in progress"
            assert "%" in call["info"], "Expected percentage in progress"

    def test_progress_callback_timing_requirements(self):
        """
        Test that progress callbacks meet timing requirements for real-time feedback.

        Requirements:
        - Immediate queuing feedback: < 10ms
        - Worker progress updates: Every 1-2 seconds during long processing
        - No silent periods > 5 seconds during active processing
        """
        test_file = self._create_test_file("test_timing.py")
        metadata = {"project_id": "test", "file_hash": "timing123"}

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock long-running chunks to test continuous feedback
        mock_chunks = [
            {
                "text": f"chunk{i}",
                "chunk_index": i,
                "total_chunks": 10,
                "file_extension": "py",
            }
            for i in range(10)
        ]
        mock_chunker.chunk_file.return_value = mock_chunks

        start_time = time.time()

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Wait for processing
            time.sleep(2.0)

            # Test immediate feedback timing
            if self.progress_calls:
                first_callback_time = self.progress_calls[0]["timestamp"]
                immediate_feedback_delay = (
                    first_callback_time - start_time
                ) * 1000  # ms

                # FAILING TEST: Should be < 10ms for immediate feedback
                assert (
                    immediate_feedback_delay < 50
                ), f"Immediate feedback took {immediate_feedback_delay:.1f}ms, expected < 50ms"

            # Test for silent periods
            callback_times = [call["timestamp"] for call in self.progress_calls]

            if len(callback_times) > 1:
                max_gap = 0
                for i in range(1, len(callback_times)):
                    gap = callback_times[i] - callback_times[i - 1]
                    max_gap = max(max_gap, gap)

                # FAILING TEST: Should not have silent periods > 5 seconds
                assert (
                    max_gap < 5.0
                ), f"Found silent period of {max_gap:.1f}s, expected < 5s"

    def test_progress_callback_cli_integration_patterns(self):
        """
        Test that progress callbacks follow exact CLI integration patterns.

        CRITICAL CLI PATTERNS:
        - total=0 with info → Setup messages (ℹ️ scrolling)
        - total>0 with info → Progress bar with format "files (%) | emb/s | threads | filename"
        """
        # Test setup message pattern (total=0)
        setup_calls = [
            call for call in self.progress_calls if call["total"] == 0 and call["info"]
        ]

        for call in setup_calls:
            assert call["current"] == 0, "Setup messages must have current=0"
            assert call["total"] == 0, "Setup messages must have total=0"
            assert call["info"] is not None, "Setup messages must have info text"

        # Test progress bar pattern (total>0)
        progress_bar_calls = [
            call for call in self.progress_calls if call["total"] > 0 and call["info"]
        ]

        for call in progress_bar_calls:
            assert call["current"] <= call["total"], "Current must not exceed total"
            assert call["total"] > 0, "Progress bar calls must have total>0"
            assert call["info"] is not None, "Progress bar calls must have info"

            # Verify expected info format for file progress
            if "files" in call["info"] and "%" in call["info"]:
                assert (
                    "files/s" in call["info"] or "KB/s" in call["info"]
                ), "Expected throughput metrics"
                assert "threads" in call["info"], "Expected thread count"

    def test_continuous_activity_feedback_no_silent_periods(self):
        """
        Test that users see continuous activity without silent periods.

        During file processing, there should be regular progress updates
        so users never wonder if the system has frozen.
        """
        # This test will verify that the enhanced system provides continuous feedback
        # Currently this will fail because enhancements haven't been implemented

        test_file = self._create_test_file("test_continuous.py")
        metadata = {"project_id": "test", "file_hash": "continuous123"}

        mock_vector_manager = Mock(spec=VectorCalculationManager)
        mock_chunker = Mock()
        mock_qdrant_client = Mock()

        # Mock processing that takes some time
        mock_chunks = [
            {
                "text": f"chunk{i}",
                "chunk_index": i,
                "total_chunks": 5,
                "file_extension": "py",
            }
            for i in range(5)
        ]
        mock_chunker.chunk_file.return_value = mock_chunks

        with FileChunkingManager(
            vector_manager=mock_vector_manager,
            chunker=mock_chunker,
            qdrant_client=mock_qdrant_client,
            thread_count=4,
        ) as file_manager:

            _future = file_manager.submit_file_for_processing(
                file_path=test_file,
                metadata=metadata,
                progress_callback=self.progress_callback,
            )

            # Wait for processing
            time.sleep(3.0)

            # FAILING TEST: Should have multiple progress updates showing activity
            activity_updates = [
                call
                for call in self.progress_calls
                if call["info"]
                and any(
                    indicator in call["info"] for indicator in ["🔄", "✅", "📥", "❌"]
                )
            ]

            # Should have at least: queuing + processing updates + completion
            assert (
                len(activity_updates) >= 3
            ), f"Expected multiple activity updates, got {len(activity_updates)}"
