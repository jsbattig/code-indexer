"""
Integration tests for Progress Callback Enhancements (Story 03).

These tests use more realistic setups to test the actual progress callbacks
without complex mocking that interferes with file system operations.
"""

import threading
import time
from pathlib import Path
from unittest.mock import Mock
import tempfile
import os


class TestProgressCallbackIntegration:
    """Integration tests for progress callback enhancements with real file operations."""

    def setup_method(self):
        """Set up test fixtures."""
        # Progress callback capture
        self.progress_calls = []
        self.progress_lock = threading.Lock()

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

    def test_error_reporting_with_no_chunks(self):
        """
        Test error reporting when no chunks are generated.

        This should trigger the "❌ Failed file.py - No chunks generated" callback.
        """
        from src.code_indexer.services.file_chunking_manager import FileChunkingManager
        from src.code_indexer.services.vector_calculation_manager import (
            VectorCalculationManager,
        )

        # Create a temporary empty file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as temp_file:
            temp_file.write("")  # Empty file
            temp_path = Path(temp_file.name)

        try:
            mock_vector_manager = Mock(spec=VectorCalculationManager)
            mock_chunker = Mock()
            mock_qdrant_client = Mock()

            # Mock chunker to return empty chunks (simulating error condition)
            mock_chunker.chunk_file.return_value = []

            metadata = {"project_id": "test", "file_hash": "error123"}

            with FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            ) as file_manager:

                future = file_manager.submit_file_for_processing(
                    file_path=temp_path,
                    metadata=metadata,
                    progress_callback=self.progress_callback,
                )

                # Wait for processing
                result = future.result(timeout=2.0)

                # Verify error result
                assert not result.success
                assert "No chunks generated" in result.error

                # Verify error callback was made
                error_calls = [
                    call
                    for call in self.progress_calls
                    if call["info"]
                    and "❌ Failed" in call["info"]
                    and "No chunks generated" in call["info"]
                ]

                assert (
                    len(error_calls) > 0
                ), "Expected error callback for no chunks generated"

                error_call = error_calls[0]
                assert (
                    error_call["current"] == 0
                ), "Expected current=0 for error message"
                assert error_call["total"] == 0, "Expected total=0 for error message"
                assert (
                    error_call["file_path"] == temp_path
                ), f"Expected file_path={temp_path}"

        finally:
            # Clean up
            os.unlink(temp_path)

    def test_immediate_queuing_feedback_timing(self):
        """
        Test that immediate queuing feedback is provided quickly.
        """
        from src.code_indexer.services.file_chunking_manager import FileChunkingManager
        from src.code_indexer.services.vector_calculation_manager import (
            VectorCalculationManager,
        )

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as temp_file:
            temp_file.write("print('hello')")
            temp_path = Path(temp_file.name)

        try:
            mock_vector_manager = Mock(spec=VectorCalculationManager)
            mock_chunker = Mock()
            mock_qdrant_client = Mock()

            metadata = {"project_id": "test", "file_hash": "timing123"}

            start_time = time.time()

            with FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            ) as file_manager:

                file_manager.submit_file_for_processing(
                    file_path=temp_path,
                    metadata=metadata,
                    progress_callback=self.progress_callback,
                )

                # Check immediate feedback
                time.sleep(0.05)  # Small delay to allow callback

                # Verify queuing callback was made immediately
                queuing_calls = [
                    call
                    for call in self.progress_calls
                    if call["info"] and "📥 Queued for processing" in call["info"]
                ]

                assert len(queuing_calls) > 0, "Expected immediate queuing callback"

                queuing_call = queuing_calls[0]
                feedback_delay = (queuing_call["timestamp"] - start_time) * 1000  # ms

                # Verify callback timing (should be very fast)
                assert (
                    feedback_delay < 100
                ), f"Queuing feedback took {feedback_delay:.1f}ms, expected < 100ms"
                assert (
                    queuing_call["current"] == 0
                ), "Expected current=0 for setup message"
                assert queuing_call["total"] == 0, "Expected total=0 for setup message"

        finally:
            # Clean up
            os.unlink(temp_path)

    def test_progress_callback_cli_patterns(self):
        """
        Test that progress callbacks follow CLI integration patterns.
        """
        from src.code_indexer.services.file_chunking_manager import FileChunkingManager
        from src.code_indexer.services.vector_calculation_manager import (
            VectorCalculationManager,
        )

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as temp_file:
            temp_file.write("print('hello')")
            temp_path = Path(temp_file.name)

        try:
            mock_vector_manager = Mock(spec=VectorCalculationManager)
            mock_chunker = Mock()
            mock_qdrant_client = Mock()

            # Mock chunker to return no chunks (triggering error path)
            mock_chunker.chunk_file.return_value = []

            metadata = {"project_id": "test", "file_hash": "cli123"}

            with FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            ) as file_manager:

                future = file_manager.submit_file_for_processing(
                    file_path=temp_path,
                    metadata=metadata,
                    progress_callback=self.progress_callback,
                )

                # Wait for processing
                future.result(timeout=2.0)

                # Verify CLI patterns in all callbacks
                for call in self.progress_calls:
                    if call["total"] == 0:
                        # Setup messages must have info
                        assert (
                            call["info"] is not None
                        ), "Setup messages must have info text"
                        assert (
                            call["current"] == 0
                        ), "Setup messages must have current=0"

                    if call["total"] > 0:
                        # Progress bar messages
                        assert (
                            call["current"] <= call["total"]
                        ), "Current must not exceed total"
                        assert (
                            call["info"] is not None
                        ), "Progress bar calls must have info"

        finally:
            # Clean up
            os.unlink(temp_path)

    def test_enhanced_feedback_user_experience(self):
        """
        Test that the enhanced system provides continuous feedback for good user experience.
        """
        from src.code_indexer.services.file_chunking_manager import FileChunkingManager
        from src.code_indexer.services.vector_calculation_manager import (
            VectorCalculationManager,
        )

        # Create a temporary test file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as temp_file:
            temp_file.write("print('hello world')")
            temp_path = Path(temp_file.name)

        try:
            mock_vector_manager = Mock(spec=VectorCalculationManager)
            mock_chunker = Mock()
            mock_qdrant_client = Mock()

            # Mock chunker to return no chunks (quick error path)
            mock_chunker.chunk_file.return_value = []

            metadata = {"project_id": "test", "file_hash": "ux123"}

            with FileChunkingManager(
                vector_manager=mock_vector_manager,
                chunker=mock_chunker,
                qdrant_client=mock_qdrant_client,
                thread_count=2,
            ) as file_manager:

                future = file_manager.submit_file_for_processing(
                    file_path=temp_path,
                    metadata=metadata,
                    progress_callback=self.progress_callback,
                )

                # Wait for processing
                future.result(timeout=2.0)

                # Verify multiple feedback stages
                activity_indicators = [
                    "📥",  # Queued for processing
                    "❌",  # Failed (error)
                ]

                found_indicators = []
                for call in self.progress_calls:
                    if call["info"]:
                        for indicator in activity_indicators:
                            if indicator in call["info"]:
                                found_indicators.append(indicator)

                # Should have at least queuing and error feedback
                assert (
                    len(found_indicators) >= 2
                ), f"Expected multiple feedback stages, got {found_indicators}"
                assert "📥" in found_indicators, "Expected queuing feedback"
                assert "❌" in found_indicators, "Expected error feedback"

        finally:
            # Clean up
            os.unlink(temp_path)
