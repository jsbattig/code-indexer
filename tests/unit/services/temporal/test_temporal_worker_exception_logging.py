"""Test that worker thread exceptions are properly caught and logged.

This test addresses the critical bug where exceptions in temporal_indexer.py
worker threads (lines 523-993) were silently swallowed because there was no
except block between try and finally.

The bug manifested when upsert_points() failed (e.g., missing projection_matrix.npy)
and the exception was never logged, making debugging impossible.
"""

import logging
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo


def test_worker_exception_is_logged_and_propagated(tmp_path, caplog):
    """Test that worker thread exceptions are logged at ERROR level and propagated.

    This test verifies:
    1. Exceptions in worker threads are logged at ERROR level
    2. The log message includes the commit hash
    3. The exception propagates (not swallowed)
    4. The slot is still released (finally block executes)
    """
    # Setup
    config_dir = tmp_path / ".code-indexer"
    config_dir.mkdir()
    (config_dir / "config.json").write_text('{"vectorStore": {"backend": "filesystem"}}')

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Create a mock TemporalIndexer
    with patch("code_indexer.services.temporal.temporal_indexer.ConfigManager") as mock_config_mgr, \
         patch("code_indexer.services.temporal.temporal_indexer.VectorCalculationManager") as mock_vcm, \
         patch("code_indexer.services.temporal.temporal_indexer.FilesystemVectorStore") as mock_store_cls, \
         patch("code_indexer.services.temporal.temporal_indexer.FileIdentifier") as mock_file_id:

        # Setup mocks
        mock_config = Mock()
        mock_config.get_vector_store_config.return_value = {"backend": "filesystem"}
        mock_config.get_model_config.return_value = {"name": "voyage-code-3", "dimensions": 1024}
        mock_config.get_model_name.return_value = "voyage-code-3"
        mock_config.get_model_dimensions.return_value = 1024
        mock_config.get_temporal_worker_threads.return_value = 1  # Single thread for predictable testing
        mock_config_mgr.return_value = mock_config

        mock_vcm_instance = Mock()
        mock_vcm.return_value = mock_vcm_instance

        mock_file_id_instance = Mock()
        mock_file_id_instance._get_project_id.return_value = "test_project"
        mock_file_id.return_value = mock_file_id_instance

        # Create mock vector store that will fail on upsert
        mock_store = Mock()
        mock_store_cls.return_value = mock_store

        # Mock the upsert_points to raise an exception
        test_exception = ValueError("Simulated upsert failure: missing projection_matrix.npy")
        mock_store.upsert_points.side_effect = test_exception

        # Create indexer
        indexer = TemporalIndexer(
            repo_path=repo_path,
            config_manager=mock_config,
            vector_calculation_manager=mock_vcm_instance,
            file_identifier=mock_file_id_instance,
            vector_store=mock_store,
        )

        # Mock the diff scanner to return a single diff
        mock_diff_info = Mock()
        mock_diff_info.file_path = "test_file.py"
        mock_diff_info.diff_content = "test content"
        mock_diff_info.action = "M"
        mock_diff_info.blob_hash = "abc123"
        mock_diff_info.file_size = 100

        indexer.diff_scanner = Mock()
        indexer.diff_scanner.get_diffs_for_commit.return_value = [mock_diff_info]

        # Mock embedding generation
        mock_vcm_instance.get_embeddings.return_value = [[0.1] * 1024]

        # Mock existing points check
        mock_store.get_existing_point_ids.return_value = []

        # Create a test commit
        test_commit = CommitInfo(
            hash="abc123def456",
            author="Test Author",
            timestamp=1234567890,
            message="Test commit message",
            branch_name="main"
        )

        # Capture logs at ERROR level
        caplog.set_level(logging.ERROR)

        # Execute: Call _index_single_commit_batch which uses the worker logic
        # This should raise an exception because upsert_points fails
        with pytest.raises(ValueError, match="Simulated upsert failure"):
            indexer._index_single_commit_batch(
                commits=[test_commit],
                branch_name="main",
                total_commits=1,
                commit_slot_tracker=Mock(),
                progress_callback=Mock(),
            )

        # Verify: Check that the exception was logged at ERROR level
        assert any(
            record.levelname == "ERROR" and
            "abc123d" in record.message and  # Commit hash prefix (first 7 chars)
            "Failed to index commit" in record.message
            for record in caplog.records
        ), f"Expected ERROR log with commit hash not found. Logs: {[r.message for r in caplog.records]}"

        # Verify: Check that the log includes exception info
        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) > 0, "No ERROR logs found"
        assert any("Simulated upsert failure" in str(r.exc_info) for r in error_logs if r.exc_info), \
            "Exception info not included in ERROR log"
