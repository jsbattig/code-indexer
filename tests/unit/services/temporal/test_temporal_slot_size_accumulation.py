"""Test size accumulation for multi-file commits in temporal indexing.

BUG: Slot tracker shows only LAST diff file size instead of TOTAL commit size.

EXPECTED BEHAVIOR:
├─ aaf9f31e - Vectorizing 30% (924/3012 chunks) (1.3 MB)
                                                 ^^^^^^^^ Total of all diffs

ACTUAL BEHAVIOR:
├─ aaf9f31e - Vectorizing 30% (924/3012 chunks) (10.0 KB)
                                                 ^^^^^^^^^ Size of LAST diff only!

ROOT CAUSE (temporal_indexer.py):
Lines 592-612: Loop OVERWRITES file_size for each diff instead of accumulating
Line 653: Transition to VECTORIZING doesn't pass file_size (keeps stale value)

THE FIX:
1. Add cumulative size tracking: total_commit_size = 0
2. Accumulate during diff loop: total_commit_size += diff_size
3. Pass total when transitioning to VECTORIZING: file_size=total_commit_size
4. Keep total during progress updates: file_size=total_commit_size

This test verifies the fix works correctly for multi-file commits.
"""

import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker, FileStatus


class TestTemporalSlotSizeAccumulation(unittest.TestCase):
    """Test that slot tracker accumulates total commit size across all diffs."""

    def test_multi_file_commit_shows_total_size_not_last_file(self):
        """Test that multi-file commit shows TOTAL size of all diffs, not just last file.

        CRITICAL BUG: With 3 files (500B + 800B + 200B), slot shows 200B instead of 1500B.
        Root cause: file_size overwritten for each diff, not accumulated.

        This test will FAIL before fix and PASS after fix.
        """
        # Setup
        test_dir = Path("/tmp/test-temporal-size-accumulation")

        # Mock ConfigManager
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 2
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-2"
        config_manager.get_config.return_value = config

        # Mock FilesystemVectorStore
        vector_store = Mock()
        vector_store.project_root = test_dir
        vector_store.base_path = test_dir / ".code-indexer" / "index"
        vector_store.load_id_index.return_value = set()  # No existing points

        with (
            patch("src.code_indexer.services.file_identifier.FileIdentifier"),
            patch(
                "src.code_indexer.services.temporal.temporal_diff_scanner.TemporalDiffScanner"
            ),
            patch("src.code_indexer.indexing.fixed_size_chunker.FixedSizeChunker"),
            patch(
                "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
            ) as mock_provider_info,
        ):

            # Mock the embedding provider info
            mock_provider_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-2",
                "dimensions": 1536,
                "model_info": {"dimension": 1536},
            }

            # Create indexer
            indexer = TemporalIndexer(
                config_manager=config_manager, vector_store=vector_store
            )

            # Mock progressive metadata
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner to return THREE diffs with different sizes
            diff1_content = "A" * 500  # 500 bytes
            diff2_content = "B" * 800  # 800 bytes
            diff3_content = "C" * 200  # 200 bytes
            # TOTAL = 1500 bytes
            # BUG would show: 200 bytes (last file only)
            # FIX should show: 1500 bytes (total)

            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                return [
                    Mock(
                        file_path="src/auth.py",
                        diff_content=diff1_content,  # 500 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path="src/database.py",
                        diff_content=diff2_content,  # 800 bytes
                        diff_type="modified",
                        blob_hash=None,
                    ),
                    Mock(
                        file_path="src/utils.py",
                        diff_content=diff3_content,  # 200 bytes (LAST file)
                        diff_type="modified",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker to return chunks for each diff
            indexer.chunker = Mock()

            def chunk_side_effect(content, file_path):
                # Return different number of chunks based on content size
                if len(content) == 500:
                    return [
                        {
                            "text": f"chunk{i}",
                            "start_line": i * 10,
                            "end_line": (i + 1) * 10,
                        }
                        for i in range(2)
                    ]
                elif len(content) == 800:
                    return [
                        {
                            "text": f"chunk{i}",
                            "start_line": i * 10,
                            "end_line": (i + 1) * 10,
                        }
                        for i in range(3)
                    ]
                else:  # 200
                    return [{"text": "chunk0", "start_line": 0, "end_line": 10}]

            indexer.chunker.chunk_text = Mock(side_effect=chunk_side_effect)

            # Mock vector manager
            mock_vector_manager = Mock()
            mock_vector_manager.cancellation_event = threading.Event()
            mock_vector_manager.embedding_provider = Mock()
            mock_vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            mock_vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )

            # Mock batch task to return embeddings
            mock_future = Mock()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1536] * 6  # 6 total chunks (2+3+1)
            mock_result.error = None
            mock_future.result.return_value = mock_result
            mock_vector_manager.submit_batch_task.return_value = mock_future

            # Mock vector store upsert
            vector_store.upsert_temporal_git_history = Mock()

            # Track slot updates to verify size accumulation
            captured_updates = []
            original_update = CleanSlotTracker.update_slot

            def capture_update(self, slot_id, status, filename=None, file_size=None):
                """Capture slot updates with file_size."""
                result = original_update(
                    self, slot_id, status, filename=filename, file_size=file_size
                )

                with self._lock:
                    file_data = self.status_array[slot_id]
                    if file_data:
                        captured_updates.append(
                            {
                                "slot_id": slot_id,
                                "filename": file_data.filename,
                                "file_size": file_data.file_size,
                                "status": file_data.status,
                            }
                        )

                return result

            with patch.object(CleanSlotTracker, "update_slot", capture_update):
                # Create test commit
                commits = [
                    CommitInfo(
                        hash="aaf9f31eabcd1234",
                        timestamp=1700000000,
                        author_name="Test Author",
                        author_email="test@example.com",
                        message="Multi-file test commit",
                        parent_hashes="",
                    )
                ]

                # Run processing
                indexer._process_commits_parallel(
                    commits=commits,
                    embedding_provider=Mock(),
                    vector_manager=mock_vector_manager,
                    progress_callback=None,
                )

            # CRITICAL ASSERTIONS: Verify VECTORIZING status shows TOTAL size (1500), not last file (200)

            # Find all VECTORIZING updates
            vectorizing_updates = [
                u for u in captured_updates if u["status"] == FileStatus.VECTORIZING
            ]

            self.assertGreater(
                len(vectorizing_updates),
                0,
                f"Expected VECTORIZING updates. All updates: {captured_updates}",
            )

            # Verify EVERY vectorizing update shows total size (1500 bytes)
            expected_total_size = 500 + 800 + 200  # 1500 bytes
            for update in vectorizing_updates:
                file_size = update["file_size"]

                # THE CRITICAL ASSERTION: Must show TOTAL (1500), not LAST (200)
                self.assertEqual(
                    file_size,
                    expected_total_size,
                    f"VECTORIZING should show total commit size {expected_total_size} bytes, "
                    f"but got {file_size} bytes. "
                    f"BUG: Showing last file (200B) instead of total (1500B)!\n"
                    f"Update: {update}\n"
                    f"All VECTORIZING updates: {vectorizing_updates}",
                )


if __name__ == "__main__":
    unittest.main()
