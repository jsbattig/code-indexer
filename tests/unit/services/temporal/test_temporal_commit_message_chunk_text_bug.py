"""
Test for critical bug: commit message text not stored in chunk_text field.

STORY ISSUE: #476
BUG: The _index_commit_message() method creates points without chunk_text field,
     causing commit messages to have empty content when queried.

LOCATION: src/code_indexer/services/temporal/temporal_indexer.py ~line 1213-1218

This test verifies that commit message points contain actual commit message text
in the chunk_text field, not empty strings.
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch


from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestCommitMessageChunkTextBug:
    """Test that commit message points have populated chunk_text field."""

    def test_commit_message_point_contains_chunk_text_field(self):
        """
        FAILING TEST: Verify upsert_points receives chunk_text in point dict.

        This test demonstrates the bug by verifying that when _index_commit_message
        calls vector_store.upsert_points(), the points contain a chunk_text field.

        The bug is on line 1213-1217 where the point dict is constructed without
        including chunk_text.

        Expected behavior:
        - Points passed to upsert_points should include chunk_text field
        - chunk_text should contain the actual commit message text
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            repo_path = tmpdir_path / "test_repo"
            repo_path.mkdir()

            # Initialize git repo (required by FilesystemVectorStore)
            subprocess.run(
                ["git", "init"], cwd=repo_path, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            # Create config manager mock
            config_manager = Mock()
            config = Mock()
            config.voyage_ai.parallel_requests = 1
            config.voyage_ai.max_concurrent_batches_per_commit = 2
            config.voyage_ai.batch_size = 10
            config.embedding_provider = "voyage-ai"
            config.voyage_ai.model = "voyage-code-3"
            config.temporal.diff_context_lines = 3
            config.chunking.chunk_size = 1000
            config.chunking.chunk_overlap = 0
            config_manager.get_config.return_value = config

            # Create vector store (will be spied on)
            index_dir = tmpdir_path / "index"
            index_dir.mkdir()
            vector_store = FilesystemVectorStore(
                base_path=index_dir, project_root=repo_path
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

                    mock_provider = Mock()
                    mock_provider.get_current_model.return_value = "voyage-code-3"
                    mock_provider.get_embeddings_batch.return_value = [[0.1] * 1024]
                    mock_provider._get_model_token_limit.return_value = 120000
                    mock_create.return_value = mock_provider

                    indexer = TemporalIndexer(config_manager, vector_store)

                    # Create a commit with a detailed message
                    commit_message = "feat: add foo function\n\nThis commit adds a new function called foo that will be used for testing purposes. The function is intentionally simple to verify commit message indexing works correctly."
                    commit = CommitInfo(
                        hash="abc123def456789",
                        timestamp=1234567890,
                        message=commit_message,
                        author_name="Test Author",
                        author_email="test@example.com",
                        parent_hashes="",
                    )

                    # Mock the vector manager with proper embedding response
                    mock_vector_manager = Mock()
                    mock_result = Mock()
                    mock_result.error = None
                    mock_result.embeddings = [
                        [0.1] * 1024
                    ]  # One embedding for the commit message
                    mock_future = Mock()
                    mock_future.result.return_value = mock_result
                    mock_vector_manager.submit_batch_task.return_value = mock_future

                    # Spy on vector_store.upsert_points to capture what's passed to it
                    original_upsert = vector_store.upsert_points
                    upsert_spy_calls = []

                    def upsert_spy(*args, **kwargs):
                        upsert_spy_calls.append((args, kwargs))
                        return original_upsert(*args, **kwargs)

                    vector_store.upsert_points = upsert_spy

                    # Call _index_commit_message directly
                    project_id = "test_project"
                    indexer._index_commit_message(
                        commit, project_id, mock_vector_manager
                    )

            # VERIFICATION: Check that upsert_points was called with points containing chunk_text
            assert len(upsert_spy_calls) > 0, "upsert_points was never called"

            # Get the points that were passed to upsert_points
            call_args, call_kwargs = upsert_spy_calls[0]

            # Extract points from the call
            if "points" in call_kwargs:
                points = call_kwargs["points"]
            else:
                # Assuming positional args: (collection_name, points)
                points = call_args[1] if len(call_args) > 1 else call_args[0]

            assert len(points) > 0, "No points were passed to upsert_points"

            # Check the first point
            first_point = points[0]

            # BUG DEMONSTRATION: chunk_text field should exist in the point
            assert "chunk_text" in first_point, (
                "BUG CONFIRMED: chunk_text field missing from point dictionary. "
                "Fix required in temporal_indexer.py _index_commit_message() method line 1213-1217. "
                f"Point keys: {list(first_point.keys())}"
            )

            chunk_text = first_point["chunk_text"]

            # Verify chunk_text is not empty
            assert chunk_text != "", (
                "BUG CONFIRMED: chunk_text field is empty. "
                "The commit message text was not stored in the point."
            )

            # Verify chunk_text contains the actual commit message
            assert "feat: add foo function" in chunk_text, (
                f"BUG: chunk_text does not contain expected commit message. "
                f"Got: {chunk_text!r}"
            )

            assert "testing purposes" in chunk_text, (
                f"BUG: chunk_text missing commit body text. " f"Got: {chunk_text!r}"
            )

            # Verify the text length is reasonable (not truncated to empty)
            assert len(chunk_text) > 50, (
                f"BUG: chunk_text is too short ({len(chunk_text)} chars). "
                f"Expected full commit message. Got: {chunk_text!r}"
            )
