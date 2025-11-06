"""
Unit tests for TemporalProgressiveMetadata class.

This class manages progressive state tracking for temporal indexing,
allowing resume from interruption without re-processing completed commits.
"""

import tempfile
import unittest
from pathlib import Path

from src.code_indexer.services.temporal.temporal_progressive_metadata import (
    TemporalProgressiveMetadata
)


class TestTemporalProgressiveMetadata(unittest.TestCase):
    """Test the TemporalProgressiveMetadata class."""

    def setUp(self):
        """Create temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.temporal_dir = Path(self.temp_dir) / ".code-indexer/index/temporal"
        self.temporal_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_completed_commits(self):
        """Test saving and loading completed commits."""
        metadata = TemporalProgressiveMetadata(self.temporal_dir)

        # Save some completed commits
        metadata.save_completed("commit1")
        metadata.save_completed("commit2")
        metadata.save_completed("commit3")

        # Load and verify
        completed = metadata.load_completed()
        self.assertEqual(completed, {"commit1", "commit2", "commit3"})

    def test_clear_removes_progress_file(self):
        """Test clear removes the progress file."""
        metadata = TemporalProgressiveMetadata(self.temporal_dir)

        # Save some progress
        metadata.save_completed("commit1")
        metadata.save_completed("commit2")

        # Verify file exists
        self.assertTrue(metadata.progress_path.exists())

        # Clear progress
        metadata.clear()

        # Verify file is removed
        self.assertFalse(metadata.progress_path.exists())

        # Verify loading returns empty set
        completed = metadata.load_completed()
        self.assertEqual(completed, set())


if __name__ == "__main__":
    unittest.main()