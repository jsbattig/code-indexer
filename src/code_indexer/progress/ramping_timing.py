"""Ramping timing management and smooth transitions.

This module handles the timing aspects of ramping down behavior:
- Control timing between ramping steps
- Adaptive timing based on processing context
- Smooth visual transitions
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TimingConfig:
    """Configuration for ramping timing."""

    min_delay_seconds: float
    max_delay_seconds: float


@dataclass
class ContextualTiming:
    """Timing configuration adapted to processing context."""

    delay_seconds: float
    reason: str


class RampingTimingManager:
    """Manages timing for ramping down operations."""

    def __init__(self) -> None:
        """Initialize ramping timing manager."""
        self.default_config = TimingConfig(min_delay_seconds=0.5, max_delay_seconds=2.0)
        self.current_config: TimingConfig = self.default_config

    def get_default_timing_config(self) -> TimingConfig:
        """Get default timing configuration.

        Returns:
            Default timing configuration
        """
        return TimingConfig(min_delay_seconds=0.5, max_delay_seconds=2.0)

    def get_timing_config(self) -> TimingConfig:
        """Get current timing configuration.

        Returns:
            Current timing configuration
        """
        return self.current_config

    def set_timing_config(self, min_delay: float, max_delay: float) -> None:
        """Set timing configuration.

        Args:
            min_delay: Minimum delay between reductions
            max_delay: Maximum delay between reductions
        """
        self.current_config = TimingConfig(
            min_delay_seconds=min_delay, max_delay_seconds=max_delay
        )

    def calculate_timing_for_context(
        self,
        avg_file_size_kb: Optional[float] = None,
        avg_processing_seconds: Optional[float] = None,
        completion_scenario: bool = False,
    ) -> ContextualTiming:
        """Calculate timing adapted to processing context.

        Args:
            avg_file_size_kb: Average file size in KB
            avg_processing_seconds: Average processing time per file
            completion_scenario: True if this is a completion scenario

        Returns:
            Contextual timing configuration
        """
        if completion_scenario:
            return ContextualTiming(
                delay_seconds=0.1, reason="immediate ramping for completion"
            )

        if avg_file_size_kb is not None and avg_processing_seconds is not None:
            # Fast ramping for small, quick files
            if avg_file_size_kb < 10.0 and avg_processing_seconds < 2.0:
                return ContextualTiming(
                    delay_seconds=0.5, reason="fast ramping for small files"
                )

            # Slower ramping for large, slow files
            if avg_file_size_kb > 100.0 and avg_processing_seconds > 10.0:
                return ContextualTiming(
                    delay_seconds=1.5, reason="slower ramping for large files"
                )

        # Default timing
        return ContextualTiming(delay_seconds=1.0, reason="default ramping timing")
