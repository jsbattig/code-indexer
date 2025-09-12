"""Tests for Qdrant segment size configuration in collection creation."""

from unittest.mock import Mock, patch

from code_indexer.config import QdrantConfig
from code_indexer.services.qdrant import QdrantClient


class TestQdrantSegmentSize:
    """Test Qdrant client uses configured segment size."""

    def test_qdrant_client_uses_configured_segment_size(self):
        """Test that QdrantClient uses max_segment_size_kb from config."""
        # Create config with custom segment size (50MB = 51200 KB)
        config = QdrantConfig(max_segment_size_kb=51200)

        # Mock httpx client to capture the request
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.put.return_value = mock_response

            # Mock index status to indicate no missing indexes (so no index creation calls)
            mock_index_status = {
                "missing_indexes": [],  # No missing indexes
                "expected_indexes": 7,
                "total_indexes": 7,
            }

            # Create QdrantClient and call _create_collection_direct
            qdrant_client = QdrantClient(config)

            with patch.object(
                qdrant_client,
                "get_payload_index_status",
                return_value=mock_index_status,
            ):
                result = qdrant_client._create_collection_direct("test_collection", 768)

            # Verify the method was called and returned success
            assert result is True

            # Verify at least the collection creation call was made
            assert mock_client.put.call_count >= 1  # At least collection creation

            # Find the collection creation call
            collection_call = None
            for call in mock_client.put.call_args_list:
                if call[0][0] == "/collections/test_collection":
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"

            # Check the collection config in the JSON payload
            collection_config = collection_call[1]["json"]
            optimizers_config = collection_config["optimizers_config"]

            # This should contain our configured segment size
            assert "max_segment_size_kb" in optimizers_config
            assert optimizers_config["max_segment_size_kb"] == 51200

    def test_qdrant_client_uses_default_segment_size(self):
        """Test that QdrantClient uses default 100MB segment size."""
        # Create config with default segment size
        config = QdrantConfig()

        # Mock httpx client to capture the request
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.put.return_value = mock_response

            # Mock index status to indicate no missing indexes (so no index creation calls)
            mock_index_status = {
                "missing_indexes": [],  # No missing indexes
                "expected_indexes": 7,
                "total_indexes": 7,
            }

            # Create QdrantClient and call _create_collection_direct
            qdrant_client = QdrantClient(config)

            with patch.object(
                qdrant_client,
                "get_payload_index_status",
                return_value=mock_index_status,
            ):
                result = qdrant_client._create_collection_direct("test_collection", 768)

            # Verify the method was called and returned success
            assert result is True

            # Verify at least the collection creation call was made
            assert mock_client.put.call_count >= 1  # At least collection creation

            # Find the collection creation call
            collection_call = None
            for call in mock_client.put.call_args_list:
                if call[0][0] == "/collections/test_collection":
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"

            # Check the collection config in the JSON payload
            collection_config = collection_call[1]["json"]
            optimizers_config = collection_config["optimizers_config"]

            # This should contain the default segment size
            assert "max_segment_size_kb" in optimizers_config
            assert optimizers_config["max_segment_size_kb"] == 102400  # 100MB default

    def test_qdrant_client_backward_compatibility(self):
        """Test backward compatibility when config doesn't have max_segment_size_kb."""
        # Create a minimal config dict without max_segment_size_kb
        config_dict = {
            "host": "http://localhost:6333",
            "collection_base_name": "code_index",
            "vector_size": 768,
            "hnsw_ef": 64,
            "hnsw_ef_construct": 200,
            "hnsw_m": 32,
        }

        # Create config from dict (this tests backward compatibility)
        config = QdrantConfig(**config_dict)

        # The default should be applied
        assert config.max_segment_size_kb == 102400

        # Mock httpx client to capture the request
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.put.return_value = mock_response

            # Mock index status to indicate no missing indexes (so no index creation calls)
            mock_index_status = {
                "missing_indexes": [],  # No missing indexes
                "expected_indexes": 7,
                "total_indexes": 7,
            }

            # Create QdrantClient and call _create_collection_direct
            qdrant_client = QdrantClient(config)

            with patch.object(
                qdrant_client,
                "get_payload_index_status",
                return_value=mock_index_status,
            ):
                result = qdrant_client._create_collection_direct("test_collection", 768)

            # Verify the method was called and returned success
            assert result is True

            # Verify at least the collection creation call was made
            assert mock_client.put.call_count >= 1  # At least collection creation

            # Find the collection creation call
            collection_call = None
            for call in mock_client.put.call_args_list:
                if call[0][0] == "/collections/test_collection":
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"

            # Check the collection config in the JSON payload
            collection_config = collection_call[1]["json"]
            optimizers_config = collection_config["optimizers_config"]

            # This should contain the default segment size
            assert "max_segment_size_kb" in optimizers_config
            assert optimizers_config["max_segment_size_kb"] == 102400

    def test_qdrant_client_different_segment_sizes(self):
        """Test QdrantClient with various segment sizes."""
        test_cases = [
            (10240, "10MB"),  # 10MB
            (25600, "25MB"),  # 25MB
            (51200, "50MB"),  # 50MB
            (204800, "200MB"),  # 200MB
        ]

        for segment_size_kb, description in test_cases:
            config = QdrantConfig(max_segment_size_kb=segment_size_kb)

            # Mock httpx client to capture the request
            with patch("httpx.Client") as mock_client_class:
                mock_client = Mock()
                mock_client_class.return_value = mock_client

                # Mock successful response
                mock_response = Mock()
                mock_response.status_code = 200
                mock_client.put.return_value = mock_response

                # Mock index status to indicate no missing indexes (so no index creation calls)
                mock_index_status = {
                    "missing_indexes": [],  # No missing indexes
                    "expected_indexes": 7,
                    "total_indexes": 7,
                }

                # Create QdrantClient and call _create_collection_direct
                qdrant_client = QdrantClient(config)

                with patch.object(
                    qdrant_client,
                    "get_payload_index_status",
                    return_value=mock_index_status,
                ):
                    result = qdrant_client._create_collection_direct(
                        f"test_collection_{description}", 768
                    )

                # Verify the method was called and returned success
                assert result is True

                # Verify at least the collection creation call was made
                assert mock_client.put.call_count >= 1  # At least collection creation

                # Find the collection creation call
                collection_call = None
                for call in mock_client.put.call_args_list:
                    if f"/collections/test_collection_{description}" == call[0][0]:
                        collection_call = call
                        break

                assert collection_call is not None, "Collection creation call not found"

                # Check the collection config in the JSON payload
                collection_config = collection_call[1]["json"]
                optimizers_config = collection_config["optimizers_config"]

                # This should contain our configured segment size
                assert "max_segment_size_kb" in optimizers_config
                assert optimizers_config["max_segment_size_kb"] == segment_size_kb

                # Reset the mock for next iteration
                mock_client.reset_mock()

    def test_qdrant_client_public_create_collection_uses_segment_size(self):
        """Test that the public create_collection method also uses segment size."""
        config = QdrantConfig(max_segment_size_kb=76800)  # 75MB

        # Mock httpx client to capture the request
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.put.return_value = mock_response

            # Mock index status to indicate no missing indexes (so no index creation calls)
            mock_index_status = {
                "missing_indexes": [],  # No missing indexes
                "expected_indexes": 7,
                "total_indexes": 7,
            }

            # Create QdrantClient and call create_collection (public method)
            qdrant_client = QdrantClient(config)

            with patch.object(
                qdrant_client,
                "get_payload_index_status",
                return_value=mock_index_status,
            ):
                result = qdrant_client.create_collection("test_collection", 768)

            # Verify the method was called and returned success
            assert result is True

            # Verify at least the collection creation call was made
            assert mock_client.put.call_count >= 1  # At least collection creation

            # Find the collection creation call
            collection_call = None
            for call in mock_client.put.call_args_list:
                if call[0][0] == "/collections/test_collection":
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"

            # Check the collection config in the JSON payload
            collection_config = collection_call[1]["json"]
            optimizers_config = collection_config["optimizers_config"]

            # This should contain our configured segment size
            assert "max_segment_size_kb" in optimizers_config
            assert optimizers_config["max_segment_size_kb"] == 76800

    def test_qdrant_client_profile_collection_uses_segment_size(self):
        """Test that create_collection_with_profile also uses configured segment size."""
        config = QdrantConfig(max_segment_size_kb=40960)  # 40MB

        # Mock httpx client to capture the request
        with patch("httpx.Client") as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client

            # Mock successful response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_client.put.return_value = mock_response

            # Mock index status to indicate no missing indexes (so no index creation calls)
            mock_index_status = {
                "missing_indexes": [],  # No missing indexes
                "expected_indexes": 7,
                "total_indexes": 7,
            }

            # Create QdrantClient and call create_collection_with_profile
            qdrant_client = QdrantClient(config)

            with patch.object(
                qdrant_client,
                "get_payload_index_status",
                return_value=mock_index_status,
            ):
                result = qdrant_client.create_collection_with_profile(
                    "small_codebase", "test_collection", 768
                )

            # Verify the method was called and returned success
            assert result is True

            # Verify at least the collection creation call was made
            assert mock_client.put.call_count >= 1  # At least collection creation

            # Find the collection creation call
            collection_call = None
            for call in mock_client.put.call_args_list:
                if call[0][0] == "/collections/test_collection":
                    collection_call = call
                    break

            assert collection_call is not None, "Collection creation call not found"

            # Check the collection config in the JSON payload
            collection_config = collection_call[1]["json"]
            optimizers_config = collection_config["optimizers_config"]

            # This should contain our configured segment size
            assert "max_segment_size_kb" in optimizers_config
            assert optimizers_config["max_segment_size_kb"] == 40960
