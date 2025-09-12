"""Integration tests for QdrantConfig payload index configuration with QdrantClient (Story 2)."""

from unittest.mock import Mock, patch

from code_indexer.services.qdrant import QdrantClient
from code_indexer.config import QdrantConfig


class TestQdrantServiceConfigIntegration:
    """Test integration between QdrantConfig and QdrantClient for payload indexes."""

    def setup_method(self):
        """Setup test environment."""
        self.mock_console = Mock()

    def test_create_payload_indexes_respects_enable_flag_true(self):
        """Test that payload indexes are created when enable_payload_indexes=True."""
        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=[
                ("field1", "keyword"),
                ("field2", "text"),
            ],
        )
        client = QdrantClient(config, self.mock_console)

        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(client.client, "put", return_value=mock_response) as mock_put:
            result = client._create_payload_indexes_with_retry("test_collection")

            assert result is True
            # Should make 2 API calls for the 2 configured indexes
            assert mock_put.call_count == 2

            # Verify the correct fields were sent
            call_args_list = mock_put.call_args_list
            sent_fields = [
                (call[1]["json"]["field_name"], call[1]["json"]["field_schema"])
                for call in call_args_list
            ]

            assert ("field1", "keyword") in sent_fields
            assert ("field2", "text") in sent_fields

    def test_create_payload_indexes_respects_enable_flag_false(self):
        """Test that no payload indexes are created when enable_payload_indexes=False."""
        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=False,
            payload_indexes=[
                ("field1", "keyword"),
                ("field2", "text"),
            ],
        )
        client = QdrantClient(config, self.mock_console)

        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(client.client, "put", return_value=mock_response) as mock_put:
            result = client._create_payload_indexes_with_retry("test_collection")

            # Should return True (no-op success) but make no API calls
            assert result is True
            assert mock_put.call_count == 0

            # When indexes are disabled, no message is printed for legacy_direct context
            # The implementation returns True silently without any console output
            # So we should not expect any specific message to be printed

    def test_create_payload_indexes_uses_custom_config(self):
        """Test that custom payload index configuration is used."""
        custom_indexes = [
            ("custom_type", "keyword"),
            ("custom_path", "text"),
            ("custom_timestamp", "integer"),
            ("custom_geo", "geo"),
            ("custom_flag", "bool"),
        ]

        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=custom_indexes,
        )
        client = QdrantClient(config, self.mock_console)

        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(client.client, "put", return_value=mock_response) as mock_put:
            result = client._create_payload_indexes_with_retry("test_collection")

            assert result is True
            # Should make 5 API calls for the 5 configured indexes
            assert mock_put.call_count == 5

            # Verify all custom fields were sent
            call_args_list = mock_put.call_args_list
            sent_fields = [
                (call[1]["json"]["field_name"], call[1]["json"]["field_schema"])
                for call in call_args_list
            ]

            for field_name, field_schema in custom_indexes:
                assert (field_name, field_schema) in sent_fields

    def test_create_payload_indexes_empty_config_succeeds(self):
        """Test that empty payload index configuration succeeds without API calls."""
        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=[],  # Empty list
        )
        client = QdrantClient(config, self.mock_console)

        # Mock the collection info response to avoid 404 errors
        mock_collection_info = Mock()
        mock_collection_info.status_code = 200
        mock_collection_info.json.return_value = {
            "result": {"payload_schema": {}}  # Empty payload schema
        }

        with patch.object(client.client, "get", return_value=mock_collection_info):
            with patch.object(client.client, "put") as mock_put:
                result = client._create_payload_indexes_with_retry("test_collection")

                # Should return True (no-op success) and make no API calls
                assert result is True
                assert mock_put.call_count == 0

                # With empty indexes config and no errors, the method returns True silently
                # No specific message is printed in this case

    def test_create_payload_indexes_uses_defaults_when_not_specified(self):
        """Test that default payload indexes are used when config uses defaults."""
        config = QdrantConfig(host="http://localhost:6333")  # Uses defaults
        client = QdrantClient(config, self.mock_console)

        # Mock the collection info response to indicate no existing indexes
        mock_collection_info = Mock()
        mock_collection_info.status_code = 200
        mock_collection_info.json.return_value = {
            "result": {"payload_schema": {}}  # No existing indexes
        }

        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(client.client, "get", return_value=mock_collection_info):
            with patch.object(
                client.client, "put", return_value=mock_response
            ) as mock_put:
                result = client._create_payload_indexes_with_retry("test_collection")

                assert result is True
                # Should make 7 API calls for the default indexes
                assert mock_put.call_count == 7

                # Verify the default fields were sent
                call_args_list = mock_put.call_args_list
                sent_fields = [
                    (call[1]["json"]["field_name"], call[1]["json"]["field_schema"])
                    for call in call_args_list
                ]

                expected_defaults = [
                    ("type", "keyword"),
                    ("path", "text"),
                    ("git_branch", "keyword"),
                    ("file_mtime", "integer"),
                    ("hidden_branches", "keyword"),
                    ("language", "keyword"),
                    ("embedding_model", "keyword"),  # Added missing default index
                ]

                for field_name, field_schema in expected_defaults:
                    assert (field_name, field_schema) in sent_fields

    def test_create_payload_indexes_partial_failure_with_custom_config(self):
        """Test partial failure scenario with custom configuration."""
        custom_indexes = [
            ("field1", "keyword"),
            ("field2", "text"),
            ("field3", "integer"),
        ]

        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=True,
            payload_indexes=custom_indexes,
        )
        client = QdrantClient(config, self.mock_console)

        # Mock the collection info response to indicate no existing indexes
        mock_collection_info = Mock()
        mock_collection_info.status_code = 200
        mock_collection_info.json.return_value = {
            "result": {"payload_schema": {}}  # No existing indexes
        }

        # Mock responses: first 2 succeed, third fails
        mock_responses = []
        for i in range(3):
            mock_response = Mock()
            if i < 2:
                mock_response.status_code = 201
            else:
                mock_response.status_code = 500
            mock_responses.append(mock_response)

        with patch.object(client.client, "get", return_value=mock_collection_info):
            with patch.object(client.client, "put", side_effect=mock_responses):
                result = client._create_payload_indexes_with_retry("test_collection")

            # Should return False (partial success is treated as failure in legacy_direct context)
            assert result is False

            # Verify appropriate feedback messages about partial failure
            self.mock_console.print.assert_any_call(
                "   📊 Created 2/3 payload indexes (1 failed)"
            )

    def test_collection_creation_methods_use_config(self):
        """Test that collection creation methods respect payload index configuration."""
        config = QdrantConfig(
            host="http://localhost:6333",
            enable_payload_indexes=False,  # Disabled
        )
        client = QdrantClient(config, self.mock_console)

        # Mock successful collection creation
        mock_collection_response = Mock()
        mock_collection_response.status_code = 201

        with patch.object(client.client, "put", return_value=mock_collection_response):
            with patch.object(
                client, "ensure_payload_indexes", return_value=True
            ) as mock_ensure_indexes:
                # Test _create_collection_direct
                result = client._create_collection_direct("test_collection", 768)
                assert result is True

                # Index creation should still be called with collection_creation context
                mock_ensure_indexes.assert_called_once_with(
                    "test_collection", context="collection_creation"
                )

                mock_ensure_indexes.reset_mock()

                # Test create_collection_with_profile
                result = client.create_collection_with_profile(
                    "small_codebase", "test_collection2", 768
                )
                assert result is True

                # Should call ensure_payload_indexes for the new collection
                mock_ensure_indexes.assert_called_with(
                    "test_collection2", context="collection_creation"
                )

    def test_backward_compatibility_with_existing_qdrant_client_usage(self):
        """Test that existing QdrantClient usage continues to work with new config fields."""
        # Create config without specifying new fields (should use defaults)
        config = QdrantConfig(
            host="http://localhost:6333",
            collection_base_name="test_collection",
            vector_size=768,
        )
        client = QdrantClient(config, self.mock_console)

        # Should have default values
        assert config.enable_payload_indexes is True
        assert len(config.payload_indexes) == 7  # Default indexes

        # Mock the collection info response to indicate no existing indexes
        mock_collection_info = Mock()
        mock_collection_info.status_code = 200
        mock_collection_info.json.return_value = {
            "result": {"payload_schema": {}}  # No existing indexes
        }

        mock_response = Mock()
        mock_response.status_code = 201

        with patch.object(client.client, "get", return_value=mock_collection_info):
            with patch.object(
                client.client, "put", return_value=mock_response
            ) as mock_put:
                result = client._create_payload_indexes_with_retry("test_collection")

                assert result is True
                # Should create all 7 default indexes
                assert mock_put.call_count == 7
