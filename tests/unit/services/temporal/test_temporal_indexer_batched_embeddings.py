"""Tests for batched embeddings in TemporalIndexer.

This test suite validates that TemporalIndexer batches all chunks from all diffs
within a commit into minimal API calls, respecting the 120,000 token limit.

EXPECTED BEHAVIOR:
- Commit with 10 diffs → 1-3 API calls (not 10 sequential calls)
- Batch respects 120,000 token limit
- Deduplication still works
- Point IDs and payloads identical to sequential implementation
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
from concurrent.futures import Future

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestTemporalIndexerBatchedEmbeddings(unittest.TestCase):
    """Test batched embedding API calls in TemporalIndexer."""

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
        self.vector_store.base_path = Path(self.temp_dir) / ".code-indexer" / "index"
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

    def test_batches_all_diffs_in_commit(self):
        """Test that all diffs in a commit are batched into minimal API calls.

        CURRENT BEHAVIOR (FAILING):
        - 10 diffs with 5 chunks each = 50 total chunks
        - Makes 10 sequential API calls (one per diff)
        - Each call waits for future.result() before processing next diff

        EXPECTED BEHAVIOR (AFTER FIX):
        - Batch all 50 chunks into 1-2 API calls (depending on token limit)
        - Submit all batches at once, wait for results together
        - Map results back to correct diffs for point creation

        NOTE: With commit message vectorization, we get:
        - 10 files × 5 chunks = 50 file diff chunks
        - 1 commit × 1 message chunk = 1 commit message chunk
        - Total: 51 chunks
        """
        # Create commit with 10 diffs
        commit = CommitInfo(
            hash="test-commit-123",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Test commit with multiple diffs",
            parent_hashes="parent-hash",
        )

        # Create 10 diffs, each will produce 5 chunks
        diffs = []
        for i in range(10):
            diff = DiffInfo(
                file_path=f"src/file_{i}.py",
                diff_type="modified",
                commit_hash="test-commit-123",
                diff_content=f"def function_{i}():\n    # File {i} content\n    pass\n"
                * 20,  # Enough content for 5 chunks
                blob_hash=f"blob-hash-{i}",
                parent_commit_hash="parent-hash",
            )
            diffs.append(diff)

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = diffs

        # Mock chunker to return 5 chunks per diff OR 1 chunk for commit message
        def mock_chunk_text(content, path):
            # If this is a commit message (path contains '[commit:')
            if "[commit:" in str(path):
                return [
                    {
                        "text": content,  # Return the commit message as-is
                        "char_start": 0,
                        "char_end": len(content),
                    }
                ]
            # Otherwise return 5 chunks for file diffs
            return [
                {
                    "text": f"chunk {j} content from {path}",
                    "char_start": j * 100,
                    "char_end": (j + 1) * 100,
                }
                for j in range(5)
            ]

        self.indexer.chunker.chunk_text.side_effect = mock_chunk_text

        # Track API calls to vector manager
        api_call_count = [0]
        submitted_batches = []

        def mock_submit_batch(chunk_texts, metadata):
            """Track each API call and return mock future."""
            api_call_count[0] += 1
            submitted_batches.append(chunk_texts)

            # Create mock future with embeddings
            future = Future()
            mock_result = Mock()
            mock_result.embeddings = [
                [0.1] * 1024 for _ in chunk_texts
            ]  # Mock embeddings
            mock_result.error = None  # No error
            future.set_result(mock_result)
            return future

        # Mock vector manager
        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_batch

        # Mock token limit from provider (120k)
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Mock cancellation event (required for worker threads)
        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # Process the commit
        self.indexer._process_commits_parallel(
            [commit], Mock(), vector_manager  # embedding_provider
        )

        # ASSERTIONS
        # Current implementation makes 10 API calls (one per diff)
        # After fix, should make 1-2 calls (all 51 chunks batched: 50 diffs + 1 commit message)
        print("\n=== API Call Analysis ===")
        print(f"Total API calls: {api_call_count[0]}")
        print("Expected: 1-2 calls (batched)")
        print(f"Actual: {api_call_count[0]} calls")

        if api_call_count[0] > 3:
            print("\nFAILING: Too many API calls! Should batch all diffs together.")
            print("Batch details:")
            for i, batch in enumerate(submitted_batches):
                print(f"  Batch {i+1}: {len(batch)} chunks")

        # After fix, this should pass
        self.assertLessEqual(
            api_call_count[0],
            3,
            f"Expected 1-3 batched API calls, got {api_call_count[0]} sequential calls",
        )

        # Verify all chunks were processed (50 file diffs + 1 commit message)
        total_chunks_submitted = sum(len(batch) for batch in submitted_batches)
        self.assertEqual(
            total_chunks_submitted,
            51,
            "Should process all 51 chunks (50 file diffs + 1 commit message)",
        )

    def test_token_limit_enforcement_large_commit(self):
        """Test that large commits exceeding 120k token limit are split into multiple batches.

        ISSUE #1: MISSING TOKEN LIMIT ENFORCEMENT (CRITICAL)

        PROBLEM:
        - Large commits (100+ files) can exceed 120,000 token VoyageAI limit
        - Current code submits all chunks in one batch without token counting
        - API rejects entire commit, causing complete failure

        EXPECTED BEHAVIOR:
        - Count tokens for each chunk using voyage tokenizer
        - Split into multiple batches at 108,000 tokens (90% of 120k limit)
        - Submit multiple batches if needed
        - Merge results before point creation

        NOTE: With commit message vectorization, we get:
        - 50 file diff chunks + 1 commit message chunk = 51 total chunks
        """
        # Create commit with chunks totaling 200k tokens
        commit = CommitInfo(
            hash="large-commit-456",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Large commit exceeding token limit",
            parent_hashes="parent-hash",
        )

        # Create 1 diff with very large content (simulating 200k tokens)
        # Each chunk will be ~4000 tokens, 50 chunks = 200k tokens total
        large_content = "x" * 16000  # ~4000 tokens per chunk (4 chars ≈ 1 token)
        diff = DiffInfo(
            file_path="src/large_file.py",
            diff_type="modified",
            commit_hash="large-commit-456",
            diff_content=large_content * 50,  # Large enough for 50 chunks
            blob_hash="large-blob-hash",
            parent_commit_hash="parent-hash",
        )

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [diff]

        # Mock chunker to return 50 large chunks for file diff, 1 chunk for commit message
        def mock_chunk_large(content, path):
            # If this is a commit message (path contains '[commit:')
            if "[commit:" in str(path):
                return [
                    {
                        "text": content,  # Return the commit message as-is
                        "char_start": 0,
                        "char_end": len(content),
                    }
                ]
            # Otherwise return 50 large chunks for file diff
            return [
                {
                    "text": large_content,  # ~4000 tokens each
                    "char_start": j * 16000,
                    "char_end": (j + 1) * 16000,
                }
                for j in range(50)
            ]

        self.indexer.chunker.chunk_text.side_effect = mock_chunk_large

        # Track API calls and batch sizes
        submitted_batches = []

        def mock_submit_batch(chunk_texts, metadata):
            """Track batch sizes - should see multiple batches."""
            submitted_batches.append(len(chunk_texts))

            # Create mock future with embeddings
            future = Future()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1024 for _ in chunk_texts]
            mock_result.error = None  # No error
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_batch

        # Mock token limit from provider (120k)
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Mock cancellation event (required for worker threads)
        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # Process the commit
        self.indexer._process_commits_parallel([commit], Mock(), vector_manager)

        # ASSERTIONS
        print("\n=== Token Limit Test ===")
        print(f"Total batches: {len(submitted_batches)}")
        print(f"Batch sizes: {submitted_batches}")
        print("Expected: 2+ batches (200k tokens > 108k limit)")

        # After fix: Should split into 2+ batches (200k tokens > 108k limit)
        self.assertGreaterEqual(
            len(submitted_batches),
            2,
            f"Expected 2+ batches for 200k tokens, got {len(submitted_batches)} batch(es)",
        )

        # Verify all chunks were processed (50 file diffs + 1 commit message)
        total_chunks = sum(submitted_batches)
        self.assertEqual(
            total_chunks,
            51,
            "Should process all 51 chunks across batches (50 file diffs + 1 commit message)",
        )

    def test_embedding_count_validation(self):
        """Test that mismatched embedding counts raise clear errors.

        ISSUE #2: NO EMBEDDING COUNT VALIDATION (HIGH)

        PROBLEM:
        - If API returns partial results, zip() silently truncates
        - Incomplete indexing with no error
        - Data loss without detection

        EXPECTED BEHAVIOR:
        - Validate len(result.embeddings) == len(all_chunks_data)
        - Raise RuntimeError with clear message on mismatch
        - Never silently truncate results
        """
        commit = CommitInfo(
            hash="partial-result-789",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Commit with partial API results",
            parent_hashes="parent-hash",
        )

        # Create diff that will produce 10 chunks
        diff = DiffInfo(
            file_path="src/test.py",
            diff_type="modified",
            commit_hash="partial-result-789",
            diff_content="def function():\n    pass\n" * 50,
            blob_hash="test-blob",
            parent_commit_hash="parent-hash",
        )

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [diff]

        # Mock chunker to return 10 chunks
        def mock_chunk(content, path):
            return [
                {
                    "text": f"chunk {j} content",
                    "char_start": j * 100,
                    "char_end": (j + 1) * 100,
                }
                for j in range(10)
            ]

        self.indexer.chunker.chunk_text.side_effect = mock_chunk

        # Mock API to return PARTIAL results (only 7 embeddings for 10 chunks)
        def mock_submit_partial(chunk_texts, metadata):
            future = Future()
            mock_result = Mock()
            # BUG: API returned only 7 embeddings for 10 chunks!
            mock_result.embeddings = [[0.1] * 1024 for _ in range(7)]
            mock_result.error = None  # No error
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_partial
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Mock cancellation event (required for worker threads)
        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # After fix: Should raise RuntimeError with clear message
        with self.assertRaises(RuntimeError) as context:
            self.indexer._process_commits_parallel([commit], Mock(), vector_manager)

        # Verify error message is clear
        error_msg = str(context.exception)
        self.assertIn("Expected 10 embeddings", error_msg)
        self.assertIn("got 7", error_msg)

    def test_empty_chunks_edge_case(self):
        """Test that commits with no processable chunks are handled correctly.

        ISSUE #3: EMPTY CHUNKS EDGE CASE (HIGH)

        PROBLEM:
        - If all diffs are binary/renamed/already indexed, all_chunks_data is empty
        - No API call made (correct)
        - Slot never marked complete (BUG)
        - Worker might hang or show incorrect status

        EXPECTED BEHAVIOR:
        - If all_chunks_data is empty, mark slot COMPLETE
        - No API calls made
        - Commit shown as successfully processed

        NOTE: With commit message vectorization, even if all file diffs are skipped,
        we still vectorize the commit message, so API will be called once.
        """
        commit = CommitInfo(
            hash="empty-commit-abc",
            timestamp=1234567890,
            author_name="Test Author",
            author_email="test@example.com",
            message="Commit with only binary/renamed files",
            parent_hashes="parent-hash",
        )

        # Create diffs that will be skipped (binary + renamed)
        diffs = [
            DiffInfo(
                file_path="image.png",
                diff_type="binary",
                commit_hash="empty-commit-abc",
                diff_content="",
                blob_hash="binary-blob",
                parent_commit_hash="parent-hash",
            ),
            DiffInfo(
                file_path="old_name.py",
                diff_type="renamed",
                commit_hash="empty-commit-abc",
                diff_content="",
                blob_hash="renamed-blob",
                parent_commit_hash="parent-hash",
            ),
        ]

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = diffs

        # Mock chunker to handle commit message
        def mock_chunk_text(content, path):
            # If this is a commit message (path contains '[commit:')
            if "[commit:" in str(path):
                return [
                    {
                        "text": content,
                        "char_start": 0,
                        "char_end": len(content),
                    }
                ]
            # For binary/renamed files, return empty list
            return []

        self.indexer.chunker.chunk_text.side_effect = mock_chunk_text

        # Track API calls - should be 1 (commit message only)
        api_call_count = [0]

        def mock_submit_batch(chunk_texts, metadata):
            api_call_count[0] += 1
            future = Future()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1024 for _ in chunk_texts]
            mock_result.error = None
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit_batch
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Mock cancellation event (required for worker threads)
        mock_cancellation_event = Mock()
        mock_cancellation_event.is_set.return_value = False
        vector_manager.cancellation_event = mock_cancellation_event

        # Process the commit
        self.indexer._process_commits_parallel([commit], Mock(), vector_manager)

        # ASSERTIONS
        print("\n=== Empty Chunks Test ===")
        print(f"API calls: {api_call_count[0]}")
        print("Expected: 1 (commit message only, all file diffs skipped)")

        # After fix: Should have 1 API call for commit message
        self.assertEqual(
            api_call_count[0],
            1,
            "Should call API once for commit message even when all file diffs are skipped",
        )

        # After fix: Verify slot was marked COMPLETE
        # (This will be validated by checking that the method doesn't hang/error)


if __name__ == "__main__":
    unittest.main()
