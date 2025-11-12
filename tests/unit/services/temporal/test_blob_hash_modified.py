"""Test that modified files get blob hashes."""

import tempfile
from pathlib import Path
import subprocess


from src.code_indexer.services.temporal.temporal_diff_scanner import TemporalDiffScanner


class TestBlobHashModified:
    """Test blob hash for modified files."""

    def test_modified_file_has_blob_hash(self):
        """Test that modified files get their blob hash populated."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)

            # Initialize git repo
            subprocess.run(["git", "init"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.com"],
                cwd=repo_path,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test User"], cwd=repo_path, check=True
            )

            # Commit 1: Create file
            test_file = repo_path / "test.py"
            test_file.write_text("print('version1')\n")
            subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True
            )

            # Commit 2: Modify file
            test_file.write_text("print('version2')\n")
            subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
            subprocess.run(
                ["git", "commit", "-m", "Modified file"], cwd=repo_path, check=True
            )

            # Get second commit hash
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            commit_hash = result.stdout.strip()

            # Get expected blob hash for modified file
            result = subprocess.run(
                ["git", "rev-parse", "HEAD:test.py"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                check=True,
            )
            expected_blob_hash = result.stdout.strip()

            # Test scanner
            scanner = TemporalDiffScanner(repo_path)
            diffs = scanner.get_diffs_for_commit(commit_hash)

            # Should have one modified file
            assert len(diffs) == 1, f"Expected 1 diff, got {len(diffs)}"
            diff = diffs[0]

            assert (
                diff.diff_type == "modified"
            ), f"Expected modified, got {diff.diff_type}"
            assert (
                diff.blob_hash == expected_blob_hash
            ), f"Modified file blob_hash should be '{expected_blob_hash}' but got '{diff.blob_hash}'"
