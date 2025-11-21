"""Hint generation for actionable error guidance in proxy mode.

This module provides intelligent hint generation based on error type and command,
helping users understand what went wrong and providing concrete next steps.

Key features:
- Command-specific hint generation
- Error category detection with regex patterns
- Actionable suggestions with concrete commands
- Conversation requirement: Query failures suggest grep as alternative
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ActionableHint:
    """Actionable hint for resolving errors.

    Attributes:
        message: Main hint message describing what to do
        suggested_commands: List of concrete commands to try
        explanation: Optional explanation of why the hint helps
    """

    message: str
    suggested_commands: List[str]
    explanation: Optional[str] = None


class ErrorCategoryDetector:
    """Detect error category from error message text.

    Uses regex patterns to categorize errors into standard types
    for context-aware hint generation.
    """

    # Pre-compiled regex patterns for performance
    ERROR_PATTERNS = {
        "connection": [
            r"cannot connect",
            r"connection refused",
            r"no.*service.*found",
            r"not responding",
        ],
        "port_conflict": [
            r"port.*already in use",
            r"address already in use",
            r"bind.*failed",
        ],
        "permission": [
            r"permission denied",
            r"access denied",
            r"forbidden",
        ],
        "configuration": [
            r"invalid.*config",
            r"missing.*config",
            r"config.*error",
        ],
        "timeout": [
            r"timeout",
            r"timed out",
            r"deadline exceeded",
        ],
    }

    def __init__(self):
        """Initialize detector with compiled regex patterns."""
        # Pre-compile patterns for performance
        self._compiled_patterns = {
            category: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for category, patterns in self.ERROR_PATTERNS.items()
        }

    def detect_category(self, error_text: str) -> str:
        """Detect error category from error message.

        Args:
            error_text: Error message text to analyze

        Returns:
            Error category string (connection, port_conflict, permission,
            configuration, timeout, unknown)
        """
        for category, compiled_patterns in self._compiled_patterns.items():
            for pattern in compiled_patterns:
                if pattern.search(error_text):
                    return str(category)  # Explicit str() for mypy

        return "unknown"


class HintGenerator:
    """Generate contextual hints based on error type and command.

    Provides command-specific, actionable guidance with concrete next steps.
    Special handling for query failures per conversation requirements.
    """

    def __init__(self):
        """Initialize hint generator with error category detector."""
        self.detector = ErrorCategoryDetector()

    def generate_hint(
        self, command: str, error_text: str, repository: str
    ) -> ActionableHint:
        """Generate actionable hint based on context.

        Args:
            command: The command that failed (query, start, stop, etc.)
            error_text: The error message text
            repository: Repository path (relative or absolute)

        Returns:
            ActionableHint with specific guidance for the error
        """
        # Command-specific hint generation
        if command == "query":
            return self._hint_for_query_failure(error_text, repository)
        elif command in ["start", "stop"]:
            return self._hint_for_container_failure(error_text, repository)
        elif command == "status":
            return self._hint_for_status_failure(error_text, repository)
        elif command == "fix-config":
            return self._hint_for_config_failure(error_text, repository)
        else:
            return self._generic_hint(command, repository)

    def _hint_for_query_failure(
        self, error_text: str, repository: str
    ) -> ActionableHint:
        """Generate hint for query command failures.

        CONVERSATION REQUIREMENT: "clearly stating so and hinting claude code
        to use grep or other means to search in that repo"

        Args:
            error_text: Error message from failed query
            repository: Repository path

        Returns:
            ActionableHint suggesting grep and alternative search methods
        """
        # Detect error category for context
        category = self.detector.detect_category(error_text)

        if category == "connection":
            # CONVERSATION CRITICAL: Explicitly suggest grep for connection failures
            return ActionableHint(
                message=f"Use grep or other search tools to search '{repository}' manually",
                suggested_commands=[
                    f"grep -r 'your-search-term' {repository}",
                    f"rg 'your-search-term' {repository}",
                    f"cd {repository} && cidx status",
                ],
                explanation="Vector store service not available - alternative search methods can still find code",
            )
        else:
            # Generic query failure - still suggest grep as fallback
            return ActionableHint(
                message=f"Use grep or other search tools to search '{repository}' manually",
                suggested_commands=[
                    f"grep -r 'your-search-term' {repository}",
                    f"rg 'your-search-term' {repository}",
                    f"cd {repository} && cidx fix-config",
                ],
                explanation="Semantic search unavailable - use text-based search tools",
            )

    def _hint_for_container_failure(
        self, error_text: str, repository: str
    ) -> ActionableHint:
        """Generate hint for container-related failures.

        Args:
            error_text: Error message from failed container operation
            repository: Repository path

        Returns:
            ActionableHint with container troubleshooting guidance
        """
        category = self.detector.detect_category(error_text)

        if category == "port_conflict":
            return ActionableHint(
                message="Check for port conflicts with existing containers",
                suggested_commands=[
                    "docker ps",
                    "podman ps",
                    f"cd {repository} && cidx status",
                    f"cd {repository} && cidx fix-config",
                ],
                explanation="Port already in use - need to resolve conflict",
            )
        elif (
            category == "connection"
            or "docker" in error_text.lower()
            or "podman" in error_text.lower()
        ):
            return ActionableHint(
                message="Ensure Docker/Podman is running and accessible",
                suggested_commands=[
                    "systemctl status docker",
                    "systemctl status podman",
                    "docker ps",
                    "podman ps",
                ],
                explanation="Container runtime not accessible",
            )
        else:
            return ActionableHint(
                message="Navigate to repository and check container status",
                suggested_commands=[
                    f"cd {repository}",
                    "cidx status",
                    "cidx start",
                ],
                explanation="Container operation failed - investigate in repository context",
            )

    def _hint_for_status_failure(
        self, error_text: str, repository: str
    ) -> ActionableHint:
        """Generate hint for status check failures.

        Args:
            error_text: Error message from failed status check
            repository: Repository path

        Returns:
            ActionableHint with status troubleshooting guidance
        """
        return ActionableHint(
            message=f"Navigate to '{repository}' to investigate configuration",
            suggested_commands=[
                f"cd {repository}",
                "cidx fix-config",
                "cidx start",
            ],
            explanation="Status check failed - may need configuration repair",
        )

    def _hint_for_config_failure(
        self, error_text: str, repository: str
    ) -> ActionableHint:
        """Generate hint for configuration failures.

        Args:
            error_text: Error message from failed config operation
            repository: Repository path

        Returns:
            ActionableHint with configuration repair guidance
        """
        return ActionableHint(
            message=f"Manually inspect and repair configuration in '{repository}'",
            suggested_commands=[
                f"cd {repository}",
                "cat .code-indexer/config.json",
                "cidx init --force",
            ],
            explanation="Configuration repair failed - manual intervention needed",
        )

    def _generic_hint(self, command: str, repository: str) -> ActionableHint:
        """Generate generic hint when specific hint not available.

        Args:
            command: Command that failed
            repository: Repository path

        Returns:
            ActionableHint with generic guidance
        """
        return ActionableHint(
            message=f"Navigate to '{repository}' and run command directly",
            suggested_commands=[
                f"cd {repository}",
                f"cidx {command}",
            ],
            explanation="Direct execution in repository context may provide more details",
        )
