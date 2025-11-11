"""Tests for worker thread exception handling in temporal indexer.

Requirement: Worker thread exceptions must:
1. Log errors at ERROR level (not DEBUG/INFO)
2. Include commit hash in error message
3. Propagate exceptions (not swallow them)
4. Include full stack trace in logs

Bug: The worker currently has try/finally but NO except block, so when
upsert_points() fails (e.g., missing projection_matrix.npy), the exception
is caught by ThreadPoolExecutor and never logged.
"""

import logging
import threading
from pathlib import Path
from queue import Queue
from unittest.mock import Mock, patch, MagicMock, call
import pytest

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestWorkerExceptionHandling:
    """Test worker thread exception handling."""

    def setup_method(self):
        """Set up test fixtures."""
        import tempfile

        # Create mock config manager and config
        self.config_manager = Mock()
        self.config = Mock()
        self.config.voyage_ai.parallel_requests = 2
        self.config.voyage_ai.max_concurrent_batches_per_commit = 10
        self.config.embedding_provider = "voyage-ai"
        self.config.voyage_ai.model = "voyage-code-3"
        self.config_manager.get_config.return_value = self.config

        # Use temporary directory for test
        self.temp_dir = tempfile.mkdtemp()

        # Create mock vector store
        self.vector_store = Mock()
        self.vector_store.project_root = Path(self.temp_dir)
        self.vector_store.base_path = Path(self.temp_dir) / ".code-indexer/index"
        self.vector_store.collection_exists.return_value = True
        self.vector_store.load_id_index.return_value = set()  # Return empty set

        # Create temporal indexer with mocks
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
        ) as mock_get_info:
            mock_get_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-3",
                "dimensions": 1024,
            }
            self.indexer = TemporalIndexer(self.config_manager, self.vector_store)

        # Real commit for testing
        self.test_commit = CommitInfo(
            hash="abc1234567890",
            timestamp=1234567890,
            message="Test commit",
            author_name="Test Author",
            author_email="test@example.com",
            parent_hashes="",
        )

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_worker_logs_upsert_failure_at_error_level(self):
        """Test 1: Verify worker logs upsert failures at ERROR level with stack trace.

        When upsert_points() raises RuntimeError, verify:
        - logger.error() is called (not logger.debug or logger.info)
        - Error message includes commit hash
        - exc_info=True is passed to include full stack trace
        """
        # Mock diff scanner to return one diff
        self.indexer.diff_scanner.get_diffs_for_commit = Mock(
            return_value=[
                Mock(
                    file_path="test.py",
                    diff_content="test content",
                    diff_type="modified",
                    blob_hash="blob123",
                    parent_commit_hash=None,
                )
            ]
        )

        # Mock chunker to return chunks
        self.indexer.chunker = Mock()
        self.indexer.chunker.chunk_text = Mock(
            return_value=[
                {
                    "text": "test chunk",
                    "char_start": 0,
                    "char_end": 10,
                }
            ]
        )

        # Mock vector manager to return embeddings
        mock_vector_manager = Mock()
        mock_future = Mock()
        mock_future.result.return_value = Mock(embeddings=[[0.1] * 1024], error=None)
        mock_vector_manager.submit_batch_task.return_value = mock_future
        mock_vector_manager.cancellation_event.is_set.return_value = False
        mock_vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

        # Mock upsert_points to raise RuntimeError
        self.vector_store.upsert_points.side_effect = RuntimeError(
            "projection matrix missing"
        )

        # Mock progressive metadata
        self.indexer.progressive_metadata = Mock()

        # Mock logger to capture calls
        with patch(
            "src.code_indexer.services.temporal.temporal_indexer.logger"
        ) as mock_logger:
            # Mock _count_tokens to avoid import
            self.indexer._count_tokens = Mock(return_value=100)

            # Call _process_commits_parallel with one commit - should propagate exception
            with pytest.raises(RuntimeError, match="projection matrix missing"):
                self.indexer._process_commits_parallel(
                    commits=[self.test_commit],
                    embedding_provider=Mock(),
                    vector_manager=mock_vector_manager,
                    progress_callback=None,
                )

            # Verify logger.error() was called with commit hash and exc_info=True
            # Should be called with message containing commit hash and exc_info=True
            error_calls = [
                call
                for call in mock_logger.error.call_args_list
                if "abc1234" in str(call) or "CRITICAL" in str(call)
            ]

            assert len(error_calls) > 0, "Expected logger.error() to be called"

            # Check that at least one error call has exc_info=True
            exc_info_found = any(
                call.kwargs.get("exc_info") is True for call in error_calls
            )
            assert exc_info_found, "Expected exc_info=True in logger.error() call"

            # Verify commit hash is in error message
            commit_hash_found = any("abc1234" in str(call) for call in error_calls)
            assert commit_hash_found, "Expected commit hash in error message"

    def test_worker_propagates_exception_to_caller(self):
        """Test 2: Verify worker propagates exceptions instead of swallowing them.

        When vector_store.upsert_points() raises ValueError, verify:
        - Exception propagates to caller (not swallowed)
        - Original exception type and message are preserved
        """
        # Mock diff scanner to return one diff
        self.indexer.diff_scanner.get_diffs_for_commit = Mock(
            return_value=[
                Mock(
                    file_path="test.py",
                    diff_content="test content",
                    diff_type="modified",
                    blob_hash="blob123",
                    parent_commit_hash=None,
                )
            ]
        )

        # Mock chunker to return chunks
        self.indexer.chunker = Mock()
        self.indexer.chunker.chunk_text = Mock(
            return_value=[
                {
                    "text": "test chunk",
                    "char_start": 0,
                    "char_end": 10,
                }
            ]
        )

        # Mock vector manager to return embeddings
        mock_vector_manager = Mock()
        mock_future = Mock()
        mock_future.result.return_value = Mock(embeddings=[[0.1] * 1024], error=None)
        mock_vector_manager.submit_batch_task.return_value = mock_future
        mock_vector_manager.cancellation_event.is_set.return_value = False
        mock_vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

        # Mock upsert_points to raise ValueError
        self.vector_store.upsert_points.side_effect = ValueError("test error")

        # Mock progressive metadata
        self.indexer.progressive_metadata = Mock()

        # Mock _count_tokens to avoid import
        self.indexer._count_tokens = Mock(return_value=100)

        # Call _process_commits_parallel - should propagate the ValueError
        with pytest.raises(ValueError, match="test error"):
            self.indexer._process_commits_parallel(
                commits=[self.test_commit],
                embedding_provider=Mock(),
                vector_manager=mock_vector_manager,
                progress_callback=None,
            )

    def test_worker_releases_slot_even_on_failure(self):
        """Test 3: Verify worker releases slot even when upsert fails.

        When upsert_points() raises exception, verify:
        - commit_slot_tracker.release_slot() is still called
        - Slot ID is released exactly once
        - Finally block works correctly
        """
        # Mock diff scanner to return one diff
        self.indexer.diff_scanner.get_diffs_for_commit = Mock(
            return_value=[
                Mock(
                    file_path="test.py",
                    diff_content="test content",
                    diff_type="modified",
                    blob_hash="blob123",
                    parent_commit_hash=None,
                )
            ]
        )

        # Mock chunker to return chunks
        self.indexer.chunker = Mock()
        self.indexer.chunker.chunk_text = Mock(
            return_value=[
                {
                    "text": "test chunk",
                    "char_start": 0,
                    "char_end": 10,
                }
            ]
        )

        # Mock vector manager to return embeddings
        mock_vector_manager = Mock()
        mock_future = Mock()
        mock_future.result.return_value = Mock(embeddings=[[0.1] * 1024], error=None)
        mock_vector_manager.submit_batch_task.return_value = mock_future
        mock_vector_manager.cancellation_event.is_set.return_value = False
        mock_vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

        # Mock upsert_points to raise exception
        self.vector_store.upsert_points.side_effect = RuntimeError("test failure")

        # Mock progressive metadata
        self.indexer.progressive_metadata = Mock()

        # Mock _count_tokens to avoid import
        self.indexer._count_tokens = Mock(return_value=100)

        # Track slot operations by mocking CleanSlotTracker
        mock_slot_tracker = Mock()
        slot_id_captured = None

        def capture_slot_id(file_data):
            nonlocal slot_id_captured
            slot_id_captured = "slot-123"
            return slot_id_captured

        mock_slot_tracker.acquire_slot.side_effect = capture_slot_id

        # Mock get_concurrent_files_data to avoid errors
        mock_slot_tracker.get_concurrent_files_data.return_value = []

        # Patch CleanSlotTracker constructor to return our mock
        # It's imported inside _process_commits_parallel from ..clean_slot_tracker
        with patch(
            "src.code_indexer.services.clean_slot_tracker.CleanSlotTracker",
            return_value=mock_slot_tracker,
        ):
            # Call _process_commits_parallel - should raise but still release slot
            with pytest.raises(RuntimeError, match="test failure"):
                self.indexer._process_commits_parallel(
                    commits=[self.test_commit],
                    embedding_provider=Mock(),
                    vector_manager=mock_vector_manager,
                    progress_callback=None,
                )

        # Verify slot was acquired
        assert (
            mock_slot_tracker.acquire_slot.called
        ), "Expected acquire_slot to be called"

        # Verify slot was released exactly once (in finally block)
        assert (
            mock_slot_tracker.release_slot.call_count == 1
        ), f"Expected release_slot to be called once, got {mock_slot_tracker.release_slot.call_count}"

        # Verify correct slot ID was released
        if slot_id_captured:
            mock_slot_tracker.release_slot.assert_called_with(slot_id_captured)

    def test_worker_includes_commit_hash_in_error_message(self):
        """Test 4: Verify worker includes commit hash in error message.

        When upsert fails, verify:
        - Error message contains commit.hash[:7] (short hash)
        - Error message is descriptive and actionable
        """
        # Mock diff scanner to return one diff
        self.indexer.diff_scanner.get_diffs_for_commit = Mock(
            return_value=[
                Mock(
                    file_path="test.py",
                    diff_content="test content",
                    diff_type="modified",
                    blob_hash="blob123",
                    parent_commit_hash=None,
                )
            ]
        )

        # Mock chunker to return chunks
        self.indexer.chunker = Mock()
        self.indexer.chunker.chunk_text = Mock(
            return_value=[
                {
                    "text": "test chunk",
                    "char_start": 0,
                    "char_end": 10,
                }
            ]
        )

        # Mock vector manager to return embeddings
        mock_vector_manager = Mock()
        mock_future = Mock()
        mock_future.result.return_value = Mock(embeddings=[[0.1] * 1024], error=None)
        mock_vector_manager.submit_batch_task.return_value = mock_future
        mock_vector_manager.cancellation_event.is_set.return_value = False
        mock_vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

        # Mock upsert_points to raise exception
        self.vector_store.upsert_points.side_effect = RuntimeError("storage failure")

        # Mock progressive metadata
        self.indexer.progressive_metadata = Mock()

        # Mock _count_tokens to avoid import
        self.indexer._count_tokens = Mock(return_value=100)

        # Mock logger to capture error message
        with patch(
            "src.code_indexer.services.temporal.temporal_indexer.logger"
        ) as mock_logger:
            # Call _process_commits_parallel - should propagate exception
            with pytest.raises(RuntimeError, match="storage failure"):
                self.indexer._process_commits_parallel(
                    commits=[self.test_commit],
                    embedding_provider=Mock(),
                    vector_manager=mock_vector_manager,
                    progress_callback=None,
                )

            # Extract all error call arguments
            error_messages = []
            for call_obj in mock_logger.error.call_args_list:
                # Get the first positional argument (the message)
                if call_obj.args:
                    error_messages.append(str(call_obj.args[0]))

            # Verify at least one error message contains the commit hash
            commit_hash_short = self.test_commit.hash[:7]  # "abc1234"
            assert any(
                commit_hash_short in msg for msg in error_messages
            ), f"Expected commit hash '{commit_hash_short}' in error messages: {error_messages}"

            # Verify error message is descriptive (contains "CRITICAL" or "Failed")
            assert any(
                "CRITICAL" in msg or "Failed" in msg for msg in error_messages
            ), f"Expected descriptive error message: {error_messages}"
