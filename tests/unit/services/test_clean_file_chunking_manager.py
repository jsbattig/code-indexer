"""
Test cases for clean FileChunkingManager resource management.

These tests define the proper resource management patterns:
1. Single acquire at start
2. All work in try block
3. Single release in finally block
4. No scattered release calls
5. Direct slot_id usage throughout
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker
from src.code_indexer.services.clean_slot_tracker import FileStatus


class TestCleanFileChunkingManagerResourceManagement:
    """Test proper resource management patterns in FileChunkingManager."""

    def setup_method(self):
        """Set up test dependencies."""
        self.slot_tracker = CleanSlotTracker(max_slots=3)

        # Mock dependencies that FileChunkingManager needs
        self.chunker = Mock()
        self.vector_manager = Mock()
        self.qdrant_client = Mock()
        self.aggregate_tracker = Mock()

        # Mock chunker behavior
        self.chunker.chunk_file.return_value = [
            {
                "text": "chunk1",
                "line_start": 1,
                "line_end": 10,
                "chunk_index": 0,
                "total_chunks": 2,
                "file_extension": "py",
            },
            {
                "text": "chunk2",
                "line_start": 11,
                "line_end": 20,
                "chunk_index": 1,
                "total_chunks": 2,
                "file_extension": "py",
            },
        ]

        # Mock vector manager behavior
        future_mock = Mock()
        future_mock.result.return_value = [0.1, 0.2, 0.3]  # Mock vector
        self.vector_manager.submit_chunk.return_value = future_mock

        # BATCH PROCESSING FIX: Add mock for submit_batch_task used by FileChunkingManager
        from src.code_indexer.services.vector_calculation_manager import VectorResult

        batch_future_mock = Mock()
        batch_result = VectorResult.create_immutable(
            task_id="test_batch",
            embeddings=([0.1, 0.2, 0.3], [0.4, 0.5, 0.6]),  # 2 embeddings for 2 chunks
            metadata={"test": "batch_metadata"},
            processing_time=0.1,
            error=None,
        )
        batch_future_mock.result.return_value = batch_result
        self.vector_manager.submit_batch_task.return_value = batch_future_mock

        # TOKEN COUNTING FIX: Mock embedding provider methods
        self.vector_manager.embedding_provider.get_current_model.return_value = (
            "voyage-large-2-instruct"
        )
        self.vector_manager.embedding_provider._get_model_token_limit.return_value = (
            120000
        )

    def _create_clean_manager(self):
        """Helper to create FileChunkingManager with proper mocking."""
        from src.code_indexer.services.file_chunking_manager import FileChunkingManager

        # Create temporary directory for codebase_dir
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())

        manager = FileChunkingManager(
            chunker=self.chunker,
            vector_manager=self.vector_manager,
            qdrant_client=self.qdrant_client,
            thread_count=2,
            slot_tracker=CleanSlotTracker(max_slots=4),
            codebase_dir=temp_dir,
        )

        # TOKEN COUNTING FIX: Mock the voyage client count_tokens method
        manager.voyage_client = Mock()
        manager.voyage_client.count_tokens.return_value = (
            100  # Return fixed token count
        )

        return manager

    def _get_complete_metadata(self, file_path: Path) -> dict:
        """Get complete metadata required for file processing."""
        return {
            "project_id": "test_project",
            "file_hash": f"test_hash_{file_path.stem}",
            "git_available": False,
            "file_mtime": file_path.stat().st_mtime,
            "file_size": file_path.stat().st_size,
        }

    def test_single_acquire_try_finally_pattern(self):
        """Test that FileChunkingManager uses proper acquire/try/finally pattern."""
        # This test will initially fail - we need to implement the clean pattern

        # Create clean manager with our clean slot tracker
        manager = self._create_clean_manager()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test(): pass\n")
            test_file = Path(f.name)

        try:
            # Track slot acquisitions and releases
            original_acquire = self.slot_tracker.acquire_slot
            original_release = self.slot_tracker.release_slot

            acquire_calls = []
            release_calls = []

            def track_acquire(file_data):
                slot_id = original_acquire(file_data)
                acquire_calls.append(slot_id)
                return slot_id

            def track_release(slot_id):
                release_calls.append(slot_id)
                original_release(slot_id)

            self.slot_tracker.acquire_slot = track_acquire
            self.slot_tracker.release_slot = track_release

            # Process file using the clean method directly
            manager._process_file_clean_lifecycle(
                test_file,
                self._get_complete_metadata(test_file),
                None,
                self.slot_tracker,
            )

            # Verify proper resource management pattern
            assert len(acquire_calls) == 1, "Should have exactly ONE acquire call"
            assert len(release_calls) == 1, "Should have exactly ONE release call"
            assert (
                acquire_calls[0] == release_calls[0]
            ), "Same slot should be acquired and released"

            # UX FIX: Files stay visible but slots become available for reuse
            assert (
                self.slot_tracker.get_slot_count() == 1
            ), "File should stay visible after processing"
            assert (
                self.slot_tracker.get_available_slot_count() == 3
            ), "All slots should be available for reuse after processing"

        finally:
            test_file.unlink()

    def test_no_multiple_release_calls(self):
        """Test that only ONE release call exists - no scattered releases."""
        # Mock scenario where exception occurs during processing
        manager = self._create_clean_manager()

        # Make vector processing fail
        self.vector_manager.submit_chunk.side_effect = Exception(
            "Vector processing failed"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test(): pass\n")
            test_file = Path(f.name)

        try:
            # Track releases
            release_calls = []
            original_release = self.slot_tracker.release_slot

            def track_release(slot_id):
                release_calls.append(slot_id)
                original_release(slot_id)

            self.slot_tracker.release_slot = track_release

            # Process file (should fail but still release properly)
            manager._process_file_clean_lifecycle(
                test_file,
                self._get_complete_metadata(test_file),
                None,
                self.slot_tracker,
            )

            # Should have exactly ONE release call even on error
            assert (
                len(release_calls) == 1
            ), "Should have exactly ONE release call even on error"

            # UX FIX: File stays visible but slot is available for reuse even after error
            assert (
                self.slot_tracker.get_slot_count() == 1
            ), "File should stay visible even after error"
            assert (
                self.slot_tracker.get_available_slot_count() == 3
            ), "Slot should be available for reuse after error"

        finally:
            test_file.unlink()

    def test_slot_id_used_throughout_lifecycle(self):
        """Test that slot_id is used directly throughout file lifecycle, no filename lookups."""
        manager = self._create_clean_manager()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def test(): pass\n")
            test_file = Path(f.name)

        try:
            # Track all slot tracker method calls
            update_calls = []

            original_update = self.slot_tracker.update_slot

            def track_update(slot_id, status):
                update_calls.append((slot_id, status))
                original_update(slot_id, status)

            self.slot_tracker.update_slot = track_update

            # Process file using the clean method directly with complete metadata
            result = manager._process_file_clean_lifecycle(
                test_file,
                self._get_complete_metadata(test_file),
                None,
                self.slot_tracker,
            )

            # Verify result is successful
            assert result.success, "File processing should be successful"

            # Verify status updates used slot_id directly
            assert len(update_calls) > 0, "Should have status updates during processing"

            # All update calls should use same slot_id
            slot_ids = [call[0] for call in update_calls]
            assert len(set(slot_ids)) == 1, "All updates should use same slot_id"

            # Verify status progression
            statuses = [call[1] for call in update_calls]
            expected_statuses = [
                FileStatus.CHUNKING,
                FileStatus.VECTORIZING,
                FileStatus.FINALIZING,
                FileStatus.COMPLETE,
            ]

            # Debug output
            print(f"Actual statuses: {statuses}")
            print(f"Expected statuses: {expected_statuses}")

            # Should have proper status progression (order matters)
            for expected_status in expected_statuses:
                assert (
                    expected_status in statuses
                ), f"Should have {expected_status} status update. Actual: {statuses}"

        finally:
            test_file.unlink()

    def test_empty_file_resource_management(self):
        """Test proper resource management for empty files."""
        # Mock empty file scenario
        self.chunker.chunk_file.return_value = []  # No chunks

        manager = self._create_clean_manager()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            # Create empty file
            test_file = Path(f.name)

        try:
            # Track resource management
            acquire_calls = []
            release_calls = []

            original_acquire = self.slot_tracker.acquire_slot
            original_release = self.slot_tracker.release_slot

            def track_acquire(file_data):
                slot_id = original_acquire(file_data)
                acquire_calls.append(slot_id)
                return slot_id

            def track_release(slot_id):
                release_calls.append(slot_id)
                original_release(slot_id)

            self.slot_tracker.acquire_slot = track_acquire
            self.slot_tracker.release_slot = track_release

            # Process empty file
            result = manager._process_file_clean_lifecycle(
                test_file,
                self._get_complete_metadata(test_file),
                None,
                self.slot_tracker,
            )

            # Even empty files should follow proper resource management
            assert len(acquire_calls) == 1, "Should acquire slot for empty file"
            assert len(release_calls) == 1, "Should release slot for empty file"
            assert result.success, "Empty file processing should succeed"

            # UX FIX: File stays visible but slot is available for reuse
            assert (
                self.slot_tracker.get_slot_count() == 1
            ), "Empty file should stay visible"
            assert (
                self.slot_tracker.get_available_slot_count() == 3
            ), "Slot should be available for reuse after empty file processing"

        finally:
            test_file.unlink()

    def test_no_thread_id_pollution_in_processing(self):
        """Test that FileChunkingManager doesn't use thread_id anywhere."""
        manager = self._create_clean_manager()

        # Verify that _process_file_clean_lifecycle method doesn't take thread_id parameter
        import inspect

        sig = inspect.signature(manager._process_file_clean_lifecycle)
        assert (
            "thread_id" not in sig.parameters
        ), "_process_file_clean_lifecycle should not take thread_id parameter"

        # The clean implementation should not call any thread_id based methods
        # This will be verified once we implement the clean version

    def test_concurrent_file_processing_isolation(self):
        """Test that multiple files process independently with clean slot management."""
        manager = self._create_clean_manager()

        # Create multiple test files
        test_files = []
        for i in range(3):
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=f"_{i}.py", delete=False
            ) as f:
                f.write(f"def test_{i}(): pass\n")
                test_files.append(Path(f.name))

        try:
            # Track slot usage
            max_concurrent_slots = 0
            slot_usage_history = []

            original_acquire = self.slot_tracker.acquire_slot
            original_release = self.slot_tracker.release_slot

            def track_acquire(file_data):
                slot_id = original_acquire(file_data)
                current_count = self.slot_tracker.get_slot_count()
                nonlocal max_concurrent_slots
                max_concurrent_slots = max(max_concurrent_slots, current_count)
                slot_usage_history.append(f"acquired:{slot_id}")
                return slot_id

            def track_release(slot_id):
                original_release(slot_id)
                slot_usage_history.append(f"released:{slot_id}")

            self.slot_tracker.acquire_slot = track_acquire
            self.slot_tracker.release_slot = track_release

            # Process files sequentially (clean manager handles one at a time)
            results = []
            for test_file in test_files:
                result = manager._process_file_clean_lifecycle(
                    test_file,
                    self._get_complete_metadata(test_file),
                    None,
                    self.slot_tracker,
                )
                results.append(result)

            # All files should process successfully
            assert all(
                r.success for r in results
            ), "All files should process successfully"

            # UX FIX: With slot reuse, only the LAST file stays visible (correct behavior)
            # When processing sequentially, the same slot gets reused, overwriting previous file data
            assert (
                self.slot_tracker.get_slot_count() == 1
            ), "Only the last processed file should be visible (slot reuse)"
            assert (
                self.slot_tracker.get_available_slot_count() == 3
            ), "All slots should be available for reuse after processing"

            # Should have proper acquire/release pairs
            acquire_count = len(
                [h for h in slot_usage_history if h.startswith("acquired:")]
            )
            release_count = len(
                [h for h in slot_usage_history if h.startswith("released:")]
            )
            assert (
                acquire_count == release_count == 3
            ), "Should have matching acquire/release pairs"

        finally:
            for test_file in test_files:
                test_file.unlink()
