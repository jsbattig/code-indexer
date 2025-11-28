"""Optimized CLI entry point with fast daemon delegation path.

This module provides a lightweight entry point that:
1. Quickly detects daemon mode (5ms) using stdlib only
2. Routes to fast path for daemon-delegatable commands (<150ms startup)
3. Falls back to full CLI for non-delegatable commands

Performance targets:
- Daemon mode startup: <150ms (vs current 1,200ms)
- Standalone mode: ~1,200ms (no regression)
"""

import json
import sys
from pathlib import Path
from typing import Tuple, Optional


def quick_daemon_check() -> Tuple[bool, Optional[Path]]:
    """Check if daemon mode enabled WITHOUT heavy imports (5ms).

    Walks up directory tree from current working directory to find
    .code-indexer/config.json and check daemon.enabled flag.

    Returns:
        Tuple of (is_daemon_enabled, config_path)
        - is_daemon_enabled: True if daemon.enabled: true in config
        - config_path: Path to config.json if found, None otherwise
    """
    current = Path.cwd()

    # Walk up directory tree (like git does)
    while current != current.parent:
        config_path = current / ".code-indexer" / "config.json"

        if config_path.exists():
            try:
                # Use stdlib json for fast parsing
                with open(config_path) as f:
                    config = json.load(f)
                    daemon_config = config.get("daemon") or {}
                    if daemon_config.get("enabled"):
                        return True, config_path
            except (json.JSONDecodeError, IOError, KeyError):
                # Malformed config - treat as daemon disabled
                pass

        current = current.parent

    return False, None


def is_delegatable_command(command: str, args: list) -> bool:
    """Check if command can be delegated to daemon.

    Commands that can be delegated:
    - query: Semantic/FTS search (EXCEPT temporal queries with --time-range)
    - index: Indexing operations
    - watch: Watch mode
    - clean/clean-data: Cleanup operations
    - start/stop: Daemon lifecycle
    - watch-stop: Stop watch mode
    - status: Status queries

    Commands that CANNOT be delegated:
    - init: Initial setup
    - fix-config: Config repair
    - reconcile: Non-git indexing
    - sync: Remote operations
    - list-repos: Server operations
    - query --time-range: Temporal queries (daemon doesn't support this yet)

    Args:
        command: Command name (first argument after 'cidx')
        args: Full command line arguments

    Returns:
        True if command can be delegated to daemon
    """
    delegatable = {
        "query",
        "index",
        "watch",
        "clean",
        "clean-data",
        # "status" removed - needs full CLI for Rich table formatting
        # "start" removed - can't delegate starting daemon to non-existent daemon!
        "stop",
        "watch-stop",
    }

    # Special case: query with --time-range or --time-range-all cannot be delegated (temporal queries)
    if command == "query" and ("--time-range" in args or "--time-range-all" in args):
        return False

    return command in delegatable


def main() -> int:
    """Optimized entry point with daemon fast path.

    Routes commands to fast path (daemon delegation) or slow path (full CLI)
    based on daemon configuration and command type.

    Fast path (daemon enabled + delegatable command):
    - Import only cli_daemon_fast (~100ms)
    - Delegate to daemon via RPC
    - Total startup: <150ms

    Slow path (daemon disabled OR non-delegatable command):
    - Import full CLI (~1200ms)
    - Execute command normally
    - Total startup: ~1200ms (no regression)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Check for help flags FIRST (before daemon delegation)
    if "--help" in sys.argv or "-h" in sys.argv:
        # Always use full CLI for help (has all Click help text)
        from .cli import cli

        try:
            cli(obj={})
            return 0
        except KeyboardInterrupt:
            from rich.console import Console

            Console().print("\n❌ Interrupted by user", style="red")
            return 1

    # Quick check for daemon mode (5ms, no heavy imports)
    is_daemon_mode, config_path = quick_daemon_check()

    # Detect if this is a daemon-delegatable command
    command = sys.argv[1] if len(sys.argv) > 1 else None
    is_delegatable = command and is_delegatable_command(command, sys.argv)

    if is_daemon_mode and is_delegatable:
        # FAST PATH: Daemon delegation (~100ms startup)
        # Import ONLY what's needed for delegation
        try:
            from .cli_daemon_fast import execute_via_daemon

            return execute_via_daemon(sys.argv, config_path)
        except ConnectionRefusedError:
            # Expected exception for --repo queries (need full CLI)
            # Fall through to slow path silently (no warning messages)
            pass
        except Exception as e:
            # Unexpected error - show warning and fall through
            from rich.console import Console

            console = Console()
            console.print(f"[yellow]Daemon unavailable: {e}[/yellow]")
            console.print("[dim]Falling back to standalone mode...[/dim]")
            # Fall through to slow path

    # SLOW PATH: Full CLI (~1200ms startup, existing behavior)
    from .cli import cli

    try:
        cli(obj={})
        return 0
    except KeyboardInterrupt:
        from rich.console import Console

        Console().print("\n❌ Interrupted by user", style="red")
        return 1
    except Exception as e:
        from rich.console import Console

        Console().print(f"❌ Unexpected error: {e}", style="red", markup=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())
