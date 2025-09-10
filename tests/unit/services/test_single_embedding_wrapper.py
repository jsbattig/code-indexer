#!/usr/bin/env python3
"""
Test suite for single embedding wrapper implementation.

Validates that get_embedding() uses get_embeddings_batch() internally while
preserving identical error handling behavior and CLI compatibility.
"""

import os
import pytest
from unittest.mock import patch
from typing import List
import inspect

from code_indexer.config import VoyageAIConfig
from code_indexer.services.voyage_ai import VoyageAIClient
from rich.console import Console


class TestSingleEmbeddingWrapper:
    """Test single embedding wrapper functionality."""

    @pytest.fixture
    def voyage_config(self):
        return VoyageAIConfig(
            model="voyage-code-3",
            batch_size=64,
            parallel_requests=4,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def mock_api_key(self):
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_api_key"}):
            yield "test_api_key"

    @pytest.fixture
    def voyage_client(self, voyage_config, console, mock_api_key):
        return VoyageAIClient(voyage_config, console)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_calls_batch_internally(self, mock_batch, voyage_client):
        """Test that get_embedding() calls get_embeddings_batch() internally."""
        # Arrange
        test_text = "test text for embedding"
        expected_embedding = [0.1, 0.2, 0.3, 0.4]
        mock_batch.return_value = [
            expected_embedding
        ]  # Batch returns array of embeddings

        # Act
        result = voyage_client.get_embedding(test_text)

        # Assert
        mock_batch.assert_called_once_with([test_text], None)
        assert result == expected_embedding
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_with_model_parameter(self, mock_batch, voyage_client):
        """Test that get_embedding() passes model parameter to batch method."""
        # Arrange
        test_text = "test text"
        test_model = "custom-model"
        expected_embedding = [0.5, 0.6, 0.7, 0.8]
        mock_batch.return_value = [expected_embedding]

        # Act
        result = voyage_client.get_embedding(test_text, model=test_model)

        # Assert
        mock_batch.assert_called_once_with([test_text], test_model)
        assert result == expected_embedding

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_extracts_first_result(self, mock_batch, voyage_client):
        """Test that get_embedding() correctly extracts first result from batch."""
        # Arrange
        test_text = "test text"
        batch_results = [
            [0.1, 0.2, 0.3, 0.4],  # This should be returned
            [0.5, 0.6, 0.7, 0.8],  # This should be ignored
        ]
        mock_batch.return_value = batch_results

        # Act
        result = voyage_client.get_embedding(test_text)

        # Assert
        assert result == batch_results[0]  # Only first result
        mock_batch.assert_called_once_with([test_text], None)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_error_passthrough(self, mock_batch, voyage_client):
        """Test that get_embedding() passes through all errors from batch method."""
        # Arrange
        test_text = "test text"
        expected_error = RuntimeError("VoyageAI API error (HTTP 500): Server error")
        mock_batch.side_effect = expected_error

        # Act & Assert
        with pytest.raises(RuntimeError, match="VoyageAI API error.*Server error"):
            voyage_client.get_embedding(test_text)

        mock_batch.assert_called_once_with([test_text], None)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_api_key_error_passthrough(self, mock_batch, voyage_client):
        """Test that API key errors are passed through unchanged."""
        # Arrange
        test_text = "test text"
        expected_error = ValueError(
            "Invalid VoyageAI API key. Check VOYAGE_API_KEY environment variable."
        )
        mock_batch.side_effect = expected_error

        # Act & Assert
        with pytest.raises(ValueError, match="Invalid VoyageAI API key"):
            voyage_client.get_embedding(test_text)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_rate_limit_error_passthrough(
        self, mock_batch, voyage_client
    ):
        """Test that rate limit errors are passed through unchanged."""
        # Arrange
        test_text = "test text"
        expected_error = RuntimeError(
            "VoyageAI rate limit exceeded. Try reducing parallel_requests or requests_per_minute."
        )
        mock_batch.side_effect = expected_error

        # Act & Assert
        with pytest.raises(RuntimeError, match="VoyageAI rate limit exceeded"):
            voyage_client.get_embedding(test_text)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_connection_error_passthrough(
        self, mock_batch, voyage_client
    ):
        """Test that connection errors are passed through unchanged."""
        # Arrange
        test_text = "test text"
        expected_error = ConnectionError(
            "Failed to connect to VoyageAI: Connection timeout"
        )
        mock_batch.side_effect = expected_error

        # Act & Assert
        with pytest.raises(ConnectionError, match="Failed to connect to VoyageAI"):
            voyage_client.get_embedding(test_text)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient.get_embeddings_batch")
    def test_get_embedding_empty_batch_result_error(self, mock_batch, voyage_client):
        """Test that empty batch results raise appropriate error."""
        # Arrange
        test_text = "test text"
        mock_batch.return_value = []  # Empty batch result

        # Act & Assert
        with pytest.raises(
            IndexError
        ):  # Should fail when trying to access first element
            voyage_client.get_embedding(test_text)

    def test_get_embedding_method_signature_unchanged(self, voyage_client):
        """Test that get_embedding() method signature is unchanged."""
        # Get method signature
        sig = inspect.signature(voyage_client.get_embedding)
        params = list(sig.parameters.keys())

        # Verify signature: get_embedding(self, text: str, model: Optional[str] = None) -> List[float]
        assert params == ["text", "model"]

        # Verify parameter types and defaults
        text_param = sig.parameters["text"]
        model_param = sig.parameters["model"]

        assert text_param.annotation is str
        assert text_param.default == inspect.Parameter.empty

        assert model_param.default is None

        # Verify return type annotation
        assert sig.return_annotation == List[float]


class TestSingleEmbeddingWrapperIntegration:
    """Integration tests for single embedding wrapper with real batch method."""

    @pytest.fixture
    def voyage_config(self):
        return VoyageAIConfig(
            model="voyage-code-3",
            batch_size=64,
            parallel_requests=4,
        )

    @pytest.fixture
    def console(self):
        return Console(quiet=True)

    @pytest.fixture
    def mock_api_key(self):
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_api_key"}):
            yield "test_api_key"

    @pytest.fixture
    def voyage_client(self, voyage_config, console, mock_api_key):
        return VoyageAIClient(voyage_config, console)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_integration_single_embedding_via_batch(self, mock_request, voyage_client):
        """Test complete integration of single embedding via batch processing."""
        # Arrange
        test_text = "integration test text"
        mock_api_response = {
            "data": [{"embedding": [0.1, 0.2, 0.3, 0.4]}],
            "usage": {"total_tokens": 10},
        }
        mock_request.return_value = mock_api_response

        # Act
        result = voyage_client.get_embedding(test_text)

        # Assert
        assert result == [0.1, 0.2, 0.3, 0.4]

        # Verify that _make_sync_request was called with single-item array
        mock_request.assert_called_once_with([test_text], None)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_integration_error_handling_preservation(self, mock_request, voyage_client):
        """Test that error handling behavior is preserved in integration."""
        # Arrange
        test_text = "test text"

        # Mock the actual ValueError that _make_sync_request would raise
        # (simulating the error transformation that happens in _make_sync_request)
        api_key_error = ValueError(
            "Invalid VoyageAI API key. Check VOYAGE_API_KEY environment variable."
        )
        mock_request.side_effect = api_key_error

        # Act & Assert - Error should be passed through by batch method
        with pytest.raises(ValueError, match="Invalid VoyageAI API key"):
            voyage_client.get_embedding(test_text)

    @patch("code_indexer.services.voyage_ai.VoyageAIClient._make_sync_request")
    def test_cli_compatibility_preserved(self, mock_request, voyage_client):
        """Test that CLI query functionality compatibility is preserved."""
        # Arrange - Simulate typical CLI query usage
        query_text = "function authentication"
        mock_api_response = {
            "data": [{"embedding": [0.15, 0.25, 0.35, 0.45, 0.55]}],
            "usage": {"total_tokens": 15},
        }
        mock_request.return_value = mock_api_response

        # Act - This is how CLI query calls get_embedding
        query_embedding = voyage_client.get_embedding(query_text)

        # Assert - Result should be suitable for vector search
        assert isinstance(query_embedding, list)
        assert len(query_embedding) == 5
        assert all(isinstance(x, float) for x in query_embedding)
        assert query_embedding == [0.15, 0.25, 0.35, 0.45, 0.55]

        # Verify proper API call was made
        mock_request.assert_called_once_with([query_text], None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
