"""
Test for the index resume routing logic bug.

This test reproduces the bug where _do_incremental_index() doesn't check for
interrupted operations before checking timestamps, causing interrupted operations
to restart from scratch instead of resuming.

Bug Scenario:
1. User starts indexing (cidx index)
2. User cancels with Ctrl+C (interrupts operation)
3. User runs cidx index again (without --reconcile)
4. BUG: System restarts from scratch instead of resuming

Root Cause:
_do_incremental_index() method goes straight to timestamp check without
checking for interrupted operations first.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_indexer.config import Config
from code_indexer.services.smart_indexer import SmartIndexer


@pytest.fixture
def temp_metadata_path():
    """Create a temporary metadata file path."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def mock_config():
    """Create a mock config for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = Mock(spec=Config)
        config.codebase_dir = Path(tmpdir)
        config.exclude_dirs = ["node_modules", ".git"]
        config.exclude_files = []
        config.file_extensions = ["py", "js", "ts"]

        # Mock the indexing sub-config
        indexing_config = Mock()
        indexing_config.chunk_size = 1000
        indexing_config.chunk_overlap = 100
        indexing_config.max_file_size = 1000000
        config.indexing = indexing_config

        # Mock qdrant config
        config.qdrant = Mock()
        config.qdrant.vector_size = 768

        yield config


@pytest.fixture
def mock_embedding_provider():
    """Create a mock embedding provider."""
    provider = Mock()
    provider.get_provider_name.return_value = "test-provider"
    provider.get_current_model.return_value = "test-model"
    provider.get_embedding.return_value = [0.1, 0.2, 0.3]
    return provider


@pytest.fixture
def mock_qdrant_client():
    """Create a mock Qdrant client."""
    client = Mock()
    client.ensure_provider_aware_collection.return_value = None
    return client


class TestIndexResumeRoutingLogicBug:
    """Test for the index resume routing logic bug in _do_incremental_index()."""

    def test_interrupted_operation_should_resume_not_restart(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test that interrupted operations correctly resume instead of restarting.

        This test verifies the fix for the bug where _do_incremental_index() didn't check
        for interrupted operations before checking timestamps.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # === PHASE 1: Setup interrupted operation state ===
        # Simulate an operation that was interrupted after processing some files
        metadata = indexer.progressive_metadata
        git_status = {
            "git_available": False,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Start indexing operation
        metadata.start_indexing("test-provider", "test-model", git_status)

        # Set up files to index (simulate large project)
        files_to_index = [
            Path("src/main.py"),
            Path("src/utils.py"),
            Path("src/config.py"),
            Path("tests/test_main.py"),
            Path("tests/test_utils.py"),
        ]
        metadata.set_files_to_index(files_to_index)

        # Process some files successfully before "interruption"
        metadata.mark_file_completed("src/main.py", chunks_count=10)
        metadata.mark_file_completed("src/utils.py", chunks_count=5)

        # Verify we have an interrupted operation that can be resumed
        assert metadata.can_resume_interrupted_operation() is True
        assert metadata.metadata["status"] == "in_progress"
        assert metadata.metadata["files_processed"] == 2
        assert len(metadata.get_remaining_files()) == 3

        # === PHASE 2: Mock dependencies for _do_incremental_index call ===
        # Mock _do_full_index to track if it gets called (this is the bug)
        with patch.object(indexer, "_do_full_index") as mock_full_index:
            # Mock _do_resume_interrupted to track if it gets called (this is correct)
            with patch.object(
                indexer, "_do_resume_interrupted"
            ) as mock_resume_interrupted:
                # Mock get_resume_timestamp to return 0.0 (this is why the bug occurs)
                # For interrupted operations, timestamp is 0.0, which triggers full index
                with patch.object(metadata, "get_resume_timestamp", return_value=0.0):
                    # Capture progress messages
                    progress_messages = []

                    def capture_progress(current, total, path, info=""):
                        progress_messages.append(info)

                    # === PHASE 3: Call _do_incremental_index (this triggers the bug) ===
                    # This should resume the interrupted operation, but due to the bug,
                    # it will call _do_full_index instead
                    indexer._do_incremental_index(
                        batch_size=10,
                        progress_callback=capture_progress,
                        git_status=git_status,
                        provider_name="test-provider",
                        model_name="test-model",
                        safety_buffer_seconds=10,
                        quiet=False,
                        vector_thread_count=1,
                    )

                    # === PHASE 4: Assert the correct behavior (after fix) ===
                    # FIXED: The method should call _do_resume_interrupted and NOT _do_full_index

                    # CORRECT ASSERTION: This should NOT be called for interrupted operation
                    assert (
                        not mock_full_index.called
                    ), "FIXED: _do_full_index should NOT be called for interrupted operation"

                    # CORRECT ASSERTION: This SHOULD be called for interrupted operation
                    assert (
                        mock_resume_interrupted.called
                    ), "FIXED: _do_resume_interrupted should be called"

                    # CORRECT ASSERTION: Wrong progress message should NOT appear
                    bug_message = "No previous index found, performing full index"
                    assert not any(
                        bug_message in msg for msg in progress_messages
                    ), f"FIXED: Bug message '{bug_message}' should not appear in {progress_messages}"

                    # CORRECT ASSERTION: This message should appear (fix working)
                    correct_message = "Resuming interrupted operation"
                    assert any(
                        correct_message in msg for msg in progress_messages
                    ), f"FIXED: Should show '{correct_message}' in {progress_messages}"

    def test_completed_operation_should_use_timestamp_resume(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test that completed operations correctly use timestamp-based incremental indexing.

        This ensures our fix doesn't break the existing behavior for completed operations.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # === PHASE 1: Setup completed operation state ===
        metadata = indexer.progressive_metadata
        git_status = {
            "git_available": False,
            "project_id": "test-project",
            "current_branch": "master",
            "current_commit": "abc123",
        }

        # Start and complete an indexing operation
        metadata.start_indexing("test-provider", "test-model", git_status)
        files_to_index = [Path("src/main.py"), Path("src/utils.py")]
        metadata.set_files_to_index(files_to_index)
        metadata.mark_file_completed("src/main.py", chunks_count=10)
        metadata.mark_file_completed("src/utils.py", chunks_count=5)
        metadata.complete_indexing()  # Mark as completed

        # Verify completed state
        assert metadata.can_resume_interrupted_operation() is False
        assert metadata.metadata["status"] == "completed"

        # === PHASE 2: Mock dependencies ===
        # Capture progress messages
        progress_messages = []

        def capture_progress(current, total, path, info=""):
            progress_messages.append(info)

        with patch.object(indexer, "_do_full_index") as mock_full_index:
            with patch.object(
                indexer, "_do_resume_interrupted"
            ) as mock_resume_interrupted:
                # Mock get_resume_timestamp to return recent timestamp (completed operation)
                with patch.object(
                    metadata, "get_resume_timestamp", return_value=1000.0
                ):
                    # Mock all the file finding logic to return empty (focus on routing logic)
                    with patch.object(
                        indexer.qdrant_client, "ensure_provider_aware_collection"
                    ):
                        with patch.object(
                            indexer.progressive_metadata, "start_indexing"
                        ):
                            with patch.object(
                                indexer,
                                "_get_git_deltas_since_commit",
                                return_value=Mock(deleted=[], added=[], modified=[]),
                            ):
                                with patch.object(
                                    indexer.file_finder,
                                    "find_modified_files",
                                    return_value=[],
                                ):
                                    # === PHASE 3: Call _do_incremental_index ===
                                    result = indexer._do_incremental_index(
                                        batch_size=10,
                                        progress_callback=capture_progress,
                                        git_status=git_status,
                                        provider_name="test-provider",
                                        model_name="test-model",
                                        safety_buffer_seconds=10,
                                        quiet=True,
                                        vector_thread_count=1,
                                    )

                                    # === PHASE 4: Assert correct behavior ===
                                    # Should NOT call resume interrupted (not an interrupted operation)
                                    assert not mock_resume_interrupted.called

                                    # Should NOT call full index (has timestamp)
                                    assert not mock_full_index.called

                                    # Should proceed with normal incremental indexing
                                    assert result is not None

    def test_fresh_project_should_do_full_index(
        self,
        temp_metadata_path,
        mock_config,
        mock_embedding_provider,
        mock_qdrant_client,
    ):
        """
        Test that fresh projects (no metadata) correctly do full index.

        This ensures our fix doesn't break the existing behavior for fresh projects.
        """
        # Create SmartIndexer instance
        indexer = SmartIndexer(
            config=mock_config,
            embedding_provider=mock_embedding_provider,
            vector_store_client=mock_qdrant_client,
            metadata_path=temp_metadata_path,
        )

        # Fresh metadata (no previous operations)
        metadata = indexer.progressive_metadata
        assert metadata.can_resume_interrupted_operation() is False

        # === Mock dependencies ===
        with patch.object(indexer, "_do_full_index") as mock_full_index:
            with patch.object(
                indexer, "_do_resume_interrupted"
            ) as mock_resume_interrupted:
                # Mock get_resume_timestamp to return 0.0 (no previous index)
                with patch.object(metadata, "get_resume_timestamp", return_value=0.0):
                    progress_messages = []

                    def capture_progress(current, total, path, info=""):
                        progress_messages.append(info)

                    # === Call _do_incremental_index ===
                    indexer._do_incremental_index(
                        batch_size=10,
                        progress_callback=capture_progress,
                        git_status={"git_available": False},
                        provider_name="test-provider",
                        model_name="test-model",
                        safety_buffer_seconds=10,
                        quiet=False,
                        vector_thread_count=1,
                    )

                    # === Assert correct behavior ===
                    # Should NOT call resume interrupted (not an interrupted operation)
                    assert not mock_resume_interrupted.called

                    # Should call full index (no previous index)
                    assert mock_full_index.called

                    # Should show correct message
                    expected_message = "No previous index found, performing full index"
                    assert any(expected_message in msg for msg in progress_messages)
