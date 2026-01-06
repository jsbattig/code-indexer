"""Test file size display during temporal git history indexing.

CRITICAL BUG FIX TEST (Display Regression - File Size):
User reported: "All sizes show 0.0 KB during temporal indexing"
Output shows: "b8c50aa8 - filename.ext (0.0 KB) complete ✓"
Should show: "b8c50aa8 - filename.ext (2.5 KB) complete ✓"

Root cause: FileData.file_size is set to 0 during acquire_slot() (line 394)
and NEVER updated because update_slot() doesn't support file_size parameter.

FIX STRATEGY: Don't acquire slot with placeholder data. Acquire slot ONLY when
we have REAL data (filename + size), just like semantic indexing does.

SEMANTIC INDEXING PATTERN (high_throughput_processor.py:350-356):
    file_data = FileData(
        filename=str(file_path.name),
        file_size=file_size,  # ✅ Real size from stat()
        status=FileStatus.PROCESSING,
    )
    slot_id = worker_slot_tracker.acquire_slot(file_data)

TEMPORAL INDEXING BROKEN PATTERN (temporal_indexer.py:391-397):
    slot_id = commit_slot_tracker.acquire_slot(
        FileData(
            filename=f"{commit.hash[:8]} - starting",
            file_size=0,  # ❌ Hardcoded 0, never updated
            status=FileStatus.STARTING,
        )
    )
"""

import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.clean_slot_tracker import (
    CleanSlotTracker,
)


class TestTemporalFileSizeDisplay(unittest.TestCase):
    """Test that file sizes display correctly during temporal indexing."""

    def test_slot_shows_diff_size_not_zero(self):
        """Test that slots show actual diff size, not 0.0 KB.

        CRITICAL BUG: User reports all sizes show 0.0 KB.
        Root cause: file_size=0 hardcoded at acquisition, never updated.
        Fix: Acquire slot with REAL diff size, like semantic indexing does.
        """
        # Setup
        test_dir = Path("/tmp/test-temporal-filesize-integration")

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

            # Mock progressive metadata to return empty set (no completed commits)
            indexer.progressive_metadata = Mock()
            indexer.progressive_metadata.load_completed.return_value = set()
            indexer.progressive_metadata.save_completed = Mock()

            # Mock diff scanner to return test diff with known size
            diff_content = "A" * 2560  # 2.5 KB of content
            indexer.diff_scanner = Mock()

            def get_diffs_side_effect(commit_hash):
                return [
                    Mock(
                        file_path="src/authentication.py",
                        diff_content=diff_content,  # 2560 bytes = 2.5 KB
                        diff_type="modified",
                        blob_hash=None,
                    ),
                ]

            indexer.diff_scanner.get_diffs_for_commit = Mock(
                side_effect=get_diffs_side_effect
            )

            # Mock chunker to return chunks (so processing happens)
            indexer.chunker = Mock()
            indexer.chunker.chunk_text.return_value = [
                {"text": "chunk1", "start_line": 0, "end_line": 10}
            ]

            # Mock vector manager
            mock_vector_manager = Mock()
            mock_vector_manager.cancellation_event = (
                threading.Event()
            )  # Required for worker threads
            mock_vector_manager.embedding_provider = Mock()
            mock_vector_manager.embedding_provider.get_current_model = Mock(
                return_value="voyage-code-2"
            )
            mock_vector_manager.embedding_provider._get_model_token_limit = Mock(
                return_value=120000
            )
            mock_future = Mock()
            mock_result = Mock()
            mock_result.embeddings = [[0.1] * 1536]  # One embedding
            mock_result.error = None  # No error
            mock_future.result.return_value = mock_result
            mock_vector_manager.submit_batch_task.return_value = mock_future

            # Mock vector store upsert
            vector_store.upsert_temporal_git_history = Mock()

            # Track slot states during update_slot (not just acquisition)
            captured_updates = []
            original_update = CleanSlotTracker.update_slot

            def capture_update(self, slot_id, status, filename=None, file_size=None):
                """Capture slot updates with file_size."""
                # Call original first
                result = original_update(
                    self, slot_id, status, filename=filename, file_size=file_size
                )

                # Capture state AFTER update
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
                        hash="abc12345def67890",
                        timestamp=1700000000,
                        author_name="Test Author",
                        author_email="test@example.com",
                        message="Test commit",
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

            # CRITICAL ASSERTIONS: Verify file_size was updated during processing

            self.assertGreater(
                len(captured_updates), 0, "Expected at least one slot update"
            )

            # Find updates with actual filename (not "starting")
            updates_with_filename = [
                u for u in captured_updates if "authentication.py" in u["filename"]
            ]

            self.assertGreater(
                len(updates_with_filename),
                0,
                f"Expected updates with actual filename. Got: {captured_updates}",
            )

            # Verify file_size is NOT zero
            for update in updates_with_filename:
                file_size = update["file_size"]
                self.assertGreater(
                    file_size,
                    0,
                    f"File size should be > 0, got {file_size}. Update: {update}",
                )

                # Verify file_size matches diff_content length
                expected_size = len(diff_content)  # 2560 bytes
                self.assertEqual(
                    file_size,
                    expected_size,
                    f"File size should be {expected_size} bytes, got {file_size}",
                )


if __name__ == "__main__":
    unittest.main()
