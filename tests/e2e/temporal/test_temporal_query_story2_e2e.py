"""E2E test for Story 2: Temporal queries with complete SQLite removal."""

import subprocess
import tempfile
import unittest
import shutil
from pathlib import Path


class TestTemporalQueryStory2E2E(unittest.TestCase):
    """Test temporal queries work without SQLite."""

    def setUp(self):
        """Create test repository."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.repo_path = self.test_dir / "test-repo"
        self.repo_path.mkdir()

    def tearDown(self):
        """Clean up test repository."""
        shutil.rmtree(self.test_dir)

    def test_temporal_query_without_sqlite(self):
        """Test that temporal queries work using JSON payloads only."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=self.repo_path, check=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=self.repo_path,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=self.repo_path,
            check=True,
        )

        # Create first commit (Nov 1)
        file1 = self.repo_path / "auth.py"
        file1.write_text("def authenticate():\n    return True\n")
        subprocess.run(["git", "add", "."], cwd=self.repo_path, check=True)
        subprocess.run(
            [
                "git",
                "commit",
                "-m",
                "Add authentication",
                "--date",
                "2025-11-01T10:00:00",
            ],
            cwd=self.repo_path,
            check=True,
            env={"GIT_COMMITTER_DATE": "2025-11-01T10:00:00"},
        )

        # Initialize cidx
        subprocess.run(["cidx", "init"], cwd=self.repo_path, check=True)

        # Index with temporal support (no need to start services for filesystem backend)
        result = subprocess.run(
            ["cidx", "index", "--index-commits"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Verify NO SQLite database created
        commits_db = (
            self.repo_path / ".code-indexer" / "index" / "temporal" / "commits.db"
        )
        self.assertFalse(
            commits_db.exists(), "commits.db should not exist with diff-based indexing"
        )

        # Query for Nov 1 changes
        result = subprocess.run(
            ["cidx", "query", "authenticate", "--time-range", "2025-11-01..2025-11-01"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=True,
        )

        # Should return results without SQLite errors
        self.assertIn("authenticate", result.stdout)
        self.assertIn("auth.py", result.stdout)
        self.assertNotIn("database not found", result.stdout)
        self.assertNotIn("sqlite", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
