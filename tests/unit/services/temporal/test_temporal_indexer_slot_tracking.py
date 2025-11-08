"""Unit tests for temporal indexer slot-based progress tracking.

Tests the refactored temporal indexing that uses CleanSlotTracker infrastructure
for progress reporting, matching the exact pattern used by file hashing/indexing.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker


class TestTemporalIndexerSlotTracking:
    """Test temporal indexer with CleanSlotTracker-based progress reporting."""

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager."""
        config_manager = MagicMock()
        config = MagicMock()
        config.voyage_ai.parallel_requests = 4  # Test with 4 threads
        config_manager.get_config.return_value = config
        return config_manager

    @pytest.fixture
    def mock_vector_store(self, tmp_path):
        """Create a mock vector store."""
        vector_store = MagicMock()
        vector_store.project_root = tmp_path
        vector_store.collection_exists.return_value = True
        return vector_store

    @pytest.fixture
    def indexer(self, mock_config_manager, mock_vector_store):
        """Create a temporal indexer instance."""
        with patch.object(TemporalIndexer, '_ensure_temporal_collection'):
            indexer = TemporalIndexer(mock_config_manager, mock_vector_store)
            return indexer

    def test_slot_tracker_initialization(self, indexer):
        """Test that slot tracker is initialized correctly in _process_commits_parallel."""
        # Mock commits
        commits = [
            CommitInfo(
                hash="abc12345",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit",
                parent_hashes=""
            )
        ]

        # Mock dependencies
        mock_embedding_provider = MagicMock()
        mock_vector_manager = MagicMock()

        # Mock diff scanner to return no diffs (simpler test)
        indexer.diff_scanner.get_diffs_for_commit = MagicMock(return_value=[])

        progress_callback = MagicMock()

        # Run the method
        indexer._process_commits_parallel(
            commits, mock_embedding_provider, mock_vector_manager, progress_callback
        )

        # Verify progress callback was called with slot_tracker
        assert progress_callback.called
        # Check for initialization call
        init_call = progress_callback.call_args_list[0]
        assert 'slot_tracker' in init_call.kwargs
        assert isinstance(init_call.kwargs['slot_tracker'], CleanSlotTracker)
        assert init_call.kwargs['slot_tracker'].max_slots == 4  # thread_count

    def test_slot_tracker_filename_format(self, indexer):
        """Test that FileData.filename follows the correct format: '{commit_hash[:8]} - {filename}'."""
        commits = [
            CommitInfo(
                hash="abc1234567890def",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit",
                parent_hashes=""
            )
        ]

        # Mock dependencies
        mock_embedding_provider = MagicMock()
        mock_vector_manager = MagicMock()

        # Track slot operations
        slot_operations = []

        # Create a custom mock for diff scanner
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        diffs = [
            DiffInfo(
                file_path="src/auth.py",
                diff_type="modified",
                commit_hash="abc1234567890def",
                diff_content="+ added line\n- removed line"
            ),
            DiffInfo(
                file_path="tests/test_auth.py",
                diff_type="modified",
                commit_hash="abc1234567890def",
                diff_content="+ test added"
            )
        ]
        indexer.diff_scanner.get_diffs_for_commit = MagicMock(return_value=diffs)

        # Mock chunker to return chunks
        indexer.chunker.chunk_text = MagicMock(return_value=[
            {"text": "chunk1", "char_start": 0, "char_end": 10}
        ])

        # Mock vector manager
        future = MagicMock()
        future.result.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_vector_manager.submit_batch_task.return_value = future

        # Patch CleanSlotTracker to intercept operations
        original_acquire = CleanSlotTracker.acquire_slot
        original_update = CleanSlotTracker.update_slot

        def track_acquire(self, file_data):
            slot_operations.append(('acquire', file_data.filename, file_data.status))
            return original_acquire(self, file_data)

        def track_update(self, slot_id, status):
            # Also track filename updates
            if hasattr(self, 'status_array') and self.status_array[slot_id]:
                slot_operations.append(('update', self.status_array[slot_id].filename, status))
            return original_update(self, slot_id, status)

        with patch.object(CleanSlotTracker, 'acquire_slot', track_acquire):
            with patch.object(CleanSlotTracker, 'update_slot', track_update):
                progress_callback = MagicMock()

                indexer._process_commits_parallel(
                    commits, mock_embedding_provider, mock_vector_manager, progress_callback
                )

        # Verify filename formats in slot operations
        # Should see "abc12345 - auth.py" at start
        assert any("abc12345 - auth.py" in op[1] for op in slot_operations if op[0] == 'acquire')

        # Should see file-specific names during processing
        assert any("abc12345 - auth.py" in op[1] for op in slot_operations)
        # Note: test_auth.py might not appear in single-threaded test since slot tracking
        # shows the file being processed at the time of the update

    def test_concurrent_files_and_slot_release(self, indexer):
        """Test concurrent_files snapshot and slot release functionality."""
        commits = [
            CommitInfo(
                hash="test123456789abc",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit",
                parent_hashes=""
            )
        ]

        # Mock dependencies
        mock_embedding_provider = MagicMock()
        mock_vector_manager = MagicMock()

        # Mock diffs
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        diffs = [
            DiffInfo(
                file_path="src/module.py",
                diff_type="modified",
                commit_hash="test123456789abc",
                diff_content="+ changes"
            )
        ]
        indexer.diff_scanner.get_diffs_for_commit = MagicMock(return_value=diffs)

        # Mock chunker and vector manager
        indexer.chunker.chunk_text = MagicMock(return_value=[
            {"text": "chunk", "char_start": 0, "char_end": 5}
        ])
        future = MagicMock()
        future.result.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_vector_manager.submit_batch_task.return_value = future

        progress_callback = MagicMock()

        indexer._process_commits_parallel(
            commits, mock_embedding_provider, mock_vector_manager, progress_callback
        )

        # Find progress calls with concurrent_files
        progress_calls_with_concurrent = [
            call for call in progress_callback.call_args_list
            if 'concurrent_files' in call.kwargs
        ]

        assert len(progress_calls_with_concurrent) > 0

        # Verify concurrent_files is a deep copy (list of dicts)
        for call in progress_calls_with_concurrent:
            concurrent_files = call.kwargs['concurrent_files']
            assert isinstance(concurrent_files, list)
            if concurrent_files:  # If not empty
                assert all(isinstance(item, dict) for item in concurrent_files)
                # Check expected keys
                for item in concurrent_files:
                    assert 'slot_id' in item
                    assert 'file_path' in item
                    assert 'status' in item

    def test_slot_release_on_completion(self, indexer):
        """Test that slots are properly released after commit processing."""
        commits = [
            CommitInfo(
                hash="release123456789",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test release",
                parent_hashes=""
            )
        ]

        # Mock dependencies
        mock_embedding_provider = MagicMock()
        mock_vector_manager = MagicMock()

        # Track slot operations
        slot_acquisitions = []
        slot_releases = []

        # Mock diffs
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        diffs = [
            DiffInfo(
                file_path="test.py",
                diff_type="modified",
                commit_hash="release123456789",
                diff_content="+ test"
            )
        ]
        indexer.diff_scanner.get_diffs_for_commit = MagicMock(return_value=diffs)

        # Mock chunker and vector manager
        indexer.chunker.chunk_text = MagicMock(return_value=[
            {"text": "chunk", "char_start": 0, "char_end": 5}
        ])
        future = MagicMock()
        future.result.return_value = MagicMock(embeddings=[[0.1] * 1024])
        mock_vector_manager.submit_batch_task.return_value = future

        # Patch slot tracker methods
        original_acquire = CleanSlotTracker.acquire_slot
        original_release = CleanSlotTracker.release_slot

        def track_acquire(self, file_data):
            slot_id = original_acquire(self, file_data)
            slot_acquisitions.append(slot_id)
            return slot_id

        def track_release(self, slot_id):
            slot_releases.append(slot_id)
            return original_release(self, slot_id)

        with patch.object(CleanSlotTracker, 'acquire_slot', track_acquire):
            with patch.object(CleanSlotTracker, 'release_slot', track_release):
                progress_callback = MagicMock()

                indexer._process_commits_parallel(
                    commits, mock_embedding_provider, mock_vector_manager, progress_callback
                )

        # Verify slots were acquired and released
        assert len(slot_acquisitions) > 0
        assert len(slot_releases) > 0

        # Each acquired slot should be released
        for slot_id in slot_acquisitions:
            assert slot_id in slot_releases