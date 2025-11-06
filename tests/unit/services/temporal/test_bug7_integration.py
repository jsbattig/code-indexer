"""
Integration test for Bug #7: Tests the actual _process_commits_parallel method.

This test verifies that the implementation correctly:
1. Checks existence BEFORE making API calls
2. Uses correct chunk indices when creating points
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo


class TestBug7Integration(unittest.TestCase):
    """Integration test for Bug #7 fix in actual implementation."""

    def test_process_commits_parallel_skips_existing_and_uses_correct_indices(self):
        """
        Test that _process_commits_parallel:
        1. Skips API calls for existing chunks
        2. Creates points with correct original indices
        """
        # Setup mocks
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(parallel_requests=1)  # Use 1 thread for simplicity
        config_manager.get_config.return_value = mock_config

        vector_store = MagicMock()
        vector_store.project_root = Path("/tmp/test")
        vector_store.collection_exists.return_value = True

        # Existing points - chunks 0 and 1 already exist for commit1:file.py
        existing_point_ids = {
            "test-project:diff:commit1:file.py:0",
            "test-project:diff:commit1:file.py:1",
        }
        vector_store.load_id_index.return_value = existing_point_ids

        # Track upserted points
        upserted_points = []
        def capture_upsert(collection_name, points):
            upserted_points.extend(points)
        vector_store.upsert_points.side_effect = capture_upsert

        with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory') as MockFactory:
            MockFactory.get_provider_model_info.return_value = {"dimensions": 1024}
            MockFactory.create.return_value = MagicMock()

            # Create indexer
            indexer = TemporalIndexer(config_manager, vector_store)

            # Mock the file identifier
            with patch.object(indexer.file_identifier, '_get_project_id') as mock_project_id:
                mock_project_id.return_value = "test-project"

                # Mock the diff scanner
                with patch.object(indexer.diff_scanner, 'get_diffs_for_commit') as mock_get_diffs:
                    # Return one diff with content that will be chunked
                    mock_get_diffs.return_value = [
                        DiffInfo(
                            file_path="file.py",
                            diff_type="modified",
                            commit_hash="commit1",
                            diff_content="+line1\n+line2\n+line3\n" * 50,  # Long enough for multiple chunks
                            blob_hash=""
                        )
                    ]

                    # Mock the chunker to return 3 chunks
                    with patch.object(indexer.chunker, 'chunk_text') as mock_chunk:
                        mock_chunk.return_value = [
                            {"text": "chunk0_existing", "char_start": 0, "char_end": 100},
                            {"text": "chunk1_existing", "char_start": 100, "char_end": 200},
                            {"text": "chunk2_new", "char_start": 200, "char_end": 300},
                        ]

                        # Mock VectorCalculationManager
                        with patch('src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager') as MockVectorManager:
                            mock_vector_manager = MagicMock()
                            MockVectorManager.return_value.__enter__ = MagicMock(return_value=mock_vector_manager)
                            MockVectorManager.return_value.__exit__ = MagicMock(return_value=None)

                            # Track API calls
                            api_calls = []
                            def track_api_call(texts, metadata):
                                api_calls.append(texts)
                                future = MagicMock()
                                result = MagicMock()
                                # Return embeddings for the chunks we received
                                result.embeddings = [[0.1, 0.2, 0.3] for _ in texts]
                                future.result.return_value = result
                                return future

                            mock_vector_manager.submit_batch_task.side_effect = track_api_call

                            # Create test commits
                            commits = [
                                CommitInfo(
                                    hash="commit1",
                                    timestamp=1234567890,
                                    author_name="Test",
                                    author_email="test@test.com",
                                    message="Test commit",
                                    parent_hashes=""
                                )
                            ]

                            # Call the actual implementation
                            total_blobs, total_vectors = indexer._process_commits_parallel(
                                commits,
                                MockFactory.create.return_value,  # embedding_provider
                                mock_vector_manager,
                                progress_callback=None
                            )

                            # ASSERTIONS

                            # 1. Verify only 1 API call was made (for the new chunk)
                            self.assertEqual(len(api_calls), 1,
                                f"Should make 1 API call for new chunk only, made {len(api_calls)} calls")

                            # 2. Verify the API call was for chunk2_new only
                            if api_calls:
                                self.assertEqual(len(api_calls[0]), 1,
                                    "API call should contain exactly 1 chunk text")
                                self.assertEqual(api_calls[0][0], "chunk2_new",
                                    f"API call should be for chunk2_new, got {api_calls[0][0]}")

                            # 3. Verify only 1 point was upserted (for chunk2)
                            self.assertEqual(len(upserted_points), 1,
                                f"Should upsert 1 point, upserted {len(upserted_points)}")

                            # 4. Verify the point ID uses the correct original index (:2)
                            if upserted_points:
                                point_id = upserted_points[0]["id"]
                                self.assertTrue(point_id.endswith(":2"),
                                    f"Point ID should end with :2, got {point_id}")

                                # 5. Verify the payload has correct chunk_index
                                chunk_index = upserted_points[0]["payload"]["chunk_index"]
                                self.assertEqual(chunk_index, 2,
                                    f"Payload chunk_index should be 2, got {chunk_index}")


if __name__ == "__main__":
    unittest.main()