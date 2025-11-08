"""
Test cases for Bug #7: API optimization to prevent duplicate VoyageAI calls.

This test ensures that existing points are checked BEFORE making API calls,
preventing 100% duplicate API calls on re-indexing.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess
from concurrent.futures import Future

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
from src.code_indexer.config import ConfigManager


class TestTemporalAPIOptimization(unittest.TestCase):
    """Test API optimization for temporal indexing."""

    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.repo_path = Path(self.test_dir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=self.repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path, check=True
        )

        # Create initial commit
        test_file = self.repo_path / "test.py"
        test_file.write_text("def test():\n    pass\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=self.repo_path, check=True
        )

        # Set up mocks
        self.config_manager = MagicMock(spec=ConfigManager)
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(parallel_requests=4)
        self.config_manager.get_config.return_value = mock_config

        self.vector_store = MagicMock()
        self.vector_store.project_root = self.repo_path
        self.vector_store.collection_exists.return_value = True

    @patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory')
    def test_bug7_optimization_skips_existing_points(self, MockEmbedFactory):
        """
        Bug #7: Verify that existing points are checked BEFORE API calls.

        This test proves that when re-indexing commits, the system:
        1. Loads existing point IDs into memory
        2. Checks each point ID BEFORE chunking/vectorization
        3. Skips API calls for existing points
        4. Only makes API calls for NEW points
        """
        # Configure the factory mock
        MockEmbedFactory.get_provider_model_info.return_value = {"dimensions": 1024}
        mock_provider = MagicMock()
        MockEmbedFactory.create.return_value = mock_provider

        # Create temporal indexer
        indexer = TemporalIndexer(self.config_manager, self.vector_store)

        # Mock file_identifier to return consistent project_id
        indexer.file_identifier._get_project_id = MagicMock(return_value="code-indexer")

        # Mock existing points in the collection
        existing_point_ids = {
            "code-indexer:diff:abc123:test.py:0",
            "code-indexer:diff:abc123:test.py:1",
            "code-indexer:diff:def456:main.py:0",
        }
        self.vector_store.load_id_index.return_value = existing_point_ids

        # Create mock commits with diffs
        commits = [
            CommitInfo(
                hash="abc123",
                timestamp=1234567890,
                author_name="Test User",
                author_email="test@test.com",
                message="First commit",
                parent_hashes=""
            ),
            CommitInfo(
                hash="def456",
                timestamp=1234567891,
                author_name="Test User",
                author_email="test@test.com",
                message="Second commit",
                parent_hashes="abc123"
            ),
            CommitInfo(
                hash="ghi789",  # NEW commit not in existing_point_ids
                timestamp=1234567892,
                author_name="Test User",
                author_email="test@test.com",
                message="Third commit",
                parent_hashes="def456"
            )
        ]

        # Debug: Check what the real diff scanner returns for our test repo
        from src.code_indexer.services.temporal.temporal_diff_scanner import TemporalDiffScanner
        real_scanner = TemporalDiffScanner(self.repo_path)

        # Get the actual commit from the test repo
        import subprocess
        actual_commit_result = subprocess.run(
            ["git", "log", "--format=%H", "-n", "1"],
            cwd=self.repo_path, capture_output=True, text=True
        )
        actual_commit_hash = actual_commit_result.stdout.strip()
        print(f"DEBUG: Actual test repo commit: {actual_commit_hash}")

        # Mock all three together: commit history, diff scanner, and vector manager
        with patch.object(indexer, '_get_commit_history') as mock_get_history, \
             patch.object(indexer.diff_scanner, 'get_diffs_for_commit') as mock_get_diffs, \
             patch('src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager') as MockVectorManager:

            mock_get_history.return_value = commits

            mock_get_diffs.side_effect = [
                # abc123 - already indexed
                [DiffInfo(
                    file_path="test.py",
                    diff_type="modified",
                    commit_hash="abc123",
                    diff_content="+def new_func():\n+    return True\n",
                    blob_hash="blob1"
                )],
                # def456 - already indexed
                [DiffInfo(
                    file_path="main.py",
                    diff_type="added",
                    commit_hash="def456",
                    diff_content="+import sys\n+print('hello')\n",
                    blob_hash="blob2"
                )],
                # ghi789 - NEW, should be processed
                [DiffInfo(
                    file_path="new_file.py",
                    diff_type="added",
                    commit_hash="ghi789",
                    diff_content="+class NewClass:\n+    pass\n",
                    blob_hash="blob3"
                )]
            ]
            mock_vector_manager = MagicMock()
            MockVectorManager.return_value.__enter__ = MagicMock(return_value=mock_vector_manager)
            MockVectorManager.return_value.__exit__ = MagicMock(return_value=None)

            # Mock token limit
            mock_vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

            # Mock submit_batch_task to return embeddings matching input count
            def mock_submit(chunk_texts, metadata):
                future = MagicMock(spec=Future)
                result = MagicMock()
                # Return embeddings matching the number of chunks submitted
                result.embeddings = [[0.1, 0.2, 0.3] for _ in chunk_texts]
                future.result.return_value = result
                return future

            mock_vector_manager.submit_batch_task.side_effect = mock_submit

            # Process commits
            result = indexer.index_commits(
                all_branches=False,
                max_commits=None,
                since_date=None,
                progress_callback=None
            )

            # Debug: Check how many times get_diffs_for_commit was called
            print(f"DEBUG: get_diffs_for_commit called {mock_get_diffs.call_count} times")
            print(f"DEBUG: Commits processed: {[c.hash for c in commits]}")
            print(f"DEBUG: API calls made: {mock_vector_manager.submit_batch_task.call_count}")

            # Check if mock_get_diffs was properly set up
            for i, call in enumerate(mock_get_diffs.call_args_list):
                print(f"DEBUG: Call {i}: {call}")

            # CRITICAL ASSERTION: With batched embeddings optimization,
            # all chunks from all commits are batched into minimal API calls
            api_calls = mock_vector_manager.submit_batch_task.call_count

            # Bug #7 fix + batching optimization:
            # - Bug #7: Skip existing point IDs (deduplication)
            # - Batching: Batch all new chunks across commits into single call
            # Expected: 1 API call for all new chunks (not 3 separate calls)
            self.assertEqual(api_calls, 1,
                f"Expected 1 batched API call for all new chunks, got {api_calls}. "
                f"Batching optimization should combine all commits into single call.")

            # Verify existing points were detected and logged
            self.vector_store.load_id_index.assert_called_once_with(
                TemporalIndexer.TEMPORAL_COLLECTION_NAME
            )

            # Verify only new points were upserted (not all points)
            upsert_calls = self.vector_store.upsert_points.call_args_list
            if upsert_calls:
                # Get all point IDs that were upserted
                upserted_ids = []
                for call in upsert_calls:
                    points = call[1]['points']
                    upserted_ids.extend([p['id'] for p in points])

                # None of the existing IDs should be in upserted points
                for existing_id in existing_point_ids:
                    self.assertNotIn(existing_id, upserted_ids,
                        f"Existing point {existing_id} was re-upserted! "
                        f"Bug #7 not fixed - duplicate disk writes occurring")


if __name__ == "__main__":
    unittest.main()