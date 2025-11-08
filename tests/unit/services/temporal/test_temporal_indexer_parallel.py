"""Tests for parallel processing in TemporalIndexer."""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import threading
import time
import tempfile

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


class TestTemporalIndexerParallel(unittest.TestCase):
    """Test parallel processing functionality in TemporalIndexer."""

    def setUp(self):
        """Set up test fixtures."""
        self.config_manager = Mock()
        self.config = Mock()
        self.config.voyage_ai.parallel_requests = 8
        self.config.embedding_provider = "voyage-ai"  # Set provider
        self.config.voyage_ai.model = "voyage-code-3"
        self.config_manager.get_config.return_value = self.config

        # Use temporary directory for test
        self.temp_dir = tempfile.mkdtemp()
        self.vector_store = Mock()
        self.vector_store.project_root = Path(self.temp_dir)
        self.vector_store.collection_exists.return_value = True
        self.vector_store.load_id_index.return_value = set()  # Return empty set for len() call

        # Mock EmbeddingProviderFactory to avoid real provider creation
        with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info') as mock_get_info:
            mock_get_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-3",
                "dimensions": 1024
            }
            self.indexer = TemporalIndexer(self.config_manager, self.vector_store)

        # Mock the diff scanner
        self.indexer.diff_scanner = Mock()

        # Mock the file identifier
        self.indexer.file_identifier = Mock()
        self.indexer.file_identifier.get_unique_project_id.return_value = "test-project"

        # Mock the chunker
        self.indexer.chunker = Mock()

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parallel_processing_uses_multiple_threads(self):
        """Test that parallel processing actually uses multiple threads."""
        # Create 10 test commits
        commits = [
            CommitInfo(
                hash=f"commit{i}",
                timestamp=1234567890 + i,
                author_name="Test Author",
                author_email="test@example.com",
                message=f"Test commit {i}",
                parent_hashes=""
            )
            for i in range(10)
        ]

        # Track which threads processed commits
        thread_ids = set()
        process_count = threading.Lock()
        processed = [0]

        def track_thread(*args):
            """Side effect to track thread IDs."""
            thread_ids.add(threading.current_thread().ident)
            with process_count:
                processed[0] += 1
            # Simulate some work
            time.sleep(0.01)
            return []  # Return empty diffs

        self.indexer.diff_scanner.get_diffs_for_commit.side_effect = track_thread

        # Mock vector manager
        vector_manager = Mock()

        # Process commits in parallel
        self.indexer._process_commits_parallel(
            commits,
            Mock(),  # embedding_provider
            vector_manager
        )

        # Should have processed all commits
        self.assertEqual(processed[0], 10)

        # Should have used multiple threads (not just 1)
        self.assertGreater(len(thread_ids), 1, "Should use multiple threads for parallel processing")

        # Should have called get_diffs_for_commit for each commit
        self.assertEqual(self.indexer.diff_scanner.get_diffs_for_commit.call_count, 10)

    def test_parallel_processing_handles_large_diffs(self):
        """Test that large diffs (500+ lines) are processed without truncation."""
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        from concurrent.futures import Future

        commits = [
            CommitInfo(
                hash="large_commit",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Large change",
                parent_hashes=""
            )
        ]

        # Create a large diff (500+ lines)
        large_diff_content = "\n".join([f"+line {i}" for i in range(600)])

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [
            DiffInfo(
                file_path="large_file.py",
                diff_type="added",
                commit_hash="large_commit",
                diff_content=large_diff_content
            )
        ]

        # Mock chunker to verify it receives the full content
        chunks_received = []
        def capture_chunks(text, path):
            # Capture the text passed to chunker
            chunks_received.append(text)
            # Return some chunks
            return [{"text": text[:100], "char_start": 0, "char_end": 100}]

        self.indexer.chunker.chunk_text.side_effect = capture_chunks

        # Mock vector manager
        vector_manager = Mock()
        future = Mock(spec=Future)
        future.result.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]], error=None)
        vector_manager.submit_batch_task.return_value = future
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Process the large commit
        self.indexer._process_commits_parallel(
            commits,
            Mock(),  # embedding_provider
            vector_manager
        )

        # Should have processed the large diff
        self.indexer.chunker.chunk_text.assert_called()

        # Verify the full content was passed to chunker (no truncation)
        self.assertEqual(len(chunks_received), 1, "Should have chunked once")
        lines_in_chunk = len(chunks_received[0].split("\n"))
        self.assertEqual(lines_in_chunk, 600, "Should pass full 600 lines to chunker without truncation")

    def test_parallel_processing_creates_correct_payloads(self):
        """Test that parallel processing creates correct payload structure."""
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        from concurrent.futures import Future

        commits = [
            CommitInfo(
                hash="test_commit_hash",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit message",
                parent_hashes=""
            )
        ]

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [
            DiffInfo(
                file_path="test.py",
                diff_type="modified",
                commit_hash="test_commit_hash",
                diff_content="+added line\n-removed line"
            )
        ]

        self.indexer.chunker.chunk_text.return_value = [
            {"text": "chunk", "char_start": 0, "char_end": 5}
        ]

        # Mock vector manager
        vector_manager = Mock()
        future = Mock(spec=Future)
        future.result.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]], error=None)
        vector_manager.submit_batch_task.return_value = future
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Capture the points that would be stored
        stored_points = []
        self.indexer.vector_store.upsert_points.side_effect = lambda collection_name, points: stored_points.extend(points)

        # Process commits
        self.indexer._process_commits_parallel(commits, Mock(), vector_manager)

        # Check that points were created with correct payload structure
        self.assertGreater(len(stored_points), 0, "Should have created points")

        point = stored_points[0]
        payload = point["payload"]

        # Verify required payload fields per acceptance criteria
        self.assertEqual(payload["type"], "commit_diff")
        self.assertEqual(payload["diff_type"], "modified")
        self.assertEqual(payload["commit_hash"], "test_commit_hash")
        self.assertEqual(payload["commit_timestamp"], 1234567890)
        self.assertIn("commit_date", payload)  # Human-readable date
        self.assertIn("commit_message", payload)
        self.assertEqual(payload["author_name"], "Test Author")
        self.assertEqual(payload["path"], "test.py")  # Changed from file_path to path (Story 2)
        self.assertNotIn("blob_hash", payload)  # Should NOT have blob_hash

    def test_parallel_processing_with_progress_callback(self):
        """Test that progress callback is called during parallel processing."""
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        from concurrent.futures import Future

        # Create test commits
        commits = [
            CommitInfo(
                hash=f"commit{i}",
                timestamp=1234567890 + i,
                author_name="Test Author",
                author_email="test@example.com",
                message=f"Test commit {i}",
                parent_hashes=""
            )
            for i in range(5)
        ]

        # Mock diffs for each commit
        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [
            DiffInfo(
                file_path="test.py",
                diff_type="modified",
                commit_hash="commit1",
                diff_content="+line1\n-line2"
            )
        ]

        # Mock chunker to return chunks
        self.indexer.chunker.chunk_text.return_value = [
            {"text": "chunk1", "char_start": 0, "char_end": 10}
        ]

        # Mock vector manager
        vector_manager = Mock()
        future = Mock(spec=Future)
        future.result.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]], error=None)
        vector_manager.submit_batch_task.return_value = future
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Track progress callbacks
        progress_calls = []
        def progress_callback(current, total, file_path, info="", **kwargs):
            """Accept new kwargs for slot-based tracking (concurrent_files, slot_tracker, item_type)."""
            progress_calls.append({
                "current": current,
                "total": total,
                "file_path": str(file_path),
                "info": info
            })

        # Process commits with progress callback
        self.indexer._process_commits_parallel(
            commits,
            Mock(),  # embedding_provider
            vector_manager,
            progress_callback=progress_callback
        )

        # Should have received progress updates
        self.assertGreater(len(progress_calls), 0, "Should have progress callbacks")

        # Check that progress info contains expected format
        for call in progress_calls:
            if call["info"]:  # Only check non-empty info
                # Should contain commits progress format
                self.assertIn("commits", call["info"])

    def test_parallel_processing_returns_totals(self):
        """Test that parallel processing returns total blobs and vectors processed."""
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        from concurrent.futures import Future

        commits = [
            CommitInfo(
                hash="test_commit",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit",
                parent_hashes=""
            )
        ]

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [
            DiffInfo(
                file_path="file1.py",
                diff_type="modified",
                commit_hash="test_commit",
                diff_content="+line1"
            ),
            DiffInfo(
                file_path="file2.py",
                diff_type="added",
                commit_hash="test_commit",
                diff_content="+line2"
            )
        ]

        self.indexer.chunker.chunk_text.return_value = [
            {"text": "chunk", "char_start": 0, "char_end": 5}
        ]

        # Mock vector manager - return embeddings matching chunk count
        def mock_submit(chunk_texts, metadata):
            future = Future()
            mock_result = Mock()
            # Return correct number of embeddings for chunks submitted
            mock_result.embeddings = [[0.1, 0.2, 0.3] for _ in chunk_texts]
            future.set_result(mock_result)
            return future

        vector_manager = Mock()
        vector_manager.submit_batch_task.side_effect = mock_submit
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Process commits and get return values
        total_blobs, total_vectors = self.indexer._process_commits_parallel(
            commits, Mock(), vector_manager
        )

        # Should return counts
        self.assertGreater(total_blobs, 0, "Should have processed blobs")
        self.assertGreater(total_vectors, 0, "Should have created vectors")

    def test_parallel_processing_skips_binary_and_renamed(self):
        """Test that parallel processing skips binary and renamed files."""
        from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
        from concurrent.futures import Future

        commits = [
            CommitInfo(
                hash="test_commit",
                timestamp=1234567890,
                author_name="Test Author",
                author_email="test@example.com",
                message="Test commit",
                parent_hashes=""
            )
        ]

        self.indexer.diff_scanner.get_diffs_for_commit.return_value = [
            DiffInfo(
                file_path="binary.jpg",
                diff_type="binary",
                commit_hash="test_commit",
                diff_content="Binary file added: binary.jpg"
            ),
            DiffInfo(
                file_path="renamed.py",
                diff_type="renamed",
                commit_hash="test_commit",
                diff_content="File renamed from old.py to renamed.py",
                old_path="old.py"
            ),
            DiffInfo(
                file_path="normal.py",
                diff_type="modified",
                commit_hash="test_commit",
                diff_content="+normal change"
            )
        ]

        # Track which files get chunked
        chunked_files = []
        def track_chunks(text, path):
            chunked_files.append(str(path))
            return [{"text": "chunk", "char_start": 0, "char_end": 5}]

        self.indexer.chunker.chunk_text.side_effect = track_chunks

        # Mock vector manager
        vector_manager = Mock()
        future = Mock(spec=Future)
        future.result.return_value = Mock(embeddings=[[0.1, 0.2, 0.3]], error=None)
        vector_manager.submit_batch_task.return_value = future
        vector_manager.embedding_provider._get_model_token_limit.return_value = 120000

        # Process commits
        self.indexer._process_commits_parallel(commits, Mock(), vector_manager)

        # Only normal.py should be chunked (binary and renamed are skipped)
        self.assertEqual(len(chunked_files), 1, "Should only chunk one file")
        self.assertEqual(chunked_files[0], "normal.py", "Should only chunk normal.py")


if __name__ == "__main__":
    unittest.main()