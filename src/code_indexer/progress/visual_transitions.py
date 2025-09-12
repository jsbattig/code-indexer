"""Visual transition effects for smooth ramping down.

This module provides smooth visual transitions for line removal
to avoid jarring display changes during ramping down.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class TransitionStep:
    """Single step in a visual transition."""

    opacity: float
    duration_seconds: float


@dataclass
class TransitionEffect:
    """Complete transition effect with multiple steps."""

    steps: List[TransitionStep]
    total_duration_seconds: float


class SmoothTransitionManager:
    """Manages smooth visual transitions during ramping."""

    def __init__(self):
        """Initialize smooth transition manager."""
        pass

    def create_line_removal_transition(
        self, lines_to_remove: int, remaining_lines: int
    ) -> TransitionEffect:
        """Create a smooth transition effect for line removal.

        Args:
            lines_to_remove: Number of lines being removed
            remaining_lines: Number of lines remaining after removal

        Returns:
            Transition effect with multiple steps
        """
        # Create fade-out transition steps
        steps = []

        # Gradual fade-out over 3 steps
        fade_steps = [
            TransitionStep(opacity=1.0, duration_seconds=0.2),
            TransitionStep(opacity=0.6, duration_seconds=0.3),
            TransitionStep(opacity=0.2, duration_seconds=0.3),
            TransitionStep(opacity=0.0, duration_seconds=0.2),
        ]

        steps.extend(fade_steps)

        # Calculate total duration
        total_duration = sum(step.duration_seconds for step in steps)

        return TransitionEffect(steps=steps, total_duration_seconds=total_duration)
