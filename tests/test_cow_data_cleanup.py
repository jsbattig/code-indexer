"""Tests for CoW (Copy-on-Write) data cleanup functionality."""

from pathlib import Path
from unittest.mock import Mock, patch

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig
from .conftest import local_temporary_directory, get_local_tmp_dir


class TestCoWDataCleanup:
    """Test CoW data cleanup functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333", collection="test_collection", vector_size=1536
        )
        self.client = QdrantClient(self.config, console=self.mock_console)

    def test_cleanup_cow_storage_with_symlink(self):
        """Test cleanup of CoW storage when collection is a symlink."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock directory structure
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            # Create actual data directory (simulating local project storage)
            project_dir = (
                temp_path
                / "project"
                / ".code-indexer"
                / "qdrant_collection"
                / "test_collection"
            )
            project_dir.mkdir(parents=True)

            # Create some mock collection data
            (project_dir / "segments.json").write_text('{"test": "data"}')
            (project_dir / "meta.json").write_text('{"test": "metadata"}')

            # Create symlink from global to local storage
            symlink_path = global_collections_dir / "test_collection"
            symlink_path.symlink_to(project_dir, target_is_directory=True)

            # Verify setup
            assert symlink_path.is_symlink()
            assert symlink_path.resolve() == project_dir
            assert (project_dir / "segments.json").exists()

            # Mock Path.home() to return our temp directory
            with patch("pathlib.Path.home", return_value=temp_path):
                # Execute cleanup using new method
                self.client._cleanup_cow_storage_with_path(
                    "test_collection", project_dir
                )

            # Verify symlink was removed
            assert not symlink_path.exists()

            # Verify actual data was deleted
            assert not project_dir.exists()

            # Verify console messages
            self.mock_console.print.assert_any_call(
                f"🗑️  Deleted CoW collection data: {project_dir}", style="dim"
            )
            self.mock_console.print.assert_any_call(
                f"🗑️  Removed symlink: {symlink_path}", style="dim"
            )

    def test_cleanup_cow_storage_with_direct_directory(self):
        """Test cleanup of CoW storage when collection is a direct directory (not symlink)."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock directory structure
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            # Create direct collection directory (not a symlink)
            collection_dir = global_collections_dir / "test_collection"
            collection_dir.mkdir()

            # Create some mock collection data
            (collection_dir / "segments.json").write_text('{"test": "data"}')

            # Verify setup
            assert collection_dir.exists()
            assert not collection_dir.is_symlink()

            # Mock Path.home() to return our temp directory
            with patch("pathlib.Path.home", return_value=temp_path):
                # Execute cleanup using new method (direct directory case)
                self.client._cleanup_cow_storage_with_path(
                    "test_collection", collection_dir
                )

            # Verify directory was removed
            assert not collection_dir.exists()

            # Verify console message
            self.mock_console.print.assert_any_call(
                f"🗑️  Deleted collection directory: {collection_dir}", style="dim"
            )

    def test_cleanup_cow_storage_nonexistent_collection(self):
        """Test cleanup when collection doesn't exist."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock directory structure but no collection
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            # Mock Path.home() to return our temp directory
            with patch("pathlib.Path.home", return_value=temp_path):
                # Execute cleanup using new method (nonexistent case)
                self.client._cleanup_cow_storage_with_path(
                    "nonexistent_collection", None
                )

            # Should complete without errors (no console messages expected)

    def test_cleanup_cow_storage_broken_symlink(self):
        """Test cleanup when symlink exists but target doesn't."""
        with local_temporary_directory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create mock directory structure
            global_collections_dir = temp_path / ".qdrant_collections"
            global_collections_dir.mkdir(parents=True)

            # Create symlink to non-existent target
            symlink_path = global_collections_dir / "test_collection"
            nonexistent_target = temp_path / "nonexistent" / "path"
            symlink_path.symlink_to(nonexistent_target, target_is_directory=True)

            # Verify setup
            assert symlink_path.is_symlink()
            assert not symlink_path.resolve().exists()

            # Mock Path.home() to return our temp directory
            with patch("pathlib.Path.home", return_value=temp_path):
                # Execute cleanup using new method (broken symlink case)
                self.client._cleanup_cow_storage_with_path(
                    "test_collection", nonexistent_target
                )

            # Verify symlink was removed (even though target didn't exist)
            assert not symlink_path.exists()

            # Verify console message about symlink removal
            self.mock_console.print.assert_any_call(
                f"🗑️  Removed symlink: {symlink_path}", style="dim"
            )

    def test_cleanup_cow_storage_permission_error(self):
        """Test cleanup handling of permission errors."""
        with local_temporary_directory():
            test_storage_path = Path(str(get_local_tmp_dir() / "test"))

            # Mock Path.home() only in the qdrant service module to raise PermissionError
            with patch(
                "code_indexer.services.qdrant.Path.home",
                side_effect=PermissionError("Permission denied"),
            ):
                # Execute cleanup (should handle error gracefully)
                self.client._cleanup_cow_storage_with_path(
                    "test_collection", test_storage_path
                )

            # Should print warning message
            self.mock_console.print.assert_any_call(
                "Warning: CoW storage cleanup failed for test_collection: Permission denied",
                style="yellow",
            )

    def test_delete_collection_with_cow_cleanup(self):
        """Test delete_collection integrates CoW cleanup."""
        # Mock HTTP client for Qdrant API
        mock_response = Mock()
        mock_response.status_code = 200

        # Mock the CoW cleanup methods and HTTP client
        with patch.object(self.client, "client") as mock_http_client, patch.object(
            self.client, "_get_cow_storage_path"
        ) as mock_get_path, patch.object(
            self.client, "_cleanup_cow_storage_with_path"
        ) as mock_cleanup:

            mock_http_client.delete.return_value = mock_response
            mock_get_path.return_value = Path(str(get_local_tmp_dir() / "test/path"))
            result = self.client.delete_collection("test_collection")

        # Verify API call was made
        mock_http_client.delete.assert_called_once_with("/collections/test_collection")

        # Verify CoW path was cached before deletion
        mock_get_path.assert_called_once_with("test_collection")

        # Verify CoW cleanup was called with cached path
        mock_cleanup.assert_called_once_with(
            "test_collection", Path(str(get_local_tmp_dir() / "test/path"))
        )

        # Verify success
        assert result is True

    def test_delete_collection_api_failure_still_cleans_cow(self):
        """Test that CoW cleanup happens even if API deletion fails."""
        # Mock HTTP client for Qdrant API failure
        mock_response = Mock()
        mock_response.status_code = 500  # Server error

        # Mock the CoW cleanup methods and HTTP client
        with patch.object(self.client, "client") as mock_http_client, patch.object(
            self.client, "_get_cow_storage_path"
        ) as mock_get_path, patch.object(
            self.client, "_cleanup_cow_storage_with_path"
        ) as mock_cleanup:

            mock_http_client.delete.return_value = mock_response
            mock_get_path.return_value = Path(str(get_local_tmp_dir() / "test/path"))
            result = self.client.delete_collection("test_collection")

        # Verify API call was made
        mock_http_client.delete.assert_called_once_with("/collections/test_collection")

        # Verify CoW path was cached before deletion
        mock_get_path.assert_called_once_with("test_collection")

        # Verify CoW cleanup was still called (cleanup local data even if API fails)
        mock_cleanup.assert_called_once_with(
            "test_collection", Path(str(get_local_tmp_dir() / "test/path"))
        )

        # Result should be False due to API failure
        assert result is False

    def test_cleanup_collections_uses_enhanced_delete(self):
        """Test that cleanup_collections method uses the enhanced delete_collection."""
        # Mock Qdrant API responses
        with patch.object(self.client, "client") as mock_client:
            # Mock collections list response
            mock_list_response = Mock()
            mock_list_response.status_code = 200
            mock_list_response.json.return_value = {
                "result": {
                    "collections": [
                        {"name": "test_collection_1"},
                        {"name": "test_collection_2"},
                        {"name": "other_collection"},
                    ]
                }
            }
            mock_client.get.return_value = mock_list_response

            # Mock delete_collection method
            with patch.object(
                self.client, "delete_collection", return_value=True
            ) as mock_delete:
                result = self.client.cleanup_collections(["test_*"])

            # Should have called delete_collection for matching collections
            expected_calls = [
                mock_delete.call_args_list[0][0][0],  # First call
                mock_delete.call_args_list[1][0][0],  # Second call
            ]
            assert "test_collection_1" in expected_calls
            assert "test_collection_2" in expected_calls
            assert mock_delete.call_count == 2

            # Verify results
            assert result["total_deleted"] == 2
            assert len(result["deleted"]) == 2
