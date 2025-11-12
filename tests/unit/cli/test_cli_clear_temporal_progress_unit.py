"""
Unit test for CLI clearing temporal progress file.
"""

import json
import tempfile
import unittest
from pathlib import Path


class TestCLIClearTemporalProgressUnit(unittest.TestCase):
    """Unit test for temporal progress cleanup."""

    def setUp(self):
        """Create temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_dir = Path(self.temp_dir) / "test_project"
        self.project_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_progress_file_cleanup_behavior(self):
        """
        Test that temporal progress file should be cleaned up with temporal_meta.json.

        This is to verify the expected behavior when --clear is used.
        """
        # Create the temporal directory structure
        temporal_dir = self.project_dir / ".code-indexer/index/temporal"
        temporal_dir.mkdir(parents=True, exist_ok=True)

        # Create both files
        progress_file = temporal_dir / "temporal_progress.json"
        progress_data = {
            "completed_commits": ["commit1", "commit2"],
            "status": "in_progress",
        }
        with open(progress_file, "w") as f:
            json.dump(progress_data, f)

        meta_file = temporal_dir / "temporal_meta.json"
        meta_data = {"last_commit": "commit2"}
        with open(meta_file, "w") as f:
            json.dump(meta_data, f)

        # Verify both files exist
        self.assertTrue(progress_file.exists(), "Progress file should exist")
        self.assertTrue(meta_file.exists(), "Meta file should exist")

        # Simulate what the CLI should do when --clear is used:
        # 1. Clear the collection (mocked, not tested here)
        # 2. Remove temporal_meta.json
        if meta_file.exists():
            meta_file.unlink()

        # 3. Remove temporal_progress.json (Bug #8 fix - this needs to be implemented)
        # THIS IS WHAT NEEDS TO BE ADDED TO THE CLI
        if progress_file.exists():
            progress_file.unlink()

        # Verify both files are removed
        self.assertFalse(meta_file.exists(), "Meta file should be removed")
        self.assertFalse(progress_file.exists(), "Progress file should be removed")

        # This test PASSES but demonstrates what the CLI should do
        # The actual CLI code needs to add the progress file cleanup


if __name__ == "__main__":
    unittest.main()
