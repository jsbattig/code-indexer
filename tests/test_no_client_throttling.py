"""Test that client-side throttling has been completely removed.

These tests verify that the system no longer performs client-side rate limiting
and instead relies on server-driven throttling with proper retry mechanisms.
"""

import asyncio
import time
from unittest.mock import Mock, patch
import pytest
import httpx

from code_indexer.services.voyage_ai import VoyageAIClient
from code_indexer.services.vector_calculation_manager import VectorCalculationManager
from code_indexer.config import VoyageAIConfig


class TestNoClientThrottling:
    """Verify that client-side throttling has been completely removed."""

    def test_voyage_ai_client_has_no_rate_limiter(self):
        """VoyageAI client should not have any rate limiter."""
        config = VoyageAIConfig()

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            client = VoyageAIClient(config)

            # Should not have rate_limiter attribute
            assert not hasattr(
                client, "rate_limiter"
            ), "Client should not have rate_limiter"

            # Should not have throttling callback
            assert not hasattr(
                client, "throttling_callback"
            ), "Client should not have throttling_callback"
            assert not hasattr(
                client, "set_throttling_callback"
            ), "Client should not have set_throttling_callback method"

    def test_voyage_ai_config_has_no_rate_limiting_fields(self):
        """VoyageAI config should not have rate limiting fields."""
        config = VoyageAIConfig()

        # Should not have rate limiting fields
        assert not hasattr(
            config, "requests_per_minute"
        ), "Config should not have requests_per_minute"
        assert not hasattr(
            config, "tokens_per_minute"
        ), "Config should not have tokens_per_minute"

        # Should still have retry configuration
        assert hasattr(config, "max_retries"), "Config should still have max_retries"
        assert hasattr(config, "retry_delay"), "Config should still have retry_delay"
        assert hasattr(
            config, "exponential_backoff"
        ), "Config should still have exponential_backoff"

    def test_vector_calculation_manager_has_no_throttling_status(self):
        """VectorCalculationManager should not track throttling status."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Should not have throttling-related attributes
        assert not hasattr(
            manager, "throttling_detection_window"
        ), "Manager should not have throttling_detection_window"
        assert not hasattr(
            manager, "recent_wait_events"
        ), "Manager should not have recent_wait_events"
        assert not hasattr(
            manager, "record_client_wait_time"
        ), "Manager should not have record_client_wait_time method"
        assert not hasattr(
            manager, "record_server_throttle"
        ), "Manager should not have record_server_throttle method"

        # Stats should not include throttling status
        stats = manager.get_stats()
        assert not hasattr(
            stats, "throttling_status"
        ), "Stats should not have throttling_status"

    @pytest.mark.asyncio
    async def test_voyage_ai_makes_requests_without_client_side_delays(self):
        """VoyageAI should make requests immediately without client-side rate limiting delays."""
        config = VoyageAIConfig()

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            client = VoyageAIClient(config)

            # Mock successful response
            mock_response = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "usage": {"total_tokens": 10},
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                # Create a proper mock response
                mock_resp = Mock()
                mock_resp.json.return_value = mock_response
                mock_resp.raise_for_status.return_value = None
                mock_post.return_value = mock_resp

                # Time multiple rapid requests - should not have artificial delays
                start_time = time.time()

                # Make 10 rapid requests
                for _ in range(10):
                    await client._make_async_request(["test text"])

                elapsed = time.time() - start_time

                # Should complete quickly without rate limiting delays
                # Allow for some overhead but should be much less than 1 second
                assert (
                    elapsed < 1.0
                ), f"Requests took {elapsed:.2f}s, should be much faster without client throttling"

    @pytest.mark.asyncio
    async def test_voyage_ai_handles_429_with_server_driven_backoff(self):
        """VoyageAI should handle 429 responses with server-driven backoff."""
        config = VoyageAIConfig(max_retries=2, retry_delay=0.1)

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            client = VoyageAIClient(config)

            # Mock 429 response with Retry-After header
            mock_429_response = Mock()
            mock_429_response.status_code = 429
            mock_429_response.headers = {
                "retry-after": "1"
            }  # Server says wait 1 second

            # Mock successful response after retry
            mock_success_response = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "usage": {"total_tokens": 10},
            }

            call_count = 0

            async def mock_post_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First call returns 429
                    raise httpx.HTTPStatusError(
                        "Rate limited", request=Mock(), response=mock_429_response
                    )
                else:
                    # Second call succeeds
                    mock_resp = Mock()
                    mock_resp.json.return_value = mock_success_response
                    mock_resp.raise_for_status.return_value = None
                    return mock_resp

            with patch("httpx.AsyncClient.post", side_effect=mock_post_side_effect):
                with patch("asyncio.sleep") as mock_sleep:
                    # Should succeed after handling 429
                    result = await client._make_async_request(["test text"])

                    # Should have made 2 calls (first 429, second success)
                    assert call_count == 2, "Should retry after 429"

                    # Should have slept based on server's Retry-After header
                    mock_sleep.assert_called_once_with(1)  # Server said wait 1 second

                    # Should return successful result
                    assert result == mock_success_response

    @pytest.mark.asyncio
    async def test_voyage_ai_uses_exponential_backoff_without_retry_after(self):
        """VoyageAI should use exponential backoff when server doesn't provide Retry-After."""
        config = VoyageAIConfig(
            max_retries=2, retry_delay=0.1, exponential_backoff=True
        )

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            client = VoyageAIClient(config)

            # Mock 429 response without Retry-After header
            mock_429_response = Mock()
            mock_429_response.status_code = 429
            mock_429_response.headers = {}  # No Retry-After header

            mock_success_response = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "usage": {"total_tokens": 10},
            }

            call_count = 0

            async def mock_post_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise httpx.HTTPStatusError(
                        "Rate limited", request=Mock(), response=mock_429_response
                    )
                else:
                    mock_resp = Mock()
                    mock_resp.json.return_value = mock_success_response
                    mock_resp.raise_for_status.return_value = None
                    return mock_resp

            with patch("httpx.AsyncClient.post", side_effect=mock_post_side_effect):
                with patch("asyncio.sleep") as mock_sleep:
                    await client._make_async_request(["test text"])

                    # Should use exponential backoff: retry_delay * (2^attempt)
                    # For attempt 0: 0.1 * (2^0) = 0.1
                    mock_sleep.assert_called_once_with(0.1)

    def test_rate_limiter_class_does_not_exist(self):
        """The RateLimiter class should be completely removed."""
        # This test will fail until we remove the RateLimiter class
        with pytest.raises(ImportError):
            from code_indexer.services.voyage_ai import RateLimiter  # noqa: F401

    def test_throttling_status_enum_does_not_exist(self):
        """The ThrottlingStatus enum should be completely removed."""
        # This test will fail until we remove the ThrottlingStatus enum
        with pytest.raises(ImportError):
            from code_indexer.services.vector_calculation_manager import (  # noqa: F401
                ThrottlingStatus,
            )

    def test_no_throttling_related_imports_in_indexers(self):
        """Indexer classes should not import throttling-related code."""
        # Just verify that smart_indexer can be imported without throttling dependencies
        from code_indexer.services.smart_indexer import SmartIndexer

        # Should be able to import without any throttling-related issues
        assert (
            SmartIndexer is not None
        ), "SmartIndexer should be importable without throttling dependencies"

    @pytest.mark.asyncio
    async def test_multiple_concurrent_requests_without_client_coordination(self):
        """Multiple concurrent clients should not try to coordinate rate limiting."""
        config = VoyageAIConfig()

        with patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}):
            # Create multiple clients (simulating multiple indexers)
            clients = [VoyageAIClient(config) for _ in range(3)]

            mock_response = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "usage": {"total_tokens": 10},
            }

            with patch("httpx.AsyncClient.post") as mock_post:
                # Create a proper mock response
                mock_resp = Mock()
                mock_resp.json.return_value = mock_response
                mock_resp.raise_for_status.return_value = None
                mock_post.return_value = mock_resp

                # All clients should make requests concurrently without coordination
                start_time = time.time()

                tasks = []
                for client in clients:
                    # Each client makes 5 requests
                    for _ in range(5):
                        task = asyncio.create_task(
                            client._make_async_request(["test text"])
                        )
                        tasks.append(task)

                # Wait for all requests to complete
                await asyncio.gather(*tasks)

                elapsed = time.time() - start_time

                # Should complete quickly without client-side coordination delays
                assert (
                    elapsed < 2.0
                ), f"Concurrent requests took {elapsed:.2f}s, too slow without client throttling"

                # Should have made all 15 requests (3 clients × 5 requests each)
                assert (
                    mock_post.call_count == 15
                ), f"Expected 15 requests, got {mock_post.call_count}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
