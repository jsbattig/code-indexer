"""Test that daemon mode properly handles temporal indexing without semantic overhead."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import shutil

from code_indexer.daemon.service import CIDXDaemonService


class TestDaemonTemporalIndexing:
    """Tests for daemon temporal indexing optimization."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        temp_dir = tempfile.mkdtemp(prefix="test_daemon_temporal_")
        # Initialize basic code-indexer structure
        config_dir = Path(temp_dir) / ".code-indexer"
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create a minimal config file
        config_file = config_dir / "config.json"
        config_file.write_text(
            """
{
    "provider": "voyageai",
    "api_key": "test-api-key",
    "language_extensions": {
        "python": [".py"]
    }
}
"""
        )

        yield Path(temp_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_temporal_indexing_skips_smart_indexer_initialization(self, temp_project):
        """Test that temporal indexing does NOT initialize SmartIndexer."""
        daemon = CIDXDaemonService()

        # Mock SmartIndexer to detect if it gets initialized
        with patch(
            "code_indexer.services.smart_indexer.SmartIndexer"
        ) as mock_smart_indexer:
            # Mock other required components
            with patch("code_indexer.config.ConfigManager") as mock_config_manager:
                with patch(
                    "code_indexer.backends.backend_factory.BackendFactory"
                ) as mock_backend_factory:
                    with patch(
                        "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
                    ) as mock_embedding_factory:
                        with patch(
                            "code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
                        ) as mock_temporal_indexer:
                            with patch(
                                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
                            ):
                                # Setup mocks
                                mock_config = MagicMock()
                                mock_config_instance = MagicMock()
                                mock_config_instance.get_config.return_value = (
                                    mock_config
                                )
                                mock_config_manager.create_with_backtrack.return_value = (
                                    mock_config_instance
                                )

                                # Setup temporal indexer mock
                                mock_temporal_instance = MagicMock()
                                mock_result = MagicMock()
                                mock_result.total_commits = 10
                                mock_result.files_processed = 50
                                mock_result.approximate_vectors_created = 100
                                mock_result.skip_ratio = 0.1
                                mock_result.branches_indexed = 2
                                mock_result.commits_per_branch = {
                                    "main": 7,
                                    "develop": 3,
                                }
                                mock_temporal_instance.index_commits.return_value = (
                                    mock_result
                                )
                                mock_temporal_indexer.return_value = (
                                    mock_temporal_instance
                                )

                                # Call exposed_index_blocking with index_commits=True
                                result = daemon.exposed_index_blocking(
                                    str(temp_project), callback=None, index_commits=True
                                )

                                # ASSERTIONS - This test should FAIL initially
                                # SmartIndexer should NOT have been initialized for temporal indexing
                                mock_smart_indexer.assert_not_called()

                                # Backend factory should NOT have been called
                                mock_backend_factory.create.assert_not_called()

                                # Embedding provider factory should NOT have been called
                                mock_embedding_factory.create.assert_not_called()

                                # Temporal indexer SHOULD have been called
                                mock_temporal_indexer.assert_called_once()
                                mock_temporal_instance.index_commits.assert_called_once()

                                # Verify result structure
                                assert result["status"] == "completed"
                                assert result["stats"]["total_commits"] == 10

    def test_temporal_indexing_no_file_discovery_phase(self, temp_project):
        """Test that temporal indexing does not run file discovery."""
        daemon = CIDXDaemonService()

        # Track any file discovery attempts
        with patch(
            "code_indexer.services.smart_indexer.SmartIndexer"
        ) as mock_smart_indexer:
            mock_indexer_instance = MagicMock()

            # Mock smart_index method to track if it's called
            mock_indexer_instance.smart_index = MagicMock(
                return_value={
                    "total_files": 1244,  # Simulate finding many files
                    "indexed": 0,
                    "failed": 0,
                }
            )
            mock_smart_indexer.return_value = mock_indexer_instance

            with patch(
                "code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
            ) as mock_temporal_indexer:
                with patch("code_indexer.config.ConfigManager"):
                    with patch(
                        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
                    ):
                        # Setup temporal indexer mock
                        mock_temporal_instance = MagicMock()
                        mock_result = MagicMock()
                        mock_result.total_commits = 5
                        mock_result.files_processed = 20
                        mock_result.approximate_vectors_created = 40
                        mock_result.skip_ratio = 0.0
                        mock_result.branches_indexed = 1
                        mock_result.commits_per_branch = {"main": 5}
                        mock_temporal_instance.index_commits.return_value = mock_result
                        mock_temporal_indexer.return_value = mock_temporal_instance

                        # Call with temporal indexing
                        daemon.exposed_index_blocking(
                            str(temp_project), callback=None, index_commits=True
                        )

                        # ASSERTION - smart_index should NEVER be called for temporal
                        mock_indexer_instance.smart_index.assert_not_called()

    def test_semantic_indexing_still_works_without_index_commits(self, temp_project):
        """Test that semantic indexing still works normally when NOT using --index-commits."""
        daemon = CIDXDaemonService()

        with patch(
            "code_indexer.services.smart_indexer.SmartIndexer"
        ) as mock_smart_indexer:
            mock_indexer_instance = MagicMock()
            # Create a mock stats object with attributes
            mock_stats = MagicMock()
            mock_stats.files_processed = 100
            mock_stats.chunks_created = 500
            mock_stats.failed_files = 5
            mock_stats.duration = 10.5
            mock_stats.cancelled = False
            mock_indexer_instance.smart_index.return_value = mock_stats
            mock_smart_indexer.return_value = mock_indexer_instance

            with patch("code_indexer.config.ConfigManager"):
                with patch(
                    "code_indexer.backends.backend_factory.BackendFactory"
                ) as mock_backend:
                    with patch(
                        "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
                    ):
                        # Setup backend mock
                        mock_backend_instance = MagicMock()
                        mock_backend.create.return_value = mock_backend_instance

                        # Call WITHOUT index_commits (regular semantic indexing)
                        result = daemon.exposed_index_blocking(
                            str(temp_project),
                            callback=None,
                            index_commits=False,  # Explicitly False for semantic
                        )

                        # SmartIndexer SHOULD be initialized for semantic indexing
                        mock_smart_indexer.assert_called_once()
                        mock_indexer_instance.smart_index.assert_called_once()

                        # Verify result
                        assert result["status"] == "completed"
                        assert result["stats"]["files_processed"] == 100
                        assert result["stats"]["chunks_created"] == 500
                        assert result["stats"]["failed_files"] == 5

    def test_temporal_early_return_prevents_semantic_overhead(self, temp_project):
        """Test that temporal indexing returns early without ANY semantic setup."""
        daemon = CIDXDaemonService()

        # Create a list to track the order of operations
        operation_order = []

        # Patch all components to track initialization order
        with patch(
            "code_indexer.services.smart_indexer.SmartIndexer"
        ) as mock_smart_indexer:
            mock_smart_indexer.side_effect = (
                lambda *args, **kwargs: operation_order.append("SmartIndexer")
            )

            with patch(
                "code_indexer.backends.backend_factory.BackendFactory"
            ) as mock_backend:

                def backend_create(*args, **kwargs):
                    operation_order.append("BackendFactory")
                    return MagicMock()

                mock_backend.create.side_effect = backend_create

                with patch(
                    "code_indexer.services.embedding_factory.EmbeddingProviderFactory"
                ) as mock_embedding:

                    def embedding_create(*args, **kwargs):
                        operation_order.append("EmbeddingProvider")
                        return MagicMock()

                    mock_embedding.create.side_effect = embedding_create

                    with patch(
                        "code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
                    ) as mock_temporal:

                        def temporal_init(*args, **kwargs):
                            operation_order.append("TemporalIndexer")
                            mock_instance = MagicMock()
                            mock_result = MagicMock()
                            mock_result.total_commits = 1
                            mock_result.files_processed = 1
                            mock_result.approximate_vectors_created = 1
                            mock_result.skip_ratio = 0.0
                            mock_result.branches_indexed = 1
                            mock_result.commits_per_branch = {"main": 1}
                            mock_instance.index_commits.return_value = mock_result
                            return mock_instance

                        mock_temporal.side_effect = temporal_init

                        with patch("code_indexer.config.ConfigManager"):
                            with patch(
                                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
                            ):
                                # Call with temporal indexing
                                daemon.exposed_index_blocking(
                                    str(temp_project), callback=None, index_commits=True
                                )

                                # ASSERTION - Only TemporalIndexer should be in the list
                                # No semantic components should have been initialized
                                assert "TemporalIndexer" in operation_order
                                assert "SmartIndexer" not in operation_order
                                assert "BackendFactory" not in operation_order
                                assert "EmbeddingProvider" not in operation_order

    def test_progress_callback_works_in_temporal_mode(self, temp_project):
        """Test that progress callbacks work correctly in temporal mode."""
        daemon = CIDXDaemonService()

        # Create a mock callback to track progress updates
        callback_calls = []

        def mock_callback(current, total, file_path, info="", **kwargs):
            callback_calls.append(
                {
                    "current": current,
                    "total": total,
                    "file_path": str(file_path),
                    "info": info,
                }
            )

        with patch(
            "code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
        ) as mock_temporal:
            with patch("code_indexer.config.ConfigManager"):
                with patch(
                    "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
                ):
                    # Setup temporal indexer to call progress callback
                    def temporal_init(*args, **kwargs):
                        mock_instance = MagicMock()

                        def index_commits_with_progress(
                            *args, progress_callback=None, **kwargs
                        ):
                            # Simulate progress updates
                            if progress_callback:
                                progress_callback(
                                    0, 10, Path("commit1.txt"), "Processing commits"
                                )
                                progress_callback(5, 10, Path("commit2.txt"), "Halfway")
                                progress_callback(
                                    10, 10, Path("commit3.txt"), "Complete"
                                )

                            result = MagicMock()
                            result.total_commits = 10
                            result.files_processed = 30
                            result.approximate_vectors_created = 60
                            result.skip_ratio = 0.0
                            result.branches_indexed = 1
                            result.commits_per_branch = {"main": 10}
                            return result

                        mock_instance.index_commits = index_commits_with_progress
                        mock_instance.close = MagicMock()
                        return mock_instance

                    mock_temporal.side_effect = temporal_init

                    # Call with progress callback
                    daemon.exposed_index_blocking(
                        str(temp_project), callback=mock_callback, index_commits=True
                    )

                    # Verify callbacks were made
                    assert len(callback_calls) > 0
                    # Check first callback
                    assert callback_calls[0]["current"] == 0
                    assert callback_calls[0]["total"] == 10
                    # Check last callback
                    assert callback_calls[-1]["current"] == 10
                    assert callback_calls[-1]["total"] == 10
