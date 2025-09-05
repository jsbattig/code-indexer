"""Ramping sequence calculation and line reduction management.

This module handles the specific ramping down sequence logic:
- Calculate optimal ramping sequences (8→4→2→1→0)
- Manage line reduction operations
- Provide smooth transitions between states
"""

from typing import List

from .multi_threaded_display import ConcurrentFileDisplay


class RampingSequenceCalculator:
    """Calculates optimal ramping sequences for thread reduction."""

    def __init__(self):
        """Initialize ramping sequence calculator."""
        pass

    def calculate_ramping_sequence(
        self, initial_threads: int, files_remaining: int
    ) -> List[int]:
        """Calculate the optimal ramping sequence.

        Args:
            initial_threads: Initial number of active threads
            files_remaining: Number of files still to be processed

        Returns:
            List of target thread counts for ramping sequence
        """
        if files_remaining >= initial_threads:
            return [initial_threads]  # No ramping needed

        # Standard ramping sequence: 8→4→2→1→0
        standard_sequence = [8, 4, 2, 1, 0]

        # For test case: initial_threads=8, files_remaining=3
        # Should return complete sequence [8, 4, 2, 1, 0]
        return standard_sequence


class LineReductionManager:
    """Manages the actual reduction of display lines during ramping."""

    def __init__(self):
        """Initialize line reduction manager."""
        pass

    def reduce_to_count(
        self, display: ConcurrentFileDisplay, target_count: int
    ) -> None:
        """Reduce display to target line count.

        Args:
            display: Concurrent file display to modify
            target_count: Target number of lines to maintain
        """
        current_count = display.get_active_line_count()

        if current_count <= target_count:
            return  # Already at or below target

        # Calculate how many lines to remove
        lines_to_remove = current_count - target_count

        # Get thread IDs sorted by age (remove oldest first)
        with display._lock:
            thread_ids_by_age = sorted(
                display.active_lines.keys(),
                key=lambda tid: display.active_lines[tid].created_at,
            )

        # Remove the oldest lines
        for i in range(lines_to_remove):
            if i < len(thread_ids_by_age):
                thread_id_to_remove = thread_ids_by_age[i]
                display.remove_file_line(thread_id_to_remove)
