"""Test query-time git reconstruction for added/deleted files.

Tests verify that temporal queries reconstruct file content from git
for added/deleted files that use pointer-based storage.
"""

import pytest
import subprocess
from unittest.mock import Mock
from datetime import datetime


class TestQueryTimeGitReconstruction:
    """Test that temporal queries reconstruct content from git for pointer-based files."""

    @pytest.fixture
    def temp_git_repo(self, tmp_path):
        """Create a temporary git repository with added file."""
        repo_dir = tmp_path / "test_repo"
        repo_dir.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
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

        # Commit: Add file with specific content
        test_file = repo_dir / "test.py"
        test_content = "def hello():\n    return 'world'\n"
        test_file.write_text(test_content)
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        add_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # Get commit timestamp
        add_timestamp = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", add_commit],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        return {
            "repo_dir": repo_dir,
            "add_commit": add_commit,
            "add_timestamp": add_timestamp,
            "test_content": test_content,
        }

    def test_query_reconstructs_added_file_content(self, temp_git_repo):
        """Test that querying an added file reconstructs content from git."""
        from src.code_indexer.services.temporal.temporal_search_service import (
            TemporalSearchService,
        )
        from src.code_indexer.config import ConfigManager

        repo_dir = temp_git_repo["repo_dir"]
        add_commit = temp_git_repo["add_commit"]
        add_timestamp = temp_git_repo["add_timestamp"]
        expected_content = temp_git_repo["test_content"]

        # Create config manager
        config_manager = ConfigManager.create_with_backtrack(repo_dir)

        # Create mock vector store with pointer-based payload (reconstruct_from_git=True)
        # Must not be instance of FilesystemVectorStore to avoid the isinstance check

        mock_vector_store = Mock()  # Simple Mock without spec
        mock_vector_store.collection_exists.return_value = True

        # Simulate search results with reconstruct_from_git marker
        mock_search_results = [
            {
                "id": "test_point_1",
                "score": 0.95,
                "payload": {
                    "file_path": "test.py",
                    "chunk_index": 0,
                    "content": "",  # No content stored - pointer only
                    "reconstruct_from_git": True,  # Marker for reconstruction
                    "diff_type": "added",
                    "commit_hash": add_commit,
                    "commit_timestamp": add_timestamp,
                    "commit_date": datetime.fromtimestamp(add_timestamp).strftime("%Y-%m-%d"),
                    "commit_message": "Add test.py",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                },
            }
        ]

        # Mock must return raw results directly (not tuple) since it's not FilesystemVectorStore
        mock_vector_store.search.return_value = mock_search_results

        # Create mock embedding provider
        mock_embedding = Mock()
        mock_embedding.get_embedding.return_value = [0.1] * 1024

        # Create search service
        search_service = TemporalSearchService(
            config_manager=config_manager,
            project_root=repo_dir,
            vector_store_client=mock_vector_store,
            embedding_provider=mock_embedding,
            collection_name="code-indexer-temporal",
        )

        # Query temporal index
        start_date = datetime.fromtimestamp(add_timestamp - 86400).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(add_timestamp + 86400).strftime("%Y-%m-%d")

        results = search_service.query_temporal(
            query="test function",
            time_range=(start_date, end_date),
        )

        # Verify: content was reconstructed from git
        assert len(results.results) == 1, "Should return one result"
        result = results.results[0]

        # CRITICAL: Content should be reconstructed from git, not empty
        assert result.content, "Content should not be empty after reconstruction"
        assert result.content == expected_content, (
            f"Content should match original file content.\n"
            f"Expected: {expected_content!r}\n"
            f"Got: {result.content!r}"
        )
        assert "def hello():" in result.content, "Should contain actual file content"

    def test_query_reconstructs_deleted_file_content(self, temp_git_repo):
        """Test that querying a deleted file reconstructs content from parent commit."""
        from src.code_indexer.services.temporal.temporal_search_service import (
            TemporalSearchService,
        )
        from src.code_indexer.config import ConfigManager
        import subprocess

        repo_dir = temp_git_repo["repo_dir"]
        add_commit = temp_git_repo["add_commit"]
        expected_content = temp_git_repo["test_content"]

        # Delete the file to create a deletion commit
        test_file = repo_dir / "test.py"
        test_file.unlink()
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Delete test.py"],
            cwd=repo_dir,
            check=True,
            capture_output=True,
        )

        delete_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        delete_timestamp = int(
            subprocess.run(
                ["git", "show", "-s", "--format=%ct", delete_commit],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )

        # Create config manager
        config_manager = ConfigManager.create_with_backtrack(repo_dir)

        # Create mock vector store with pointer-based payload for deleted file
        mock_vector_store = Mock()
        mock_vector_store.collection_exists.return_value = True

        # Simulate search results with reconstruct_from_git marker and parent_commit_hash
        mock_search_results = [
            {
                "id": "test_point_2",
                "score": 0.93,
                "payload": {
                    "file_path": "test.py",
                    "chunk_index": 0,
                    "content": "",  # No content stored - pointer only
                    "reconstruct_from_git": True,  # Marker for reconstruction
                    "diff_type": "deleted",
                    "commit_hash": delete_commit,
                    "parent_commit_hash": add_commit,  # Parent commit for reconstruction
                    "commit_timestamp": delete_timestamp,
                    "commit_date": datetime.fromtimestamp(delete_timestamp).strftime("%Y-%m-%d"),
                    "commit_message": "Delete test.py",
                    "author_name": "Test User",
                    "author_email": "test@example.com",
                },
            }
        ]

        mock_vector_store.search.return_value = mock_search_results

        # Create mock embedding provider
        mock_embedding = Mock()
        mock_embedding.get_embedding.return_value = [0.1] * 1024

        # Create search service
        search_service = TemporalSearchService(
            config_manager=config_manager,
            project_root=repo_dir,
            vector_store_client=mock_vector_store,
            embedding_provider=mock_embedding,
            collection_name="code-indexer-temporal",
        )

        # Query temporal index
        start_date = datetime.fromtimestamp(delete_timestamp - 86400).strftime("%Y-%m-%d")
        end_date = datetime.fromtimestamp(delete_timestamp + 86400).strftime("%Y-%m-%d")

        results = search_service.query_temporal(
            query="test function",
            time_range=(start_date, end_date),
        )

        # Verify: content was reconstructed from parent commit
        assert len(results.results) == 1, "Should return one result"
        result = results.results[0]

        # CRITICAL: Content should be reconstructed from parent commit, not empty
        assert result.content, "Content should not be empty after reconstruction"
        assert result.content == expected_content, (
            f"Content should match original file content from parent commit.\n"
            f"Expected: {expected_content!r}\n"
            f"Got: {result.content!r}"
        )
        assert "def hello():" in result.content, "Should contain actual file content"
