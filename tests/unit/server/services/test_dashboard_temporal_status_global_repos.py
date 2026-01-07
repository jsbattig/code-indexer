"""Unit tests for DashboardService.get_temporal_index_status() global repo handling.

Bug Fix: Global repos fail with "Repository not found" because the method
uses activated_manager instead of GlobalRegistry for global repos.

When username="_global", the method should:
1. Use GlobalRegistry to look up the global repo by alias
2. Get the index_path from the registry metadata
3. Use that index_path to check for temporal index

Tests verify the fix works correctly for global repos.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from code_indexer.server.services.dashboard_service import DashboardService


class TestGetTemporalIndexStatusGlobalRepos:
    """Test suite for global repo handling in get_temporal_index_status()."""

    def test_global_repo_uses_global_registry(self):
        """Test that global repos (username='_global') use GlobalRegistry to get index_path.

        When username="_global", the method should:
        1. NOT call activated_manager.get_repository()
        2. Instead use GlobalRegistry to look up the repo
        3. Get index_path from the registry metadata
        """
        # Arrange
        service = DashboardService()
        username = "_global"
        repo_alias = "test-repo-global"
        expected_index_path = "/fake/golden-repos/test-repo/v_123/index"

        # Mock GlobalRegistry at source module (lazy import in function)
        with patch(
            "code_indexer.global_repos.global_registry.GlobalRegistry"
        ) as MockRegistry:
            mock_registry_instance = MagicMock()
            mock_registry_instance.get_global_repo.return_value = {
                "repo_name": "test-repo",
                "alias_name": "test-repo-global",
                "index_path": expected_index_path,
            }
            MockRegistry.return_value = mock_registry_instance

            # Mock temporal collection path does not exist (simple case)
            with patch(
                "code_indexer.server.services.dashboard_service.Path"
            ) as MockPath:
                # Mock path operations for index_dir / temporal_collection_name
                mock_index_dir = MagicMock()
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = False
                mock_index_dir.__truediv__ = MagicMock(return_value=mock_temporal_path)

                # Path(expected_index_path) / ".code-indexer" / "index"
                mock_code_indexer_path = MagicMock()
                mock_code_indexer_path.__truediv__ = MagicMock(return_value=mock_index_dir)

                mock_main_path = MagicMock()
                mock_main_path.__truediv__ = MagicMock(return_value=mock_code_indexer_path)
                MockPath.return_value = mock_main_path

                # Act
                result = service.get_temporal_index_status(username, repo_alias)

                # Assert - GlobalRegistry was used to look up the repo
                MockRegistry.assert_called_once()
                mock_registry_instance.get_global_repo.assert_called_once_with(repo_alias)

                # Assert - Result is valid (no temporal index in this case)
                assert result["format"] == "none"
                assert result["file_count"] == 0
                assert result["needs_reindex"] is False

    def test_global_repo_not_found_raises_error(self):
        """Test that FileNotFoundError is raised when global repo not found in registry."""
        # Arrange
        service = DashboardService()
        username = "_global"
        repo_alias = "nonexistent-repo-global"

        # Mock GlobalRegistry at source module (lazy import in function)
        with patch(
            "code_indexer.global_repos.global_registry.GlobalRegistry"
        ) as MockRegistry:
            mock_registry_instance = MagicMock()
            mock_registry_instance.get_global_repo.return_value = None
            MockRegistry.return_value = mock_registry_instance

            # Act & Assert
            with pytest.raises(FileNotFoundError) as exc_info:
                service.get_temporal_index_status(username, repo_alias)

            assert "not found" in str(exc_info.value).lower()
            assert repo_alias in str(exc_info.value)

    def test_global_repo_with_temporal_v2_index(self):
        """Test global repo with v2 temporal index returns correct status."""
        # Arrange
        service = DashboardService()
        username = "_global"
        repo_alias = "test-repo-global"
        expected_index_path = "/fake/golden-repos/test-repo/v_123"

        # Mock GlobalRegistry at source module (lazy import in function)
        with patch(
            "code_indexer.global_repos.global_registry.GlobalRegistry"
        ) as MockRegistry:
            mock_registry_instance = MagicMock()
            mock_registry_instance.get_global_repo.return_value = {
                "repo_name": "test-repo",
                "alias_name": "test-repo-global",
                "index_path": expected_index_path,
            }
            MockRegistry.return_value = mock_registry_instance

            # Mock temporal collection path exists
            with patch(
                "code_indexer.server.services.dashboard_service.Path"
            ) as MockPath:
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = True

                # Set up path chain for: Path(index_path) / ".code-indexer" / "index" / temporal_collection
                mock_index_dir = MagicMock()
                mock_index_dir.__truediv__ = MagicMock(return_value=mock_temporal_path)

                mock_code_indexer_path = MagicMock()
                mock_code_indexer_path.__truediv__ = MagicMock(return_value=mock_index_dir)

                mock_main_path = MagicMock()
                mock_main_path.__truediv__ = MagicMock(return_value=mock_code_indexer_path)
                MockPath.return_value = mock_main_path

                # Mock format detection
                with patch(
                    "code_indexer.storage.temporal_metadata_store.TemporalMetadataStore"
                ) as MockStore:
                    MockStore.detect_format.return_value = "v2"

                    # Mock vector file count
                    with patch(
                        "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
                    ) as MockVectorStore:
                        mock_store_instance = MockVectorStore.return_value
                        mock_store_instance.get_indexed_file_count_fast.return_value = 200

                        # Act
                        result = service.get_temporal_index_status(username, repo_alias)

                        # Assert
                        assert result["format"] == "v2"
                        assert result["file_count"] == 200
                        assert result["needs_reindex"] is False
                        assert "active" in result["message"].lower() or "v2" in result["message"].lower()

    def test_activated_repo_still_uses_activated_manager(self):
        """Test that non-global repos still use activated_manager (regression test).

        When username is NOT "_global", the existing behavior should be preserved:
        - Use activated_manager.get_repository() to look up the repo
        """
        # Arrange
        service = DashboardService()
        username = "testuser"  # NOT "_global"
        repo_alias = "test-repo"

        with patch.object(
            service, "_get_activated_repo_manager"
        ) as mock_manager_getter:
            mock_manager = MagicMock()
            mock_manager.data_dir = "/fake/data"
            mock_manager.get_repository.return_value = {
                "alias": repo_alias,
                "path": "/fake/repo/path",
                "collection_name": "test-collection",
            }
            mock_manager_getter.return_value = mock_manager

            # Mock temporal collection path does not exist
            with patch(
                "code_indexer.server.services.dashboard_service.Path"
            ) as MockPath:
                mock_temporal_path = MagicMock(spec=Path)
                mock_temporal_path.exists.return_value = False
                MockPath.return_value.__truediv__.return_value.__truediv__.return_value = mock_temporal_path

                # Act
                result = service.get_temporal_index_status(username, repo_alias)

                # Assert - activated_manager was used (NOT GlobalRegistry)
                mock_manager.get_repository.assert_called_once_with(username, repo_alias)
                assert result["format"] == "none"

    def test_global_repo_golden_repos_dir_from_environment(self):
        """Test that golden_repos_dir is correctly derived from environment variable."""
        # Arrange
        service = DashboardService()
        username = "_global"
        repo_alias = "test-repo-global"
        custom_server_dir = "/custom/cidx-server"

        with patch.dict(
            "os.environ", {"CIDX_SERVER_DATA_DIR": custom_server_dir}
        ):
            # Mock GlobalRegistry at source module (lazy import in function)
            with patch(
                "code_indexer.global_repos.global_registry.GlobalRegistry"
            ) as MockRegistry:
                mock_registry_instance = MagicMock()
                mock_registry_instance.get_global_repo.return_value = None
                MockRegistry.return_value = mock_registry_instance

                # Act & Assert - We expect FileNotFoundError since repo not found
                # But we verify the registry was created with correct path
                with pytest.raises(FileNotFoundError):
                    service.get_temporal_index_status(username, repo_alias)

                # Verify GlobalRegistry was called with correct golden_repos_dir
                expected_golden_dir = f"{custom_server_dir}/data/golden-repos"
                MockRegistry.assert_called_once_with(expected_golden_dir)
