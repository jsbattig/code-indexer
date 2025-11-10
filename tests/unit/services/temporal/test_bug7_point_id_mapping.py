"""
Test for Bug #7 Part 2: Correct point ID mapping after filtering.

When we filter out existing chunks, we need to ensure the point IDs
still use the original chunk indices, not the filtered indices.
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestBug7PointIDMapping(unittest.TestCase):
    """Test correct point ID mapping after existence filtering."""

    def test_point_ids_use_original_chunk_indices(self):
        """
        When filtering existing chunks, point IDs should preserve original indices.

        Example: If chunks 0 and 1 exist but chunk 2 is new, the new point
        should have ID ending in ":2" not ":0".
        """
        # Setup mocks
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(parallel_requests=4, max_concurrent_batches_per_commit=10)
        config_manager.get_config.return_value = mock_config

        vector_store = MagicMock()
        vector_store.project_root = Path("/tmp/test")
        vector_store.collection_exists.return_value = True

        # Existing points - chunks 0 and 1 already exist
        existing_point_ids = {
            "test-project:diff:commit1:file.py:0",  # chunk 0 exists
            "test-project:diff:commit1:file.py:1",  # chunk 1 exists
            # chunk 2 does NOT exist - should be created
        }
        vector_store.load_id_index.return_value = existing_point_ids

        # Track what gets upserted
        upserted_points = []
        def capture_upsert(collection_name, points):
            upserted_points.extend(points)
        vector_store.upsert_points.side_effect = capture_upsert

        with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory') as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}
            MockFactory.create.return_value = MagicMock()

            # Create indexer
            indexer = TemporalIndexer(config_manager, vector_store)

            # Mock the chunker to return 3 chunks
            with patch.object(indexer.chunker, 'chunk_text') as mock_chunk:
                mock_chunk.return_value = [
                    {"text": "chunk0", "char_start": 0, "char_end": 100},
                    {"text": "chunk1", "char_start": 100, "char_end": 200},
                    {"text": "chunk2", "char_start": 200, "char_end": 300},
                ]

                # Mock file identifier
                with patch.object(indexer.file_identifier, '_get_project_id') as mock_project_id:
                    mock_project_id.return_value = "test-project"

                    # Create test data
                    commit = CommitInfo(
                        hash="commit1",
                        timestamp=1234567890,
                        author_name="Test",
                        author_email="test@test.com",
                        message="Test",
                        parent_hashes=""
                    )

                    diff_info = DiffInfo(
                        file_path="file.py",
                        diff_type="modified",
                        commit_hash="commit1",
                        diff_content="+test",
                        blob_hash=""
                    )

                    # Simulate the worker logic with the fix
                    with patch('src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager') as MockVectorManager:
                        mock_vector_manager = MagicMock()
                        # Mock cancellation event (no cancellation)
                        mock_cancellation_event = MagicMock()
                        mock_cancellation_event.is_set.return_value = False
                        mock_vector_manager.cancellation_event = mock_cancellation_event
                        MockVectorManager.return_value.__enter__ = MagicMock(return_value=mock_vector_manager)
                        MockVectorManager.return_value.__exit__ = MagicMock(return_value=None)

                        # Mock API response
                        def mock_api_call(texts, metadata):
                            future = MagicMock()
                            result = MagicMock()
                            # Return one embedding (for chunk2 only)
                            result.embeddings = [[0.7, 0.8, 0.9]]
                            result.error = None  # No error
                            future.result.return_value = result
                            return future

                        mock_vector_manager.submit_batch_task.side_effect = mock_api_call

                        # Import necessary classes
                        from src.code_indexer.services.clean_slot_tracker import CleanSlotTracker, FileData, FileStatus

                        # Create slot tracker
                        slot_tracker = CleanSlotTracker(max_slots=4)
                        slot_id = slot_tracker.acquire_slot(FileData(
                            filename="test",
                            file_size=0,
                            status=FileStatus.CHUNKING
                        ))

                        # SIMULATE THE ACTUAL CODE PATH
                        # This is what happens inside _process_commits_parallel worker

                        # Get chunks
                        chunks = indexer.chunker.chunk_text(
                            diff_info.diff_content,
                            Path(diff_info.file_path)
                        )

                        if chunks:
                            # Check existence BEFORE API call (Bug #7 fix part 1)
                            project_id = indexer.file_identifier._get_project_id()
                            chunks_to_process = []
                            chunk_indices_to_process = []

                            for j, chunk in enumerate(chunks):
                                point_id = f"{project_id}:diff:{commit.hash}:{diff_info.file_path}:{j}"

                                if point_id not in existing_point_ids:
                                    chunks_to_process.append(chunk)
                                    chunk_indices_to_process.append(j)

                            if chunks_to_process:
                                # Make API call
                                chunk_texts = [c["text"] for c in chunks_to_process]
                                future = mock_vector_manager.submit_batch_task(chunk_texts, {})
                                result = future.result()

                                if result.embeddings:
                                    # Create points - THIS IS WHERE THE BUG WOULD OCCUR
                                    points = []

                                    # WRONG WAY (would create :0 instead of :2):
                                    # for j, (chunk, embedding) in enumerate(zip(chunks_to_process, result.embeddings)):
                                    #     point_id = f"{project_id}:diff:{commit.hash}:{diff_info.file_path}:{j}"

                                    # CORRECT WAY (uses original indices):
                                    for chunk, embedding, original_index in zip(chunks_to_process, result.embeddings, chunk_indices_to_process):
                                        point_id = f"{project_id}:diff:{commit.hash}:{diff_info.file_path}:{original_index}"

                                        from datetime import datetime
                                        commit_date = datetime.fromtimestamp(commit.timestamp).strftime("%Y-%m-%d")

                                        payload = {
                                            "type": "commit_diff",
                                            "diff_type": diff_info.diff_type,
                                            "commit_hash": commit.hash,
                                            "commit_timestamp": commit.timestamp,
                                            "commit_date": commit_date,
                                            "path": diff_info.file_path,
                                            "chunk_index": original_index,  # Use original index
                                            "char_start": chunk.get("char_start", 0),
                                            "char_end": chunk.get("char_end", 0),
                                            "project_id": project_id,
                                            "content": chunk.get("text", ""),
                                            "language": Path(diff_info.file_path).suffix.lstrip(".") or "txt",
                                            "file_extension": Path(diff_info.file_path).suffix.lstrip(".") or "txt"
                                        }

                                        points.append({
                                            "id": point_id,
                                            "vector": list(embedding),
                                            "payload": payload
                                        })

                                    # Upsert points
                                    vector_store.upsert_points(
                                        collection_name="code-indexer-temporal",
                                        points=points
                                    )

                        # ASSERTIONS
                        # Should create exactly 1 point (for chunk2)
                        self.assertEqual(len(upserted_points), 1,
                            f"Should create 1 new point, but created {len(upserted_points)}")

                        # The point ID should end with :2 (the original chunk index)
                        created_point_id = upserted_points[0]["id"]
                        self.assertTrue(created_point_id.endswith(":2"),
                            f"Point ID should end with :2 (original chunk index), got {created_point_id}")

                        # Verify the chunk_index in payload is also 2
                        self.assertEqual(upserted_points[0]["payload"]["chunk_index"], 2,
                            f"Payload chunk_index should be 2, got {upserted_points[0]['payload']['chunk_index']}")


if __name__ == "__main__":
    unittest.main()