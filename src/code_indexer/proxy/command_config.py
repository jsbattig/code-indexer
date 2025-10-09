"""Command classification for proxy mode.

This module defines which commands should execute in parallel vs sequentially
in proxy mode. Read-only commands execute in parallel for performance, while
resource-intensive commands (start, stop, uninstall) execute sequentially
to prevent resource contention.
"""

from typing import List

# Commands that execute in parallel (read-only, no resource contention)
PARALLEL_COMMANDS: List[str] = ['query', 'status', 'watch', 'fix-config']

# Commands that execute sequentially (container lifecycle, prevent contention)
SEQUENTIAL_COMMANDS: List[str] = ['start', 'stop', 'uninstall']


def is_parallel_command(command: str) -> bool:
    """Check if command should execute in parallel.

    Args:
        command: CIDX command name

    Returns:
        True if command should execute in parallel, False otherwise
    """
    return command in PARALLEL_COMMANDS


def is_sequential_command(command: str) -> bool:
    """Check if command should execute sequentially.

    Sequential commands (start, stop, uninstall) execute one repository
    at a time to prevent resource contention, port conflicts, and race
    conditions during container lifecycle operations.

    Args:
        command: CIDX command name

    Returns:
        True if command should execute sequentially, False otherwise
    """
    return command in SEQUENTIAL_COMMANDS
