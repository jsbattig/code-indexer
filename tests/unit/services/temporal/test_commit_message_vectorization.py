"""Unit tests for commit message vectorization (Story #476 AC1).

Tests that commit messages are vectorized as separate chunks during temporal indexing.
"""

from unittest.mock import Mock, patch

from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from src.code_indexer.services.temporal.models import CommitInfo


def test_commit_message_chunk_created_with_type_commit_message():
    """Test that commit message chunk is created with type='commit_message'.

    AC1: Commit message chunks are created with chunk_type="commit_message"

    This test verifies the FIRST requirement: that when we index a commit message,
    a chunk is created with the correct type field in its payload.
    """
    # Arrange - Create minimal mocks
    mock_config = Mock()
    mock_config.temporal = Mock()
    mock_config.temporal.diff_context_lines = 3
    mock_config.voyage_ai = Mock()
    mock_config.voyage_ai.parallel_requests = 4
    mock_config.voyage_ai.model = "voyage-code-3"
    mock_config.embedding_provider = "voyage-ai"

    mock_config_manager = Mock()
    mock_config_manager.get_config.return_value = mock_config

    from pathlib import Path

    mock_vector_store = Mock()
    mock_vector_store.project_root = Path("/tmp/test_repo")
    mock_vector_store.base_path = Path("/tmp/.code-indexer/index")
    mock_vector_store.collection_exists.return_value = True
    mock_vector_store.load_id_index.return_value = set()

    with patch(
        "src.code_indexer.services.temporal.temporal_indexer.TemporalDiffScanner"
    ):
        with patch(
            "src.code_indexer.services.temporal.temporal_indexer.FileIdentifier"
        ):
            temporal_indexer = TemporalIndexer(mock_config_manager, mock_vector_store)

    commit = CommitInfo(
        hash="abc123def456",
        timestamp=1699564800,
        author_name="John Doe",
        author_email="john@example.com",
        message="Fix authentication timeout bug",
        parent_hashes="parent123",
    )

    project_id = "test-project"
    mock_vector_manager = Mock()

    # Mock embedding response
    mock_future = Mock()
    mock_result = Mock()
    mock_result.error = None
    mock_result.embeddings = [[0.1] * 1024]
    mock_future.result.return_value = mock_result
    mock_vector_manager.submit_batch_task.return_value = mock_future

    # Mock chunker
    temporal_indexer.chunker = Mock()
    temporal_indexer.chunker.chunk_text.return_value = [
        {"text": commit.message, "char_start": 0, "char_end": len(commit.message)}
    ]

    # Act
    temporal_indexer._index_commit_message(commit, project_id, mock_vector_manager)

    # Assert
    assert mock_vector_store.upsert_points.called
    call_args = mock_vector_store.upsert_points.call_args
    points = call_args[1]["points"]
    assert len(points) > 0

    payload = points[0]["payload"]
    assert payload["type"] == "commit_message"


def test_commit_message_payload_includes_all_required_metadata():
    """Test that commit message chunk metadata includes all required fields.

    AC1: Message chunks include metadata: commit_hash, date, author, files_changed
    """
    # Arrange
    from pathlib import Path
    from unittest.mock import Mock, patch
    from src.code_indexer.services.temporal.temporal_indexer import TemporalIndexer
    from src.code_indexer.services.temporal.models import CommitInfo

    mock_config = Mock()
    mock_config.temporal = Mock()
    mock_config.temporal.diff_context_lines = 3
    mock_config.voyage_ai = Mock()
    mock_config.voyage_ai.parallel_requests = 4
    mock_config.voyage_ai.model = "voyage-code-3"
    mock_config.embedding_provider = "voyage-ai"

    mock_config_manager = Mock()
    mock_config_manager.get_config.return_value = mock_config

    mock_vector_store = Mock()
    mock_vector_store.project_root = Path("/tmp/test_repo")
    mock_vector_store.base_path = Path("/tmp/.code-indexer/index")
    mock_vector_store.collection_exists.return_value = True
    mock_vector_store.load_id_index.return_value = set()

    with patch(
        "src.code_indexer.services.temporal.temporal_indexer.TemporalDiffScanner"
    ):
        with patch(
            "src.code_indexer.services.temporal.temporal_indexer.FileIdentifier"
        ):
            temporal_indexer = TemporalIndexer(mock_config_manager, mock_vector_store)

    commit = CommitInfo(
        hash="def456abc789",
        timestamp=1699651200,  # 2023-11-10 15:20:00 UTC
        author_name="Jane Smith",
        author_email="jane@example.com",
        message="Refactor database connection pooling",
        parent_hashes="parent456",
    )

    project_id = "test-project"
    mock_vector_manager = Mock()

    # Mock embedding response
    mock_future = Mock()
    mock_result = Mock()
    mock_result.error = None
    mock_result.embeddings = [[0.2] * 1024]
    mock_future.result.return_value = mock_result
    mock_vector_manager.submit_batch_task.return_value = mock_future

    # Mock chunker
    temporal_indexer.chunker = Mock()
    temporal_indexer.chunker.chunk_text.return_value = [
        {"text": commit.message, "char_start": 0, "char_end": len(commit.message)}
    ]

    # Act
    temporal_indexer._index_commit_message(commit, project_id, mock_vector_manager)

    # Assert
    call_args = mock_vector_store.upsert_points.call_args
    points = call_args[1]["points"]
    payload = points[0]["payload"]

    # AC1: Verify all required metadata fields exist
    assert "commit_hash" in payload
    assert payload["commit_hash"] == commit.hash

    assert "commit_timestamp" in payload
    assert payload["commit_timestamp"] == commit.timestamp

    assert "commit_date" in payload
    assert payload["commit_date"] == "2023-11-10"  # YYYY-MM-DD format

    assert "author_name" in payload
    assert payload["author_name"] == commit.author_name

    assert "author_email" in payload
    assert payload["author_email"] == commit.author_email
