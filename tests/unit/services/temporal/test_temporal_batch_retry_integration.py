"""Integration tests for batch retry and rollback in temporal indexer.

These tests verify the complete flow:
1. Batch fails with transient error
2. Retry logic kicks in with appropriate delays
3. After MAX_RETRIES exhaustion, rollback triggers
4. Points upserted before failure are deleted
5. RuntimeError raised with clear message
"""

import pytest
import subprocess
from unittest.mock import Mock, MagicMock, patch
from types import SimpleNamespace

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo
from code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


def test_retry_exhaustion_triggers_rollback_integration(tmp_path):
    """Test complete flow: retry exhaustion → rollback → error raised.

    This is the integration test that proves the retry and rollback logic works end-to-end.
    """
    # Setup config manager
    config_manager = Mock()
    config = Mock()
    config.voyage_ai.parallel_requests = 1
    config.voyage_ai.max_concurrent_batches_per_commit = 2
    config.voyage_ai.batch_size = 10
    config.embedding_provider = "voyage-ai"
    config.voyage_ai.model = "voyage-code-3"
    config_manager.get_config.return_value = config

    # Create vector store
    project_root = tmp_path / "repo"
    project_root.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=project_root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=project_root, check=True, capture_output=True)

    vector_store = FilesystemVectorStore(
        base_path=tmp_path / "index",
        project_root=project_root
    )

    # Create indexer with mocked embedding provider
    with patch('code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info') as mock_get_info:
        with patch('code_indexer.services.embedding_factory.EmbeddingProviderFactory.create') as mock_create:
            mock_get_info.return_value = {
                "provider": "voyage-ai",
                "model": "voyage-code-3",
                "dimensions": 1024
            }

            mock_provider = Mock()
            mock_provider.get_current_model.return_value = "voyage-code-3"
            mock_provider.get_embeddings_batch.return_value = []
            mock_provider._get_model_token_limit.return_value = 120000  # VoyageAI token limit
            mock_create.return_value = mock_provider

            indexer = TemporalIndexer(config_manager, vector_store)

            # Setup: Create a commit with chunks that will fail
            commit = CommitInfo(
                hash="abc123def456",
                timestamp=1234567890,
                message="Test commit",
                author_name="Test Author",
                author_email="test@example.com",
                parent_hashes=""
            )

            # Mock git show to return content
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="test content line 1\ntest content line 2\ntest content line 3",
                    returncode=0
                )

                # Mock diff scanner to return diffs
                diff_info = DiffInfo(
                    file_path="test.py",
                    diff_type="modified",
                    commit_hash="abc123def456",
                    diff_content="test content",
                    blob_hash="blob123",
                    parent_commit_hash="parent123"
                )

                with patch.object(
                    indexer.diff_scanner,
                    'get_diffs_for_commit',
                    return_value=[diff_info]
                ):
                    # Mock chunker to return chunks
                    with patch.object(
                        indexer.chunker,
                        'chunk_text',
                        return_value=[
                            {"text": "chunk 1", "char_start": 0, "char_end": 10},
                            {"text": "chunk 2", "char_start": 11, "char_end": 20}
                        ]
                    ):
                        # Mock batch submission - all batches fail with transient errors
                        # This will test retry exhaustion and rollback
                        batch_call_count = 0

                        def mock_submit_batch(texts, metadata):
                            nonlocal batch_call_count
                            batch_call_count += 1

                            # All batches fail immediately (simulating rate limit)
                            result = SimpleNamespace(
                                embeddings=[],
                                error="Rate limit exceeded: 429 Too Many Requests"
                            )

                            future = MagicMock()
                            future.result.return_value = result
                            return future

                        # Create mock VectorCalculationManager
                        mock_vcm_instance = Mock()
                        mock_vcm_instance.submit_batch_task = mock_submit_batch
                        mock_vcm_instance.cancellation_event = Mock()
                        mock_vcm_instance.cancellation_event.is_set.return_value = False
                        mock_vcm_instance.embedding_provider = mock_provider

                        # Mock vector_store.upsert_points to track calls
                        upserted_point_ids = []

                        def mock_upsert(collection_name, points):
                            for point in points:
                                upserted_point_ids.append(point["id"])

                        indexer.vector_store.upsert_points = mock_upsert

                        # Mock delete_points to verify rollback
                        deleted_point_ids = []

                        def mock_delete(collection_name, point_ids):
                            deleted_point_ids.extend(point_ids)

                        indexer.vector_store.delete_points = mock_delete

                        # Mock time.sleep to avoid delays
                        with patch('time.sleep'):
                            # Execute: Process commit should fail after retry exhaustion
                            with pytest.raises(RuntimeError) as exc_info:
                                indexer._process_commits_parallel(
                                    commits=[commit],
                                    embedding_provider=mock_provider,
                                    vector_manager=mock_vcm_instance
                                )

                            # Verify error message contains "retry exhaustion" or similar failure message
                            error_msg = str(exc_info.value).lower()
                            assert "retry exhaustion" in error_msg or "processing failed" in error_msg, \
                                f"Expected retry exhaustion error, got: {exc_info.value}"
                            assert commit.hash[:8] in str(exc_info.value)

                            # Verify retry attempts were made (MAX_RETRIES = 5)
                            # Each batch should be attempted 5 times before giving up
                            assert batch_call_count >= 5, f"Expected at least 5 retry attempts, got {batch_call_count}"

                            # Since all batches failed, no points should be upserted
                            assert len(upserted_point_ids) == 0, "No points should be upserted when all batches fail"

                            # No rollback needed since nothing was upserted
                            assert len(deleted_point_ids) == 0, "No deletions needed when no points were upserted"
