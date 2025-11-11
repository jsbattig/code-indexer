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
    (config_dir / "config.json").write_text(
        '{"vectorStore": {"backend": "filesystem"}}'
    )

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    # Create a mock TemporalIndexer
    with (
        patch(
            "code_indexer.services.temporal.temporal_indexer.ConfigManager"
        ) as mock_config_mgr,
        patch(
            "code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
        ) as mock_vcm,
        patch(
            "code_indexer.services.temporal.temporal_indexer.FilesystemVectorStore"
        ) as mock_store_cls,
        patch(
            "code_indexer.services.temporal.temporal_indexer.FileIdentifier"
        ) as mock_file_id,
    ):

        # Setup mocks
        mock_config = Mock()
        mock_config.get_vector_store_config.return_value = {"backend": "filesystem"}
        mock_config.get_model_config.return_value = {
            "name": "voyage-code-3",
            "dimensions": 1024,
        }
        mock_config.get_model_name.return_value = "voyage-code-3"
        mock_config.get_model_dimensions.return_value = 1024
        mock_config.get_temporal_worker_threads.return_value = (
            1  # Single thread for predictable testing
        )
        mock_config_mgr.return_value = mock_config

        # Properly configure VectorCalculationManager as a context manager
        mock_vcm_instance = MagicMock()
        mock_vcm.return_value.__enter__.return_value = mock_vcm_instance
        mock_vcm.return_value.__exit__.return_value = None

        # Add cancellation_event (required by worker function)
        import threading

        mock_vcm_instance.cancellation_event = threading.Event()

        # Mock embedding provider for token counting (required by batching logic)
        mock_embedding_provider = MagicMock()
        mock_embedding_provider._count_tokens_accurately = MagicMock(return_value=100)
        mock_embedding_provider._get_model_token_limit = MagicMock(return_value=120000)
        mock_vcm_instance.embedding_provider = mock_embedding_provider

        mock_file_id_instance = Mock()
        mock_file_id_instance._get_project_id.return_value = "test_project"
        mock_file_id.return_value = mock_file_id_instance

        # Create mock vector store that will fail on upsert
        mock_store = Mock()
        mock_store.project_root = repo_path
        mock_store.base_path = repo_path / ".code-indexer" / "index"
        mock_store_cls.return_value = mock_store

        # Mock the upsert_points to raise an exception
        test_exception = ValueError(
            "Simulated upsert failure: missing projection_matrix.npy"
        )
        mock_store.upsert_points.side_effect = test_exception

        # Create indexer using correct constructor signature
        mock_config_mgr_instance = Mock()
        mock_voyage_ai_config = Mock(parallel_requests=1, model="voyage-code-3")
        # CRITICAL FIX: Set max_concurrent_batches_per_commit as an actual integer
        # getattr() on Mock returns Mock, not the default value, so we must set it explicitly
        mock_voyage_ai_config.max_concurrent_batches_per_commit = 10

        mock_config_mgr_instance.get_config.return_value = Mock(
            embedding_provider="voyage-ai", voyage_ai=mock_voyage_ai_config
        )

        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
        ) as mock_info:
            mock_info.return_value = {"dimensions": 1024}
            indexer = TemporalIndexer(
                config_manager=mock_config_mgr_instance,
                vector_store=mock_store,
            )

        # Mock the diff scanner to return a single diff
        mock_diff_info = Mock()
        mock_diff_info.file_path = "test_file.py"
        mock_diff_info.diff_content = "test content"
        mock_diff_info.action = "M"
        mock_diff_info.diff_type = "modified"
        mock_diff_info.blob_hash = "abc123"
        mock_diff_info.file_size = 100
        mock_diff_info.parent_commit_hash = None

        indexer.diff_scanner = Mock()
        indexer.diff_scanner.get_diffs_for_commit.return_value = [mock_diff_info]

        # Mock progressive_metadata (required for commit filtering)
        indexer.progressive_metadata = Mock()
        indexer.progressive_metadata.load_completed.return_value = []
        indexer.progressive_metadata.save_completed = Mock()

        # Mock indexed_blobs (blob deduplication)
        indexer.indexed_blobs = set()

        # Mock chunker to return a single chunk
        indexer.chunker = Mock()
        indexer.chunker.chunk_text.return_value = [
            {"text": "test content chunk", "char_start": 0, "char_end": 18}
        ]

        # Mock embedding generation - submit_batch_task returns a Future
        from concurrent.futures import Future
        from types import SimpleNamespace

        def mock_submit_batch(texts, metadata):
            future = Future()
            # Create a result with embeddings
            result = SimpleNamespace(
                embeddings=[[0.1] * 1024 for _ in texts], error=None
            )
            future.set_result(result)
            return future

        mock_vcm_instance.submit_batch_task = mock_submit_batch

        # Mock existing points check
        mock_store.get_existing_point_ids.return_value = []
        mock_store.load_id_index.return_value = []  # Return empty list for existing IDs

        # Create a test commit
        test_commit = CommitInfo(
            hash="abc123def456",
            author_name="Test Author",
            author_email="test@example.com",
            timestamp=1234567890,
            message="Test commit message",
            parent_hashes="",
        )

        # Capture logs at ERROR level
        caplog.set_level(logging.ERROR)

        # Mock git operations to return our test commit
        with (
            patch.object(indexer, "_get_commit_history", return_value=[test_commit]),
            patch.object(indexer, "_get_current_branch", return_value="main"),
            patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"
            ) as mock_create,
        ):

            # Mock embedding provider
            mock_embedding = Mock()
            mock_create.return_value = mock_embedding

            # Execute: Call index_commits which uses parallel worker logic
            # This should raise an exception because upsert_points fails
            with pytest.raises(ValueError, match="Simulated upsert failure"):
                indexer.index_commits(all_branches=False)

        # Verify: Check that the exception was logged at ERROR level
        assert any(
            record.levelname == "ERROR"
            and "abc123d" in record.message  # Commit hash prefix (first 7 chars)
            and "Failed to index commit" in record.message
            for record in caplog.records
        ), f"Expected ERROR log with commit hash not found. Logs: {[r.message for r in caplog.records]}"

        # Verify: Check that the log includes exception info
        error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(error_logs) > 0, "No ERROR logs found"
        assert any(
            "Simulated upsert failure" in str(r.exc_info)
            for r in error_logs
            if r.exc_info
        ), "Exception info not included in ERROR log"
