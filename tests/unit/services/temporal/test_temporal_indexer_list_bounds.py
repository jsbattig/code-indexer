"""Test for list index out of range bug in temporal indexing.

Bug reproduction: At 365/366 commits, temporal indexing fails with
'list index out of range' error during metadata save operation.

Root cause analysis:
- Progressive metadata filtering removes already-completed commits
- If ALL commits are filtered out, commits list becomes empty
- commits[-1].hash access at line 202 fails with IndexError
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer
from code_indexer.services.temporal.models import CommitInfo


@pytest.fixture
def mock_config_manager():
    """Create mock config manager."""
    config_manager = Mock()
    config = Mock()
    config.embedding_provider = "voyage-ai"
    config.voyage_ai = Mock()
    config.voyage_ai.parallel_requests = 4
    config.voyage_ai.max_concurrent_batches_per_commit = 10
    config_manager.get_config.return_value = config
    return config_manager


@pytest.fixture
def mock_vector_store():
    """Create mock vector store."""
    vector_store = Mock()
    vector_store.project_root = Path(tempfile.mkdtemp())
    vector_store.collection_exists.return_value = True
    vector_store.load_id_index.return_value = set()
    return vector_store


@pytest.fixture
def temporal_indexer(mock_config_manager, mock_vector_store):
    """Create temporal indexer instance."""
    with patch("code_indexer.services.embedding_factory.EmbeddingProviderFactory"):
        indexer = TemporalIndexer(mock_config_manager, mock_vector_store)
        return indexer


def test_empty_commits_after_filtering_should_return_early(temporal_indexer):
    """Test that filtering ALL commits returns early gracefully without error.

    Bug scenario that should be fixed:
    1. Get 366 commits from git history
    2. Progressive metadata shows ALL 366 already completed
    3. Filter removes all commits, leaving empty list
    4. Code should return early with zero results
    5. Currently crashes with IndexError at line 202: commits[-1].hash
    """
    # Setup: Create 3 commits
    commits = [
        CommitInfo(
            hash=f"commit{i}",
            timestamp=1234567890 + i,
            author_name="Test Author",
            author_email="test@example.com",
            message=f"Commit {i}",
            parent_hashes="",
        )
        for i in range(3)
    ]

    # Mock progressive metadata to show ALL commits already completed
    # This is the critical condition - after filtering, commits will be empty
    temporal_indexer.progressive_metadata.load_completed = Mock(
        return_value={c.hash for c in commits}
    )

    # Mock git operations and embedding provider
    with patch.object(temporal_indexer, "_get_commit_history", return_value=commits):
        with patch.object(temporal_indexer, "_get_current_branch", return_value="main"):
            with patch("code_indexer.services.embedding_factory.EmbeddingProviderFactory.create"):
                # Expected behavior: Should return early with zero results
                # Current bug: Crashes with IndexError at line 202
                result = temporal_indexer.index_commits(all_branches=False)

                # Verify correct early return behavior with new field names
                assert result.total_commits == 0
                assert result.files_processed == 0
                assert result.approximate_vectors_created == 0
                assert result.skip_ratio == 1.0  # All commits skipped
                assert result.branches_indexed == []
                assert result.commits_per_branch == {}
