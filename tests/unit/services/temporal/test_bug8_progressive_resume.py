"""
Test for Bug #8: Progressive resume capability for temporal indexing.

When temporal indexing is interrupted, all progress is lost and must restart
from the beginning. This test verifies that progressive tracking is implemented
to allow resuming from where it left off.
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestBug8ProgressiveResume(unittest.TestCase):
    """Test progressive resume capability for temporal indexing."""

    def test_indexer_filters_already_completed_commits(self):
        """
        Bug #8: Temporal indexer should skip already-completed commits on resume.

        Current behavior: Processes ALL commits every time
        Expected behavior: Skip commits that were already completed
        """
        # Setup mocks
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(parallel_requests=1, max_concurrent_batches_per_commit=10)
        config_manager.get_config.return_value = mock_config

        vector_store = MagicMock()
        vector_store.project_root = Path("/tmp/test")
        vector_store.collection_exists.return_value = True
        vector_store.load_id_index.return_value = set()

        with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory') as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}
            MockFactory.create.return_value = MagicMock()

            # Create indexer
            indexer = TemporalIndexer(config_manager, vector_store)

            # Create 5 test commits
            all_commits = [
                CommitInfo(hash=f"commit{i}", timestamp=1234567890 + i,
                          author_name="Test", author_email="test@test.com",
                          message=f"Commit {i}", parent_hashes="")
                for i in range(1, 6)
            ]

            # Simulate that commits 1 and 2 were already processed
            # This would be loaded from temporal_progress.json
            already_completed = {"commit1", "commit2"}

            # Mock progressive_metadata to return already completed commits
            indexer.progressive_metadata.load_completed = MagicMock(return_value=already_completed)
            indexer.progressive_metadata.save_completed = MagicMock()

            # Mock _get_commit_history to return all commits
            with patch.object(indexer, '_get_commit_history') as mock_get_history:
                mock_get_history.return_value = all_commits

                # Mock _get_current_branch to avoid git subprocess call
                with patch.object(indexer, '_get_current_branch') as mock_branch:
                    mock_branch.return_value = "main"

                    # Track which commits get_diffs is called for (indicates processing)
                    processed_commits = []

                    def track_diffs(commit_hash):
                        # Find commit object by hash
                        for c in all_commits:
                            if c.hash == commit_hash:
                                processed_commits.append(c)
                                break
                        return []  # No diffs to avoid further processing

                    indexer.diff_scanner.get_diffs_for_commit = MagicMock(side_effect=track_diffs)
                    indexer.vector_store.load_id_index = MagicMock(return_value=set())

                    # Index commits - should skip already completed ones
                    result = indexer.index_commits(
                        all_branches=False,
                        max_commits=None,
                        since_date=None
                    )

                    # ASSERTION: Only 3 commits should be processed (3, 4, 5)
                    # Commits 1 and 2 should be skipped
                    self.assertEqual(len(processed_commits), 3,
                        f"Should process only 3 new commits, but processed {len(processed_commits)}")

                    # Verify the processed commits are the right ones
                    processed_hashes = {c.hash for c in processed_commits}
                    expected_hashes = {"commit3", "commit4", "commit5"}
                    self.assertEqual(processed_hashes, expected_hashes,
                        f"Should process commits 3-5, but processed {processed_hashes}")


if __name__ == "__main__":
    unittest.main()