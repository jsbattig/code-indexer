"""Test that client-side throttling has been completely removed.

These tests verify that the system no longer performs client-side rate limiting
and instead relies on server-driven throttling with proper retry mechanisms.
"""

from unittest.mock import Mock, patch
import pytest

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

    def test_vector_calculation_manager_has_no_client_throttling(self):
        """VectorCalculationManager should not have client-side throttling."""
        mock_provider = Mock()
        manager = VectorCalculationManager(mock_provider, thread_count=2)

        # Should not have CLIENT-side throttling attributes
        assert not hasattr(
            manager, "throttling_detection_window"
        ), "Manager should not have throttling_detection_window"
        assert not hasattr(
            manager, "recent_wait_events"
        ), "Manager should not have recent_wait_events"
        assert not hasattr(
            manager, "record_client_wait_time"
        ), "Manager should not have record_client_wait_time method"

        # SERVER-side throttling detection is allowed for monitoring purposes
        # These help detect when the API is throttling us
        assert hasattr(
            manager, "record_server_throttle"
        ), "Manager should have server throttle detection for monitoring"

        # Stats should include server throttling status for display purposes
        stats = manager.get_stats()
        assert hasattr(
            stats, "throttling_status"
        ), "Stats should have server throttling status for display"

    def test_rate_limiter_class_does_not_exist(self):
        """The RateLimiter class should be completely removed."""
        # This test will fail until we remove the RateLimiter class
        with pytest.raises(ImportError):
            from code_indexer.services.voyage_ai import RateLimiter  # noqa: F401

    def test_throttling_status_enum_is_server_only(self):
        """The ThrottlingStatus enum should only have server-side status indicators."""
        from code_indexer.services.vector_calculation_manager import ThrottlingStatus

        # Should only have server-side throttling indicators
        assert hasattr(
            ThrottlingStatus, "FULL_SPEED"
        ), "Should have FULL_SPEED indicator"
        assert hasattr(
            ThrottlingStatus, "SERVER_THROTTLED"
        ), "Should have SERVER_THROTTLED indicator"

        # Should NOT have client-side throttling indicators
        assert not hasattr(
            ThrottlingStatus, "CLIENT_THROTTLED"
        ), "Should not have CLIENT_THROTTLED"

        # Verify the enum only has the expected values
        status_values = set(status.name for status in ThrottlingStatus)
        expected_values = {"FULL_SPEED", "SERVER_THROTTLED"}
        assert (
            status_values == expected_values
        ), f"Expected {expected_values}, got {status_values}"

    def test_no_throttling_related_imports_in_indexers(self):
        """Indexer classes should not import throttling-related code."""
        # Just verify that smart_indexer can be imported without throttling dependencies
        from code_indexer.services.smart_indexer import SmartIndexer

        # Should be able to import without any throttling-related issues
        assert (
            SmartIndexer is not None
        ), "SmartIndexer should be importable without throttling dependencies"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
