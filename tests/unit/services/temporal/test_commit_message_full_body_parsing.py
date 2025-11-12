"""
Unit tests for full commit message body parsing with null delimiters.

Tests that temporal indexer correctly:
1. Uses %B format to capture full commit message (not just first line with %s)
2. Uses null byte delimiters to prevent | characters in messages from breaking parsing
3. Preserves multi-paragraph commit messages
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_indexer.services.temporal.temporal_indexer import TemporalIndexer


class TestCommitMessageFullBodyParsing:
    """Test full commit message body parsing with null delimiters."""

    @pytest.fixture
    def temp_repo(self, tmp_path: Path) -> Path:
        """Create a temporary git repository."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        return repo_dir

    @patch("code_indexer.services.embedding_factory.EmbeddingProviderFactory")
    def test_full_commit_message_with_multiple_paragraphs(
        self, mock_factory, temp_repo: Path
    ):
        """Test that full multi-paragraph commit messages are captured."""
        # Setup mock factory
        mock_factory.get_provider_model_info.return_value = {"dimensions": 1024}
        mock_factory.create.return_value = MagicMock()

        # Create indexer
        config_manager = MagicMock()
        mock_config = MagicMock()
        mock_config.embedding_provider = "voyage-ai"
        mock_config.voyage_ai = MagicMock(
            parallel_requests=1, max_concurrent_batches_per_commit=10
        )
        config_manager.get_config.return_value = mock_config

        # Setup temporal directory
        temporal_dir = temp_repo / ".code-indexer" / "index"
        temporal_dir.mkdir(parents=True, exist_ok=True)

        vector_store = MagicMock()
        vector_store.project_root = temp_repo
        vector_store.base_path = temporal_dir
        vector_store.collection_exists.return_value = True

        indexer = TemporalIndexer(config_manager, vector_store)

        # Create a commit with a multi-paragraph message
        test_file = temp_repo / "test.txt"
        test_file.write_text("Initial content\n")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )

        # Multi-paragraph commit message
        commit_message = """feat: implement HNSW incremental updates

This is the second paragraph with more details about the implementation.
It spans multiple lines and provides context.

Third paragraph:
- Bullet point 1
- Bullet point 2

Final paragraph with closing thoughts."""

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=temp_repo,
            check=True,
            capture_output=True,
        )

        # Get commits using the indexer
        commits = indexer._get_commit_history(
            all_branches=False, max_commits=None, since_date=None
        )

        assert len(commits) == 1
        commit = commits[0]

        # Verify the FULL message is captured, not just the first line
        assert "second paragraph" in commit.message.lower()
        assert "third paragraph" in commit.message.lower()
        assert "bullet point 1" in commit.message.lower()
        assert "final paragraph" in commit.message.lower()

        # Verify first line is also present
        assert "feat: implement HNSW incremental updates" in commit.message
