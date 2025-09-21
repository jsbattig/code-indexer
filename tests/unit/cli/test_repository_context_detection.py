"""Tests for repository context detection functionality.

Tests the ability to detect activated repository context from current directory
and provide repository-aware enhancements to sync functionality.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from dataclasses import dataclass
from typing import Optional

from code_indexer.sync.repository_context_detector import (
    RepositoryContextDetector,
    RepositoryContextError,
)


@dataclass
class MockRepositoryContext:
    """Mock repository context for testing."""

    user_alias: str
    golden_repo_alias: str
    repository_path: Path
    current_branch: str
    sync_status: str
    last_sync_time: Optional[str] = None
    has_uncommitted_changes: bool = False
    has_conflicts: bool = False


class TestRepositoryContextDetector:
    """Test repository context detection functionality."""

    def test_detect_repository_context_in_activated_repo(self, tmp_path):
        """Test detection when current directory is in an activated repository."""
        # Arrange
        activated_repo_path = (
            tmp_path
            / ".cidx-server"
            / "data"
            / "activated-repos"
            / "user"
            / "my-project"
        )
        activated_repo_path.mkdir(parents=True)

        # Create repository metadata
        metadata_path = activated_repo_path / ".repository-metadata.json"
        metadata_path.write_text(
            """{
            "user_alias": "my-project",
            "golden_repo_alias": "web-app",
            "activation_date": "2024-01-01T10:00:00Z",
            "last_sync_time": "2024-01-01T12:00:00Z"
        }"""
        )

        # Create git directory to simulate repository
        git_dir = activated_repo_path / ".git"
        git_dir.mkdir()

        detector = RepositoryContextDetector()

        # Mock git commands to return clean status
        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            # Mock git branch --show-current
            # Mock git status --porcelain
            mock_run.side_effect = [
                Mock(returncode=0, stdout="main"),  # git branch --show-current
                Mock(returncode=0, stdout=""),  # git status --porcelain (clean)
                Mock(
                    returncode=0, stdout=""
                ),  # git status --porcelain (uncommitted check)
                Mock(
                    returncode=0, stdout=""
                ),  # git status --porcelain (conflict check)
            ]

            # Act
            context = detector.detect_repository_context(activated_repo_path)

            # Assert
            assert context is not None
            assert context.user_alias == "my-project"
            assert context.golden_repo_alias == "web-app"
            assert context.repository_path == activated_repo_path
            assert context.sync_status == "synced"

    def test_detect_repository_context_not_in_repository(self, tmp_path):
        """Test detection when current directory is not in a repository."""
        # Arrange
        non_repo_path = tmp_path / "random-directory"
        non_repo_path.mkdir()

        detector = RepositoryContextDetector()

        # Act
        context = detector.detect_repository_context(non_repo_path)

        # Assert
        assert context is None

    def test_detect_repository_context_in_subdirectory(self, tmp_path):
        """Test detection when current directory is in subdirectory of activated repo."""
        # Arrange
        activated_repo_path = (
            tmp_path
            / ".cidx-server"
            / "data"
            / "activated-repos"
            / "user"
            / "my-project"
        )
        activated_repo_path.mkdir(parents=True)

        subdirectory = activated_repo_path / "src" / "components"
        subdirectory.mkdir(parents=True)

        # Create repository metadata at root
        metadata_path = activated_repo_path / ".repository-metadata.json"
        metadata_path.write_text(
            """{
            "user_alias": "my-project",
            "golden_repo_alias": "web-app",
            "activation_date": "2024-01-01T10:00:00Z"
        }"""
        )

        git_dir = activated_repo_path / ".git"
        git_dir.mkdir()

        detector = RepositoryContextDetector()

        # Act
        context = detector.detect_repository_context(subdirectory)

        # Assert
        assert context is not None
        assert context.user_alias == "my-project"
        assert context.repository_path == activated_repo_path

    def test_get_repository_sync_status_synced(self, tmp_path):
        """Test getting sync status for a synced repository."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        # Mock git status showing no changes
        detector = RepositoryContextDetector()

        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""

            # Act
            status = detector.get_repository_sync_status(repo_path)

            # Assert
            assert status == "synced"

    def test_get_repository_sync_status_with_uncommitted_changes(self, tmp_path):
        """Test getting sync status when repository has uncommitted changes."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        detector = RepositoryContextDetector()

        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "M file.py\n?? new_file.py"

            # Act
            status = detector.get_repository_sync_status(repo_path)

            # Assert
            assert status == "needs_sync"

    def test_get_repository_sync_status_with_conflicts(self, tmp_path):
        """Test getting sync status when repository has merge conflicts."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        detector = RepositoryContextDetector()

        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "UU conflicted_file.py"

            # Act
            status = detector.get_repository_sync_status(repo_path)

            # Assert
            assert status == "conflict"

    def test_get_current_branch(self, tmp_path):
        """Test getting current git branch."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        detector = RepositoryContextDetector()

        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "main"

            # Act
            branch = detector.get_current_branch(repo_path)

            # Assert
            assert branch == "main"

    def test_get_current_branch_git_error(self, tmp_path):
        """Test getting current branch when git command fails."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        detector = RepositoryContextDetector()

        with patch(
            "code_indexer.sync.repository_context_detector.subprocess.run"
        ) as mock_run:
            mock_run.return_value.returncode = 128
            mock_run.return_value.stderr = "fatal: not a git repository"

            # Act
            branch = detector.get_current_branch(repo_path)

            # Assert
            assert branch == "unknown"

    def test_find_repository_root_success(self, tmp_path):
        """Test finding repository root directory walking up from path."""
        # Arrange
        repo_root = tmp_path / "repo"
        repo_root.mkdir()

        metadata_path = repo_root / ".repository-metadata.json"
        metadata_path.write_text("{}")

        subdirectory = repo_root / "src" / "components"
        subdirectory.mkdir(parents=True)

        detector = RepositoryContextDetector()

        # Act
        found_root = detector.find_repository_root(subdirectory)

        # Assert
        assert found_root == repo_root

    def test_find_repository_root_not_found(self, tmp_path):
        """Test finding repository root when no repository metadata found."""
        # Arrange
        non_repo_path = tmp_path / "not-a-repo"
        non_repo_path.mkdir()

        detector = RepositoryContextDetector()

        # Act
        found_root = detector.find_repository_root(non_repo_path)

        # Assert
        assert found_root is None

    def test_load_repository_metadata_valid(self, tmp_path):
        """Test loading valid repository metadata."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        metadata_path = repo_path / ".repository-metadata.json"
        metadata_path.write_text(
            """{
            "user_alias": "test-project",
            "golden_repo_alias": "golden-project",
            "activation_date": "2024-01-01T10:00:00Z",
            "last_sync_time": "2024-01-01T12:00:00Z"
        }"""
        )

        detector = RepositoryContextDetector()

        # Act
        metadata = detector.load_repository_metadata(repo_path)

        # Assert
        assert metadata["user_alias"] == "test-project"
        assert metadata["golden_repo_alias"] == "golden-project"
        assert "activation_date" in metadata
        assert "last_sync_time" in metadata

    def test_load_repository_metadata_missing_file(self, tmp_path):
        """Test loading repository metadata when file doesn't exist."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        detector = RepositoryContextDetector()

        # Act & Assert
        with pytest.raises(RepositoryContextError) as exc_info:
            detector.load_repository_metadata(repo_path)

        assert "Repository metadata not found" in str(exc_info.value)

    def test_load_repository_metadata_invalid_json(self, tmp_path):
        """Test loading repository metadata with invalid JSON."""
        # Arrange
        repo_path = tmp_path / "repo"
        repo_path.mkdir()

        metadata_path = repo_path / ".repository-metadata.json"
        metadata_path.write_text("invalid json content")

        detector = RepositoryContextDetector()

        # Act & Assert
        with pytest.raises(RepositoryContextError) as exc_info:
            detector.load_repository_metadata(repo_path)

        assert "Invalid repository metadata JSON" in str(exc_info.value)

    def test_is_activated_repository_path_true(self, tmp_path):
        """Test checking if path is in activated repository directory structure."""
        # Arrange
        activated_repos_path = (
            tmp_path / ".cidx-server" / "data" / "activated-repos" / "user" / "project"
        )
        activated_repos_path.mkdir(parents=True)

        detector = RepositoryContextDetector()

        # Act
        result = detector.is_activated_repository_path(activated_repos_path)

        # Assert
        assert result is True

    def test_is_activated_repository_path_false(self, tmp_path):
        """Test checking if path is not in activated repository directory structure."""
        # Arrange
        regular_path = tmp_path / "regular" / "directory"
        regular_path.mkdir(parents=True)

        detector = RepositoryContextDetector()

        # Act
        result = detector.is_activated_repository_path(regular_path)

        # Assert
        assert result is False

    def test_detect_repository_context_error_handling(self, tmp_path):
        """Test repository context detection with error conditions."""
        # Arrange
        activated_repo_path = (
            tmp_path
            / ".cidx-server"
            / "data"
            / "activated-repos"
            / "user"
            / "broken-repo"
        )
        activated_repo_path.mkdir(parents=True)

        # Create corrupted metadata file
        metadata_path = activated_repo_path / ".repository-metadata.json"
        metadata_path.write_text("corrupted json {")

        detector = RepositoryContextDetector()

        # Act & Assert
        with pytest.raises(RepositoryContextError):
            detector.detect_repository_context(activated_repo_path)
