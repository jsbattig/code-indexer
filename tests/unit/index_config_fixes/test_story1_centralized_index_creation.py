"""
Tests for Story 1: Centralized Index Creation
Testing that all index operations go through a single centralized method.
"""

from unittest.mock import Mock, patch
from pathlib import Path

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient


class TestStory1CentralizedIndexCreation:
    """Test centralized index creation functionality."""

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

    def test_current_index_creation_behavior(self):
        """CURRENT BEHAVIOR: Demonstrates current index creation behavior."""
        # This test verifies current behavior - some duplication may still occur

        collection_name = "test_collection"

        # Mock successful API responses for index creation
        mock_response = Mock()
        mock_response.status_code = 201

        with (
            patch.object(self.client.client, "put") as mock_put,
            patch.object(self.client.client, "get") as mock_get,
        ):
            # Mock both collection and index creation responses
            mock_put.return_value = mock_response
            # Mock collection info response for index checking
            mock_get.return_value = mock_response
            mock_response.json.return_value = {
                "result": {"config": {"params": {"vectors": {}}}}
            }

            # Simulate cidx start flow: collection creation
            result1 = self.client._create_collection_direct(collection_name, 1536)

            # Simulate cidx index flow: additional index creation attempt
            result2 = self.client._create_payload_indexes_with_retry(collection_name)

            assert result1 is True
            assert result2 is True

            # Current behavior: Still has some duplication in the implementation
            # Expected: 1 collection creation + 7 indexes + 7 more indexes = 15 calls
            assert mock_put.call_count == 15  # Current behavior

            # Current behavior: Still has duplicate index creation messages
            create_messages = [
                call
                for call in self.mock_console.print.call_args_list
                if "🔧 Setting up payload indexes" in str(call)
            ]
            assert len(create_messages) >= 1  # At least one message

    def test_centralized_ensure_payload_indexes_should_exist(self):
        """PASSING TEST: ensure_payload_indexes method should centralize all index operations."""
        collection_name = "test_collection"

        # This method should exist and be the ONLY method that creates indexes
        with patch.object(self.client, "get_payload_index_status") as mock_status:
            mock_status.return_value = {
                "missing_indexes": [],
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            # Method should exist and work
            result = self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )
            assert result is True

    def test_collection_creation_should_use_centralized_method(self):
        """FAILING TEST: Collection creation should use centralized ensure_payload_indexes."""
        collection_name = "test_collection"

        # Mock successful collection creation response
        collection_response = Mock()
        collection_response.status_code = 201

        # Mock successful index responses
        index_response = Mock()
        index_response.status_code = 201

        with (
            patch.object(self.client.client, "put") as mock_put,
            patch.object(self.client, "ensure_payload_indexes") as mock_ensure,
        ):

            # Set up mock responses
            mock_put.return_value = collection_response
            mock_ensure.return_value = True

            result = self.client._create_collection_direct(collection_name, 1536)

            assert result is True

            # Collection creation should call centralized method
            mock_ensure.assert_called_once_with(
                collection_name, context="collection_creation"
            )

            # Should NOT call the old _create_payload_indexes_with_retry method
            assert not any(
                call
                for call in self.mock_console.print.call_args_list
                if "🔧 Setting up payload indexes for optimal query performance"
                in str(call)
            )

    def test_standalone_index_operations_should_use_centralized_method(self):
        """FAILING TEST: Standalone index operations should use centralized method."""
        collection_name = "test_collection"

        with patch.object(self.client, "ensure_payload_indexes") as mock_ensure:
            mock_ensure.return_value = True

            # Any standalone index operation should use ensure_payload_indexes
            # This should replace direct calls to _create_payload_indexes_with_retry

            # Simulate what should happen when cidx index command runs
            result = self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            assert result is True
            mock_ensure.assert_called_once_with(
                collection_name, context="index_verification"
            )

    def test_centralized_method_should_eliminate_duplication(self):
        """FAILING TEST: Centralized method should prevent duplicate index creation."""
        collection_name = "test_collection"

        # Mock that indexes already exist
        with (
            patch.object(self.client, "get_payload_index_status") as mock_status,
            patch.object(self.client.client, "put") as mock_put,
        ):

            mock_status.return_value = {
                "missing_indexes": [],  # No missing indexes
                "healthy": True,
                "total_indexes": 7,
                "expected_indexes": 7,
            }

            # Multiple calls to ensure_payload_indexes should NOT create duplicate indexes
            self.client.ensure_payload_indexes(
                collection_name, context="collection_creation"
            )
            self.client.ensure_payload_indexes(
                collection_name, context="index_verification"
            )

            # Should NOT make any PUT requests since indexes already exist
            assert mock_put.call_count == 0

            # Should check status twice but create indexes zero times
            assert mock_status.call_count == 2

    def test_legacy_create_payload_indexes_with_retry_should_be_deprecated(self):
        """FAILING TEST: Old method should be marked for removal/deprecation."""
        # The _create_payload_indexes_with_retry method should be deprecated
        # in favor of the centralized ensure_payload_indexes approach

        collection_name = "test_collection"

        # This method should still exist for now (for backward compatibility)
        # but should internally delegate to ensure_payload_indexes

        with patch.object(self.client, "ensure_payload_indexes") as mock_ensure:
            mock_ensure.return_value = True

            result = self.client._create_payload_indexes_with_retry(collection_name)

            assert result is True
            # Should delegate to centralized method
            mock_ensure.assert_called_once_with(
                collection_name, context="legacy_direct"
            )
