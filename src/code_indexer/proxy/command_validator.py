"""Command validation for proxy mode.

This module validates that only supported commands execute in proxy mode
and provides clear error messages for unsupported commands.

Supported proxy commands (hardcoded as per Story 2.4):
- query: Search across all repositories
- status: Check status of all repositories
- start: Start services in all repositories (sequential)
- stop: Stop services in all repositories (sequential)
- uninstall: Uninstall services from all repositories (sequential)
- fix-config: Fix configuration in all repositories
- watch: Watch for changes in all repositories

All other commands (init, index, reconcile, etc.) are not supported in proxy mode.
"""

from typing import FrozenSet

# Hardcoded supported proxy commands (as per conversation)
# Using frozenset for immutability and O(1) lookup
PROXIED_COMMANDS: FrozenSet[str] = frozenset(
    {"query", "status", "start", "stop", "uninstall", "fix-config", "watch"}
)


class UnsupportedProxyCommandError(Exception):
    """Raised when unsupported command attempted in proxy mode.

    Attributes:
        command: The unsupported command that was attempted
        message: Detailed error message with guidance
    """

    def __init__(self, command: str):
        """Initialize with command name and generate error message.

        Args:
            command: The unsupported command that was attempted
        """
        self.command = command
        self.message = format_unsupported_command_error(command)
        super().__init__(self.message)


def is_supported_proxy_command(command: str) -> bool:
    """Check if command is supported in proxy mode.

    Args:
        command: CIDX command name (case-sensitive)

    Returns:
        True if command is supported in proxy mode, False otherwise
    """
    return command in PROXIED_COMMANDS


def validate_proxy_command(command: str) -> None:
    """Validate that command is supported in proxy mode.

    This function should be called BEFORE any subprocess execution
    to prevent attempting unsupported commands.

    Args:
        command: CIDX command name to validate

    Raises:
        UnsupportedProxyCommandError: If command is not supported in proxy mode
    """
    if not is_supported_proxy_command(command):
        raise UnsupportedProxyCommandError(command)


def format_unsupported_command_error(command: str) -> str:
    """Format error message for unsupported command.

    Generates a clear, actionable error message that:
    - States the command is not supported in proxy mode
    - Lists all supported proxy commands
    - Shows how to execute the command in a specific repository

    Args:
        command: The unsupported command that was attempted

    Returns:
        Formatted error message string
    """
    # Command descriptions for supported commands
    command_descriptions = {
        "query": "Search across all repositories",
        "status": "Check status of all repositories",
        "start": "Start services in all repositories",
        "stop": "Stop services in all repositories",
        "uninstall": "Uninstall services from all repositories",
        "fix-config": "Fix configuration in all repositories",
        "watch": "Watch for changes in all repositories",
    }

    lines = [
        f"ERROR: Command '{command}' is not supported in proxy mode.",
        "",
        "Supported proxy commands:",
    ]

    # List supported commands alphabetically with descriptions
    for cmd in sorted(PROXIED_COMMANDS):
        desc = command_descriptions.get(cmd, "")
        lines.append(f"  • {cmd:12} - {desc}")

    lines.extend(
        [
            "",
            f"To run '{command}', navigate to a specific repository:",
            "  cd <repository-path>",
            f"  cidx {command}",
        ]
    )

    return "\n".join(lines)
