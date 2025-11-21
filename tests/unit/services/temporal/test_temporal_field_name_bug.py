"""Test for Bug #1: Field name mismatch (file_path vs path) in temporal indexing.

This test verifies that temporal indexing uses the correct field name ("path")
for git-aware storage optimization in FilesystemVectorStore.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        import subprocess

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
        )

        # Create and commit a file
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
        )

        yield repo_path


class TestTemporalFieldNameBug:
    """Test suite for temporal indexing field name bug."""

    def test_temporal_payload_uses_path_field_not_file_path(self, temp_repo):
        """Test that temporal indexer uses 'path' field in payload, not 'file_path'.

        Bug #1: Temporal indexing uses 'file_path' in payload, but FilesystemVectorStore
        expects 'path' for git-aware storage optimization.
        """
        # Setup
        config_manager = MagicMock()
        config = MagicMock()
        config.codebase_dir = temp_repo
        config.voyage_ai.parallel_requests = 1
        config.voyage_ai.max_concurrent_batches_per_commit = 10
        config_manager.get_config.return_value = config
        config_manager.load.return_value = config

        # Create real FilesystemVectorStore
        index_dir = temp_repo / ".code-indexer" / "index"
        vector_store = FilesystemVectorStore(
            base_path=index_dir, project_root=temp_repo
        )

        # Mock embedding provider
        with patch(
            "src.code_indexer.services.embedding_factory.EmbeddingProviderFactory"
        ) as mock_factory:
            # Mock provider info
            mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}

            # Mock embedding provider
            mock_provider = MagicMock()
            mock_factory.create.return_value = mock_provider

            # Create temporal indexer
            temporal_indexer = TemporalIndexer(config_manager, vector_store)

            # Spy on upsert_points to capture payload
            captured_points = []
            original_upsert = vector_store.upsert_points

            def capture_upsert(collection_name, points):
                captured_points.extend(points)
                return original_upsert(collection_name, points)

            vector_store.upsert_points = capture_upsert

            # Mock diff scanner to return diffs
            from src.code_indexer.services.temporal.temporal_diff_scanner import (
                DiffInfo,
            )

            with patch.object(
                temporal_indexer.diff_scanner, "get_diffs_for_commit"
            ) as mock_get_diffs:
                mock_get_diffs.return_value = [
                    DiffInfo(
                        file_path="test.py",
                        diff_type="added",
                        commit_hash="abc123",
                        diff_content="+print('hello')",
                        old_path="",
                    )
                ]

                # Mock VectorCalculationManager
                with patch(
                    "src.code_indexer.services.temporal.temporal_indexer.VectorCalculationManager"
                ) as mock_vcm:
                    mock_manager = MagicMock()
                    mock_vcm.return_value.__enter__.return_value = mock_manager

                    # Mock cancellation_event (required by worker function)
                    import threading

                    mock_manager.cancellation_event = threading.Event()

                    # Mock embedding provider methods for token counting
                    mock_embedding_provider = MagicMock()
                    mock_embedding_provider._count_tokens_accurately = MagicMock(
                        return_value=100
                    )
                    mock_embedding_provider._get_model_token_limit = MagicMock(
                        return_value=120000
                    )
                    mock_manager.embedding_provider = mock_embedding_provider

                    # Mock embedding result
                    def mock_submit_batch(texts, metadata):
                        mock_future = MagicMock()
                        mock_result = MagicMock()
                        mock_result.embeddings = [[0.1] * 1024 for _ in texts]
                        mock_result.error = None
                        mock_future.result.return_value = mock_result
                        return mock_future

                    mock_manager.submit_batch_task.side_effect = mock_submit_batch

                    # Run temporal indexing
                    temporal_indexer.index_commits(max_commits=1)

                    # Verify points were captured
                    assert len(captured_points) > 0, "No points were created"

                    # Check that payload uses 'path' field, not 'file_path'
                    # Filter to only check file diff points (commit messages don't have paths)
                    file_diff_points = [
                        point
                        for point in captured_points
                        if point["payload"].get("type") != "commit_message"
                    ]

                    assert len(file_diff_points) > 0, "No file diff points were created"

                    for point in file_diff_points:
                        payload = point["payload"]

                        # Bug verification: Currently uses 'file_path' (WRONG)
                        # After fix: Should use 'path' (CORRECT)

                        # This assertion will FAIL with current code (proving bug exists)
                        # and will PASS after fix
                        assert (
                            "path" in payload
                        ), f"Payload missing 'path' field: {payload.keys()}"
                        assert "file_path" not in payload or payload.get(
                            "path"
                        ) == payload.get(
                            "file_path"
                        ), "Payload should use 'path' not 'file_path' for git-aware storage"
