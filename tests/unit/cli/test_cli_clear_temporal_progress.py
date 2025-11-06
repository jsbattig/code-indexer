"""
Test that CLI --clear flag removes temporal progress tracking file.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

from src.code_indexer.cli import cli


class TestCLIClearTemporalProgress(unittest.TestCase):
    """Test that --clear flag properly cleans up temporal progress file."""

    def setUp(self):
        """Create temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = Path(self.temp_dir) / "test_project"
        self.project_dir.mkdir(parents=True, exist_ok=True)

        # Create git repository
        import subprocess

        subprocess.run(["git", "init"], cwd=self.project_dir, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=self.project_dir
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=self.project_dir
        )

        # Create a test file and commit
        test_file = self.project_dir / "test.py"
        test_file.write_text("def test():\n    pass")
        subprocess.run(["git", "add", "."], cwd=self.project_dir)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.project_dir)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clear_flag_removes_temporal_progress_file(self):
        """
        Test that --clear flag removes temporal_progress.json when used with --index-commits.

        This ensures that when users want a fresh temporal index, all progress
        tracking is also cleared to avoid inconsistencies.
        """
        # Create the temporal progress file manually
        temporal_dir = self.project_dir / ".code-indexer/index/temporal"
        temporal_dir.mkdir(parents=True, exist_ok=True)

        progress_file = temporal_dir / "temporal_progress.json"
        progress_data = {
            "completed_commits": ["commit1", "commit2"],
            "status": "in_progress",
        }
        with open(progress_file, "w") as f:
            json.dump(progress_data, f)

        # Also create temporal_meta.json to simulate existing temporal index
        meta_file = temporal_dir / "temporal_meta.json"
        meta_data = {"last_commit": "commit2"}
        with open(meta_file, "w") as f:
            json.dump(meta_data, f)

        # Verify files exist
        self.assertTrue(
            progress_file.exists(), "Progress file should exist before clear"
        )
        self.assertTrue(meta_file.exists(), "Meta file should exist before clear")

        runner = CliRunner()

        # Mock the necessary components
        with patch("src.code_indexer.cli.ConfigManager") as MockConfig:
            with patch(
                "src.code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as MockVectorStore:
                with patch(
                    "src.code_indexer.services.temporal.temporal_indexer.TemporalIndexer"
                ) as MockTemporal:
                    # Setup mocks
                    mock_config = MagicMock()
                    mock_config.codebase_dir = self.project_dir
                    mock_config.embedding_provider = "voyage-ai"
                    MockConfig.create_with_backtrack.return_value.get_config.return_value = (
                        mock_config
                    )

                    mock_vector_store = MagicMock()
                    MockVectorStore.return_value = mock_vector_store
                    mock_vector_store.clear_collection.return_value = True

                    # Mock temporal indexer to avoid actual indexing
                    mock_temporal = MagicMock()
                    MockTemporal.return_value = mock_temporal
                    mock_temporal.index_commits.return_value = MagicMock(
                        total_commits=0,
                        unique_blobs=0,
                        new_blobs_indexed=0,
                        deduplication_ratio=1.0,
                        branches_indexed=[],
                        commits_per_branch={},
                    )

                    # Run the command with --clear and --index-commits
                    result = runner.invoke(
                        cli,
                        ["index", "--index-commits", "--clear"],
                        cwd=str(self.project_dir),
                    )

                    # Check that the command succeeded
                    if result.exit_code != 0:
                        print(f"Command output: {result.output}")

                    # Verify that temporal_meta.json was removed (existing behavior)
                    self.assertFalse(
                        meta_file.exists(), "Meta file should be removed after clear"
                    )

                    # Verify that temporal_progress.json was also removed (Bug #8 fix)
                    # This will FAIL because we haven't implemented this yet
                    self.assertFalse(
                        progress_file.exists(),
                        "Progress file should be removed after clear to ensure clean restart",
                    )


if __name__ == "__main__":
    unittest.main()
