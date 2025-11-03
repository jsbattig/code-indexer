"""Tests for TemporalIndexer - Basic integration tests."""
import pytest
import subprocess
import sqlite3
from pathlib import Path
from code_indexer.config import ConfigManager
from code_indexer.storage.filesystem_vector_store import FilesystemVectorStore
from code_indexer.services.temporal.temporal_indexer import TemporalIndexer


class TestTemporalIndexer:
    """Test TemporalIndexer basic functionality."""

    def test_temporal_indexer_initializes_database(self, tmp_path):
        """Test TemporalIndexer creates SQLite databases."""
        # Create test git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create minimal config
        config_dir = repo_path / ".code-indexer"
        config_dir.mkdir(parents=True)

        config_manager = ConfigManager.create_with_backtrack(repo_path)

        # Create vector store (no project_id parameter)
        vector_store_path = config_dir / "index" / "default"
        vector_store_path.mkdir(parents=True)
        vector_store = FilesystemVectorStore(vector_store_path, project_root=repo_path)

        # Initialize temporal indexer
        indexer = TemporalIndexer(config_manager, vector_store)

        # Verify databases created
        assert (repo_path / ".code-indexer/index/temporal/commits.db").exists()
        assert (repo_path / ".code-indexer/index/temporal/blob_registry.db").exists()

        # Verify tables exist
        conn = sqlite3.connect(str(repo_path / ".code-indexer/index/temporal/commits.db"))
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "commits" in tables
        assert "trees" in tables
        assert "commit_branches" in tables

        indexer.close()
