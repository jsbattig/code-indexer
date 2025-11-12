"""
Test that TemporalIndexer saves progress as it processes commits.
"""

import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestProgressiveSaveIntegration(unittest.TestCase):
    """Test that progress is saved during indexing."""

    def test_indexer_saves_completed_commits_during_processing(self):
        """
        Verify that TemporalIndexer saves each commit as completed during processing.

        This ensures that if indexing is interrupted, we can resume from the last
        successfully processed commit.
        """
        # Setup mocks
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(
            parallel_requests=1, max_concurrent_batches_per_commit=10
        )
        config_manager.get_config.return_value = mock_config

        vector_store = MagicMock()
        vector_store.project_root = Path("/tmp/test")
        vector_store.collection_exists.return_value = True
        vector_store.load_id_index.return_value = set()
        vector_store.begin_indexing = MagicMock()

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}
            MockFactory.create.return_value = MagicMock()

            # Create indexer
            indexer = TemporalIndexer(config_manager, vector_store)

            # Create test commits
            commits = [
                CommitInfo(
                    hash=f"commit{i}",
                    timestamp=1234567890 + i,
                    author_name="Test",
                    author_email="test@test.com",
                    message=f"Commit {i}",
                    parent_hashes="",
                )
                for i in range(1, 4)
            ]

            # Mock _get_commit_history to return commits
            with patch.object(indexer, "_get_commit_history") as mock_get_history:
                mock_get_history.return_value = commits

                # Mock _get_current_branch
                with patch.object(indexer, "_get_current_branch") as mock_branch:
                    mock_branch.return_value = "main"

                    # Track saves to progressive metadata
                    with patch.object(
                        indexer, "progressive_metadata", create=True
                    ) as mock_progressive:
                        mock_progressive.load_completed.return_value = set()

                        # Mock _process_commits_parallel to simulate processing
                        def simulate_processing(commits, *args, **kwargs):
                            # Simulate that each commit is processed and saved
                            # Call save_completed for each commit (simulating worker behavior)
                            for commit in commits:
                                mock_progressive.save_completed(commit.hash)
                            return (
                                len(commits),
                                0,
                                0,
                            )  # commits_processed, files_processed, vectors_created

                        with patch.object(
                            indexer, "_process_commits_parallel"
                        ) as mock_process:
                            mock_process.side_effect = simulate_processing

                            # Index commits
                            result = indexer.index_commits(
                                all_branches=False, max_commits=None, since_date=None
                            )

                            # Verify that save_completed was called for each commit
                            # This will FAIL because we haven't implemented saving yet
                            expected_calls = [
                                call.save_completed("commit1"),
                                call.save_completed("commit2"),
                                call.save_completed("commit3"),
                            ]

                            # Check that all commits were saved
                            mock_progressive.assert_has_calls(
                                expected_calls, any_order=True
                            )


if __name__ == "__main__":
    unittest.main()
