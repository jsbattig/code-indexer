"""
Unit tests for VoyageAI partial response validation.

Tests the critical bug where VoyageAI returns fewer embeddings than requested,
leading to zip() length mismatches and IndexError in temporal_indexer.py.
"""

import os
import pytest
from unittest.mock import Mock, patch
from src.code_indexer.services.voyage_ai import VoyageAIClient
from src.code_indexer.config import VoyageAIConfig


class TestVoyageAIPartialResponse:
    """Test VoyageAI API partial response handling."""

    @pytest.fixture
    def voyage_config(self):
        """Create VoyageAI configuration."""
        return VoyageAIConfig(
            model="voyage-code-3",
            parallel_requests=4,
            batch_size=64,
        )

    @pytest.fixture
    def mock_api_key(self):
        """Mock API key environment variable."""
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "test_api_key"}):
            yield "test_api_key"

    def test_partial_response_single_batch_detected(self, voyage_config, mock_api_key):
        """
        Test that partial response in single batch is detected and raises error.

        Bug scenario: VoyageAI returns 7 embeddings when 10 were requested.
        Expected: RuntimeError with clear message about partial response.
        """
        # Setup
        service = VoyageAIClient(voyage_config)
        texts = [f"text_{i}" for i in range(10)]

        # Mock API to return only 7 embeddings instead of 10
        mock_response = {
            "data": [{"embedding": [0.1] * 1536} for _ in range(7)]  # Only 7 embeddings
        }

        with patch.object(service, "_make_sync_request", return_value=mock_response):
            # Execute & Verify
            with pytest.raises(RuntimeError) as exc_info:
                service.get_embeddings_batch(texts)

            # Verify error message describes the problem
            error_msg = str(exc_info.value)
            assert "returned 7 embeddings" in error_msg.lower()
            assert "expected 10" in error_msg.lower()
            assert "partial response" in error_msg.lower()

    def test_correct_response_length_passes(self, voyage_config, mock_api_key):
        """
        Test that correct response length passes validation.

        Scenario: VoyageAI returns exactly the number of embeddings requested.
        Expected: No error, all embeddings returned.
        """
        # Setup
        service = VoyageAIClient(voyage_config)
        texts = [f"text_{i}" for i in range(10)]

        # Mock API to return correct number of embeddings
        mock_response = {
            "data": [
                {"embedding": [0.1 * i] * 1536}
                for i in range(10)  # Exactly 10 embeddings
            ]
        }

        with patch.object(service, "_make_sync_request", return_value=mock_response):
            # Execute
            embeddings = service.get_embeddings_batch(texts)

            # Verify
            assert len(embeddings) == 10
            assert all(len(emb) == 1536 for emb in embeddings)
