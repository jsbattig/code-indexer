"""
Tests for Story 2: Index Existence Checking
Testing that indexes are checked for existence before creation attempts.
"""

from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient


class TestStory2IndexExistenceChecking:
    """Test index existence checking functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
                ("language", "keyword"),
                ("chunk_index", "integer"),
            ],
        )
        self.mock_console = Mock()
        self.client = QdrantClient(self.config, self.mock_console, Path("."))

    def test_ensure_payload_indexes_should_check_existence_first(self):
        """PASSING TEST: ensure_payload_indexes should check if indexes exist before creating."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):
            mock_status.return_value = {
                "missing_indexes": ["type", "path"],  # Some missing
                "healthy": False,
                "total_indexes": 5,
                "expected_indexes": 7,
            }
            mock_create.return_value = True

            # Method should exist and check status first
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should check status first
            mock_status.assert_called_once_with(collection_name)
            # Should create only missing indexes
            mock_create.assert_called_once_with(collection_name, ["type", "path"])

    def test_all_indexes_exist_no_creation_needed(self):
        """FAILING TEST: When all indexes exist, no creation attempts should be made."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": [],  # All indexes exist
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            # This should succeed without creating any indexes
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should NOT attempt to create any indexes
            mock_create.assert_not_called()

            # Should check status once
            mock_status.assert_called_once_with(collection_name)

    def test_partial_indexes_exist_only_missing_created(self):
        """FAILING TEST: Only missing indexes should be created, not all indexes."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": ["type", "path"],  # Only 2 missing
                "healthy": False,
                "total_indexes": 5,
                "expected_indexes": 7,
                "extra_indexes": [],
            }
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should only create the missing indexes, not all 7
            mock_create.assert_called_once_with(collection_name, ["type", "path"])

    def test_no_indexes_exist_all_created(self):
        """FAILING TEST: When no indexes exist, all should be created."""
        collection_name = "test_collection"
        expected_missing = [
            "type",
            "path",
            "git_branch",
            "file_mtime",
            "hidden_branches",
            "language",
            "chunk_index",
        ]

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(
                self.client, "_create_missing_indexes_with_detailed_feedback"
            ) as mock_create,
        ):

            mock_status.return_value = {
                "missing_indexes": expected_missing,
                "healthy": False,
                "total_indexes": 0,
                "expected_indexes": 7,
                "extra_indexes": [],
            }
            mock_create.return_value = True

            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should create all 7 indexes
            mock_create.assert_called_once_with(collection_name, expected_missing)

    def test_index_status_error_handling(self):
        """FAILING TEST: Handle errors when checking index status."""
        collection_name = "test_collection"

        with patch.object(self.client, "get_payload_index_status") as mock_status:
            # Simulate error in status checking
            mock_status.return_value = {
                "error": "Connection failed",
                "healthy": False,
            }

            # Should handle errors gracefully
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            # Should fail gracefully
            assert result is False

    def test_existence_check_prevents_unnecessary_api_calls(self):
        """FAILING TEST: Existence checking should prevent unnecessary API calls."""
        collection_name = "test_collection"

        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(self.client.client, "put") as mock_put,
        ):

            mock_status.return_value = {
                "missing_indexes": [],  # All exist
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should make NO API calls to create indexes
            assert mock_put.call_count == 0

            # Should only check status
            mock_status.assert_called_once()

    def test_get_payload_index_status_should_return_missing_indexes(self):
        """FAILING TEST: get_payload_index_status should identify missing indexes."""
        collection_name = "test_collection"

        # Mock that only some indexes exist
        existing_indexes = [
            {"field": "type", "type": "keyword"},
            {"field": "path", "type": "text"},
            {"field": "git_branch", "type": "keyword"},
            # Missing: file_mtime, hidden_branches, language, chunk_index
        ]

        with patch.object(self.client, "list_payload_indexes") as mock_list:
            mock_list.return_value = existing_indexes

            status = self.client.get_payload_index_status(collection_name)

            expected_missing = [
                "file_mtime",
                "hidden_branches",
                "language",
                "chunk_index",
            ]

            assert "missing_indexes" in status
            assert set(status["missing_indexes"]) == set(expected_missing)
            assert status["total_indexes"] == 3
            assert status["expected_indexes"] == 7
            assert status["healthy"] is False

    def test_disabled_indexes_should_skip_existence_checks(self):
        """FAILING TEST: When indexes are disabled, should skip all checks."""
        # Create config with indexes disabled
        disabled_config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=False,  # Disabled
        )
        disabled_client = QdrantClient(disabled_config, self.mock_console, Path("."))

        collection_name = "test_collection"

        with patch.object(disabled_client, "get_payload_index_status") as mock_status:
            result = disabled_client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )

            assert result is True
            # Should NOT check status when disabled
            mock_status.assert_not_called()
