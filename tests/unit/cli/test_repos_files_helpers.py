"""Unit tests for repository file browsing helper functions."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path


class TestGetRepoIdFromAlias:
    """Tests for get_repo_id_from_alias() helper function."""

    @pytest.mark.asyncio
    async def test_get_repo_id_from_alias_success(self):
        """Test successful lookup of repository ID from alias."""
        # Arrange
        from code_indexer.api_clients.repos_client import ActivatedRepository

        mock_repos = [
            ActivatedRepository(
                alias="myrepo",
                current_branch="main",
                sync_status="synced",
                last_sync="2025-01-01T00:00:00Z",
                activation_date="2025-01-01T00:00:00Z",
            ),
            ActivatedRepository(
                alias="other-repo",
                current_branch="main",
                sync_status="synced",
                last_sync="2025-01-01T00:00:00Z",
                activation_date="2025-01-01T00:00:00Z",
            ),
        ]

        # Act
        from code_indexer.cli_repos_files import get_repo_id_from_alias

        with patch("code_indexer.cli_repos_files.ReposAPIClient") as mock_client_class:
            mock_client = Mock()
            mock_client.list_activated_repositories = AsyncMock(return_value=mock_repos)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            result = await get_repo_id_from_alias("myrepo", Path("/fake/project/root"))

        # Assert
        assert result == "myrepo"  # For now, alias IS the repo_id


class TestFormatFileSize:
    """Tests for format_file_size() helper function."""

    def test_format_bytes(self):
        """Test formatting bytes (< 1 KB)."""
        from code_indexer.cli_repos_files import format_file_size

        assert format_file_size(512) == "512 B"

    def test_format_kilobytes(self):
        """Test formatting kilobytes."""
        from code_indexer.cli_repos_files import format_file_size

        assert format_file_size(1024) == "1.0 KB"

    def test_format_megabytes(self):
        """Test formatting megabytes."""
        from code_indexer.cli_repos_files import format_file_size

        assert format_file_size(1048576) == "1.0 MB"

    def test_format_gigabytes(self):
        """Test formatting gigabytes."""
        from code_indexer.cli_repos_files import format_file_size

        assert format_file_size(1073741824) == "1.0 GB"


class TestDisplayFileTree:
    """Tests for display_file_tree() helper function."""

    def test_display_empty_tree(self, capsys):
        """Test displaying an empty file tree."""
        from code_indexer.cli_repos_files import display_file_tree

        display_file_tree([], "/src")

        captured = capsys.readouterr()
        assert "(empty directory)" in captured.out

    def test_display_single_file(self, capsys):
        """Test displaying a single file."""
        from code_indexer.cli_repos_files import display_file_tree

        files = [
            {"name": "main.py", "type": "file", "size": 1024, "is_directory": False}
        ]

        display_file_tree(files, "/src")

        captured = capsys.readouterr()
        assert "main.py" in captured.out
        assert "1.0 KB" in captured.out
