"""Unit tests for commit message vectorization (Story #476 AC1).

Tests commit message chunk creation and integration into temporal indexing workflow.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


@pytest.fixture
def mock_config():
    """Create mock config with required attributes."""
    config = MagicMock()
    config.temporal.diff_context_lines = 3
    config.voyage_ai.parallel_requests = 2
    config.embedding_provider = "voyage-ai"
    # Mock voyage_ai config for EmbeddingProviderFactory
    config.voyage_ai.model = "voyage-code-3"
    return config


@pytest.fixture
def mock_config_manager(mock_config):
    """Create mock config manager."""
    manager = MagicMock()
    manager.get_config.return_value = mock_config
    return manager


@pytest.fixture
def mock_vector_store(tmp_path):
    """Create mock vector store."""
    store = MagicMock()
    store.project_root = tmp_path
    store.base_path = tmp_path / ".code-indexer" / "index"
    store.collection_exists.return_value = True
    store.load_id_index.return_value = []
    return store


@pytest.fixture
def temporal_indexer(mock_config_manager, mock_vector_store):
    """Create TemporalIndexer instance for testing."""
    return TemporalIndexer(mock_config_manager, mock_vector_store)


class TestCommitMessageChunkCreation:
    """Test AC1: Commit messages vectorized during temporal indexing."""

    def test_index_commit_message_creates_chunk_with_full_message(
        self, temporal_indexer
    ):
        """Test that commit message is chunked and stored completely (not truncated)."""
        # Arrange
        long_message = "Fix authentication timeout bug\n\n" + ("Details. " * 100)
        commit = CommitInfo(
            hash="abc123def456",
            timestamp=1704067200,  # 2024-01-01
            author_name="John Doe",
            author_email="john@example.com",
            message=long_message,
            parent_hashes="parent123",
        )
        project_id = "test-project"

        # Mock vector manager with successful embedding
        mock_vector_manager = MagicMock()
        mock_future = MagicMock()
        mock_result = MagicMock()
        mock_result.error = None
        mock_result.embeddings = [[0.1] * 1024]  # Single chunk embedding
        mock_future.result.return_value = mock_result
        mock_vector_manager.submit_batch_task.return_value = mock_future

        # Act
        temporal_indexer._index_commit_message(commit, project_id, mock_vector_manager)

        # Assert: Verify submit_batch_task was called with FULL message (not truncated)
        mock_vector_manager.submit_batch_task.assert_called_once()
        call_args = mock_vector_manager.submit_batch_task.call_args
        chunk_texts = call_args[0][0]  # First positional arg is list of texts

        # Verify full message was used for chunking
        assert len(chunk_texts) > 0
        # The chunker should have preserved the full message
        combined_text = "".join(chunk_texts)
        assert "Fix authentication timeout bug" in combined_text
        assert len(combined_text) >= 500  # Long message should not be truncated to 200


class TestCommitMessageIntegration:
    """Test AC1: Integration of commit message indexing into workflow."""

    @patch("src.code_indexer.services.temporal.temporal_indexer.subprocess.run")
    def test_process_commits_parallel_indexes_commit_messages(
        self, mock_subprocess, temporal_indexer, tmp_path
    ):
        """Test that _process_commits_parallel() calls _index_commit_message() for each commit.

        This is the critical integration test verifying commit message indexing is ACTIVATED.
        """
        # Arrange
        commits = [
            CommitInfo(
                hash="commit1",
                timestamp=1704067200,
                author_name="Test Author",
                author_email="test@example.com",
                message="First commit message",
                parent_hashes="",
            ),
        ]

        # Mock git operations
        mock_subprocess.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )

        # Mock diff scanner to return no diffs (focus on commit message only)
        temporal_indexer.diff_scanner.get_diffs_for_commit = MagicMock(return_value=[])

        # Mock embedding provider and vector manager
        from src.code_indexer.services.vector_calculation_manager import VectorCalculationManager
        mock_embedding_provider = MagicMock()
        mock_embedding_provider._get_model_token_limit.return_value = 120000

        # Patch _index_commit_message to track calls
        with patch.object(temporal_indexer, '_index_commit_message') as mock_index_msg:
            with VectorCalculationManager(mock_embedding_provider, 2) as vector_manager:
                # Act
                temporal_indexer._process_commits_parallel(
                    commits,
                    mock_embedding_provider,
                    vector_manager,
                    progress_callback=None,
                    reconcile=None,
                )

                # Assert: _index_commit_message should be called for each commit
                assert mock_index_msg.call_count == len(commits), \
                    "Expected _index_commit_message to be called once per commit"

                # Verify called with correct arguments
                call_args = mock_index_msg.call_args_list[0]
                commit_arg = call_args[0][0]
                assert commit_arg.hash == "commit1"
                assert commit_arg.message == "First commit message"
