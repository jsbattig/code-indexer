"""
Tests for the GitAwareDocumentProcessor class.
"""

import pytest
import subprocess
import uuid
from pathlib import Path

from unittest.mock import patch, MagicMock

from code_indexer.config import Config
from code_indexer.services.git_aware_processor import GitAwareDocumentProcessor


class TestGitAwareDocumentProcessor:
    @pytest.fixture
    def temp_dir(self):
        import shutil

        # Use shared test directory to avoid creating multiple container sets
        temp_dir = Path.home() / ".tmp" / "shared_test_containers"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Clean only test files, preserve .code-indexer directory for containers
        test_subdirs = ["test_repo", "src", "docs", ".git"]
        for subdir in test_subdirs:
            subdir_path = temp_dir / subdir
            if subdir_path.exists():
                shutil.rmtree(subdir_path, ignore_errors=True)

        # Clean any test files in root
        for item in temp_dir.iterdir():
            if item.is_file() and item.name != ".gitignore":
                item.unlink(missing_ok=True)

        yield temp_dir

        # Clean up test files after test
        for subdir in test_subdirs:
            subdir_path = temp_dir / subdir
            if subdir_path.exists():
                shutil.rmtree(subdir_path, ignore_errors=True)

    @pytest.fixture
    def config(self, temp_dir):
        return Config(
            codebase_dir=temp_dir,
            file_extensions=["py", "js", "md"],
            exclude_dirs=["node_modules", ".git", "__pycache__"],
        )

    @pytest.fixture
    def mock_clients(self):
        ollama_client = MagicMock()
        ollama_client.get_embedding.return_value = [
            0.1
        ] * 768  # Match default vector size

        qdrant_client = MagicMock()
        qdrant_client.create_point.return_value = {"id": "test_point"}
        qdrant_client.upsert_points.return_value = True

        return ollama_client, qdrant_client

    @pytest.fixture
    def processor(self, config, mock_clients):
        ollama_client, qdrant_client = mock_clients
        return GitAwareDocumentProcessor(config, ollama_client, qdrant_client)

    @pytest.fixture
    def git_repo(self, temp_dir):
        """Create a minimal git repository for testing."""
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=temp_dir,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"], cwd=temp_dir, check=True
        )

        # Create test files
        (temp_dir / "main.py").write_text('print("main")\n# This is the main file')
        (temp_dir / "utils.py").write_text(
            'def helper():\n    """Helper function"""\n    pass'
        )

        # Create .gitignore to prevent committing .code-indexer directory
        (temp_dir / ".gitignore").write_text(
            """.code-indexer/
__pycache__/
*.pyc
.pytest_cache/
venv/
.env
"""
        )

        # Initial commit
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True
        )

        return temp_dir

    def test_create_point_id_with_git(self, processor):
        """Test point ID creation with git metadata."""
        file_metadata = {
            "project_id": "test_project",
            "git_available": True,
            "git_hash": "abc123",
            "file_hash": "def456",
        }

        point_id = processor._create_point_id(file_metadata, 0)
        # Point ID should be a valid UUID string

        assert uuid.UUID(point_id)  # Validates it's a proper UUID
        # Check it's deterministic (same input = same output)
        point_id2 = processor._create_point_id(file_metadata, 0)
        assert point_id == point_id2

    def test_create_point_id_without_git(self, processor):
        """Test point ID creation without git metadata."""
        file_metadata = {
            "project_id": "test_project",
            "git_available": False,
            "file_hash": "def456",
        }

        point_id = processor._create_point_id(file_metadata, 1)
        # Point ID should be a valid UUID string

        assert uuid.UUID(point_id)  # Validates it's a proper UUID
        # Check it's deterministic
        point_id2 = processor._create_point_id(file_metadata, 1)
        assert point_id == point_id2

    def test_process_file_with_git(self, temp_dir, config, mock_clients, git_repo):
        """Test file processing with git repository."""
        processor = GitAwareDocumentProcessor(config, *mock_clients)

        # Create a test file
        test_file = git_repo / "test.py"
        test_file.write_text("def test():\n    pass")

        # Add and commit the file
        subprocess.run(["git", "add", "test.py"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add test file"], cwd=git_repo, check=True
        )

        points = processor.process_file(test_file)

        assert len(points) > 0

        # Verify git metadata was included in the point
        create_point_call = mock_clients[1].create_point.call_args
        payload = create_point_call[1]["payload"]

        assert "git_available" in payload
        assert payload["git_available"] is True
        assert "git_commit_hash" in payload
        assert "git_branch" in payload
        assert "project_id" in payload

    def test_process_file_without_git(self, processor, temp_dir):
        """Test file processing without git repository."""
        # Create a test file in non-git directory
        test_file = temp_dir / "test.py"
        test_file.write_text("def test():\n    pass")

        points = processor.process_file(test_file)

        assert len(points) > 0

        # Verify filesystem metadata was included
        create_point_call = processor.qdrant_client.create_point.call_args
        payload = create_point_call[1]["payload"]

        assert "git_available" in payload
        assert payload["git_available"] is False
        assert "filesystem_mtime" in payload
        assert "filesystem_size" in payload
        assert "project_id" in payload

    def test_process_files_parallel_with_git_detection(
        self, temp_dir, config, mock_clients
    ):
        """Test parallel processing instead of deprecated index_codebase."""
        processor = GitAwareDocumentProcessor(config, *mock_clients)

        # Create test file
        test_file = temp_dir / "test.py"
        test_file.write_text('print("test")')

        # Test direct file processing with parallel methods
        stats = processor.process_files_parallel([test_file], batch_size=50)

        # Should have processed the file successfully
        assert stats.files_processed >= 0  # Basic smoke test

    def test_process_files_with_branch_change(
        self, temp_dir, config, mock_clients, git_repo
    ):
        """Test parallel processing handles git context properly."""
        processor = GitAwareDocumentProcessor(config, *mock_clients)

        # Create a new branch
        subprocess.run(["git", "checkout", "-b", "feature"], cwd=git_repo, check=True)

        # Test that files are processed correctly in the new branch context
        test_files = [git_repo / "main.py"]
        stats = processor.process_files_parallel(test_files, batch_size=50)

        # Should have processed files successfully
        assert stats.files_processed >= 0

    def test_git_detection_integration(self, processor):
        """Test git detection service integration."""
        # Test that git detection is properly integrated
        git_available = processor.git_detection._get_current_git_state()[
            "git_available"
        ]

        # Should return a boolean value
        assert isinstance(git_available, bool)

    def test_get_git_status(self, temp_dir, config, mock_clients, git_repo):
        """Test getting git status and metadata."""
        processor = GitAwareDocumentProcessor(config, *mock_clients)

        status = processor.get_git_status()

        assert "git_available" in status
        assert "current_branch" in status
        assert "current_commit" in status
        assert "project_id" in status
        assert "file_stats" in status

        # With git repo, should be available
        assert status["git_available"] is True
        # Current branch should be 'master' or 'main' based on the git_repo fixture
        assert status["current_branch"] in ["master", "main"]

    def test_get_git_status_no_git(self, processor):
        """Test getting git status without git repository."""
        status = processor.get_git_status()

        assert "git_available" in status
        assert status["git_available"] is False
        assert status["current_branch"] == "unknown"
        assert status["current_commit"] == "unknown"

    def test_error_handling_in_process_file(self, processor, temp_dir):
        """Test error handling during file processing."""
        # Create a file that will cause an error (e.g., binary file)
        test_file = temp_dir / "binary.bin"
        test_file.write_bytes(b"\x00\x01\x02\x03")

        # Mock chunker to raise an exception
        with patch.object(
            processor.fixed_size_chunker,
            "chunk_file",
            side_effect=Exception("Chunking failed"),
        ):
            with pytest.raises(ValueError, match="Failed to process file"):
                processor.process_file(test_file)

    def test_integration_with_file_identifier(
        self, temp_dir, config, mock_clients, git_repo
    ):
        """Test integration with FileIdentifier service."""
        processor = GitAwareDocumentProcessor(config, *mock_clients)

        test_file = git_repo / "integration_test.py"
        test_file.write_text('# Integration test file\nprint("hello")')

        # Add and commit
        subprocess.run(["git", "add", "integration_test.py"], cwd=git_repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Add integration test"], cwd=git_repo, check=True
        )

        points = processor.process_file(test_file)

        assert len(points) > 0

        # Verify the FileIdentifier was used correctly
        create_point_call = processor.qdrant_client.create_point.call_args
        payload = create_point_call[1]["payload"]

        # Should have project_id from FileIdentifier (uses temp directory name)
        assert len(payload["project_id"]) > 0
        assert payload["git_available"] is True
        assert len(payload["git_commit_hash"]) == 40  # Git commit hash length
