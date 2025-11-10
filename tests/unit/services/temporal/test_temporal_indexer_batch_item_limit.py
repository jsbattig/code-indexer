"""Tests for VoyageAI 1,000 item batch size limit in TemporalIndexer.

BUG: temporal_indexer.py line 625 only enforces TOKEN_LIMIT (108k tokens) but not
VoyageAI's 1,000 ITEM COUNT limit, causing API rejections with HTTP 400 errors.

This test validates that batches respect BOTH limits:
- Token limit: 108,000 tokens (90% of 120k)
- Item limit: 1,000 items per batch

ERROR MESSAGE FROM PRODUCTION:
VoyageAI API error (HTTP 400): The batch size limit is 1000. Your batch size is 1331.
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
from concurrent.futures import Future

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestTemporalIndexerBatchItemLimit(unittest.TestCase):
    """Test VoyageAI 1,000 item batch size limit enforcement."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_manager = Mock()
        self.config = Mock()
        self.config.voyage_ai.parallel_requests = 8
        self.config.voyage_ai.max_concurrent_batches_per_commit = 10
        self.config.embedding_provider = "voyage-ai"
        self.config.voyage_ai.model = "voyage-code-3"
        self.config_manager.get_config.return_value = self.config

        # Use temporary directory for test
        self.temp_dir = tempfile.mkdtemp()
        self.vector_store = Mock()
        self.vector_store.project_root = Path(self.temp_dir)
        self.vector_store.collection_exists.return_value = True
        self.vector_store.load_id_index.return_value = set()

        # Mock EmbeddingProviderFactory
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
        ) as mock_get_info:
            mock_get_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-3",
                "dimensions": 1024,
            }
            self.indexer = TemporalIndexer(self.config_manager, self.vector_store)

        # Mock the diff scanner
        self.indexer.diff_scanner = Mock()

        # Mock the file identifier
        self.indexer.file_identifier = Mock()
        self.indexer.file_identifier._get_project_id.return_value = "test-project"

        # Mock the chunker
        self.indexer.chunker = Mock()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_enforces_1000_item_batch_limit(self):
        """Test that batches are split at 1,000 items even if under token limit.

        REPRODUCTION CASE:
        - Commit with 1,331 small chunks (well under token limit)
        - Each chunk is only 10 tokens (13,310 total tokens << 108,000 limit)
        - Current code creates single batch with 1,331 items
        - VoyageAI rejects with HTTP 400: "batch size limit is 1000"

        EXPECTED BEHAVIOR AFTER FIX:
        - Split into 2 batches: [1000 items] + [331 items]
        - Both batches stay under token limit AND item limit
        """
        # Create commit with 1,331 small chunks (reproduces production error)
        commit = CommitInfo(
            hash="test-commit-1331-items",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Commit with 1,331 small chunks exceeding item limit",
            parent_hashes="parent-hash",
        )

        # Create diff that will produce 1,331 small chunks
        # Each chunk is only 10 tokens (way under token limit, but over item limit)
        diff = DiffInfo(
            file_path="src/large_file_many_chunks.py",
            diff_type="modified",
            commit_hash="test-commit-1331-items",
            diff_content="small chunk\n" * 2000,  # Enough for 1,331 chunks
            blob_hash="blob-1331",
            parent_commit_hash="parent-hash",
        )

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [diff]

        # Mock chunker to return exactly 1,331 small chunks
        def mock_chunk_many_small(content, path):
            return [
                {
                    "text": f"small chunk {j}",  # Only ~3 tokens each
                    "char_start": j * 20,
                    "char_end": (j + 1) * 20,
                }
                for j in range(1331)  # Exact count from production error
            ]

        self.indexer.chunker.chunk_text.side_effect = mock_chunk_many_small

        # Track batch sizes submitted to API
        submitted_batch_sizes = []

        def mock_submit_batch(chunk_texts, metadata):
            """Track batch sizes to verify 1,000 item limit enforcement."""
            batch_size = len(chunk_texts)
            submitted_batch_sizes.append(batch_size)

            # FAIL if any batch exceeds 1,000 items (simulates VoyageAI rejection)
            if batch_size > 1000:
                raise RuntimeError(
                    f"VoyageAI API error (HTTP 400): The batch size limit is 1000. "
                    f"Your batch size is {batch_size}."
                )

            # Create mock future with embeddings
            future = Future()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1024 for _ in chunk_texts]
            mock_result.error = None
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_batch

        # Mock token limit (120k) - our chunks are tiny, so token limit won't trigger
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Mock cancellation event
        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # Process the commit
        # BEFORE FIX: This will raise RuntimeError about batch size 1331
        # AFTER FIX: Should succeed with batches of [1000, 331]
        try:
            self.indexer._process_commits_parallel([commit], Mock(), vector_manager)
            processing_succeeded = True
        except RuntimeError as e:
            processing_succeeded = False
            error_message = str(e)

        # ASSERTIONS
        print("\n=== Batch Item Limit Test ===")
        print(f"Processing succeeded: {processing_succeeded}")
        print(f"Submitted batch sizes: {submitted_batch_sizes}")

        if not processing_succeeded:
            print(f"ERROR: {error_message}")
            print("\nFAILING: Batch exceeded 1,000 item limit!")
            print("Expected: Batches split at 1,000 items [1000, 331]")
            print(
                f"Actual: Single batch with {submitted_batch_sizes[0] if submitted_batch_sizes else 0} items"
            )

        # AFTER FIX: Should succeed with proper batch splitting
        self.assertTrue(
            processing_succeeded,
            f"Processing failed due to batch size exceeding 1,000 items. "
            f"Batches: {submitted_batch_sizes}",
        )

        # AFTER FIX: Should have 2 batches
        self.assertEqual(
            len(submitted_batch_sizes),
            2,
            f"Expected 2 batches for 1,331 items, got {len(submitted_batch_sizes)}",
        )

        # AFTER FIX: First batch should be exactly 1,000 items
        self.assertEqual(
            submitted_batch_sizes[0],
            1000,
            f"First batch should be 1,000 items, got {submitted_batch_sizes[0]}",
        )

        # AFTER FIX: Second batch should be remaining 331 items
        self.assertEqual(
            submitted_batch_sizes[1],
            331,
            f"Second batch should be 331 items, got {submitted_batch_sizes[1]}",
        )

        # AFTER FIX: All batches should be ≤ 1,000 items
        for i, size in enumerate(submitted_batch_sizes):
            self.assertLessEqual(
                size, 1000, f"Batch {i+1} has {size} items, exceeds 1,000 item limit"
            )

        # Verify all chunks were processed
        total_chunks = sum(submitted_batch_sizes)
        self.assertEqual(
            total_chunks,
            1331,
            f"Should process all 1,331 chunks, processed {total_chunks}",
        )

    def test_item_limit_with_multiple_batches(self):
        """Test that item limit is enforced across multiple token-based batches.

        EDGE CASE:
        - Commit with 2,500 small chunks
        - Should create 3 batches: [1000, 1000, 500]
        - Validates both token AND item limits work together
        """
        commit = CommitInfo(
            hash="test-commit-2500-items",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Commit with 2,500 chunks for multi-batch test",
            parent_hashes="parent-hash",
        )

        diff = DiffInfo(
            file_path="src/very_large_file.py",
            diff_type="modified",
            commit_hash="test-commit-2500-items",
            diff_content="chunk\n" * 5000,
            blob_hash="blob-2500",
            parent_commit_hash="parent-hash",
        )

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [diff]

        # Mock chunker to return 2,500 small chunks
        def mock_chunk_2500(content, path):
            return [
                {"text": f"chunk {j}", "char_start": j * 10, "char_end": (j + 1) * 10}
                for j in range(2500)
            ]

        self.indexer.chunker.chunk_text.side_effect = mock_chunk_2500

        submitted_batch_sizes = []

        def mock_submit_batch(chunk_texts, metadata):
            batch_size = len(chunk_texts)
            submitted_batch_sizes.append(batch_size)

            if batch_size > 1000:
                raise RuntimeError(f"Batch size {batch_size} exceeds 1,000 limit")

            future = Future()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1024 for _ in chunk_texts]
            mock_result.error = None
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_batch
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # Process the commit
        self.indexer._process_commits_parallel([commit], Mock(), vector_manager)

        # ASSERTIONS
        print("\n=== Multi-Batch Item Limit Test ===")
        print(f"Batch sizes: {submitted_batch_sizes}")

        # Should have 3 batches: [1000, 1000, 500]
        self.assertEqual(len(submitted_batch_sizes), 3)
        self.assertEqual(submitted_batch_sizes[0], 1000)
        self.assertEqual(submitted_batch_sizes[1], 1000)
        self.assertEqual(submitted_batch_sizes[2], 500)

        # All batches ≤ 1,000
        for size in submitted_batch_sizes:
            self.assertLessEqual(size, 1000)

        # All chunks processed
        self.assertEqual(sum(submitted_batch_sizes), 2500)


if __name__ == "__main__":
    unittest.main()
