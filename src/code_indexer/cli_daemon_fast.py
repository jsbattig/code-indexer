"""Lightweight daemon delegation - minimal imports for fast startup.

This module provides the fast path for daemon-mode queries:
- Imports only rpyc (~50ms) + rich (~40ms)
- Minimal argument parsing (no Click)
- Direct RPC calls to daemon
- Simple result display

Target: <150ms total startup for daemon-mode queries
"""
from pathlib import Path
from typing import List, Dict, Any

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
    result = {
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


def _display_results(results: Any, console: Console) -> None:
    """Display query results with minimal formatting.

    Args:
        results: Query results from daemon
        console: Rich console for output
    """
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    if isinstance(results, list):
        for i, res in enumerate(results, 1):
            # Extract payload
            payload = res.get("payload", {})
            path = payload.get("path", "unknown")
            line = payload.get("line_start", 0)
            score = res.get("score", 0.0)

            # Display result
            console.print(f"{i}. {path}:{line} (score: {score:.3f})")

            # Show content snippet if available
            content = payload.get("content")
            if content:
                # Truncate long content
                if len(content) > 100:
                    content = content[:97] + "..."
                console.print(f"   [dim]{content}[/dim]")
    else:
        console.print("[yellow]Unexpected result format[/yellow]")


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

            # Build options dict for daemon
            options = {
                'limit': limit,
                **filters
            }

            # Execute query via daemon RPC
            if is_fts and is_semantic:
                # Hybrid search
                result = conn.root.exposed_query_hybrid(
                    str(Path.cwd()), query_text, **options
                )
            elif is_fts:
                # FTS only
                result = conn.root.exposed_query_fts(
                    str(Path.cwd()), query_text, **options
                )
            else:
                # Semantic only
                result = conn.root.exposed_query(
                    str(Path.cwd()), query_text, limit, **filters
                )

            # Display results
            _display_results(result, console)

        elif command == "start":
            # Start daemon (should already be handled by cli_daemon_lifecycle)
            from . import cli_daemon_lifecycle
            return cli_daemon_lifecycle.start_daemon_command()

        elif command == "stop":
            # Stop daemon
            from . import cli_daemon_lifecycle
            return cli_daemon_lifecycle.stop_daemon_command()

        elif command == "status":
            # Status command needs full CLI for Rich table display
            # Close daemon connection and fallback to full CLI
            conn.close()
            raise NotImplementedError("Status requires full CLI for table formatting")

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
