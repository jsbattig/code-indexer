"""Tests for temporal indexer batch processing error handling and rollback.

Tests anti-fallback compliance: NO partial commit data in index.
Tests retry logic: Batch failures retry up to 5 times with exponential backoff.
Tests rollback: Failed commits have all points deleted from vector store.
Tests logging: Comprehensive failure diagnostics logged.

Anti-Fallback Principle (Messi Rule #2):
- Never leave partial commit data in index
- Failed commits must be rolled back completely
- Better to fail explicitly than hide problems
"""

import pytest
import logging
import time
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from types import SimpleNamespace
import numpy as np

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestBatchRetryLogic:
    """Test batch-level retry logic with error classification."""

    def test_batch_retries_on_transient_error_succeeds_on_third_attempt(self, tmp_path):
        """
        GIVEN batch processing fails with timeout error twice
        WHEN worker processes batch
        THEN batch is retried with exponential backoff
        AND succeeds on third attempt
        AND all embeddings are stored

        AC: Transient errors (timeout, 503, connection) trigger retry

        NOTE: This test currently fails because retry logic doesn't exist yet.
        Expected behavior: Current code stops on first error without retrying.
        """
        # Setup mocks
        config_manager = Mock()
        config = Mock()
        config.voyage_ai.parallel_requests = 1  # Single thread for predictable behavior
        config.voyage_ai.max_concurrent_batches_per_commit = 1
        config.embedding_provider = "voyage-ai"
        config.voyage_ai.model = "voyage-code-3"
        config_manager.get_config.return_value = config

        # Create vector store
        project_root = tmp_path / "repo"
        project_root.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(
            ["git", "init"], cwd=project_root, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=project_root,
            check=True,
            capture_output=True,
        )

        vector_store = FilesystemVectorStore(
            base_path=tmp_path / "index", project_root=project_root
        )

        # Create indexer with mocked embedding provider
        with patch(
            "code_indexer.services.embedding_factory.EmbeddingProviderFactory.get_provider_model_info"
        ) as mock_get_info:
            with patch(
                "code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"
            ) as mock_create:
                mock_get_info.return_value = {
                    "provider": "voyage-ai",
                    "model": "voyage-code-3",
                    "dimensions": 1024,
                }

                # Mock embedding provider
                mock_provider = Mock()
                mock_provider.get_current_model.return_value = "voyage-code-3"
                mock_provider.get_embeddings_batch.return_value = []
                mock_provider._get_model_token_limit.return_value = (
                    120000  # VoyageAI token limit
                )
                mock_create.return_value = mock_provider

                indexer = TemporalIndexer(config_manager, vector_store)

                # Track batch submission attempts
                attempt_count = [0]

                def mock_submit_batch(texts, metadata):
                    """Simulate timeout on first 2 attempts, success on 3rd."""
                    from concurrent.futures import Future

                    future = Future()
                    attempt_count[0] += 1

                    if attempt_count[0] <= 2:
                        # Return error result (transient timeout)
                        result = SimpleNamespace(
                            embeddings=[], error="Request timeout after 120s"
                        )
                    else:
                        # Success on 3rd attempt
                        result = SimpleNamespace(
                            embeddings=[np.random.rand(1024).tolist() for _ in texts],
                            error=None,
                        )

                    future.set_result(result)
                    return future

                # Mock diff scanner
                from code_indexer.services.temporal.temporal_diff_scanner import (
                    DiffInfo,
                )

                mock_diffs = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="modified",
                        commit_hash="abc123",
                        diff_content="test content",
                        blob_hash="blob1",
                        parent_commit_hash="parent1",
                    )
                ]

                indexer.diff_scanner.get_diffs_for_commit = Mock(
                    return_value=mock_diffs
                )

                # Mock chunker
                indexer.chunker.chunk_text = Mock(
                    return_value=[
                        {
                            "text": "chunk1",
                            "start_line": 1,
                            "end_line": 5,
                            "char_start": 0,
                            "char_end": 100,
                        }
                    ]
                )

                # Create commit
                commit = CommitInfo(
                    hash="abc123",
                    message="Test commit",
                    timestamp=int(time.time()),
                    author_name="Test",
                    author_email="test@test.com",
                    parent_hashes="",
                )

                # Create mock VectorCalculationManager
                mock_vcm_instance = Mock()
                mock_vcm_instance.submit_batch_task = mock_submit_batch
                mock_vcm_instance.cancellation_event = Mock()
                mock_vcm_instance.cancellation_event.is_set.return_value = False
                mock_vcm_instance.embedding_provider = mock_provider

                # Process commit (should retry and succeed)
                try:
                    result = indexer._process_commits_parallel(
                        commits=[commit],
                        embedding_provider=mock_provider,
                        vector_manager=mock_vcm_instance,
                    )
                except Exception as e:
                    # Currently expected to fail because retry logic doesn't exist
                    pytest.fail(
                        f"Test failed with expected error (retry logic not implemented): {e}"
                    )

                # VERIFY: Batch was attempted 3 times (with retry logic)
                assert (
                    attempt_count[0] == 3
                ), f"Should retry twice and succeed on 3rd attempt, got {attempt_count[0]} attempts"

                # VERIFY: Final embeddings were stored (no partial data)
                point_count = vector_store.count_points("code-indexer-temporal")
                assert point_count > 0, "Should store embeddings after successful retry"
