"""
Tests for the GenericQueryService class.
"""

import pytest
import shutil

from pathlib import Path
from unittest.mock import patch
import subprocess

from code_indexer.config import Config
from code_indexer.services.generic_query_service import GenericQueryService


class TestGenericQueryService:
    @pytest.fixture
    def temp_dir(self):
        # Use shared test directory to avoid creating multiple container sets
        temp_dir = Path.home() / ".tmp" / "shared_test_containers"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Clean only test files, preserve .code-indexer directory for containers
        # NOTE: Don't clean .git directory here as it will be handled by git_repo fixture
        test_subdirs = ["src", "test_files"]
        for subdir in test_subdirs:
            subdir_path = temp_dir / subdir
            if subdir_path.exists():
                shutil.rmtree(subdir_path, ignore_errors=True)

        # Clean any test files in root (preserve .code-indexer)
        for item in temp_dir.iterdir():
            if item.is_file() and item.suffix in [".py", ".js", ".md", ".txt"]:
                item.unlink(missing_ok=True)

        yield temp_dir

        # Clean up test files after test (but preserve .git for subsequent tests)
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
    def query_service(self, temp_dir, config):
        return GenericQueryService(temp_dir, config)

    @pytest.fixture
    def git_repo(self, temp_dir):
        """Create a minimal git repository for testing."""
        # Remove any existing git repository to ensure clean state
        git_dir = temp_dir / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)

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
        (temp_dir / "main.py").write_text('print("main")')
        (temp_dir / "utils.py").write_text("def helper(): pass")

        # Initial commit - only add the specific test files
        subprocess.run(["git", "add", "main.py", "utils.py"], cwd=temp_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True
        )

        return temp_dir

    def test_filter_results_no_git(self, query_service):
        """Test that all results are returned when git is not available."""
        test_results = [
            {"payload": {"path": "test1.py", "git_available": False}},
            {"payload": {"path": "test2.py", "git_available": False}},
        ]

        with patch.object(query_service.file_identifier, "git_available", False):
            filtered = query_service.filter_results_by_branch(test_results)

        assert len(filtered) == 2
        assert filtered == test_results

    def test_filter_results_with_git(self, temp_dir, config, git_repo):
        """Test filtering results when git is available."""
        query_service = GenericQueryService(git_repo, config)

        test_results = [
            {"payload": {"path": "main.py", "git_available": True}},
            {"payload": {"path": "nonexistent.py", "git_available": True}},
            {"payload": {"path": "utils.py", "git_available": True}},
        ]

        filtered = query_service.filter_results_by_branch(test_results)

        # Should only include files that exist in current branch
        assert len(filtered) == 2
        file_paths = [r["payload"]["path"] for r in filtered]
        assert "main.py" in file_paths
        assert "utils.py" in file_paths
        assert "nonexistent.py" not in file_paths

    def test_get_current_branch_context(self, temp_dir, config, git_repo):
        """Test getting current branch context."""
        query_service = GenericQueryService(git_repo, config)

        context = query_service._get_current_branch_context()

        assert "branch" in context
        assert "commit" in context
        assert "files" in context
        assert context["branch"] == "main" or context["branch"] == "master"
        assert len(context["commit"]) == 40  # Git commit hash length
        assert "main.py" in context["files"]
        assert "utils.py" in context["files"]

    def test_get_current_branch_context_no_git(self, query_service, temp_dir):
        """Test branch context when git is not available."""
        # Temporarily remove git directory to simulate no git
        git_dir = temp_dir / ".git"
        git_backup = None
        if git_dir.exists():
            import tempfile

            git_backup = tempfile.mkdtemp()
            shutil.move(str(git_dir), git_backup)

        try:
            context = query_service._get_current_branch_context()

            assert context["branch"] == "unknown"
            assert context["commit"] == "unknown"
            assert context["files"] == set()
        finally:
            # Restore git directory if it was backed up
            if git_backup and Path(git_backup).exists():
                shutil.move(str(Path(git_backup) / ".git"), str(git_dir))

    def test_is_result_current_branch_filesystem(self, query_service):
        """Test that filesystem-based results are always included."""
        result = {"payload": {"path": "test.py", "git_available": False}}
        branch_context = {"branch": "main", "commit": "abc123", "files": set()}

        assert query_service._is_result_current_branch(result, branch_context) is True

    def test_is_result_current_branch_git_exists(self, query_service):
        """Test git-based result when file exists in current branch."""
        result = {"payload": {"path": "test.py", "git_available": True}}
        branch_context = {
            "branch": "main",
            "commit": "abc123",
            "files": {"test.py", "other.py"},
        }

        assert query_service._is_result_current_branch(result, branch_context) is True

    def test_is_result_current_branch_git_missing(self, query_service):
        """Test git-based result when file doesn't exist in current branch."""
        result = {"payload": {"path": "missing.py", "git_available": True}}
        branch_context = {
            "branch": "main",
            "commit": "abc123",
            "files": {"test.py", "other.py"},
        }

        with patch.object(query_service, "_is_commit_reachable", return_value=False):
            assert (
                query_service._is_result_current_branch(result, branch_context) is False
            )

    def test_is_commit_reachable(self, temp_dir, config, git_repo):
        """Test checking if a commit is reachable."""
        query_service = GenericQueryService(git_repo, config)

        # Get current commit hash
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=git_repo,
            capture_output=True,
            text=True,
            check=True,
        )
        current_commit = result.stdout.strip()

        # Current commit should be reachable
        assert query_service._is_commit_reachable(current_commit) is True

        # Non-existent commit should not be reachable
        fake_commit = "a" * 40
        assert query_service._is_commit_reachable(fake_commit) is False

    def test_enhance_query_metadata_no_git(self, query_service):
        """Test query metadata enhancement without git."""
        with patch.object(query_service.file_identifier, "git_available", False):
            metadata = query_service.enhance_query_metadata("test query")

        assert metadata["query"] == "test query"
        assert metadata["git_available"] is False
        assert "project_id" in metadata
        assert "branch" not in metadata

    def test_enhance_query_metadata_with_git(self, temp_dir, config, git_repo):
        """Test query metadata enhancement with git."""
        query_service = GenericQueryService(git_repo, config)

        metadata = query_service.enhance_query_metadata("test query")

        assert metadata["query"] == "test query"
        assert metadata["git_available"] is True
        assert "project_id" in metadata
        assert "branch" in metadata
        assert "commit" in metadata
        assert "file_count" in metadata
        assert metadata["file_count"] == 2  # main.py and utils.py

    def test_error_handling_in_branch_context(self, query_service, temp_dir):
        """Test error handling when git commands fail."""
        # Mock subprocess to raise an exception
        with patch(
            "subprocess.run", side_effect=subprocess.CalledProcessError(1, "git")
        ):
            context = query_service._get_current_branch_context()

        # Should return default values on error
        assert context["branch"] == "unknown"
        assert context["commit"] == "unknown"
        assert context["files"] == set()

    def test_error_handling_in_result_filtering(self, query_service):
        """Test error handling during result filtering."""
        malformed_result = {"malformed": "data"}
        branch_context = {"branch": "main", "commit": "abc123", "files": {"test.py"}}

        # Should default to including the result on error
        assert (
            query_service._is_result_current_branch(malformed_result, branch_context)
            is True
        )

    def test_different_result_formats(self, query_service):
        """Test handling different result payload formats."""
        # Test direct metadata (no payload wrapper)
        result1 = {"path": "test.py", "git_available": False}
        # Test wrapped metadata
        result2 = {"payload": {"path": "test.py", "git_available": False}}

        branch_context = {"branch": "main", "commit": "abc123", "files": set()}

        assert query_service._is_result_current_branch(result1, branch_context) is True
        assert query_service._is_result_current_branch(result2, branch_context) is True

    def test_branch_filtering_uses_correct_filesystem_field_name(self, query_service):
        """Test that branch filtering uses 'path' field (Filesystem format) not 'file_path'.

        BUG REPRODUCTION: Filesystem stores file paths as 'path' field in payloads,
        but GenericQueryService was looking for 'file_path', causing all results
        to be filtered out on feature branches.

        GIVEN search results with 'path' field (actual Filesystem format)
        WHEN filtering by current branch with file in branch_context
        THEN file path correctly extracted and result included
        """
        # Mock result with ACTUAL Filesystem structure (uses "path" not "file_path")
        result = {
            "payload": {
                "path": "src/auth/login.py",  # Filesystem uses "path"
                "git_available": True,
                "content": "test content",
            }
        }

        branch_context = {
            "branch": "feature-branch",
            "commit": "abc123def456",
            "files": {"src/auth/login.py", "src/other.py"},  # File exists in branch
        }

        # Should return True because file exists in current branch
        # BUG: Returns False because it looks for "file_path" instead of "path"
        assert query_service._is_result_current_branch(result, branch_context) is True

    def test_branch_filtering_path_field_not_in_branch(self, query_service):
        """Test that results with 'path' field are correctly filtered when file NOT in branch."""
        # Mock result with ACTUAL Filesystem structure
        result = {
            "payload": {
                "path": "src/deleted_file.py",  # Filesystem uses "path"
                "git_available": True,
                "content": "old content",
            }
        }

        branch_context = {
            "branch": "feature-branch",
            "commit": "abc123def456",
            "files": {"src/auth/login.py", "src/other.py"},  # File NOT in branch
        }

        # Mock commit reachability check to return False
        with patch.object(query_service, "_is_commit_reachable", return_value=False):
            # Should return False because file doesn't exist in current branch
            assert (
                query_service._is_result_current_branch(result, branch_context) is False
            )
