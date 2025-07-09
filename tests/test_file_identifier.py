"""
Tests for the FileIdentifier service.

This test suite covers both git-aware and non-git functionality
to ensure the FileIdentifier works correctly in all scenarios.
"""

import pytest

from .conftest import local_temporary_directory
import subprocess
from pathlib import Path
from unittest.mock import patch

from code_indexer.config import Config
from code_indexer.services.file_identifier import FileIdentifier


class TestFileIdentifier:
    """Test the FileIdentifier service."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        with local_temporary_directory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def git_repo(self, temp_dir):
        """Create a git repository for testing."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            check=True,
        )

        # Create and commit a test file
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello world')")

        subprocess.run(["git", "add", "test.py"], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True
        )

        return temp_dir

    @pytest.fixture
    def non_git_dir(self, temp_dir):
        """Create a non-git directory for testing."""
        # Create some test files
        (temp_dir / "test.py").write_text("print('hello world')")
        (temp_dir / "test.js").write_text("console.log('hello world')")
        (temp_dir / "README.md").write_text("# Test Project")
        (temp_dir / "ignore.txt").write_text("should be ignored")

        return temp_dir

    @pytest.fixture
    def config(self, temp_dir):
        """Create a test configuration."""
        config = Config(
            codebase_dir=temp_dir,
            file_extensions=["py", "js", "md"],
            exclude_dirs=["node_modules", ".git", "__pycache__"],
        )
        return config

    def test_git_detection_positive(self, git_repo, config):
        """Test that git repository is correctly detected."""
        identifier = FileIdentifier(git_repo, config)
        assert identifier.git_available is True

    def test_git_detection_negative(self, non_git_dir, config):
        """Test that non-git directory is correctly identified."""
        identifier = FileIdentifier(non_git_dir, config)
        assert identifier.git_available is False

    def test_project_id_from_directory(self, non_git_dir, config):
        """Test project ID generation from directory name."""
        identifier = FileIdentifier(non_git_dir, config)
        project_id = identifier._get_project_id()

        # Should use directory name, converted to lowercase with underscores replaced
        expected = non_git_dir.name.lower().replace("_", "-")
        assert project_id == expected

    def test_project_id_from_git_remote(self, git_repo, config):
        """Test project ID generation from git remote URL."""
        # Add a fake remote
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/user/test-repo.git"],
            cwd=git_repo,
            check=True,
        )

        identifier = FileIdentifier(git_repo, config)
        project_id = identifier._get_project_id()

        assert project_id == "test-repo"

    def test_file_content_hash_consistency(self, temp_dir, config):
        """Test that file content hashing is consistent."""
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello world')")

        identifier = FileIdentifier(temp_dir, config)

        hash1 = identifier._get_file_content_hash(test_file)
        hash2 = identifier._get_file_content_hash(test_file)

        assert hash1 == hash2
        assert hash1.startswith("sha256:")

    def test_file_content_hash_different_content(self, temp_dir, config):
        """Test that different content produces different hashes."""
        file1 = temp_dir / "test1.py"
        file2 = temp_dir / "test2.py"

        file1.write_text("print('hello')")
        file2.write_text("print('world')")

        identifier = FileIdentifier(temp_dir, config)

        hash1 = identifier._get_file_content_hash(file1)
        hash2 = identifier._get_file_content_hash(file2)

        assert hash1 != hash2

    def test_should_index_file_with_config(self, temp_dir, config):
        """Test file filtering based on configuration."""
        identifier = FileIdentifier(temp_dir, config)

        # Should index these extensions
        assert identifier._should_index_file("test.py") is True
        assert identifier._should_index_file("test.js") is True
        assert identifier._should_index_file("README.md") is True

        # Should not index these
        assert identifier._should_index_file("test.txt") is False
        assert identifier._should_index_file("test.exe") is False

        # Should exclude files in excluded directories
        assert identifier._should_index_file("node_modules/test.js") is False
        assert identifier._should_index_file(".git/config") is False

    def test_should_index_file_without_config(self, temp_dir):
        """Test file filtering without configuration (uses defaults)."""
        identifier = FileIdentifier(temp_dir, None)

        # Should index common extensions
        assert identifier._should_index_file("test.py") is True
        assert identifier._should_index_file("test.js") is True
        assert identifier._should_index_file("README.md") is True

        # Should not index uncommon extensions
        assert identifier._should_index_file("test.exe") is False
        assert identifier._should_index_file("test.bin") is False

    def test_git_metadata_extraction(self, git_repo, config):
        """Test extraction of git-specific metadata."""
        identifier = FileIdentifier(git_repo, config)
        test_file = git_repo / "test.py"

        metadata = identifier.get_file_metadata(test_file)

        # Check required fields
        assert "project_id" in metadata
        assert "file_path" in metadata
        assert "file_hash" in metadata
        assert "indexed_at" in metadata
        assert metadata["git_available"] is True

        # Check git-specific fields
        assert "git_hash" in metadata
        assert "branch" in metadata
        assert "commit_hash" in metadata

        assert metadata["git_hash"] is not None
        assert metadata["branch"] is not None
        assert metadata["commit_hash"] is not None

    def test_filesystem_metadata_extraction(self, non_git_dir, config):
        """Test extraction of filesystem-based metadata."""
        identifier = FileIdentifier(non_git_dir, config)
        test_file = non_git_dir / "test.py"

        metadata = identifier.get_file_metadata(test_file)

        # Check required fields
        assert "project_id" in metadata
        assert "file_path" in metadata
        assert "file_hash" in metadata
        assert "indexed_at" in metadata
        assert metadata["git_available"] is False

        # Check filesystem-specific fields
        assert "file_mtime" in metadata
        assert "file_size" in metadata

        assert isinstance(metadata["file_mtime"], int)
        assert isinstance(metadata["file_size"], int)

    def test_get_current_files_git(self, git_repo, config):
        """Test getting current files in git repository."""
        # Add more files
        (git_repo / "src" / "main.py").parent.mkdir(exist_ok=True)
        (git_repo / "src" / "main.py").write_text("# main file")
        (git_repo / "ignore.txt").write_text("should be ignored")

        # Commit the new python file only
        subprocess.run(["git", "add", "src/main.py"], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "Add main.py"], cwd=git_repo, check=True)

        identifier = FileIdentifier(git_repo, config)
        current_files = identifier.get_current_files()

        # Should include committed files that match extensions
        file_paths = set(current_files.keys())
        assert "test.py" in file_paths
        assert "src/main.py" in file_paths

        # Should not include uncommitted or ignored files
        assert "ignore.txt" not in file_paths

    def test_get_current_files_non_git(self, non_git_dir, config):
        """Test getting current files in non-git directory."""
        identifier = FileIdentifier(non_git_dir, config)
        current_files = identifier.get_current_files()

        file_paths = set(current_files.keys())

        # Should include files with allowed extensions
        assert "test.py" in file_paths
        assert "test.js" in file_paths
        assert "README.md" in file_paths

        # Should not include files with disallowed extensions
        assert "ignore.txt" not in file_paths

    def test_file_signature_git_vs_non_git(self, temp_dir, config):
        """Test that file signatures work correctly for git and non-git."""
        # Create identical file content
        test_content = "print('hello world')"

        # Test in git repo
        git_dir = temp_dir / "git_repo"
        git_dir.mkdir()
        subprocess.run(["git", "init"], cwd=git_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=git_dir, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=git_dir, check=True
        )

        git_file = git_dir / "test.py"
        git_file.write_text(test_content)
        subprocess.run(["git", "add", "test.py"], cwd=git_dir, check=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=git_dir, check=True)

        # Test in non-git directory
        non_git_dir = temp_dir / "non_git"
        non_git_dir.mkdir()
        non_git_file = non_git_dir / "test.py"
        non_git_file.write_text(test_content)

        # Get metadata
        git_config = Config(codebase_dir=git_dir)
        non_git_config = Config(codebase_dir=non_git_dir)

        git_identifier = FileIdentifier(git_dir, git_config)
        non_git_identifier = FileIdentifier(non_git_dir, non_git_config)

        git_metadata = git_identifier.get_file_metadata(git_file)
        non_git_metadata = non_git_identifier.get_file_metadata(non_git_file)

        # File hashes should be the same (same content)
        assert git_metadata["file_hash"] == non_git_metadata["file_hash"]

        # But signatures should be different (git uses git_hash, non-git uses file_hash)
        git_signature = git_identifier.get_file_signature(git_metadata)
        non_git_signature = non_git_identifier.get_file_signature(non_git_metadata)

        # Git signature should be git_hash, non-git should be file_hash
        assert git_signature == git_metadata["git_hash"]
        assert non_git_signature == non_git_metadata["file_hash"]

    def test_point_id_creation(self, git_repo, config):
        """Test creation of unique point IDs."""
        identifier = FileIdentifier(git_repo, config)
        test_file = git_repo / "test.py"

        metadata = identifier.get_file_metadata(test_file)

        point_id_0 = identifier.create_point_id(metadata, 0)
        point_id_1 = identifier.create_point_id(metadata, 1)

        # Should include project_id, signature, and chunk_index
        assert point_id_0 != point_id_1
        assert point_id_0.endswith(":0")
        assert point_id_1.endswith(":1")

        # Should start with project_id
        project_id = metadata["project_id"]
        assert point_id_0.startswith(f"{project_id}:")
        assert point_id_1.startswith(f"{project_id}:")

    @patch("subprocess.run")
    def test_git_command_failure_handling(self, mock_run, temp_dir, config):
        """Test graceful handling of git command failures."""
        # Mock git command to fail
        mock_run.side_effect = subprocess.CalledProcessError(1, "git")

        identifier = FileIdentifier(temp_dir, config)

        # Should detect as non-git
        assert identifier.git_available is False

        # Should still work for file operations
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')")

        metadata = identifier.get_file_metadata(test_file)
        assert metadata["git_available"] is False
        assert "file_mtime" in metadata
        assert "file_size" in metadata

    def test_file_not_found_handling(self, temp_dir, config):
        """Test handling of non-existent files."""
        identifier = FileIdentifier(temp_dir, config)
        non_existent_file = temp_dir / "does_not_exist.py"

        # Should handle gracefully
        file_hash = identifier._get_file_content_hash(non_existent_file)
        assert file_hash.startswith("sha256:error-")

    def test_relative_path_handling(self, temp_dir, config):
        """Test that relative paths are handled correctly."""
        # Create nested directory structure
        nested_dir = temp_dir / "src" / "utils"
        nested_dir.mkdir(parents=True)
        test_file = nested_dir / "helper.py"
        test_file.write_text("def helper(): pass")

        identifier = FileIdentifier(temp_dir, config)
        metadata = identifier.get_file_metadata(test_file)

        # Should store relative path from project root
        assert metadata["file_path"] == "src/utils/helper.py"
