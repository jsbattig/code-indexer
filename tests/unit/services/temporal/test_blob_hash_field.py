"""Test that DiffInfo includes blob_hash field for deduplication."""
import tempfile
from pathlib import Path
import subprocess

import pytest

from src.code_indexer.services.temporal.temporal_diff_scanner import TemporalDiffScanner


@pytest.fixture
def temp_repo():
    """Create a temporary git repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, check=True)

        # Create and commit a file
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello')\n")
        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        # Get the commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True
        )
        commit_hash = result.stdout.strip()

        # Get the blob hash for the file
        result = subprocess.run(
            ["git", "rev-parse", "HEAD:test.py"],
            cwd=repo_path, capture_output=True, text=True, check=True
        )
        blob_hash = result.stdout.strip()

        yield repo_path, commit_hash, blob_hash


class TestBlobHashField:
    """Test that DiffInfo has blob_hash field for deduplication."""

    def test_diff_info_has_blob_hash_field(self, temp_repo):
        """Test that DiffInfo dataclass includes blob_hash field."""
        repo_path, commit_hash, expected_blob_hash = temp_repo

        # Create scanner and get diffs
        scanner = TemporalDiffScanner(repo_path)
        diffs = scanner.get_diffs_for_commit(commit_hash)

        assert len(diffs) > 0, "Should have at least one diff"

        # Check that DiffInfo has blob_hash attribute
        diff = diffs[0]
        assert hasattr(diff, 'blob_hash'), "DiffInfo should have blob_hash attribute"

        # The blob_hash should be populated with the actual git blob hash
        assert diff.blob_hash == expected_blob_hash, \
            f"blob_hash should be '{expected_blob_hash}' but got '{diff.blob_hash}'"