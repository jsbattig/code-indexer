"""Tests for TemporalBlobScanner - TDD approach."""
import subprocess
import pytest
from pathlib import Path
from code_indexer.services.temporal.temporal_blob_scanner import TemporalBlobScanner
from code_indexer.services.temporal.models import BlobInfo


class TestTemporalBlobScanner:
    """Test TemporalBlobScanner for discovering blobs in git history."""

    def test_get_blobs_for_commit_returns_list_of_blob_info(self, tmp_path):
        """Test get_blobs_for_commit returns BlobInfo objects for valid commit."""
        # Create a test git repository
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create a test file
        test_file = repo_path / "test.py"
        test_file.write_text("print('hello')")

        # Commit the file
        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Test get_blobs_for_commit
        scanner = TemporalBlobScanner(repo_path)
        blobs = scanner.get_blobs_for_commit(commit_hash)

        # Assertions
        assert len(blobs) == 1
        assert isinstance(blobs[0], BlobInfo)
        assert blobs[0].file_path == "test.py"
        assert blobs[0].commit_hash == commit_hash
        assert blobs[0].size > 0
        assert len(blobs[0].blob_hash) == 40  # Git SHA-1

    def test_get_blobs_for_commit_with_multiple_files(self, tmp_path):
        """Test get_blobs_for_commit returns all files in a commit."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create multiple files
        (repo_path / "file1.py").write_text("print('file1')")
        (repo_path / "file2.py").write_text("print('file2')")
        (repo_path / "dir1").mkdir()
        (repo_path / "dir1" / "file3.py").write_text("print('file3')")

        # Commit all files
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Multiple files"], cwd=repo_path, check=True)

        # Get commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Test
        scanner = TemporalBlobScanner(repo_path)
        blobs = scanner.get_blobs_for_commit(commit_hash)

        # Assertions
        assert len(blobs) == 3
        file_paths = {blob.file_path for blob in blobs}
        assert file_paths == {"file1.py", "file2.py", "dir1/file3.py"}

        # All blobs should have correct commit_hash
        for blob in blobs:
            assert blob.commit_hash == commit_hash
            assert blob.size > 0
            assert len(blob.blob_hash) == 40

    def test_get_blobs_for_commit_excludes_directories(self, tmp_path):
        """Test get_blobs_for_commit only returns blobs, not tree objects."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create nested directory structure
        (repo_path / "dir1" / "dir2").mkdir(parents=True)
        (repo_path / "dir1" / "dir2" / "file.py").write_text("test")

        subprocess.run(["git", "add", "."], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Nested dirs"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Test
        scanner = TemporalBlobScanner(repo_path)
        blobs = scanner.get_blobs_for_commit(commit_hash)

        # Should only return the file, not directory entries
        assert len(blobs) == 1
        assert blobs[0].file_path == "dir1/dir2/file.py"

    def test_get_blobs_for_commit_with_invalid_commit_raises_error(self, tmp_path):
        """Test get_blobs_for_commit raises error for invalid commit hash."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo (empty)
        subprocess.run(["git", "init"], cwd=repo_path, check=True)

        scanner = TemporalBlobScanner(repo_path)

        with pytest.raises(subprocess.CalledProcessError):
            scanner.get_blobs_for_commit("invalid_commit_hash")

    def test_get_blobs_for_commit_with_empty_commit(self, tmp_path):
        """Test get_blobs_for_commit handles commits with no files."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create empty commit
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Empty commit"],
            cwd=repo_path,
            check=True
        )

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Test
        scanner = TemporalBlobScanner(repo_path)
        blobs = scanner.get_blobs_for_commit(commit_hash)

        # Empty commit should return empty list
        assert blobs == []

    def test_blob_info_contains_correct_metadata(self, tmp_path):
        """Test BlobInfo objects contain all required metadata fields."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create file with known content
        test_content = "def hello():\n    print('world')\n"
        test_file = repo_path / "module.py"
        test_file.write_text(test_content)

        subprocess.run(["git", "add", "module.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Add module"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        commit_hash = result.stdout.strip()

        # Get the actual blob hash from git
        result = subprocess.run(
            ["git", "ls-tree", commit_hash, "module.py"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        # Format: <mode> <type> <hash>\t<path>
        parts = result.stdout.split()
        expected_blob_hash = parts[2]

        # Test
        scanner = TemporalBlobScanner(repo_path)
        blobs = scanner.get_blobs_for_commit(commit_hash)

        blob = blobs[0]
        assert blob.blob_hash == expected_blob_hash
        assert blob.file_path == "module.py"
        assert blob.commit_hash == commit_hash
        assert blob.size == len(test_content)
