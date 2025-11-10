"""Test that temporal indexer skips already-indexed blobs."""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestBlobDeduplicationLogic:
    """Test deduplication logic in temporal indexer."""

    def test_temporal_indexer_skips_blobs_in_registry(self):
        """Test that temporal indexer skips blobs that are already in the registry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            import subprocess
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)

            # Create a file and commit
            test_file = repo_path / "test.py"
            test_file.write_text("print('hello')\n")
            subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

            # Setup
            config_manager = MagicMock()
            config = MagicMock()
            config.codebase_dir = repo_path
            config.voyage_ai.parallel_requests = 1
            config.voyage_ai.max_concurrent_batches_per_commit = 10
            config_manager.get_config.return_value = config

            index_dir = repo_path / ".code-indexer" / "index"
            vector_store = FilesystemVectorStore(base_path=index_dir, project_root=repo_path)

            with patch('src.code_indexer.services.embedding_factory.EmbeddingProviderFactory') as mock_factory:
                mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
                mock_provider = MagicMock()
                mock_factory.create.return_value = mock_provider

                temporal_indexer = TemporalIndexer(config_manager, vector_store)

                # Pre-populate the blob registry with a known blob hash
                test_blob_hash = "abc123def456"
                temporal_indexer.indexed_blobs.add(test_blob_hash)

                # Mock the diff scanner to return a diff with that blob hash
                with patch.object(temporal_indexer.diff_scanner, 'get_diffs_for_commit') as mock_get_diffs:
                    from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo

                    # Return a diff with the known blob hash
                    mock_get_diffs.return_value = [
                        DiffInfo(
                            file_path="test.py",
                            diff_type="added",
                            commit_hash="commit123",
                            diff_content="+print('hello')",
                            blob_hash=test_blob_hash  # This blob is already in the registry
                        )
                    ]

                    # Track vectorization calls
                    vectorization_called = False

                    with patch('src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager') as mock_vcm:
                        mock_manager = MagicMock()
                        mock_vcm.return_value.__enter__.return_value = mock_manager

                        # Mock cancellation_event (required by worker function)
                        import threading
                        mock_manager.cancellation_event = threading.Event()

                        # Mock embedding provider methods for token counting
                        mock_embedding_provider = MagicMock()
                        mock_embedding_provider._count_tokens_accurately = MagicMock(return_value=100)
                        mock_embedding_provider._get_model_token_limit = MagicMock(return_value=120000)
                        mock_manager.embedding_provider = mock_embedding_provider

                        def track_vectorization(chunk_texts, metadata):
                            nonlocal vectorization_called
                            vectorization_called = True
                            mock_future = MagicMock()
                            mock_result = MagicMock()
                            mock_result.embeddings = [[0.1] * 1024]
                            mock_result.error = None
                            mock_future.result.return_value = mock_result
                            return mock_future

                        mock_manager.submit_batch_task.side_effect = track_vectorization

                        # Get commits and process
                        commits = temporal_indexer._get_commit_history(False, 1, None)
                        if commits:
                            # Process the commit
                            temporal_indexer._process_commits_parallel(
                                commits, mock_provider, mock_manager
                            )

                        # Verify: Since the blob is already in the registry,
                        # vectorization should NOT be called
                        assert not vectorization_called, \
                            "Vectorization should not be called for blobs already in the registry"