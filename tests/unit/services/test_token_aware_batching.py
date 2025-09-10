"""Tests for token-aware batching fix in VoyageAI client."""

import pytest
from unittest.mock import Mock, patch
from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.config import VoyageAIConfig


class TestTokenAwareBatching:
    """Test token-aware batching to prevent VoyageAI token limit violations."""

    @pytest.fixture
    def voyage_config(self):
        """Fixture providing VoyageAI configuration."""
        return VoyageAIConfig(
            batch_size=128,
            max_retries=2,
            retry_delay=1.0,
            exponential_backoff=True
        )

    @pytest.fixture  
    def voyage_client(self, voyage_config):
        """Fixture providing VoyageAI client with mocked API key."""
        with patch("code_indexer.services.voyage_ai.os.getenv", return_value="test_key"):
            return VoyageAIClient(voyage_config)

    def test_token_limit_respected_for_large_batches(self, voyage_client):
        """Test that token limits are respected when processing large batches."""
        # Create large text chunks that would exceed 120K token limit
        # Each chunk ~2000 tokens, 70 chunks = ~140K tokens (exceeds limit)
        large_texts = [
            "This is a very large text chunk " * 150  # ~600 words = ~450 tokens each
            for i in range(70)  # 70 chunks * 450 tokens = ~31,500 tokens total
        ]
        
        # Mock the API response for multiple batches
        mock_responses = [
            {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]} 
                    for _ in range(len(batch))
                ]
            }
            for batch in [large_texts[:35], large_texts[35:]]  # Split into 2 batches
        ]
        
        with patch.object(voyage_client, '_make_sync_request', side_effect=mock_responses):
            # This should NOT fail with token limit error
            embeddings = voyage_client.get_embeddings_batch(large_texts)
            
            # Should return embeddings for all texts
            assert len(embeddings) == 70
            assert all(len(emb) == 3 for emb in embeddings)

    def test_token_estimation_accuracy(self, voyage_client):
        """Test that token estimation provides reasonable approximations."""
        test_cases = [
            ("hello world", 2),  # 2 words * 0.75 = 1.5 → 2 tokens
            ("", 1),  # Empty text should estimate minimum 1 token
            ("single", 1),  # 1 word * 0.75 = 0.75 → 1 token
            ("this is a longer piece of text with many words", 9),  # 10 words * 0.75 = 7.5 → 8 tokens
        ]
        
        for text, expected_min_tokens in test_cases:
            estimated = voyage_client._estimate_tokens(text)
            assert estimated >= expected_min_tokens, f"Text '{text}' should estimate at least {expected_min_tokens} tokens, got {estimated}"

    def test_single_batch_when_under_limits(self, voyage_client):
        """Test that small batches still process as single API call."""
        small_texts = ["short text"] * 10  # 10 chunks, ~20 tokens total
        
        # Mock single API response
        mock_response = {
            "data": [
                {"embedding": [0.1, 0.2, 0.3]} 
                for _ in range(10)
            ]
        }
        
        with patch.object(voyage_client, '_make_sync_request', return_value=mock_response) as mock_api:
            embeddings = voyage_client.get_embeddings_batch(small_texts)
            
            # Should make exactly 1 API call for small batch
            assert mock_api.call_count == 1
            assert len(embeddings) == 10

    def test_multiple_batches_for_large_files(self, voyage_client):
        """Test that very large files are split into multiple batches."""
        # Create text that definitely exceeds 100K token limit
        huge_texts = [
            "word " * 1000  # ~750 tokens per chunk  
            for i in range(200)  # 200 chunks * 750 = 150K tokens (exceeds limit)
        ]
        
        # Mock multiple API responses
        call_count = 0
        def mock_api_call(texts):
            nonlocal call_count
            call_count += 1
            return {
                "data": [
                    {"embedding": [0.1, 0.2, 0.3]} 
                    for _ in texts
                ]
            }
        
        with patch.object(voyage_client, '_make_sync_request', side_effect=mock_api_call):
            embeddings = voyage_client.get_embeddings_batch(huge_texts)
            
            # Should split into multiple API calls to respect token limits
            assert call_count > 1, f"Large batch should require multiple API calls, got {call_count}"
            assert len(embeddings) == 200, "All embeddings should be returned despite batching"

    def test_edge_case_single_huge_text(self, voyage_client):
        """Test handling of single text that exceeds token limits."""
        # Single huge text that exceeds limits by itself
        huge_text = "word " * 50000  # ~37,500 tokens in single text
        
        # Mock API response  
        mock_response = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}]
        }
        
        with patch.object(voyage_client, '_make_sync_request', return_value=mock_response):
            # Should process single huge text (VoyageAI will truncate)
            embeddings = voyage_client.get_embeddings_batch([huge_text])
            assert len(embeddings) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])