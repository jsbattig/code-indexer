"""Unit tests for ReposAPIClient file listing methods.

Tests for list_repository_files() and get_file_content() methods
that support repository file browsing in Story #494.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path


class TestListRepositoryFiles:
    """Tests for list_repository_files() method."""

    @pytest.mark.asyncio
    async def test_list_repository_files_basic(self):
        """Test listing files in repository root directory."""
        from code_indexer.api_clients.repos_client import ReposAPIClient

        # Arrange
        client = ReposAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "testuser", "password": "testpass"},
            project_root=Path("/fake/project"),
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "files": [
                {
                    "full_path": "backend-api/main.py",
                    "name": "main.py",
                    "size": 1024,
                    "modified": "2025-01-01T00:00:00Z",
                    "is_directory": False,
                    "component_repo": "backend-api",
                }
            ]
        }

        with patch.object(
            client, "_authenticated_request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            # Act
            result = await client.list_repository_files(repo_alias="myrepo")

            # Assert
            assert "files" in result
            assert len(result["files"]) == 1
            assert result["files"][0]["name"] == "main.py"
            mock_request.assert_called_once_with(
                "GET",
                "/api/repositories/myrepo/files",
                params={"recursive": "false"},
            )

        await client.close()


class TestGetFileContent:
    """Tests for get_file_content() method."""

    @pytest.mark.asyncio
    async def test_get_file_content_basic(self):
        """Test getting file metadata for a specific file."""
        from code_indexer.api_clients.repos_client import ReposAPIClient

        # Arrange
        client = ReposAPIClient(
            server_url="http://localhost:8000",
            credentials={"username": "testuser", "password": "testpass"},
            project_root=Path("/fake/project"),
        )

        # Mock list_repository_files to return file info
        mock_file_info = {
            "full_path": "backend-api/main.py",
            "name": "main.py",
            "size": 1024,
            "modified": "2025-01-01T00:00:00Z",
            "is_directory": False,
            "component_repo": "backend-api",
        }

        with patch.object(
            client, "list_repository_files", new_callable=AsyncMock
        ) as mock_list:
            mock_list.return_value = {"files": [mock_file_info]}

            # Act
            result = await client.get_file_content(
                repo_alias="myrepo", file_path="main.py"
            )

            # Assert
            assert result["name"] == "main.py"
            assert result["size"] == 1024
            assert result["is_directory"] is False
            mock_list.assert_called_once_with(
                repo_alias="myrepo", path="", recursive=False
            )

        await client.close()
