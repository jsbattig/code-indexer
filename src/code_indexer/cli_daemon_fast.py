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
    """Display query results by calling existing standalone display logic.

    CRITICAL FIX: This function now delegates to the existing display code
    in cli.py instead of duplicating 107 lines of display logic.

    Args:
        results: Query results from daemon (list of dicts with score/payload)
        console: Rich console for output
        timing_info: Optional timing information for performance display
    """
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    # Import standalone display functions
    from .cli import _display_query_timing

    # Display timing information if available
    if timing_info and not timing_info.get("quiet", False):
        _display_query_timing(console, timing_info)

    # Display each result using EXISTING standalone logic (NO code duplication)
    for i, result in enumerate(results, 1):
        payload = result.get("payload", {})
        score = result.get("score", 0.0)

        # File info
        file_path = payload.get("path", "unknown")
        language = payload.get("language", "unknown")
        content = payload.get("content", "")

        # Staleness info (if available)
        staleness_info = result.get("staleness", {})
        staleness_indicator = staleness_info.get("staleness_indicator", "")

        # Line number info
        line_start = payload.get("line_start")
        line_end = payload.get("line_end")

        # Create file path with line numbers
        if line_start is not None and line_end is not None:
            if line_start == line_end:
                file_path_with_lines = f"{file_path}:{line_start}"
            else:
                file_path_with_lines = f"{file_path}:{line_start}-{line_end}"
        else:
            file_path_with_lines = file_path

        # IDENTICAL DISPLAY LOGIC AS cli.py (lines 5072-5140)
        # Normal verbose mode
        file_size = payload.get("file_size", 0)
        indexed_at = payload.get("indexed_at", "unknown")

        # Git-aware metadata
        git_available = payload.get("git_available", False)
        project_id = payload.get("project_id", "unknown")

        # Create header with git info and line numbers
        header = f"📄 File: {file_path_with_lines}"
        if language != "unknown":
            header += f" | 🏷️  Language: {language}"
        header += f" | 📊 Score: {score:.3f}"

        # Add staleness indicator to header if available
        if staleness_indicator:
            header += f" | {staleness_indicator}"

        console.print(f"\n[bold cyan]{header}[/bold cyan]")

        # Enhanced metadata display
        metadata_info = f"📏 Size: {file_size} bytes | 🕒 Indexed: {indexed_at}"

        # Add staleness details in verbose mode
        if staleness_info.get("staleness_delta_seconds") is not None:
            delta_seconds = staleness_info["staleness_delta_seconds"]
            if delta_seconds > 0:
                delta_hours = delta_seconds / 3600
                if delta_hours < 1:
                    delta_minutes = int(delta_seconds / 60)
                    staleness_detail = f"Local file newer by {delta_minutes}m"
                elif delta_hours < 24:
                    delta_hours_int = int(delta_hours)
                    staleness_detail = f"Local file newer by {delta_hours_int}h"
                else:
                    delta_days = int(delta_hours / 24)
                    staleness_detail = f"Local file newer by {delta_days}d"
                metadata_info += f" | ⏰ Staleness: {staleness_detail}"

        if git_available:
            import subprocess
            try:
                git_result = subprocess.run(
                    ["git", "symbolic-ref", "--short", "HEAD"],
                    cwd=Path.cwd(),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                current_display_branch = git_result.stdout.strip() if git_result.returncode == 0 else "unknown"
            except Exception:
                current_display_branch = "unknown"

            git_branch = current_display_branch
            git_commit = payload.get("git_commit_hash", "unknown")
            if git_commit != "unknown" and len(git_commit) > 8:
                git_commit = git_commit[:8] + "..."
            metadata_info += f" | 🌿 Branch: {git_branch}"
            if git_commit != "unknown":
                metadata_info += f" | 📦 Commit: {git_commit}"

        metadata_info += f" | 🏗️  Project: {project_id}"
        console.print(metadata_info)

        # Content display with line numbers (FULL content, NO truncation)
        if content:
            content_lines = content.split("\n")

            # Add line number prefixes if we have line start info
            if line_start is not None:
                numbered_lines = []
                for j, line in enumerate(content_lines):
                    line_num = line_start + j
                    numbered_lines.append(f"{line_num:3}: {line}")
                content_with_line_numbers = "\n".join(numbered_lines)
            else:
                content_with_line_numbers = content

            console.print(f"\n📖 Content:")
            console.print("─" * 50)
            console.print(content_with_line_numbers)
            console.print("─" * 50)


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
            console.print(f"\n✅ Found {len(result) if result else 0} results:")
            console.print("=" * 80)
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
