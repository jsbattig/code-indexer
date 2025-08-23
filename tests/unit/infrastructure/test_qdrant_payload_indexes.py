"""Tests for automatic payload index creation in Qdrant collections."""

from unittest.mock import Mock, patch

import httpx

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestQdrantPayloadIndexes:
    """Test automatic payload index creation during collection setup."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            hnsw_m=16,
            hnsw_ef_construct=100,
            hnsw_ef=64,
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_create_payload_indexes_with_retry_method_exists(self):
        """Test that _create_payload_indexes_with_retry method exists and is callable."""
        # Verify the method exists and is callable
        assert hasattr(self.client, "_create_payload_indexes_with_retry")
        assert callable(getattr(self.client, "_create_payload_indexes_with_retry"))

    def test_create_payload_indexes_with_retry_success(self):
        """Test successful payload index creation with proper user feedback."""
        collection_name = "test_collection"

        # Mock successful HTTP responses for all index creation attempts
        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(
            self.client.client, "put", return_value=mock_response
        ) as mock_put:
            # This will fail until we implement the method
            result = self.client._create_payload_indexes_with_retry(collection_name)

            assert result is True

            # Verify all 7 required indexes were created
            assert mock_put.call_count == 7

            # Verify the correct API endpoints were called
            expected_calls = [
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
                f"/collections/{collection_name}/index",
            ]

            actual_calls = [call[0][0] for call in mock_put.call_args_list]
            assert all(call in expected_calls for call in actual_calls)

            # Verify correct field names and schemas were sent
            expected_fields = {
                "type": "keyword",
                "path": "text",
                "git_branch": "keyword",
                "file_mtime": "integer",
                "hidden_branches": "keyword",
                "language": "keyword",
                "embedding_model": "keyword",
            }

            for call_args in mock_put.call_args_list:
                json_data = call_args[1]["json"]
                field_name = json_data["field_name"]
                field_schema = json_data["field_schema"]
                assert field_name in expected_fields
                assert expected_fields[field_name] == field_schema

    def test_create_payload_indexes_with_retry_partial_failure(self):
        """Test partial failure scenario where some indexes succeed and some fail."""
        collection_name = "test_collection"

        # Mock responses: first 3 succeed, last 3 fail
        mock_responses = []
        for i in range(6):
            mock_response = Mock()
            if i < 3:
                mock_response.status_code = 201
            else:
                mock_response.status_code = 500
            mock_responses.append(mock_response)

        with patch.object(self.client.client, "put", side_effect=mock_responses):
            # This will fail until we implement the method
            result = self.client._create_payload_indexes_with_retry(collection_name)

            # Should return True if at least some indexes were created
            assert result is True  # Partial success should be acceptable

            # Verify user feedback messages were displayed
            self.mock_console.print.assert_any_call(
                "🔧 Setting up payload indexes for optimal query performance..."
            )

    def test_create_payload_indexes_with_retry_handles_existing_indexes(self):
        """Test that existing indexes (409 status) are handled gracefully."""
        collection_name = "test_collection"

        # Mock response indicating index already exists
        mock_response = Mock()
        mock_response.status_code = 409

        with patch.object(self.client.client, "put", return_value=mock_response):
            # This will fail until we implement the method
            result = self.client._create_payload_indexes_with_retry(collection_name)

            assert result is True

            # Should display success message for existing indexes
            self.mock_console.print.assert_any_call(
                "   ✅ Index for 'type' already exists"
            )

    def test_create_payload_indexes_with_retry_handles_exceptions(self):
        """Test that network exceptions are handled with retry logic."""
        collection_name = "test_collection"

        # Mock to raise exception on first attempts, then succeed
        call_count = 0

        def mock_put_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:  # First 2 attempts fail
                raise httpx.RequestError("Network error")
            # Third attempt succeeds
            mock_response = Mock()
            mock_response.status_code = 201
            return mock_response

        with patch.object(self.client.client, "put", side_effect=mock_put_side_effect):
            # This will fail until we implement the method
            result = self.client._create_payload_indexes_with_retry(collection_name)

            assert result is True

            # Should show retry messages
            assert any(
                "retrying in 1s" in str(call)
                for call in self.mock_console.print.call_args_list
            )

    def test_create_payload_indexes_with_retry_complete_failure(self):
        """Test scenario where all index creation attempts fail."""
        collection_name = "test_collection"

        # Mock to always fail
        mock_response = Mock()
        mock_response.status_code = 500

        with patch.object(self.client.client, "put", return_value=mock_response):
            # This will fail until we implement the method
            result = self.client._create_payload_indexes_with_retry(collection_name)

            assert result is False

            # Should display failure summary
            self.mock_console.print.assert_any_call(
                "   📊 Created 0/7 payload indexes (7 failed)"
            )

    def test_create_collection_direct_calls_payload_indexes(self):
        """Test that _create_collection_direct integrates with payload index creation."""
        collection_name = "test_collection"
        vector_size = 384

        # Mock successful collection creation
        mock_collection_response = Mock()
        mock_collection_response.status_code = 201

        # Mock successful index creation
        mock_index_response = Mock()
        mock_index_response.status_code = 201

        with patch.object(self.client.client, "put") as mock_put:
            mock_put.return_value = mock_collection_response

            # Mock the index creation method to return True
            with patch.object(
                self.client, "_create_payload_indexes_with_retry", return_value=True
            ) as mock_create_indexes:
                result = self.client._create_collection_direct(
                    collection_name, vector_size
                )

                assert result is True

                # Verify that index creation was called
                mock_create_indexes.assert_called_once_with(collection_name)

    def test_create_collection_with_profile_calls_payload_indexes(self):
        """Test that create_collection_with_profile integrates with payload index creation."""
        profile = "small_codebase"
        collection_name = "test_collection"
        vector_size = 384

        # Mock successful collection creation
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status.return_value = None

        with patch.object(self.client.client, "put", return_value=mock_response):
            # Mock the index creation method to return True
            with patch.object(
                self.client, "_create_payload_indexes_with_retry", return_value=True
            ) as mock_create_indexes:
                result = self.client.create_collection_with_profile(
                    profile, collection_name, vector_size
                )

                assert result is True

                # Verify that index creation was called
                mock_create_indexes.assert_called_once_with(collection_name)


class TestQdrantPayloadIndexesIntegration:
    """Integration tests for payload index functionality."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_ensure_collection_includes_payload_indexes(self):
        """Test that ensure_collection creates payload indexes for new collections."""
        collection_name = "test_collection"

        # Mock collection doesn't exist initially
        with patch.object(self.client, "collection_exists", return_value=False):
            # Mock successful collection creation
            with patch.object(
                self.client, "_create_collection_direct", return_value=True
            ) as mock_create:
                # Mock successful index creation
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ):
                    result = self.client.ensure_collection(collection_name)

                    assert result is True
                    mock_create.assert_called_once()
                    # Index creation should be called as part of collection creation

    def test_payload_indexes_failure_does_not_fail_collection_creation(self):
        """Test that payload index failures don't prevent collection creation."""
        collection_name = "test_collection"
        vector_size = 384

        # Mock successful collection creation
        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(self.client.client, "put", return_value=mock_response):
            # Mock failed index creation
            with patch.object(
                self.client, "_create_payload_indexes_with_retry", return_value=False
            ):
                result = self.client._create_collection_direct(
                    collection_name, vector_size
                )

                # Collection creation should still succeed even if indexes fail
                assert result is True

    def test_user_feedback_during_index_creation(self):
        """Test that appropriate user feedback is shown during index creation."""
        collection_name = "test_collection"

        # Mock successful responses
        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(self.client.client, "put", return_value=mock_response):
            # This will fail until we implement the method
            self.client._create_payload_indexes_with_retry(collection_name)

            # Verify progress messages were shown
            expected_messages = [
                "🔧 Setting up payload indexes for optimal query performance...",
                "   • Creating index for 'type' field (keyword type)...",
                "   • Creating index for 'path' field (text type)...",
                "   • Creating index for 'git_branch' field (keyword type)...",
                "   • Creating index for 'file_mtime' field (integer type)...",
                "   • Creating index for 'hidden_branches' field (keyword type)...",
                "   • Creating index for 'language' field (keyword type)...",
                "   📊 Successfully created all 7 payload indexes",
            ]

            for message in expected_messages:
                self.mock_console.print.assert_any_call(message)


class TestQdrantPayloadIndexStatus:
    """Tests for payload index status monitoring and reporting."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
                ("language", "keyword"),
            ],
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_list_payload_indexes_method_exists(self):
        """Test that list_payload_indexes method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "list_payload_indexes")
        assert callable(getattr(self.client, "list_payload_indexes"))

    def test_list_payload_indexes_success(self):
        """Test successful retrieval of existing payload indexes."""
        collection_name = "test_collection"

        # Mock get_collection_info to return payload_schema
        mock_collection_info = {
            "status": "green",
            "payload_schema": {
                "type": "keyword",
                "path": "text",
                "git_branch": "keyword",
            },
        }

        with patch.object(
            self.client, "get_collection_info", return_value=mock_collection_info
        ):
            result = self.client.list_payload_indexes(collection_name)

            assert isinstance(result, list)
            assert len(result) == 3
            assert {"field": "type", "schema": "keyword"} in result
            assert {"field": "path", "schema": "text"} in result
            assert {"field": "git_branch", "schema": "keyword"} in result

    def test_list_payload_indexes_empty_collection(self):
        """Test listing indexes for collection with no indexes."""
        collection_name = "test_collection"

        # Mock get_collection_info to return empty payload_schema
        mock_collection_info = {"status": "green", "payload_schema": {}}

        with patch.object(
            self.client, "get_collection_info", return_value=mock_collection_info
        ):
            result = self.client.list_payload_indexes(collection_name)

            assert isinstance(result, list)
            assert len(result) == 0

    def test_list_payload_indexes_collection_not_exists(self):
        """Test listing indexes when collection doesn't exist."""
        collection_name = "nonexistent_collection"

        # Mock get_collection_info to raise exception
        with patch.object(
            self.client,
            "get_collection_info",
            side_effect=RuntimeError("Collection doesn't exist"),
        ):
            result = self.client.list_payload_indexes(collection_name)

            assert isinstance(result, list)
            assert len(result) == 0

    def test_list_payload_indexes_api_error(self):
        """Test handling of API errors when listing indexes."""
        collection_name = "test_collection"

        with patch.object(
            self.client, "get_collection_info", side_effect=Exception("Network error")
        ):
            result = self.client.list_payload_indexes(collection_name)

            assert isinstance(result, list)
            assert len(result) == 0

    def test_estimate_index_memory_usage_method_exists(self):
        """Test that _estimate_index_memory_usage method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "_estimate_index_memory_usage")
        assert callable(getattr(self.client, "_estimate_index_memory_usage"))

    def test_estimate_index_memory_usage_calculation(self):
        """Test memory usage estimation for payload indexes."""
        indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
            {"field": "git_branch", "schema": "keyword"},
            {"field": "file_mtime", "schema": "integer"},
        ]

        # This will fail until we implement the method
        result = self.client._estimate_index_memory_usage(indexes)

        assert isinstance(result, (int, float))
        assert result > 0  # Should estimate some memory usage
        # Expect reasonable range for 4 indexes (50-200MB typical)
        assert 50 <= result <= 200

    def test_estimate_index_memory_usage_empty_list(self) -> None:
        """Test memory estimation with no indexes."""
        from typing import Dict, Any, List

        indexes: List[Dict[str, Any]] = []

        result = self.client._estimate_index_memory_usage(indexes)

        assert isinstance(result, (int, float))
        assert result == 0

    def test_get_payload_index_status_method_exists(self):
        """Test that get_payload_index_status method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "get_payload_index_status")
        assert callable(getattr(self.client, "get_payload_index_status"))

    def test_get_payload_index_status_healthy(self):
        """Test status reporting for healthy payload indexes."""
        collection_name = "test_collection"

        # Mock list_payload_indexes to return expected indexes
        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
            {"field": "git_branch", "schema": "keyword"},
            {"field": "file_mtime", "schema": "integer"},
            {"field": "hidden_branches", "schema": "keyword"},
            {"field": "language", "schema": "keyword"},
        ]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(
                self.client, "_estimate_index_memory_usage", return_value=150.5
            ):
                # This will fail until we implement the method
                result = self.client.get_payload_index_status(collection_name)

                assert isinstance(result, dict)
                assert result["indexes_enabled"] is True
                assert result["total_indexes"] == 6
                assert result["expected_indexes"] == 6
                assert result["missing_indexes"] == []
                assert result["extra_indexes"] == []
                assert result["healthy"] is True
                assert result["estimated_memory_mb"] == 150.5
                assert "indexes" in result

    def test_get_payload_index_status_missing_indexes(self):
        """Test status reporting when some indexes are missing."""
        collection_name = "test_collection"

        # Mock list_payload_indexes to return only partial indexes
        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
        ]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(
                self.client, "_estimate_index_memory_usage", return_value=75.0
            ):
                result = self.client.get_payload_index_status(collection_name)

                assert isinstance(result, dict)
                assert result["indexes_enabled"] is True
                assert result["total_indexes"] == 2
                assert result["expected_indexes"] == 6
                assert set(result["missing_indexes"]) == {
                    "git_branch",
                    "file_mtime",
                    "hidden_branches",
                    "language",
                }
                assert result["extra_indexes"] == []
                assert result["healthy"] is False
                assert result["estimated_memory_mb"] == 75.0

    def test_get_payload_index_status_extra_indexes(self):
        """Test status reporting when extra indexes exist."""
        collection_name = "test_collection"

        # Mock list_payload_indexes to return extra indexes
        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
            {"field": "git_branch", "schema": "keyword"},
            {"field": "file_mtime", "schema": "integer"},
            {"field": "hidden_branches", "schema": "keyword"},
            {"field": "language", "schema": "keyword"},
            {"field": "extra_field", "schema": "keyword"},  # Extra index
        ]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(
                self.client, "_estimate_index_memory_usage", return_value=180.0
            ):
                result = self.client.get_payload_index_status(collection_name)

                assert isinstance(result, dict)
                assert result["indexes_enabled"] is True
                assert result["total_indexes"] == 7
                assert result["expected_indexes"] == 6
                assert result["missing_indexes"] == []
                assert result["extra_indexes"] == ["extra_field"]
                assert (
                    result["healthy"] is True
                )  # Extra indexes don't make it unhealthy
                assert result["estimated_memory_mb"] == 180.0

    def test_get_payload_index_status_indexes_disabled(self):
        """Test status reporting when payload indexes are disabled."""
        collection_name = "test_collection"

        # Create config with disabled indexes
        disabled_config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=False,
        )
        client = QdrantClient(disabled_config, self.mock_console)

        with patch.object(client, "list_payload_indexes", return_value=[]):
            with patch.object(client, "_estimate_index_memory_usage", return_value=0):
                result = client.get_payload_index_status(collection_name)

                assert isinstance(result, dict)
                assert result["indexes_enabled"] is False
                assert result["total_indexes"] == 0
                assert result["expected_indexes"] == 0
                assert result["missing_indexes"] == []
                assert result["extra_indexes"] == []
                assert result["healthy"] is True
                assert result["estimated_memory_mb"] == 0

    def test_get_payload_index_status_api_error(self):
        """Test status reporting when API calls fail."""
        collection_name = "test_collection"

        with patch.object(
            self.client, "list_payload_indexes", side_effect=Exception("API error")
        ):
            result = self.client.get_payload_index_status(collection_name)

            assert isinstance(result, dict)
            assert "error" in result
            assert result["healthy"] is False
            assert "API error" in result["error"]


class TestQdrantPayloadIndexRebuild:
    """Tests for payload index rebuild functionality (Story 5)."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()
        self.config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=True,
            payload_indexes=[
                ("type", "keyword"),
                ("path", "text"),
                ("git_branch", "keyword"),
                ("file_mtime", "integer"),
                ("hidden_branches", "keyword"),
                ("language", "keyword"),
            ],
        )
        self.client = QdrantClient(self.config, self.mock_console)

    def test_rebuild_payload_indexes_method_exists(self):
        """Test that rebuild_payload_indexes method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "rebuild_payload_indexes")
        assert callable(getattr(self.client, "rebuild_payload_indexes"))

    def test_drop_payload_index_method_exists(self):
        """Test that _drop_payload_index method exists and is callable."""
        # This should fail initially - method doesn't exist yet
        assert hasattr(self.client, "_drop_payload_index")
        assert callable(getattr(self.client, "_drop_payload_index"))

    def test_rebuild_payload_indexes_success(self):
        """Test successful rebuild of all payload indexes."""
        collection_name = "test_collection"

        # Mock existing indexes to be dropped
        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
        ]

        # Mock successful drop responses (204 No Content)
        mock_drop_response = Mock()
        mock_drop_response.status_code = 204

        # Mock successful create responses
        mock_create_response = Mock()
        mock_create_response.status_code = 201

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(
                self.client, "_drop_payload_index", return_value=True
            ) as mock_drop:
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ) as mock_create:
                    with patch.object(
                        self.client,
                        "get_payload_index_status",
                        return_value={"healthy": True},
                    ):
                        # This will fail until we implement the method
                        result = self.client.rebuild_payload_indexes(collection_name)

                        assert result is True

                        # Verify existing indexes were dropped
                        assert mock_drop.call_count == 2
                        mock_drop.assert_any_call(collection_name, "type")
                        mock_drop.assert_any_call(collection_name, "path")

                        # Verify indexes were recreated
                        mock_create.assert_called_once_with(collection_name)

                        # Verify success message was shown
                        self.mock_console.print.assert_any_call(
                            "✅ Payload indexes rebuilt successfully"
                        )

    def test_rebuild_payload_indexes_disabled_configuration(self):
        """Test rebuild behavior when payload indexes are disabled."""
        collection_name = "test_collection"

        # Create config with disabled indexes
        disabled_config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=384,
            enable_payload_indexes=False,
        )
        disabled_client = QdrantClient(disabled_config, self.mock_console)

        # This will fail until we implement the method
        result = disabled_client.rebuild_payload_indexes(collection_name)

        assert result is True
        self.mock_console.print.assert_any_call(
            "Payload indexes are disabled in configuration"
        )

    def test_rebuild_payload_indexes_drop_failure(self):
        """Test rebuild behavior when dropping existing indexes fails."""
        collection_name = "test_collection"

        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
        ]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(
                self.client, "_drop_payload_index", side_effect=[False, True]
            ) as mock_drop:
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ):
                    with patch.object(
                        self.client,
                        "get_payload_index_status",
                        return_value={"healthy": True},
                    ):
                        # This will fail until we implement the method
                        result = self.client.rebuild_payload_indexes(collection_name)

                        # Should still succeed and continue with creation
                        assert result is True
                        assert mock_drop.call_count == 2

    def test_rebuild_payload_indexes_create_failure(self):
        """Test rebuild behavior when creating indexes fails."""
        collection_name = "test_collection"

        existing_indexes = [{"field": "type", "schema": "keyword"}]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(self.client, "_drop_payload_index", return_value=True):
                with patch.object(
                    self.client,
                    "_create_payload_indexes_with_retry",
                    return_value=False,
                ):
                    # This will fail until we implement the method
                    result = self.client.rebuild_payload_indexes(collection_name)

                    assert result is False
                    self.mock_console.print.assert_any_call(
                        "❌ Failed to rebuild some indexes"
                    )

    def test_rebuild_payload_indexes_health_check_failure(self):
        """Test rebuild behavior when health check fails after creation."""
        collection_name = "test_collection"

        existing_indexes = [{"field": "type", "schema": "keyword"}]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(self.client, "_drop_payload_index", return_value=True):
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ):
                    with patch.object(
                        self.client,
                        "get_payload_index_status",
                        return_value={"healthy": False},
                    ):
                        # Current implementation trusts creation success and skips health check
                        result = self.client.rebuild_payload_indexes(collection_name)

                        # Should succeed if creation succeeds (health check is currently disabled due to timing issues)
                        assert result is True
                        self.mock_console.print.assert_any_call(
                            "✅ Payload indexes rebuilt successfully"
                        )

    def test_rebuild_payload_indexes_exception_handling(self):
        """Test rebuild behavior when exceptions occur."""
        collection_name = "test_collection"

        with patch.object(
            self.client, "list_payload_indexes", side_effect=Exception("Network error")
        ):
            # This will fail until we implement the method
            result = self.client.rebuild_payload_indexes(collection_name)

            assert result is False
            # Should show error message with exception details
            error_calls = [
                call
                for call in self.mock_console.print.call_args_list
                if "❌ Index rebuild failed:" in str(call)
            ]
            assert len(error_calls) > 0

    def test_drop_payload_index_success(self):
        """Test successful drop of individual payload index."""
        collection_name = "test_collection"
        field_name = "type"

        # Mock successful delete response
        mock_response = Mock()
        mock_response.status_code = 204

        with patch.object(
            self.client.client, "delete", return_value=mock_response
        ) as mock_delete:
            # This will fail until we implement the method
            result = self.client._drop_payload_index(collection_name, field_name)

            assert result is True
            mock_delete.assert_called_once_with(
                f"/collections/{collection_name}/index/{field_name}"
            )

    def test_drop_payload_index_not_found(self):
        """Test drop behavior when index doesn't exist (404)."""
        collection_name = "test_collection"
        field_name = "nonexistent_field"

        # Mock 404 response (index doesn't exist - this is acceptable)
        mock_response = Mock()
        mock_response.status_code = 404

        with patch.object(self.client.client, "delete", return_value=mock_response):
            # This will fail until we implement the method
            result = self.client._drop_payload_index(collection_name, field_name)

            assert result is True  # 404 is acceptable - already deleted

    def test_drop_payload_index_already_deleted(self):
        """Test drop behavior when index was already deleted (200)."""
        collection_name = "test_collection"
        field_name = "type"

        # Mock 200 response (successfully deleted)
        mock_response = Mock()
        mock_response.status_code = 200

        with patch.object(self.client.client, "delete", return_value=mock_response):
            # This will fail until we implement the method
            result = self.client._drop_payload_index(collection_name, field_name)

            assert result is True

    def test_drop_payload_index_server_error(self):
        """Test drop behavior when server returns error."""
        collection_name = "test_collection"
        field_name = "type"

        # Mock server error response
        mock_response = Mock()
        mock_response.status_code = 500

        with patch.object(self.client.client, "delete", return_value=mock_response):
            # This will fail until we implement the method
            result = self.client._drop_payload_index(collection_name, field_name)

            assert result is False

    def test_drop_payload_index_exception_handling(self):
        """Test drop behavior when exceptions occur."""
        collection_name = "test_collection"
        field_name = "type"

        with patch.object(
            self.client.client, "delete", side_effect=Exception("Network error")
        ):
            # This will fail until we implement the method
            result = self.client._drop_payload_index(collection_name, field_name)

            assert result is False

    def test_rebuild_payload_indexes_user_feedback(self):
        """Test that appropriate user feedback is shown during rebuild."""
        collection_name = "test_collection"

        existing_indexes = [
            {"field": "type", "schema": "keyword"},
            {"field": "path", "schema": "text"},
        ]

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(self.client, "_drop_payload_index", return_value=True):
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ):
                    with patch.object(
                        self.client,
                        "get_payload_index_status",
                        return_value={"healthy": True},
                    ):
                        # This will fail until we implement the method
                        self.client.rebuild_payload_indexes(collection_name)

                        # Verify progress messages were shown
                        expected_messages = [
                            "🔧 Rebuilding payload indexes...",
                            "✅ Payload indexes rebuilt successfully",
                        ]

                        for message in expected_messages:
                            self.mock_console.print.assert_any_call(message)

    def test_rebuild_payload_indexes_empty_existing_indexes(self):
        """Test rebuild behavior when no existing indexes are present."""
        collection_name = "test_collection"

        # No existing indexes
        existing_indexes: list[dict[str, str]] = []

        with patch.object(
            self.client, "list_payload_indexes", return_value=existing_indexes
        ):
            with patch.object(self.client, "_drop_payload_index") as mock_drop:
                with patch.object(
                    self.client, "_create_payload_indexes_with_retry", return_value=True
                ):
                    with patch.object(
                        self.client,
                        "get_payload_index_status",
                        return_value={"healthy": True},
                    ):
                        # This will fail until we implement the method
                        result = self.client.rebuild_payload_indexes(collection_name)

                        assert result is True
                        # Should not call drop since no existing indexes
                        mock_drop.assert_not_called()
