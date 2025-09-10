"""
Additional edge case tests for VoyageAI metadata compatibility wrapper.

Tests edge cases and error conditions to ensure robust error handling.
"""

import os
import pytest
from unittest.mock import patch
from rich.console import Console

from code_indexer.config import VoyageAIConfig
from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.services.embedding_provider import BatchEmbeddingResult


class TestVoyageAIMetadataWrapperEdgeCases:
    """Test edge cases for metadata compatibility wrapper."""

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

    def test_api_error_propagation(self, voyage_client):
        """Test that API errors from batch method are properly propagated."""
        api_error = RuntimeError("VoyageAI API unavailable")

        with patch.object(
            voyage_client, "get_embeddings_batch_with_metadata", side_effect=api_error
        ):
            with pytest.raises(RuntimeError, match="VoyageAI API unavailable"):
                voyage_client.get_embedding_with_metadata("test text")

    def test_network_error_propagation(self, voyage_client):
        """Test that network errors are properly propagated."""
        network_error = ConnectionError("Network unreachable")

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            side_effect=network_error,
        ):
            with pytest.raises(ConnectionError, match="Network unreachable"):
                voyage_client.get_embedding_with_metadata("test text")

    def test_rate_limit_error_propagation(self, voyage_client):
        """Test that rate limit errors are properly propagated."""
        rate_limit_error = ValueError("Rate limit exceeded")

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            side_effect=rate_limit_error,
        ):
            with pytest.raises(ValueError, match="Rate limit exceeded"):
                voyage_client.get_embedding_with_metadata("test text")

    def test_empty_text_handling(self, voyage_client):
        """Test handling of empty text input."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.0, 0.0, 0.0]],  # Empty text might return zero vector
            model="voyage-code-3",
            total_tokens_used=1,  # Minimal tokens for empty input
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("")

            assert result.embedding == [0.0, 0.0, 0.0]
            assert result.tokens_used == 1

    def test_very_long_text_handling(self, voyage_client):
        """Test handling of very long text input."""
        long_text = "x" * 10000  # Very long text
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model="voyage-code-3",
            total_tokens_used=2500,  # Many tokens for long text
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata(long_text)

            assert result.tokens_used == 2500

    def test_special_characters_handling(self, voyage_client):
        """Test handling of text with special characters."""
        special_text = "Special chars: αβγ δεζ ηθι κλμ 中文 😀🎉"
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.5, -0.3, 0.8]],
            model="voyage-code-3",
            total_tokens_used=12,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata(special_text)

            assert result.embedding == [0.5, -0.3, 0.8]
            assert result.tokens_used == 12

    def test_zero_token_usage_handling(self, voyage_client):
        """Test handling when API returns zero token usage."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2]],
            model="voyage-code-3",
            total_tokens_used=0,  # Zero tokens reported
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("test")

            assert result.tokens_used == 0

    def test_model_override_with_custom_model(self, voyage_client):
        """Test that custom model parameter is correctly passed through."""
        custom_model = "voyage-large-2"
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[0.1, 0.2, 0.3]],
            model=custom_model,
            total_tokens_used=8,
            provider="voyage-ai",
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ) as mock_batch:
            result = voyage_client.get_embedding_with_metadata(
                "test", model=custom_model
            )

            # Verify custom model was passed to batch method
            mock_batch.assert_called_once_with(["test"], custom_model)
            assert result.model == custom_model

    def test_concurrent_access_safety(self, voyage_client):
        """Test that concurrent access to the wrapper is safe."""
        import threading

        results = []
        errors = []

        def call_wrapper(text_suffix):
            try:
                mock_batch_result = BatchEmbeddingResult(
                    embeddings=[[float(text_suffix), 0.2, 0.3]],
                    model="voyage-code-3",
                    total_tokens_used=5,
                    provider="voyage-ai",
                )

                with patch.object(
                    voyage_client,
                    "get_embeddings_batch_with_metadata",
                    return_value=mock_batch_result,
                ):
                    result = voyage_client.get_embedding_with_metadata(
                        f"test{text_suffix}"
                    )
                    results.append(result)
            except Exception as e:
                errors.append(e)

        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=call_wrapper, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors and all results collected
        assert len(errors) == 0
        assert len(results) == 5

    def test_metadata_field_types_preserved(self, voyage_client):
        """Test that metadata field types are exactly preserved."""
        mock_batch_result = BatchEmbeddingResult(
            embeddings=[[1.23456789, -0.987654321]],  # High precision floats
            model="voyage-code-3",
            total_tokens_used=42,  # Integer
            provider="voyage-ai",  # String
        )

        with patch.object(
            voyage_client,
            "get_embeddings_batch_with_metadata",
            return_value=mock_batch_result,
        ):
            result = voyage_client.get_embedding_with_metadata("precision test")

            # Verify exact type preservation
            assert isinstance(result.embedding, list)
            assert isinstance(result.embedding[0], float)
            assert isinstance(result.model, str)
            assert isinstance(result.tokens_used, int)
            assert isinstance(result.provider, str)

            # Verify exact values
            assert result.embedding[0] == 1.23456789
            assert result.embedding[1] == -0.987654321
