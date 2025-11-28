"""Disabled Command Handling for CIDX CLI.

Provides command compatibility checking, mode-aware error handling, and user guidance
for commands that are not available in the current operational mode.

This module implements Story 2: As a CIDX user in remote mode, I want clear error messages
when I try to use commands that aren't compatible with remote mode.
"""

import functools
import logging
from pathlib import Path
from typing import List, Literal, Dict, Any, Optional

from click import ClickException

from code_indexer.mode_detection.command_mode_detector import (
    CommandModeDetector,
    find_project_root,
)

logger = logging.getLogger(__name__)

# Command compatibility matrix defining which commands work in which modes
COMMAND_COMPATIBILITY: Dict[str, Dict[str, bool]] = {
    # Always available commands - help and version work in all scenarios
    "help": {"local": True, "remote": True, "proxy": True, "uninitialized": True},
    "version": {"local": True, "remote": True, "proxy": True, "uninitialized": True},
    # Core functionality commands - work in initialized modes only
    "query": {"local": True, "remote": True, "proxy": True, "uninitialized": False},
    "ask": {
        "local": True,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },  # Claude integration
    # Initialization commands - always available since they set up the system
    "init": {"local": True, "remote": True, "proxy": True, "uninitialized": True},
    # Local-only infrastructure commands - require local container management
    "start": {"local": True, "remote": False, "proxy": True, "uninitialized": False},
    "stop": {"local": True, "remote": False, "proxy": True, "uninitialized": False},
    "index": {"local": True, "remote": False, "proxy": False, "uninitialized": False},
    "watch": {"local": True, "remote": False, "proxy": True, "uninitialized": False},
    # Mode-adapted commands - different behavior per mode but available in both
    "status": {"local": True, "remote": True, "proxy": True, "uninitialized": False},
    "uninstall": {"local": True, "remote": True, "proxy": True, "uninitialized": False},
    "optimize": {
        "local": True,
        "remote": False,
        "proxy": False,
        "uninitialized": False,
    },  # Local optimization only
    "force-flush": {
        "local": True,
        "remote": False,
        "proxy": False,
        "uninitialized": False,
    },  # Local DB operations
    "clean": {
        "local": True,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },  # Clear vectors from collection
    "teach-ai": {
        "local": True,
        "remote": True,
        "proxy": True,
        "uninitialized": True,
    },  # Generate AI platform instruction files
    "clean-data": {
        "local": True,
        "remote": False,
        "proxy": False,
        "uninitialized": False,
    },  # Local cleanup
    "fix-config": {
        "local": True,
        "remote": True,
        "proxy": True,
        "uninitialized": True,
    },  # Config fixes always available
    "setup-global-registry": {
        "local": True,
        "remote": False,
        "proxy": False,
        "uninitialized": True,
    },  # Local registry
    "install-server": {
        "local": True,
        "remote": False,
        "proxy": False,
        "uninitialized": True,
    },  # Server installation
    # Server management commands - local only since they manage local server instances
    "server": {"local": True, "remote": False, "proxy": False, "uninitialized": True},
    # Authentication commands - remote only since they manage remote server credentials
    "auth": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
    # Repository synchronization - remote only since it syncs with remote server
    "sync": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
    # Job management commands - remote only since they manage server-side background jobs
    "list_jobs": {
        "local": False,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },
    "jobs": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
    # Admin commands - remote only since they manage server-side administration
    "admin": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
    "admin_group": {
        "local": False,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },
    "admin_users": {
        "local": False,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },
    "admin_repos": {
        "local": False,
        "remote": True,
        "proxy": False,
        "uninitialized": False,
    },
    # Repository management commands - remote only since they manage server-side repositories
    "repos": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
    # System health commands - remote only since they check server-side system health
    "system": {"local": False, "remote": True, "proxy": False, "uninitialized": False},
}

# Command alternatives mapping for helpful error messages
COMMAND_ALTERNATIVES: Dict[str, str] = {
    "start": "Remote mode uses server-side containers. Use 'cidx query' directly - no local startup needed.",
    "stop": "Remote mode doesn't manage local containers. Server containers are always available.",
    "index": "Remote mode uses server-side indexing. Repository linking provides access to indexed content automatically.",
    "watch": "Remote mode doesn't support file watching. Query server indexes directly - they stay current automatically.",
    "optimize": "Remote mode uses server-side optimization. Database performance is managed by the remote server.",
    "force-flush": "Remote mode database operations are managed server-side. Contact your server administrator if needed.",
    "clean-data": "Remote mode data management is handled server-side. Use repository unlinking if you need to remove access.",
    "setup-global-registry": "Remote mode doesn't use local port registries. Server configuration handles resource management.",
    "install-server": "Remote mode connects to existing servers. Use 'cidx init' to configure remote server connection.",
    "server": "Remote mode doesn't manage local server instances. You're already connected to a remote server.",
    "list_jobs": "Local mode doesn't have background job management. Use remote mode to access server-side job monitoring capabilities.",
    "jobs": "Local mode doesn't have background job management. Use remote mode to access server-side job monitoring capabilities.",
    "admin": "Local mode doesn't have admin functions. Use remote mode to access server administration capabilities.",
    "admin_group": "Local mode doesn't have admin functions. Use remote mode to access server administration capabilities.",
    "admin_users": "Local mode doesn't have user management. Use remote mode to access server user administration.",
    "admin_repos": "Local mode doesn't have repository administration. Use remote mode to access server repository management.",
    "repos": "Local mode doesn't have repository management. Use remote mode to link and manage repositories on the server.",
    "system": "Local mode doesn't have system health commands. Use remote mode to access server system monitoring.",
}


class DisabledCommandError(ClickException):
    """Exception for commands disabled in current mode.

    Provides educational error messages that explain why commands are disabled
    and suggest appropriate alternatives for the current operational mode.
    """

    def __init__(self, command_name: str, current_mode: str, allowed_modes: List[str]):
        """Initialize disabled command error with contextual information.

        Args:
            command_name: Name of the command that was attempted
            current_mode: Current operational mode (local, remote, uninitialized)
            allowed_modes: List of modes where this command is available
        """
        self.command_name = command_name
        self.current_mode = current_mode
        self.allowed_modes = allowed_modes

        # Generate comprehensive error message
        message = self._generate_error_message()
        super().__init__(message)

    def _generate_error_message(self) -> str:
        """Generate a comprehensive error message with context and alternatives.

        Returns:
            Formatted error message explaining the restriction and providing guidance
        """
        # Mode context explanations
        mode_contexts = {
            "remote": "remote mode connects to server-side infrastructure",
            "local": "local mode manages containers and services on this machine",
            "proxy": "proxy mode coordinates operations across multiple discovered repositories",
            "uninitialized": "no configuration found - project needs initialization",
        }

        current_context = mode_contexts.get(
            self.current_mode, f"'{self.current_mode}' mode"
        )
        allowed_context = ", ".join([f"'{mode}'" for mode in self.allowed_modes])

        # Base error message with architectural context
        message_parts = [
            f"❌ Command '{self.command_name}' is not available in {current_context}.",
            f"This command requires: {allowed_context} mode(s).",
        ]

        # Add mode-specific explanation
        if self.current_mode == "remote":
            message_parts.append(
                "🔄 Remote mode uses server-side processing - local container management is not needed."
            )
        elif self.current_mode == "uninitialized":
            message_parts.append(
                "⚠️  Project is not initialized. Run 'cidx init' to set up local or remote mode."
            )

        # Add specific alternative if available
        if self.command_name in COMMAND_ALTERNATIVES:
            alternative = COMMAND_ALTERNATIVES[self.command_name]
            message_parts.append(f"💡 Alternative: {alternative}")

        # Add educational context about mode differences
        if self.current_mode == "remote" and "local" in self.allowed_modes:
            message_parts.append(
                "📚 Remote mode provides the same functionality through server-side processing. "
                "Local commands manage containers that aren't needed when using a remote server."
            )

        return "\n".join(message_parts)


def detect_current_mode() -> Literal["local", "remote", "proxy", "uninitialized"]:
    """Detect current operational mode using project root discovery.

    Integrates with CommandModeDetector from Story 1 to provide consistent
    mode detection across the CLI system.

    Returns:
        Current operational mode: "local", "remote", "proxy", or "uninitialized"
    """
    try:
        # Find project root using the same logic as other CLI components
        project_root = find_project_root(Path.cwd())

        # Use CommandModeDetector to determine mode
        detector = CommandModeDetector(project_root)
        mode: Literal["local", "remote", "proxy", "uninitialized"] = (
            detector.detect_mode()
        )
        return mode

    except Exception as e:
        logger.warning(f"Mode detection failed, assuming uninitialized: {e}")
        return "uninitialized"


def require_mode(*allowed_modes: str):
    """Decorator to enforce command mode compatibility.

    Checks current operational mode against allowed modes and raises
    DisabledCommandError if the command is not compatible with the current mode.

    Args:
        *allowed_modes: Variable arguments specifying which modes allow this command

    Returns:
        Decorated function that enforces mode requirements

    Raises:
        DisabledCommandError: If current mode is not in allowed_modes
    """

    def decorator(command_func):
        @functools.wraps(command_func)
        def wrapper(*args, **kwargs):
            # Story #521: Allow --repo flag to bypass mode check for global repo queries
            # When querying a global repo, mode detection is not needed because
            # the repo path is resolved from the global alias
            if kwargs.get("repo"):
                # Global repo query - bypass mode check
                return command_func(*args, **kwargs)

            current_mode = detect_current_mode()

            if current_mode not in allowed_modes:
                # Extract command name from function
                command_name = getattr(command_func, "__name__", "unknown")

                # Remove CLI naming prefixes if present
                if command_name.startswith("cmd_"):
                    command_name = command_name[4:]

                raise DisabledCommandError(
                    command_name=command_name,
                    current_mode=current_mode,
                    allowed_modes=list(allowed_modes),
                )

            return command_func(*args, **kwargs)

        return wrapper

    return decorator


def check_command_compatibility(command_name: str, mode: Optional[str] = None) -> bool:
    """Check if a command is compatible with the specified or current mode.

    Args:
        command_name: Name of the command to check
        mode: Mode to check against, or None to use current mode

    Returns:
        True if command is compatible with the mode, False otherwise
    """
    if mode is None:
        mode = detect_current_mode()

    if command_name not in COMMAND_COMPATIBILITY:
        logger.warning(f"Unknown command '{command_name}' not in compatibility matrix")
        return False

    return COMMAND_COMPATIBILITY[command_name].get(mode, False)


def get_disabled_commands_for_mode(mode: str) -> List[str]:
    """Get list of commands that are disabled in the specified mode.

    Args:
        mode: Operational mode to check

    Returns:
        List of command names that are disabled in the specified mode
    """
    disabled_commands = []

    for command_name, compatibility in COMMAND_COMPATIBILITY.items():
        if not compatibility.get(mode, False):
            disabled_commands.append(command_name)

    return disabled_commands


def get_available_commands_for_mode(mode: str) -> List[str]:
    """Get list of commands that are available in the specified mode.

    Args:
        mode: Operational mode to check

    Returns:
        List of command names that are available in the specified mode
    """
    available_commands = []

    for command_name, compatibility in COMMAND_COMPATIBILITY.items():
        if compatibility.get(mode, False):
            available_commands.append(command_name)

    return available_commands


def get_command_mode_icons(command_name: str) -> str:
    """Get mode indicator icons with proper column alignment.

    Args:
        command_name: Name of the command to get icons for

    Returns:
        String with aligned mode icons accounting for emoji display width
        Format: 🌐 (remote) 🐳 (local) 🔗 (proxy)
    """
    compatibility = COMMAND_COMPATIBILITY.get(command_name, {})
    remote_support = compatibility.get("remote", False)
    local_support = compatibility.get("local", False)
    proxy_support = compatibility.get("proxy", False)

    # Build icon string - each emoji takes 2 visual columns
    # Always show in order: Remote, Local, Proxy
    icons = ""
    icons += "🌐" if remote_support else "  "
    icons += "🐳" if local_support else "  "
    icons += "🔗" if proxy_support else "  "

    return icons


def validate_command_compatibility_matrix() -> Dict[str, Any]:
    """Validate the command compatibility matrix for consistency and completeness.

    Returns:
        Dictionary with validation results including any issues found
    """
    validation_results: Dict[str, Any] = {
        "valid": True,
        "issues": [],
        "stats": {
            "total_commands": len(COMMAND_COMPATIBILITY),
            "always_available": 0,
            "local_only": 0,
            "remote_compatible": 0,
            "proxy_compatible": 0,
            "initialization_required": 0,
        },
    }

    required_modes = ["local", "remote", "proxy", "uninitialized"]

    for command_name, compatibility in COMMAND_COMPATIBILITY.items():
        # Check all required modes are defined
        for mode in required_modes:
            if mode not in compatibility:
                validation_results["valid"] = False
                validation_results["issues"].append(
                    f"Command '{command_name}' missing mode definition for '{mode}'"
                )

        # Update statistics
        if all(compatibility.get(mode, False) for mode in required_modes):
            validation_results["stats"]["always_available"] += 1

        if compatibility.get("local", False) and not compatibility.get("remote", False):
            validation_results["stats"]["local_only"] += 1

        if compatibility.get("remote", False):
            validation_results["stats"]["remote_compatible"] += 1

        if compatibility.get("proxy", False):
            validation_results["stats"]["proxy_compatible"] += 1

        if not compatibility.get("uninitialized", False):
            validation_results["stats"]["initialization_required"] += 1

    return validation_results
