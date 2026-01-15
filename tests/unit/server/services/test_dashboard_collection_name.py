"""
Unit tests for dashboard service handling of missing collection_name.

Tests the fix for the warning about legacy activated repos missing collection_name.
The service should derive collection_name from user_alias if not present.
"""

import tempfile
from unittest.mock import MagicMock, patch


class TestDashboardServiceCollectionName:
    """Test dashboard service collection_name handling."""

    def test_get_repo_counts_handles_missing_collection_name(self):
        """
        Test that _get_repo_counts handles repos missing collection_name.

        Legacy repos like 'evolution-temporal-active', 'flask-active', etc.
        may not have collection_name field. The service should derive it
        from user_alias instead of logging a warning and skipping.
        """
        from src.code_indexer.server.services.dashboard_service import DashboardService

        service = DashboardService()

        # Create mock repo data without collection_name but with user_alias
        mock_repos = [
            {
                "user_alias": "legacy-repo-active",
                "golden_repo_alias": "legacy-repo",
                "username": "testuser",
                # Note: no collection_name field
            },
            {
                "user_alias": "modern-repo-active",
                "golden_repo_alias": "modern-repo",
                "username": "testuser",
                "collection_name": "modern-repo-active",  # Has collection_name
            },
        ]

        # Mock the managers and store
        with (
            patch.object(service, "_get_golden_repo_manager") as mock_golden,
            patch.object(service, "_get_activated_repo_manager") as mock_activated,
        ):

            # Setup golden repo manager mock
            mock_golden_manager = MagicMock()
            mock_golden_manager.list_golden_repos.return_value = []
            mock_golden.return_value = mock_golden_manager

            # Setup activated repo manager mock
            mock_activated_manager = MagicMock()
            mock_activated_manager.list_activated_repositories.return_value = mock_repos
            mock_activated_manager.data_dir = tempfile.mkdtemp()
            mock_activated.return_value = mock_activated_manager

            # Mock FilesystemVectorStore at its source module
            with patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_store_class:
                mock_store = MagicMock()
                mock_store.get_indexed_file_count_fast.return_value = 100
                mock_store_class.return_value = mock_store

                # Call _get_repo_counts - this should NOT skip the legacy repo
                result = service._get_repo_counts("testuser")

                # Both repos should be processed (total_files = 200 if both counted)
                # With the bug, only 1 repo would be counted (100)
                # After the fix, both should be counted (200)
                assert (
                    result.total_files == 200
                ), f"Expected 200 total files (both repos), got {result.total_files}"

                # Verify get_indexed_file_count_fast was called twice
                assert mock_store.get_indexed_file_count_fast.call_count == 2

                # Verify the legacy repo was called with user_alias as collection_name
                calls = mock_store.get_indexed_file_count_fast.call_args_list
                collection_names = [call[0][0] for call in calls]
                assert (
                    "legacy-repo-active" in collection_names
                ), "Legacy repo should use user_alias as collection_name"
                assert (
                    "modern-repo-active" in collection_names
                ), "Modern repo should use its collection_name"

    def test_get_repo_counts_with_all_missing_collection_names(self):
        """
        Test handling when all repos are missing collection_name (legacy data).
        """
        from src.code_indexer.server.services.dashboard_service import DashboardService

        service = DashboardService()

        # All legacy repos without collection_name
        mock_repos = [
            {
                "user_alias": "evolution-temporal-active",
                "golden_repo_alias": "evolution-temporal",
                "username": "testuser",
            },
            {
                "user_alias": "flask-active",
                "golden_repo_alias": "flask",
                "username": "testuser",
            },
            {
                "user_alias": "prompt-tutorial-active",
                "golden_repo_alias": "prompt-tutorial",
                "username": "testuser",
            },
        ]

        with (
            patch.object(service, "_get_golden_repo_manager") as mock_golden,
            patch.object(service, "_get_activated_repo_manager") as mock_activated,
        ):

            mock_golden_manager = MagicMock()
            mock_golden_manager.list_golden_repos.return_value = []
            mock_golden.return_value = mock_golden_manager

            mock_activated_manager = MagicMock()
            mock_activated_manager.list_activated_repositories.return_value = mock_repos
            mock_activated_manager.data_dir = tempfile.mkdtemp()
            mock_activated.return_value = mock_activated_manager

            with patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_store_class:
                mock_store = MagicMock()
                mock_store.get_indexed_file_count_fast.return_value = 50
                mock_store_class.return_value = mock_store

                result = service._get_repo_counts("testuser")

                # All 3 repos should be processed
                assert (
                    result.total_files == 150
                ), f"Expected 150 total files (3 repos * 50), got {result.total_files}"
                assert mock_store.get_indexed_file_count_fast.call_count == 3

    def test_get_repo_counts_handles_repo_missing_user_alias_too(self):
        """
        Test graceful handling when both collection_name and user_alias are missing.
        This is an edge case that should not happen, but we should handle it gracefully.
        """
        from src.code_indexer.server.services.dashboard_service import DashboardService

        service = DashboardService()

        # Malformed repo data - missing both collection_name and user_alias
        mock_repos = [
            {
                "golden_repo_alias": "broken-repo",
                "username": "testuser",
                # No collection_name, no user_alias
            },
            {
                "user_alias": "working-repo-active",
                "golden_repo_alias": "working-repo",
                "username": "testuser",
            },
        ]

        with (
            patch.object(service, "_get_golden_repo_manager") as mock_golden,
            patch.object(service, "_get_activated_repo_manager") as mock_activated,
        ):

            mock_golden_manager = MagicMock()
            mock_golden_manager.list_golden_repos.return_value = []
            mock_golden.return_value = mock_golden_manager

            mock_activated_manager = MagicMock()
            mock_activated_manager.list_activated_repositories.return_value = mock_repos
            mock_activated_manager.data_dir = tempfile.mkdtemp()
            mock_activated.return_value = mock_activated_manager

            with patch(
                "code_indexer.storage.filesystem_vector_store.FilesystemVectorStore"
            ) as mock_store_class:
                mock_store = MagicMock()
                mock_store.get_indexed_file_count_fast.return_value = 100
                mock_store_class.return_value = mock_store

                # Should not raise, should skip the malformed repo
                result = service._get_repo_counts("testuser")

                # Only the working repo should be counted
                assert (
                    result.total_files == 100
                ), f"Expected 100 total files (1 working repo), got {result.total_files}"
                assert mock_store.get_indexed_file_count_fast.call_count == 1
