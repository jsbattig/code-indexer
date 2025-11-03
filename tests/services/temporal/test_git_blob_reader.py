"""Tests for GitBlobReader - TDD approach."""
import subprocess
import pytest
from pathlib import Path
from code_indexer.services.temporal.git_blob_reader import GitBlobReader


class TestGitBlobReader:
    """Test GitBlobReader for reading blob content from git object store."""

    def test_read_blob_content_returns_text(self, tmp_path):
        """Test read_blob_content returns text content for valid blob."""
        # Create test git repo
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create file with known content
        test_content = "def hello():\n    return 'world'\n"
        test_file = repo_path / "test.py"
        test_file.write_text(test_content)

        subprocess.run(["git", "add", "test.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Add test"], cwd=repo_path, check=True)

        # Get blob hash
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "test.py"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        blob_hash = result.stdout.split()[2]

        # Test read_blob_content
        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(blob_hash)

        assert content == test_content

    def test_read_blob_content_preserves_exact_content(self, tmp_path):
        """Test read_blob_content preserves exact file content including whitespace."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Content with various whitespace patterns
        test_content = "line1\n  line2 with spaces  \n\tline3 with tab\n\nline5 after blank\n"
        test_file = repo_path / "whitespace.txt"
        test_file.write_text(test_content)

        subprocess.run(["git", "add", "whitespace.txt"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Whitespace test"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "whitespace.txt"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        blob_hash = result.stdout.split()[2]

        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(blob_hash)

        # Content must be exactly preserved
        assert content == test_content
        assert content.count("\n") == 5
        assert "\t" in content

    def test_read_blob_content_handles_unicode(self, tmp_path):
        """Test read_blob_content handles Unicode characters correctly."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Unicode content
        test_content = "# Testing Unicode: 你好世界 🚀 café\ndef greet():\n    return '¡Hola!'\n"
        test_file = repo_path / "unicode.py"
        test_file.write_text(test_content, encoding="utf-8")

        subprocess.run(["git", "add", "unicode.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Unicode test"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "unicode.py"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        blob_hash = result.stdout.split()[2]

        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(blob_hash)

        assert content == test_content
        assert "你好世界" in content
        assert "🚀" in content
        assert "café" in content

    def test_read_blob_content_with_invalid_blob_raises_error(self, tmp_path):
        """Test read_blob_content raises error for invalid blob hash."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)

        reader = GitBlobReader(repo_path)

        with pytest.raises(ValueError, match="Failed to read blob"):
            reader.read_blob_content("invalid_blob_hash_1234567890")

    def test_read_blob_content_handles_large_files(self, tmp_path):
        """Test read_blob_content can handle large file blobs."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create a large file (10KB of content)
        large_content = "x" * 10000 + "\n"
        test_file = repo_path / "large.txt"
        test_file.write_text(large_content)

        subprocess.run(["git", "add", "large.txt"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Large file"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "large.txt"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        blob_hash = result.stdout.split()[2]

        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(blob_hash)

        assert len(content) == 10001
        assert content == large_content

    def test_read_blob_content_with_empty_file(self, tmp_path):
        """Test read_blob_content handles empty files."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create empty file
        test_file = repo_path / "empty.txt"
        test_file.write_text("")

        subprocess.run(["git", "add", "empty.txt"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Empty file"], cwd=repo_path, check=True)

        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "empty.txt"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True)
        blob_hash = result.stdout.split()[2]

        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(blob_hash)

        assert content == ""

    def test_read_blob_content_from_old_commit(self, tmp_path):
        """Test read_blob_content can read blobs from historical commits."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        subprocess.run(["git", "init"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo_path, check=True)

        # Create initial version
        test_file = repo_path / "versioned.py"
        old_content = "version = 1\n"
        test_file.write_text(old_content)

        subprocess.run(["git", "add", "versioned.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Version 1"], cwd=repo_path, check=True)

        # Get OLD blob hash
        result = subprocess.run(
            ["git", "ls-tree", "HEAD", "versioned.py"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        old_blob_hash = result.stdout.split()[2]

        # Modify file (create new version)
        new_content = "version = 2\n"
        test_file.write_text(new_content)
        subprocess.run(["git", "add", "versioned.py"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Version 2"], cwd=repo_path, check=True)

        # Read OLD blob (should still return version 1)
        reader = GitBlobReader(repo_path)
        content = reader.read_blob_content(old_blob_hash)

        assert content == old_content
        assert "version = 1" in content
        assert "version = 2" not in content
