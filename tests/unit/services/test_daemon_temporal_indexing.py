"""
Unit tests for RPyC daemon temporal indexing support.

Tests verify that daemon correctly handles index_commits flag and delegates
to TemporalIndexer instead of FileChunkingManager.
"""

import sys
import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

# Mock rpyc before import if not available
try:
    import rpyc
except ImportError:
    sys.modules["rpyc"] = MagicMock()
    sys.modules["rpyc.utils.server"] = MagicMock()
    rpyc = sys.modules["rpyc"]


class TestDaemonTemporalIndexing(TestCase):
    """Test suite for daemon temporal indexing functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_path = Path(self.temp_dir) / "test_project"
        self.project_path.mkdir(parents=True, exist_ok=True)

        # Create .git directory to simulate git repo
        git_dir = self.project_path / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)

        # Create mock config
        config_path = self.project_path / ".code-indexer" / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "daemon": {
                        "enabled": True,
                        "ttl_minutes": 10,
                        "auto_shutdown_on_idle": False,
                    }
                }
            )
        )

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)

    def test_perform_indexing_without_index_commits_flag(self):
        """Test that normal indexing uses FileChunkingManager (not temporal)."""
        from src.code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Mock callback
        callback = MagicMock()

        # Patch FileChunkingManager at import location inside method
        with patch(
            "src.code_indexer.services.file_chunking_manager.FileChunkingManager"
        ) as mock_fcm:
            mock_chunking_manager = MagicMock()
            mock_fcm.return_value = mock_chunking_manager

            # Call without index_commits flag (default behavior)
            service._perform_indexing(self.project_path, callback, force_reindex=False)

            # Verify FileChunkingManager was instantiated
            mock_fcm.assert_called_once()

            # Verify index_repository was called with correct args
            mock_chunking_manager.index_repository.assert_called_once_with(
                repo_path=str(self.project_path),
                force_reindex=False,
                progress_callback=callback,
            )

    def test_perform_indexing_with_index_commits_flag(self):
        """Test that index_commits=True triggers TemporalIndexer."""
        from src.code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Mock callback
        callback = MagicMock()

        # Patch TemporalIndexer and FilesystemVectorStore at their actual import paths
        with (
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
            ) as mock_temporal,
            patch(
                "src.code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_vector_store,
            patch(
                "src.code_indexer.services.file_chunking_manager.FileChunkingManager"
            ) as mock_fcm,
        ):

            mock_indexer = MagicMock()
            mock_temporal.return_value = mock_indexer

            mock_store = MagicMock()
            mock_vector_store.return_value = mock_store

            # Mock indexing result
            mock_indexer.index_commits.return_value = {
                "commits_processed": 10,
                "chunks_indexed": 50,
            }

            # Call WITH index_commits flag
            service._perform_indexing(
                self.project_path,
                callback,
                index_commits=True,
                all_branches=False,
                max_commits=None,
                since_date=None,
            )

            # Verify FileChunkingManager was NOT called
            mock_fcm.assert_not_called()

            # Verify FilesystemVectorStore was instantiated
            mock_vector_store.assert_called_once()

            # Verify TemporalIndexer was instantiated
            mock_temporal.assert_called_once()

            # Verify index_commits was called with correct args
            mock_indexer.index_commits.assert_called_once_with(
                all_branches=False,
                max_commits=None,
                since_date=None,
                progress_callback=callback,
            )

    def test_perform_indexing_temporal_with_all_branches(self):
        """Test temporal indexing with all_branches=True."""
        from src.code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()
        callback = MagicMock()

        with (
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
            ) as mock_temporal,
            patch(
                "src.code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ),
        ):

            mock_indexer = MagicMock()
            mock_temporal.return_value = mock_indexer
            mock_indexer.index_commits.return_value = {
                "commits_processed": 100,
                "chunks_indexed": 500,
            }

            # Call with all_branches=True
            service._perform_indexing(
                self.project_path,
                callback,
                index_commits=True,
                all_branches=True,
                max_commits=50,
                since_date="2024-01-01",
            )

            # Verify index_commits called with correct parameters
            mock_indexer.index_commits.assert_called_once_with(
                all_branches=True,
                max_commits=50,
                since_date="2024-01-01",
                progress_callback=callback,
            )

    def test_perform_indexing_temporal_error_handling(self):
        """Test that temporal indexing errors are properly propagated."""
        from src.code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()
        callback = MagicMock()

        with (
            patch(
                "src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
            ) as mock_temporal,
            patch(
                "src.code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ),
        ):

            mock_indexer = MagicMock()
            mock_temporal.return_value = mock_indexer

            # Simulate indexing error
            mock_indexer.index_commits.side_effect = Exception(
                "Git indexing failed: invalid commit"
            )

            # Verify exception is propagated
            with self.assertRaises(Exception) as context:
                service._perform_indexing(
                    self.project_path, callback, index_commits=True
                )

            self.assertIn("Git indexing failed", str(context.exception))

    def test_exposed_index_with_index_commits_flag(self):
        """Test that exposed_index API correctly passes index_commits to _perform_indexing."""
        from src.code_indexer.services.rpyc_daemon import CIDXDaemonService

        service = CIDXDaemonService()

        # Patch _perform_indexing to verify it receives correct kwargs
        with patch.object(service, "_perform_indexing") as mock_perform:

            # Call exposed_index with index_commits=True
            service.exposed_index(
                str(self.project_path),
                force_reindex=False,
                index_commits=True,
                all_branches=True,
                max_commits=100,
                since_date="2024-01-01",
            )

            # Verify _perform_indexing was called with all kwargs
            mock_perform.assert_called_once()
            call_args = mock_perform.call_args

            # Verify kwargs include temporal parameters
            self.assertEqual(call_args.kwargs.get("index_commits"), True)
            self.assertEqual(call_args.kwargs.get("all_branches"), True)
            self.assertEqual(call_args.kwargs.get("max_commits"), 100)
            self.assertEqual(call_args.kwargs.get("since_date"), "2024-01-01")
            self.assertEqual(call_args.kwargs.get("force_reindex"), False)
