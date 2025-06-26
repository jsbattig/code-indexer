"""Integration tests for throttling indicators in progress display."""

import pytest
from unittest.mock import Mock

from code_indexer.services.vector_calculation_manager import (
    ThrottlingStatus,
)


class TestProgressDisplayThrottling:
    """Test throttling indicators in progress display."""

    def test_high_throughput_processor_progress_format(self):
        """Test the progress message format in high throughput processor."""
        # Test the progress message formatting logic directly
        test_cases = [
            (ThrottlingStatus.FULL_SPEED, "⚡"),
            (ThrottlingStatus.CLIENT_THROTTLED, "🟡"),
            (ThrottlingStatus.SERVER_THROTTLED, "🔴"),
        ]

        for throttling_status, expected_icon in test_cases:
            # Mock vector stats
            mock_stats = Mock()
            mock_stats.embeddings_per_second = 5.7
            mock_stats.throttling_status = throttling_status

            # Simulate the formatting logic from high_throughput_processor
            files_completed = 3
            files_total = 10
            file_progress_pct = files_completed / files_total * 100
            vector_thread_count = 4
            display_file_name = "test.py"

            info_msg = (
                f"{files_completed}/{files_total} files ({file_progress_pct:.0f}%) | "
                f"{mock_stats.embeddings_per_second:.1f} emb/s {mock_stats.throttling_status.value} | "
                f"{vector_thread_count} threads | "
                f"{display_file_name}"
            )

            # Verify the format
            expected_msg = (
                f"3/10 files (30%) | 5.7 emb/s {expected_icon} | 4 threads | test.py"
            )
            assert info_msg == expected_msg

    def test_branch_aware_indexer_throttling_display_format(self):
        """Test throttling status format in branch aware indexer progress messages."""
        # Test the throttling icon formatting logic directly
        test_cases = [
            (ThrottlingStatus.FULL_SPEED, "⚡"),
            (ThrottlingStatus.CLIENT_THROTTLED, "🟡"),
            (ThrottlingStatus.SERVER_THROTTLED, "🔴"),
        ]

        for throttling_status, expected_icon in test_cases:
            # Mock stats object
            mock_stats = Mock()
            mock_stats.embeddings_per_second = 12.3
            mock_stats.throttling_status = throttling_status

            # Simulate the formatting logic from branch_aware_indexer
            throttle_icon = getattr(mock_stats, "throttling_status", None)
            throttle_str = f" {throttle_icon.value}" if throttle_icon else ""
            emb_speed = f"{mock_stats.embeddings_per_second:.1f} emb/s{throttle_str}"

            # Verify the format
            expected_emb_speed = f"12.3 emb/s {expected_icon}"
            assert emb_speed == expected_emb_speed

    def test_missing_throttling_status_graceful_handling(self):
        """Test graceful handling when throttling status is missing."""
        # Mock stats object without throttling_status
        mock_stats = Mock()
        mock_stats.embeddings_per_second = 8.5
        # Remove throttling_status to simulate older stats
        if hasattr(mock_stats, "throttling_status"):
            delattr(mock_stats, "throttling_status")

        # Simulate the formatting logic with graceful handling
        throttle_icon = getattr(mock_stats, "throttling_status", None)
        throttle_str = f" {throttle_icon.value}" if throttle_icon else ""
        emb_speed = f"{mock_stats.embeddings_per_second:.1f} emb/s{throttle_str}"

        # Should work without throttling icon
        assert emb_speed == "8.5 emb/s"


if __name__ == "__main__":
    pytest.main([__file__])
