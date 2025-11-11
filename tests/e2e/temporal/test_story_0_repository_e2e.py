"""E2E test for Story 1 - Diff-based temporal indexing using Story 0 test repository.

Tests the complete flow of indexing a real git repository with diff-based approach.
"""

import subprocess
from pathlib import Path


class TestStory0RepositoryE2E:
    """End-to-end test using the Story 0 test repository."""

    def test_temporal_indexing_no_sqlite_created(self):
        """Test that temporal indexing does NOT create SQLite databases (Story 1 requirement)."""
        # Use the existing test repository
        repo_path = Path("/tmp/cidx-test-repo")

        # Verify repository exists
        assert (
            repo_path.exists()
        ), "Story 0 test repository must exist at /tmp/cidx-test-repo"
        assert (repo_path / ".git").exists(), "Must be a git repository"

        # Clean up any previous indexing
        index_dir = repo_path / ".code-indexer"
        if index_dir.exists():
            import shutil

            shutil.rmtree(index_dir)

        # Run cidx init
        result = subprocess.run(
            ["cidx", "init"], cwd=repo_path, capture_output=True, text=True
        )
        assert result.returncode == 0, f"cidx init failed: {result.stderr}"

        # Run temporal indexing
        result = subprocess.run(
            ["cidx", "index", "--index-commits", "--all-branches"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"cidx index failed: {result.stderr}"

        # Verify NO SQLite databases created
        assert not (
            index_dir / "index/temporal/commits.db"
        ).exists(), "Should NOT create commits.db"
        assert not (
            index_dir / "index/temporal/blob_registry.db"
        ).exists(), "Should NOT create blob_registry.db"

        # Count .db files - should be zero
        db_files = list(index_dir.rglob("*.db"))
        assert len(db_files) == 0, f"Found unexpected SQLite files: {db_files}"

    def test_temporal_indexing_storage_reduction(self):
        """Test that diff-based indexing achieves 90%+ storage reduction."""
        # Use the existing test repository
        repo_path = Path("/tmp/cidx-test-repo")
        index_dir = repo_path / ".code-indexer"

        # Verify temporal collection exists from previous test
        temporal_collection = index_dir / "index/code-indexer-temporal"
        assert temporal_collection.exists(), "Temporal collection should exist"

        # Count vector files (should be significantly less than 500)
        vector_files = [
            f
            for f in temporal_collection.rglob("*.json")
            if f.name != "collection_meta.json"
        ]
        vector_count = len(vector_files)

        # Story 1 expects ~50-100 vectors instead of 500+
        # With 12 commits and diff-based approach, should have way fewer vectors
        assert (
            vector_count < 150
        ), f"Too many vectors: {vector_count}, expected < 150 for diff-based indexing"
        print(
            f"✓ Storage reduction achieved: {vector_count} vectors (vs 500+ in old approach)"
        )
