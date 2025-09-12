"""
Unit tests for VoyageAI metadata compatibility wrapper implementation.

Tests verify that get_embedding_with_metadata() correctly uses get_embeddings_batch_with_metadata()
internally while preserving all metadata fields and error handling behavior.
"""

import os
import pytest
from unittest.mock import patch
from rich.console import Console

from code_indexer.config import VoyageAIConfig
from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.services.embedding_provider import (
    EmbeddingResult,
    BatchEmbeddingResult,
)


class TestVoyageAIMetadataCompatibilityWrapper:
    """Test metadata compatibility wrapper for get_embedding_with_metadata()."""

    @pytest.fixture
    def voyage_config(self):
        return VoyageAIConfig(
            model="voyage-code-3",
            parallel_requests=4,
            batch_size=64,
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

    def test_get_embedding_with_metadata_uses_batch_internally(self, voyage_client):
        """Test that get_embedding_with_metadata() uses get_embeddings_batch_with_metadata() internally."""
        # Mock the batch method to return expected BatchEmbeddingResult
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3, 0.4]],
            model="voyage-code-3",
            total_tokens_used=10,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ) as mock_batch:
            result = voyage_client.get_embedding_with_metadata(
                "test text", model="voyage-code-3"
            )

            # Verify batch method was called with correct parameters
            mock_batch.assert_called_once_with(["test text"], "voyage-code-3")

            # Verify correct mapping from batch to single result
            assert isinstance(result, EmbeddingResult)
            assert result.embedding == [0.1, 0.2, 0.3, 0.4]
            assert result.model == "voyage-code-3"
            assert result.tokens_used == 10  # mapped from total_tokens_used
            assert result.provider == "voyage-ai"

    def test_get_embedding_with_metadata_preserves_default_model(self, voyage_client):
        """Test that default model is preserved when no model specified."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.5, 0.6, 0.7, 0.8]],
            model="voyage-code-3",  # default model
            total_tokens_used=15,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ) as mock_batch:
            result = voyage_client.get_embedding_with_metadata("test text")

            # Verify batch method was called with None model (uses default)
            mock_batch.assert_called_once_with(["test text"], None)

            # Verify result uses default model
            assert result.model == "voyage-code-3"

    def test_get_embedding_with_metadata_handles_empty_batch_result(
        self, voyage_client
    ):
        """Test error handling when batch result has no embeddings."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[],  # empty results
            model="voyage-code-3",
            total_tokens_used=0,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            with pytest.raises(
                ValueError, match="No embedding returned from batch processing"
            ):
                voyage_client.get_embedding_with_metadata("test text")

    def test_get_embedding_with_metadata_preserves_batch_errors(self, voyage_client):
        """Test that errors from batch method are propagated correctly."""
        error_message = "API rate limit exceeded"

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            side_effect=RuntimeError(error_message),
        ):
            with pytest.raises(RuntimeError, match=error_message):
                voyage_client.get_embedding_with_metadata("test text")

    def test_get_embedding_with_metadata_handles_none_tokens(self, voyage_client):
        """Test handling when batch result has None total_tokens_used."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3, 0.4]],
            model="voyage-code-3",
            total_tokens_used=None,  # API didn't provide token usage
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("test text")

            assert result.tokens_used is None  # preserved None value

    def test_get_embedding_with_metadata_preserves_exact_behavior(self, voyage_client):
        """Test that wrapper preserves exact behavior of dependent systems."""
        # Test with realistic scenario
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.123, -0.456, 0.789, -0.101]],
            model="voyage-code-2",  # custom model
            total_tokens_used=42,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata(
                "complex test text", model="voyage-code-2"
            )

            # Verify all metadata fields are exactly preserved
            assert result.embedding == [0.123, -0.456, 0.789, -0.101]
            assert result.model == "voyage-code-2"
            assert result.tokens_used == 42
            assert result.provider == "voyage-ai"

    def test_integration_with_logging_systems(self, voyage_client):
        """Test compatibility with systems that log embedding metadata."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2]],
            model="voyage-code-3",
            total_tokens_used=25,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("log test")

            # Verify result can be used for logging/monitoring
            log_data = {
                "model": result.model,
                "tokens": result.tokens_used,
                "provider": result.provider,
                "embedding_length": len(result.embedding),
            }

            assert log_data == {
                "model": "voyage-code-3",
                "tokens": 25,
                "provider": "voyage-ai",
                "embedding_length": 2,
            }

    def test_token_tracking_compatibility(self, voyage_client):
        """Test compatibility with token tracking systems."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="voyage-code-3",
            total_tokens_used=100,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("tracking test")

            # Simulate token tracking system usage
            total_tokens = 0
            if result.tokens_used is not None:
                total_tokens += result.tokens_used

            assert total_tokens == 100
