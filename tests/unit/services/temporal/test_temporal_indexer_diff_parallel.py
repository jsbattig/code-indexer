"""Tests for TemporalIndexer diff-based indexing with parallel processing.

Following TDD methodology - tests first, then implementation.
"""

from unittest.mock import patch, MagicMock

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.temporal_diff_scanner import DiffInfo
from src.code_indexer.config import ConfigManager
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalIndexerDiffBasedParallel:
    """Test suite for diff-based temporal indexing with parallel processing."""

    def test_index_commits_uses_diff_scanner_not_blob_scanner(self, tmp_path):
        """Test that index_commits uses TemporalDiffScanner instead of blob scanner."""
        # Setup
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True
        )

        # Create a test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Setup indexer
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True)
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        vector_store_path = config_dir / "index" / "default"
        vector_store_path.mkdir(parents=True)
        vector_store = FilesystemVectorStore(vector_store_path, project_root=repo_path)

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            indexer = TemporalIndexer(config_manager, vector_store)

            # Mock the diff scanner
            with patch.object(
                indexer.diff_scanner, "get_diffs_for_commit"
            ) as mock_get_diffs:
                mock_get_diffs.return_value = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="added",
                        commit_hash="abc123",
                        diff_content="+def hello():\n+    return 'world'",
                        old_path="",
                    )
                ]

                # Mock VectorCalculationManager
                import threading

                with patch(
                    "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                ) as mock_vcm:
                    mock_manager = MagicMock()
                    mock_manager.cancellation_event = threading.Event()
                    mock_embedding_provider = MagicMock()
                    mock_embedding_provider._count_tokens_accurately = MagicMock(
                        return_value=100
                    )
                    mock_embedding_provider._get_model_token_limit = MagicMock(
                        return_value=120000
                    )
                    mock_manager.embedding_provider = mock_embedding_provider

                    def mock_submit_batch(texts, metadata):
                        mock_future = MagicMock()
                        mock_result = MagicMock()
                        mock_result.embeddings = [[0.1] * 1024 for _ in texts]
                        mock_result.error = None
                        mock_future.result.return_value = mock_result
                        return mock_future

                    mock_manager.submit_batch_task.side_effect = mock_submit_batch
                    mock_manager.__enter__ = MagicMock(return_value=mock_manager)
                    mock_manager.__exit__ = MagicMock(return_value=None)
                    mock_vcm.return_value = mock_manager

                    # Run indexing
                    indexer.index_commits(all_branches=False, max_commits=1)

                    # Verify diff scanner was called
                    assert mock_get_diffs.called
                    # Should NOT have references to blob_scanner
                    assert not hasattr(indexer, "blob_scanner")
                    assert not hasattr(indexer, "blob_registry")
                    assert not hasattr(indexer, "blob_reader")

    def test_index_commits_chunks_diffs(self, tmp_path):
        """Test that diff content is properly chunked."""
        # Setup
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True
        )

        # Create a test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Setup indexer
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True)
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        vector_store_path = config_dir / "index" / "default"
        vector_store_path.mkdir(parents=True)
        vector_store = FilesystemVectorStore(vector_store_path, project_root=repo_path)

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            indexer = TemporalIndexer(config_manager, vector_store)

            # Track what gets chunked
            chunked_texts = []

            def capture_chunk_text(text, file_path):
                chunked_texts.append(text)
                return [{"text": text, "line_start": 0, "line_end": 2}]  # Fake chunk

            # Mock the diff scanner and chunker
            with patch.object(
                indexer.diff_scanner, "get_diffs_for_commit"
            ) as mock_get_diffs:
                mock_get_diffs.return_value = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="added",
                        commit_hash="abc123",
                        diff_content="+def hello():\n+    return 'world'",
                        old_path="",
                    )
                ]

                with patch.object(
                    indexer.chunker, "chunk_text", side_effect=capture_chunk_text
                ):
                    # Mock VectorCalculationManager
                    import threading

                    with patch(
                        "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                    ) as mock_vcm:
                        mock_manager = MagicMock()
                        mock_manager.cancellation_event = threading.Event()
                        mock_embedding_provider = MagicMock()
                        mock_embedding_provider._count_tokens_accurately = MagicMock(
                            return_value=100
                        )
                        mock_embedding_provider._get_model_token_limit = MagicMock(
                            return_value=120000
                        )
                        mock_manager.embedding_provider = mock_embedding_provider

                        def mock_submit_batch(texts, metadata):
                            mock_future = MagicMock()
                            mock_result = MagicMock()
                            mock_result.embeddings = [[0.1] * 1024 for _ in texts]
                            mock_result.error = None
                            mock_future.result.return_value = mock_result
                            return mock_future

                        mock_manager.submit_batch_task.side_effect = mock_submit_batch
                        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
                        mock_manager.__exit__ = MagicMock(return_value=None)
                        mock_vcm.return_value = mock_manager

                        # Run indexing
                        indexer.index_commits(all_branches=False, max_commits=1)

                        # Verify diff content was chunked
                        assert (
                            len(chunked_texts) > 0
                        ), "Should have chunked diff content"
                        assert "+def hello()" in chunked_texts[0]

    def test_index_commits_processes_diffs_into_vectors(self, tmp_path):
        """Test that diffs are properly chunked and converted to vectors with correct payload."""
        # Setup
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=repo_path, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True
        )

        # Create a test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        # Setup indexer
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True)
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        vector_store_path = config_dir / "index" / "default"
        vector_store_path.mkdir(parents=True)
        vector_store = FilesystemVectorStore(vector_store_path, project_root=repo_path)

        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            indexer = TemporalIndexer(config_manager, vector_store)

            # Mock the diff scanner to return a known diff
            with patch.object(
                indexer.diff_scanner, "get_diffs_for_commit"
            ) as mock_get_diffs:
                mock_get_diffs.return_value = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="added",
                        commit_hash="abc123",
                        diff_content="+def hello():\n+    return 'world'",
                        old_path="",
                    )
                ]

                # Mock the vector store to capture what's being stored
                stored_points = []
                original_upsert = vector_store.upsert_points

                def capture_upsert(collection_name, points):
                    stored_points.extend(points)
                    return original_upsert(collection_name, points)

                with patch.object(
                    vector_store, "upsert_points", side_effect=capture_upsert
                ):
                    # Mock VectorCalculationManager
                    import threading

                    with patch(
                        "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                    ) as mock_vcm:
                        mock_manager = MagicMock()
                        mock_manager.cancellation_event = threading.Event()
                        mock_embedding_provider = MagicMock()
                        mock_embedding_provider._count_tokens_accurately = MagicMock(
                            return_value=100
                        )
                        mock_embedding_provider._get_model_token_limit = MagicMock(
                            return_value=120000
                        )
                        mock_manager.embedding_provider = mock_embedding_provider

                        def mock_submit_batch(texts, metadata):
                            mock_future = MagicMock()
                            mock_result = MagicMock()
                            mock_result.embeddings = [[0.1] * 1024 for _ in texts]
                            mock_result.error = None
                            mock_future.result.return_value = mock_result
                            return mock_future

                        mock_manager.submit_batch_task.side_effect = mock_submit_batch
                        mock_manager.__enter__ = MagicMock(return_value=mock_manager)
                        mock_manager.__exit__ = MagicMock(return_value=None)
                        mock_vcm.return_value = mock_manager

                        # Run indexing
                        indexer.index_commits(all_branches=False, max_commits=1)

                    # Verify vectors were created
                    assert len(stored_points) > 0, "Should have created vector points"

                    # Check payload structure
                    first_point = stored_points[0]
                    payload = first_point["payload"]

                    # Verify payload has correct diff-based fields (Story 1 requirements)
                    assert (
                        payload["type"] == "commit_diff"
                    ), "Should be commit_diff type"
                    assert "commit_hash" in payload
                    assert "commit_timestamp" in payload
                    assert "commit_date" in payload
                    assert "commit_message" in payload
                    assert "path" in payload  # Note: field is 'path', not 'file_path'
                    assert payload["diff_type"] == "added"
                    assert "blob_hash" not in payload, "Should NOT have blob_hash"
