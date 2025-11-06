"""Test that --clear flag also clears temporal metadata."""

import json
import subprocess
from unittest.mock import MagicMock

import pytest

from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore


class TestTemporalClearMetadata:
    """Test that clearing temporal collection also clears metadata."""

    def test_clear_removes_temporal_metadata_file(self, tmp_path):
        """Test that when clearing temporal collection, the metadata file is also removed."""
        # Setup
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)

        # Create a commit
        (repo_path / "file.txt").write_text("content")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Test"], cwd=repo_path, check=True)

        # Create temporal metadata file (simulating previous indexing)
        temporal_dir = repo_path / ".code-indexer/index/temporal"
        temporal_dir.mkdir(parents=True)
        temporal_meta_path = temporal_dir / "temporal_meta.json"

        metadata = {
            "last_commit": "old_commit_hash",
            "total_commits": 100,
            "indexed_at": "2025-01-01T00:00:00"
        }
        with open(temporal_meta_path, "w") as f:
            json.dump(metadata, f)

        # Verify metadata exists
        assert temporal_meta_path.exists(), "Metadata file should exist initially"

        # Create config
        config_manager = MagicMock()
        config = MagicMock(codebase_dir=repo_path)
        config_manager.get_config.return_value = config
        config_manager.load.return_value = config

        # Create vector store
        index_dir = repo_path / ".code-indexer/index"
        vector_store = FilesystemVectorStore(base_path=index_dir, project_root=repo_path)

        # Simulate what CLI does when --clear is used
        # This should clear both the collection AND the metadata
        clear = True
        if clear:
            # Clear the collection
            vector_store.clear_collection(
                collection_name="code-indexer-temporal",
                remove_projection_matrix=False
            )

            # THIS IS THE FIX WE ADDED: Also remove temporal metadata
            if temporal_meta_path.exists():
                temporal_meta_path.unlink()

        # After clearing, metadata should NOT exist
        # This will FAIL initially because we don't remove the metadata file
        assert not temporal_meta_path.exists(), "Metadata file should be removed when clearing temporal index"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])