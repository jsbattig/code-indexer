"""Ramping sequence calculation - DEPRECATED MODULE.

This module is deprecated as ramping functionality has been eliminated
with the direct array access architecture. CleanSlotTracker handles
all slot management automatically.

The new architecture uses simple array scanning: for slot_id in range(threadcount+2)
No ramping, no complex display management - just direct array access.
"""

from typing import List

from ..services.clean_slot_tracker import CleanSlotTracker


class RampingSequenceCalculator:
    """DEPRECATED - Ramping is no longer used with direct array access."""

    def __init__(self):
        """Initialize ramping sequence calculator - DEPRECATED."""
        pass

    def calculate_ramping_sequence(
        self, initial_threads: int, files_remaining: int
    ) -> List[int]:
        """DEPRECATED - Direct array access eliminates need for ramping.

        Args:
            initial_threads: Initial number of active threads
            files_remaining: Number of files still to be processed

        Returns:
            List of target thread counts (always returns empty for new architecture)
        """
        # DEPRECATED: Direct array access eliminates ramping complexity
        return []


class LineReductionManager:
    """DEPRECATED - Direct array access eliminates need for line reduction."""

    def __init__(self):
        """Initialize line reduction manager - DEPRECATED."""
        pass

    def reduce_to_count(
        self, slot_tracker: CleanSlotTracker, target_count: int
    ) -> None:
        """DEPRECATED - CleanSlotTracker handles slot management automatically.

        Args:
            slot_tracker: CleanSlotTracker (replaces display parameter)
            target_count: Target number of lines (not used in new architecture)
        """
        # DEPRECATED: CleanSlotTracker handles all slot cleanup automatically
        # No manual line reduction needed with direct array access
        pass
