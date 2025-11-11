"""
End-to-end test for progressive save functionality.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestProgressiveSaveE2E(unittest.TestCase):
    """Test progressive save in a more realistic scenario."""

    def setUp(self):
        """Create temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = Path(self.temp_dir) / "test_project"
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_commits_are_saved_to_progress_file(self):
        """
        Test that commits are saved to temporal_progress.json as they are processed.

        This verifies the complete flow from indexing through to progress persistence.
        """
        # Setup mocks
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(
            parallel_requests=1, max_concurrent_batches_per_commit=10
        )
        mock_config.codebase_dir = self.project_dir
        config_manager.get_config.return_value = mock_config

        vector_store = MagicMock()
        vector_store.project_root = self.project_dir
        vector_store.base_path = self.project_dir / ".code-indexer" / "index"
        vector_store.collection_exists.return_value = True
        vector_store.load_id_index.return_value = set()
        vector_store.begin_indexing = MagicMock()
        vector_store.upsert_points = MagicMock()

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}

            # Mock embedding provider
            mock_embedding = MagicMock()
            mock_result = MagicMock()
            mock_result.embeddings = [[0.1] * 1024]  # Fake embedding
            mock_result.error = None
            mock_embedding.embed_batch.return_value = mock_result
            MockFactory.create.return_value = mock_embedding

            # Create indexer
            indexer = TemporalIndexer(config_manager, vector_store)

            # Create a simple commit
            commit = CommitInfo(
                hash="abc123",
                timestamp=1234567890,
                author_name="Test",
                author_email="test@test.com",
                message="Test commit",
                parent_hashes="",
            )

            # Mock git operations
            with patch.object(indexer, "_get_commit_history") as mock_history:
                mock_history.return_value = [commit]

                with patch.object(indexer, "_get_current_branch") as mock_branch:
                    mock_branch.return_value = "main"

                    # Mock diff scanner to return a simple diff
                    with patch.object(
                        indexer.diff_scanner, "get_diffs_for_commit"
                    ) as mock_diffs:
                        diff = DiffInfo(
                            file_path="test.py",
                            diff_type="modified",
                            commit_hash="abc123",
                            blob_hash="blob123",
                            diff_content="def test():\n    pass",
                        )
                        mock_diffs.return_value = [diff]

                        # Mock VectorCalculationManager
                        with patch(
                            "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                        ) as MockVCM:
                            # Setup mock vector manager with embedding provider
                            mock_vector_manager = MagicMock()
                            # Mock cancellation event (no cancellation)
                            mock_cancellation_event = MagicMock()
                            mock_cancellation_event.is_set.return_value = False
                            mock_vector_manager.cancellation_event = (
                                mock_cancellation_event
                            )
                            MockVCM.return_value.__enter__.return_value = (
                                mock_vector_manager
                            )
                            MockVCM.return_value.__exit__.return_value = None

                            # Mock embedding provider methods for token counting
                            mock_embedding_provider = MagicMock()
                            mock_embedding_provider._count_tokens_accurately = (
                                MagicMock(return_value=100)
                            )
                            mock_embedding_provider._get_model_token_limit = MagicMock(
                                return_value=120000
                            )
                            mock_vector_manager.embedding_provider = (
                                mock_embedding_provider
                            )

                            # Mock embedding results
                            mock_future = MagicMock()
                            mock_result = MagicMock()
                            mock_result.embeddings = [[0.1] * 1024]
                            mock_result.error = None
                            mock_future.result.return_value = mock_result
                            mock_vector_manager.submit_batch_task.return_value = (
                                mock_future
                            )

                            # Run indexing
                            result = indexer.index_commits(
                                all_branches=False, max_commits=None, since_date=None
                            )

                            # Check that progress file was created and contains the commit
                            progress_file = (
                                self.project_dir
                                / ".code-indexer/index/code-indexer-temporal/temporal_progress.json"
                            )

                            # This assertion will FAIL because we haven't implemented saving yet
                            self.assertTrue(
                                progress_file.exists(),
                                "Progress file should be created",
                            )

                            with open(progress_file) as f:
                                progress_data = json.load(f)

                            self.assertIn("completed_commits", progress_data)
                            self.assertIn(
                                "abc123",
                                progress_data["completed_commits"],
                                "Commit should be saved in progress file",
                            )


if __name__ == "__main__":
    unittest.main()
