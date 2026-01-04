"""Unit tests for DashboardService.get_temporal_index_status() method.

Story #669 AC6: Web UI temporal status display
Tests temporal format detection and status reporting
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from code_indexer.server.services.dashboard_service import DashboardService


class TestGetTemporalIndexStatus:
    """Test suite for DashboardService.get_temporal_index_status() method."""

    def test_get_temporal_status_v2_format(self):
        """Test get_temporal_index_status returns v2 format with file count."""
        # Arrange
        service = DashboardService()
        username = "testuser"
        repo_alias = "test-repo"

        with patch.object(service, "_get_activated_repo_manager") as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.data_dir = "/fake/data"
            mock_manager.get_repository.return_value = {
                "alias": repo_alias,
                "path": "/fake/repo/path",
                "collection_name": "test-collection"
            }
            mock_manager_getter.return_value = mock_manager

            # Mock temporal collection path exists
            with patch("code_indexer.server.services.dashboard_service.Path") as MockPath:
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = True
                MockPath.return_value.__truediv__.return_value.__truediv__.return_value = mock_temporal_path

                # Mock format detection at source module
                with patch("code_indexer.storage.temporal_metadata_store.TemporalMetadataStore") as MockStore:
                    MockStore.detect_format.return_value = "v2"

                    # Mock vector file count at source module
                    with patch("code_indexer.storage.filesystem_vector_store.FilesystemVectorStore") as MockVectorStore:
                        mock_store_instance = MockVectorStore.return_value
                        mock_store_instance.get_indexed_file_count_fast.return_value = 150

                        # Act
                        result = service.get_temporal_index_status(username, repo_alias)

                        # Assert
                        assert result["format"] == "v2"
                        assert result["file_count"] == 150
                        assert result["needs_reindex"] is False
                        assert "active" in result["message"].lower() or "v2" in result["message"].lower()
                        assert "150" in result["message"]

    def test_get_temporal_status_v1_format(self):
        """Test get_temporal_index_status returns v1 format with reindex warning."""
        # Arrange
        service = DashboardService()
        username = "testuser"
        repo_alias = "test-repo"

        with patch.object(service, "_get_activated_repo_manager") as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.data_dir = "/fake/data"
            mock_manager.get_repository.return_value = {
                "alias": repo_alias,
                "path": "/fake/repo/path",
                "collection_name": "test-collection"
            }
            mock_manager_getter.return_value = mock_manager

            # Mock temporal collection path exists
            with patch("code_indexer.server.services.dashboard_service.Path") as MockPath:
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = True
                MockPath.return_value.__truediv__.return_value.__truediv__.return_value = mock_temporal_path

                # Mock format detection at source module
                with patch("code_indexer.storage.temporal_metadata_store.TemporalMetadataStore") as MockStore:
                    MockStore.detect_format.return_value = "v1"

                    # Mock vector file count at source module
                    with patch("code_indexer.storage.filesystem_vector_store.FilesystemVectorStore") as MockVectorStore:
                        mock_store_instance = MockVectorStore.return_value
                        mock_store_instance.get_indexed_file_count_fast.return_value = 85

                        # Act
                        result = service.get_temporal_index_status(username, repo_alias)

                        # Assert
                        assert result["format"] == "v1"
                        assert result["file_count"] == 85
                        assert result["needs_reindex"] is True
                        assert "legacy" in result["message"].lower() or "v1" in result["message"].lower()
                        assert "re-index" in result["message"].lower()

    def test_get_temporal_status_no_index(self):
        """Test get_temporal_index_status returns none when no temporal index exists."""
        # Arrange
        service = DashboardService()
        username = "testuser"
        repo_alias = "test-repo"

        with patch.object(service, "_get_activated_repo_manager") as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.data_dir = "/fake/data"
            mock_manager.get_repository.return_value = {
                "alias": repo_alias,
                "path": "/fake/repo/path",
                "collection_name": "test-collection"
            }
            mock_manager_getter.return_value = mock_manager

            with patch("code_indexer.server.services.dashboard_service.Path") as MockPath:
                # Mock temporal collection path does not exist
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = False
                MockPath.return_value.__truediv__.return_value.__truediv__.return_value = mock_temporal_path

                # Act
                result = service.get_temporal_index_status(username, repo_alias)

                # Assert
                assert result["format"] == "none"
                assert result["file_count"] == 0
                assert result["needs_reindex"] is False
                assert "no temporal" in result["message"].lower()

    def test_get_temporal_status_repository_not_found(self):
        """Test get_temporal_index_status raises FileNotFoundError for invalid repository."""
        # Arrange
        service = DashboardService()
        username = "testuser"
        repo_alias = "nonexistent-repo"

        with patch.object(service, "_get_activated_repo_manager") as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.get_repository.return_value = None
            mock_manager_getter.return_value = mock_manager

            # Act & Assert
            with pytest.raises(FileNotFoundError) as exc_info:
                service.get_temporal_index_status(username, repo_alias)

            assert "not found" in str(exc_info.value).lower()

    def test_get_temporal_status_requires_username_parameter(self):
        """Test get_temporal_index_status accepts and uses username parameter.

        This test ensures the method signature includes username and correctly
        calls get_repository(username, user_alias) instead of the non-existent
        get_repository_by_alias() method.
        """
        # Arrange
        service = DashboardService()
        username = "testuser"
        repo_alias = "test-repo"

        with patch.object(service, "_get_activated_repo_manager") as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.data_dir = "/fake/data"
            # Mock the CORRECT signature: get_repository(username, user_alias)
            mock_manager.get_repository.return_value = {
                "alias": repo_alias,
                "path": "/fake/repo/path",
                "collection_name": "test-collection"
            }
            mock_manager_getter.return_value = mock_manager

            # Mock temporal collection path does not exist for simple test
            with patch("code_indexer.server.services.dashboard_service.Path") as MockPath:
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = False
                MockPath.return_value.__truediv__.return_value.__truediv__.return_value = mock_temporal_path

                # Act - Call with username parameter
                result = service.get_temporal_index_status(username=username, repo_alias=repo_alias)

                # Assert - Verify get_repository was called with correct signature
                mock_manager.get_repository.assert_called_once_with(username, repo_alias)
                assert result["format"] == "none"
