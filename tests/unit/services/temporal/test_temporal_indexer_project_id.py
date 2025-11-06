"""Test TemporalIndexer project_id access bug.

This test reproduces the error:
'Config' object has no attribute 'project_id'

The fix should use FileIdentifier to get project_id instead of accessing config.project_id.
"""
import tempfile
from pathlib import Path
import subprocess
import pytest

from code_indexer.config import ConfigManager
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer


def test_temporal_indexer_uses_file_identifier_for_project_id():
    """Test that TemporalIndexer gets project_id from FileIdentifier, not Config.

    This test creates a minimal git repo, initializes TemporalIndexer, and attempts
    to index commits. The test should fail with AttributeError if TemporalIndexer
    tries to access config.project_id directly.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)

        # Create a test file and commit
        test_file = repo_path / "test.py"
        test_file.write_text("def hello(): return 'world'\n")
        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        # Initialize config and vector store
        config_manager = ConfigManager.create_with_backtrack(repo_path)
        index_dir = repo_path / ".code-indexer/index"
        index_dir.mkdir(parents=True, exist_ok=True)
        vector_store = FilesystemVectorStore(
            base_path=index_dir,
            project_root=repo_path
        )

        # Create temporal indexer
        temporal_indexer = TemporalIndexer(config_manager, vector_store)

        # This should NOT raise AttributeError about config.project_id
        # If it does, the test will fail and show we need to fix it
        try:
            result = temporal_indexer.index_commits(
                all_branches=False,
                max_commits=1,
                progress_callback=None
            )
            # If we get here without error, the fix is working
            assert result.total_commits == 1
        except AttributeError as e:
            if "project_id" in str(e):
                pytest.fail(f"TemporalIndexer should not access config.project_id directly: {e}")
            raise
        finally:
            temporal_indexer.close()


if __name__ == "__main__":
    test_temporal_indexer_uses_file_identifier_for_project_id()
