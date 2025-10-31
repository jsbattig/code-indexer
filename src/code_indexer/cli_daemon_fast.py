"""Lightweight daemon delegation - minimal imports for fast startup.

This module provides the fast path for daemon-mode queries:
- Imports only rpyc (~50ms) + rich (~40ms)
- Minimal argument parsing (no Click)
- Direct RPC calls to daemon
- Simple result display

Target: <150ms total startup for daemon-mode queries
"""
from pathlib import Path
from typing import List, Dict, Any, Optional

# ONLY import what's absolutely needed for daemon delegation
from rpyc.utils.factory import unix_connect  # ~50ms
from rich.console import Console              # ~40ms


def get_socket_path(config_path: Path) -> Path:
    """Get daemon socket path from config path.

    Args:
        config_path: Path to .code-indexer/config.json

    Returns:
        Path to daemon.sock in same directory
    """
    return config_path.parent / "daemon.sock"


def parse_query_args(args: List[str]) -> Dict[str, Any]:
    """Parse query arguments without Click (faster).

    Args:
        args: Command arguments after 'query' (e.g., ['test', '--fts', '--limit', '20'])

    Returns:
        Dict with parsed arguments:
        - query_text: Search query
        - is_fts: FTS mode enabled
        - is_semantic: Semantic mode enabled
        - limit: Result limit
        - filters: Language/path filters
    """
    result: Dict[str, Any] = {
        'query_text': '',
        'is_fts': False,
        'is_semantic': False,
        'limit': 10,
        'filters': {}
    }

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith('--'):
            # Flag arguments
            if arg == '--fts':
                result['is_fts'] = True
            elif arg == '--semantic':
                result['is_semantic'] = True
            elif arg == '--limit' and i + 1 < len(args):
                result['limit'] = int(args[i + 1])
                i += 1
            elif arg == '--language' and i + 1 < len(args):
                result['filters']['language'] = args[i + 1]
                i += 1
            elif arg == '--path-filter' and i + 1 < len(args):
                result['filters']['path_filter'] = args[i + 1]
                i += 1
            elif arg == '--exclude-language' and i + 1 < len(args):
                result['filters']['exclude_language'] = args[i + 1]
                i += 1
            elif arg == '--exclude-path' and i + 1 < len(args):
                result['filters']['exclude_path'] = args[i + 1]
                i += 1
            # Skip other flags for now
        else:
            # Query text (first non-flag argument)
            if not result['query_text']:
                result['query_text'] = arg

        i += 1

    # Default: if no mode specified, use semantic
    if not result['is_fts'] and not result['is_semantic']:
        result['is_semantic'] = True

    return result


def _display_results(results: Any, console: Console, timing_info: Optional[Dict[str, Any]] = None) -> None:
    """Display query results by delegating to shared display function (DRY principle).

    CRITICAL: This function calls the EXISTING display code from cli.py instead of
    duplicating 107 lines. This ensures identical display in both daemon and standalone modes.

    Args:
        results: Query results from daemon (list of dicts with score/payload)
        console: Rich console for output
        timing_info: Optional timing information for performance display
    """
    # Import shared display function (SINGLE source of truth)
    from .cli import _display_semantic_results

    # Delegate to shared function (NO code duplication)
    _display_semantic_results(
        results=results,
        console=console,
        quiet=False,  # Daemon mode always shows full output
        timing_info=timing_info,
        current_display_branch=None,  # Auto-detect in shared function
    )


def execute_via_daemon(argv: List[str], config_path: Path) -> int:
    """Execute command via daemon with minimal imports.

    Args:
        argv: Command line arguments (e.g., ['cidx', 'query', 'test', '--fts'])
        config_path: Path to .code-indexer/config.json

    Returns:
        Exit code (0 for success, non-zero for error)

    Raises:
        ConnectionRefusedError: If daemon is not running
        Exception: For other daemon communication errors
    """
    console = Console()

    command = argv[1] if len(argv) > 1 else ""
    args = argv[2:] if len(argv) > 2 else []

    # Get socket path
    socket_path = get_socket_path(config_path)

    # Connect to daemon
    try:
        conn = unix_connect(str(socket_path))
    except ConnectionRefusedError:
        console.print("[red]❌ Daemon not running[/red]")
        console.print("[dim]Run 'cidx start' to start daemon[/dim]")
        raise

    try:
        # Route based on command
        if command == "query":
            # Parse query arguments
            parsed = parse_query_args(args)

            query_text = parsed['query_text']
            is_fts = parsed['is_fts']
            is_semantic = parsed['is_semantic']
            limit = parsed['limit']
            filters = parsed['filters']

            # DISPLAY QUERY CONTEXT (identical to standalone mode)
            project_root = Path.cwd()
            console.print(f"🔍 Executing local query in: {project_root}", style="dim")

            # Get current branch for context
            try:
                import subprocess
                git_result = subprocess.run(
                    ["git", "symbolic-ref", "--short", "HEAD"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if git_result.returncode == 0:
                    current_branch = git_result.stdout.strip()
                    console.print(f"🌿 Current branch: {current_branch}", style="dim")
            except Exception:
                pass

            console.print(f"🔍 Searching for: '{query_text}'", style="dim")
            if filters.get('language'):
                console.print(f"🏷️  Language filter: {filters['language']}", style="dim")
            if filters.get('path_filter'):
                console.print(f"📁 Path filter: {filters['path_filter']}", style="dim")
            console.print(f"📊 Limit: {limit}", style="dim")

            # Build options dict for daemon
            options = {
                'limit': limit,
                **filters
            }

            # Execute query via daemon RPC
            if is_fts and is_semantic:
                # Hybrid search
                response = conn.root.exposed_query_hybrid(
                    str(Path.cwd()), query_text, **options
                )
                result = response  # Hybrid returns list directly (for now)
                timing_info = None
            elif is_fts:
                # FTS only
                response = conn.root.exposed_query_fts(
                    str(Path.cwd()), query_text, **options
                )
                result = response  # FTS returns list directly (for now)
                timing_info = None
            else:
                # Semantic only
                response = conn.root.exposed_query(
                    str(Path.cwd()), query_text, limit, **filters
                )
                # CRITICAL FIX: Parse response dict with results and timing
                result = response.get("results", [])
                timing_info = response.get("timing", None)

            # Display results with full formatting including timing
            _display_results(result, console, timing_info=timing_info)

        elif command == "start":
            # Start daemon (should already be handled by cli_daemon_lifecycle)
            from . import cli_daemon_lifecycle
            return cli_daemon_lifecycle.start_daemon_command()

        elif command == "stop":
            # Stop daemon
            from . import cli_daemon_lifecycle
            return cli_daemon_lifecycle.stop_daemon_command()

        elif command == "index":
            # Index command with progress callbacks
            from . import cli_daemon_delegation

            # Parse flags
            force_reindex = "--clear" in args
            enable_fts = "--fts" in args

            # Get daemon config from connection
            # We need to get config for retry delays
            from .config import ConfigManager

            try:
                config_manager = ConfigManager.create_with_backtrack(Path.cwd())
                daemon_config = config_manager.get_daemon_config()
            except Exception:
                daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

            # Close the connection before calling delegation (it will create its own)
            conn.close()

            # Delegate to index via daemon
            return cli_daemon_delegation._index_via_daemon(
                force_reindex=force_reindex,
                enable_fts=enable_fts,
                daemon_config=daemon_config,
            )

        elif command == "watch":
            # Watch command delegation
            from . import cli_daemon_delegation

            # Parse arguments
            debounce = 1.0
            batch_size = 50
            initial_sync = False
            enable_fts = False

            i = 0
            while i < len(args):
                if args[i] == "--debounce" and i + 1 < len(args):
                    debounce = float(args[i + 1])
                    i += 2
                elif args[i] == "--batch-size" and i + 1 < len(args):
                    batch_size = int(args[i + 1])
                    i += 2
                elif args[i] == "--initial-sync":
                    initial_sync = True
                    i += 1
                elif args[i] == "--fts":
                    enable_fts = True
                    i += 1
                else:
                    i += 1

            # Get daemon config
            from .config import ConfigManager

            try:
                config_manager = ConfigManager.create_with_backtrack(Path.cwd())
                daemon_config = config_manager.get_daemon_config()
            except Exception:
                daemon_config = {"enabled": True, "retry_delays_ms": [100, 500, 1000, 2000]}

            # Close the connection before calling delegation (it will create its own)
            conn.close()

            # Delegate to watch via daemon
            return cli_daemon_delegation._watch_via_daemon(
                debounce=debounce,
                batch_size=batch_size,
                initial_sync=initial_sync,
                enable_fts=enable_fts,
                daemon_config=daemon_config,
            )

        elif command == "status":
            # Status command needs full CLI (Rich table formatting)
            # Don't delegate via fast path - use full CLI for better UX
            conn.close()
            raise NotImplementedError(f"Command '{command}' needs full CLI for rich output")

        else:
            # Unsupported command in fast path
            console.print(
                f"[yellow]Command '{command}' not supported in fast path[/yellow]"
            )
            console.print("[dim]Falling back to full CLI...[/dim]")
            raise NotImplementedError(f"Fast path doesn't support: {command}")

        return 0

    finally:
        conn.close()
