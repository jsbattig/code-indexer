"""Lightweight daemon delegation - minimal imports for fast startup.

This module provides the fast path for daemon-mode queries:
- Imports only rpyc (~50ms) + rich (~40ms)
- Minimal argument parsing (no Click)
- Direct RPC calls to daemon
- Simple result display

Target: <150ms total startup for daemon-mode queries
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, cast

# ONLY import what's absolutely needed for daemon delegation
# Import timeout-aware connection function from delegation module
# (rpyc unix_connect imported inside _connect_to_daemon as needed)
from rich.console import Console  # ~40ms


def get_socket_path(config_path: Path) -> Path:
    """Get daemon socket path from config path.

    Uses ConfigManager.get_socket_path() which generates /tmp/cidx/ paths
    to avoid Unix socket 108-character limit.

    Args:
        config_path: Path to .code-indexer/config.json

    Returns:
        Path to daemon socket file
    """
    from code_indexer.config import ConfigManager

    config_manager = ConfigManager(config_path)
    return cast(Path, config_manager.get_socket_path())


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

    Raises:
        ValueError: If unknown flag is encountered
    """
    # Define valid flags for validation
    VALID_FLAGS = {
        "--fts",
        "--semantic",
        "--quiet",
        "--limit",
        "--language",
        "--path-filter",
        "--exclude-language",
        "--exclude-path",
        "--snippet-lines",
        "--repo",
    }

    result: Dict[str, Any] = {
        "query_text": "",
        "is_fts": False,
        "is_semantic": False,
        "limit": 10,
        "quiet": False,
        "filters": {},
    }

    i = 0
    while i < len(args):
        arg = args[i]

        if arg.startswith("--"):
            # Validate flag is known
            if arg not in VALID_FLAGS:
                raise ValueError(f"Unknown flag: {arg}")

            # Flag arguments
            if arg == "--fts":
                result["is_fts"] = True
            elif arg == "--semantic":
                result["is_semantic"] = True
            elif arg == "--quiet":
                result["quiet"] = True
            elif arg == "--limit" and i + 1 < len(args):
                result["limit"] = int(args[i + 1])
                i += 1
            elif arg == "--language" and i + 1 < len(args):
                # Accumulate multiple values into list
                if "language" not in result["filters"]:
                    result["filters"]["language"] = args[i + 1]
                else:
                    # Convert to list on second occurrence
                    if isinstance(result["filters"]["language"], str):
                        result["filters"]["language"] = [
                            result["filters"]["language"],
                            args[i + 1],
                        ]
                    else:
                        result["filters"]["language"].append(args[i + 1])
                i += 1
            elif arg == "--path-filter" and i + 1 < len(args):
                # Accumulate multiple values into list
                if "path_filter" not in result["filters"]:
                    result["filters"]["path_filter"] = args[i + 1]
                else:
                    # Convert to list on second occurrence
                    if isinstance(result["filters"]["path_filter"], str):
                        result["filters"]["path_filter"] = [
                            result["filters"]["path_filter"],
                            args[i + 1],
                        ]
                    else:
                        result["filters"]["path_filter"].append(args[i + 1])
                i += 1
            elif arg == "--exclude-language" and i + 1 < len(args):
                # Accumulate multiple values into list
                if "exclude_language" not in result["filters"]:
                    result["filters"]["exclude_language"] = args[i + 1]
                else:
                    # Convert to list on second occurrence
                    if isinstance(result["filters"]["exclude_language"], str):
                        result["filters"]["exclude_language"] = [
                            result["filters"]["exclude_language"],
                            args[i + 1],
                        ]
                    else:
                        result["filters"]["exclude_language"].append(args[i + 1])
                i += 1
            elif arg == "--exclude-path" and i + 1 < len(args):
                # Accumulate multiple values into list
                if "exclude_path" not in result["filters"]:
                    result["filters"]["exclude_path"] = args[i + 1]
                else:
                    # Convert to list on second occurrence
                    if isinstance(result["filters"]["exclude_path"], str):
                        result["filters"]["exclude_path"] = [
                            result["filters"]["exclude_path"],
                            args[i + 1],
                        ]
                    else:
                        result["filters"]["exclude_path"].append(args[i + 1])
                i += 1
            elif arg == "--snippet-lines" and i + 1 < len(args):
                result["filters"]["snippet_lines"] = int(args[i + 1])
                i += 1
        else:
            # Query text (first non-flag argument)
            if not result["query_text"]:
                result["query_text"] = arg

        i += 1

    # Default: if no mode specified, use semantic
    if not result["is_fts"] and not result["is_semantic"]:
        result["is_semantic"] = True

    return result


def _display_results(
    results: Any,
    console: Console,
    timing_info: Optional[Dict[str, Any]] = None,
    quiet: bool = False,
) -> None:
    """Display query results by delegating to shared display functions (DRY principle).

    CRITICAL: This function calls the EXISTING display code from cli.py instead of
    duplicating lines. This ensures identical display in both daemon and standalone modes.

    FTS Display Fix: Detects result type (FTS vs semantic) and routes to appropriate
    display function. FTS results have 'match_text' key and no 'payload' key.
    Semantic results have 'payload' key and no 'match_text' key.

    Args:
        results: Query results from daemon (FTS or semantic format)
        console: Rich console for output
        timing_info: Optional timing information for performance display (semantic only)
        quiet: Whether to use quiet output mode (default: False)
    """
    # Import shared display functions (SINGLE source of truth)
    from .cli import _display_semantic_results, _display_fts_results

    # Detect result type by examining first result
    # FTS results have 'match_text' and no 'payload'
    # Semantic results have 'payload' and no 'match_text'
    is_fts_result = False
    if results and len(results) > 0:
        first_result = results[0]
        is_fts_result = "match_text" in first_result or "payload" not in first_result

    # Route to appropriate display function
    if is_fts_result:
        # FTS results: display with FTS-specific formatting
        _display_fts_results(
            results=results,
            console=console,
            quiet=quiet,  # Pass quiet flag from caller
        )
    else:
        # Semantic results: display with semantic-specific formatting
        _display_semantic_results(
            results=results,
            console=console,
            quiet=quiet,  # Pass quiet flag from caller
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

    # Skip daemon for --repo flag (global repos require full CLI for alias resolution)
    if command == "query" and "--repo" in args:
        raise ConnectionRefusedError("--repo requires full CLI (not daemon)")

    # CRITICAL: Validate arguments BEFORE attempting daemon connection
    # This ensures typos and invalid flags are caught immediately
    if command == "query":
        try:
            parsed = parse_query_args(args)
        except ValueError as e:
            console.print(f"[red]❌ Error: {e}[/red]")
            console.print("[dim]Try 'cidx query --help' for valid options[/dim]")
            return 2  # Exit code 2 for usage errors (matches Click)

    # Get socket path
    socket_path = get_socket_path(config_path)

    # Connect to daemon with timeout protection (prevents indefinite hangs)
    try:
        from . import cli_daemon_delegation
        from .config import ConfigManager

        # Load daemon config for retry settings
        config_manager = ConfigManager.create_with_backtrack(config_path.parent)
        daemon_config = config_manager.get_daemon_config()

        conn = cli_daemon_delegation._connect_to_daemon(socket_path, daemon_config)
    except (ConnectionRefusedError, FileNotFoundError, TimeoutError):
        console.print("[red]❌ Daemon not running[/red]")
        console.print("[dim]Run 'cidx start' to start daemon[/dim]")
        raise

    try:
        # Route based on command
        if command == "query":
            # Arguments already parsed and validated above

            query_text = parsed["query_text"]
            is_fts = parsed["is_fts"]
            is_semantic = parsed["is_semantic"]
            limit = parsed["limit"]
            filters = parsed["filters"]

            # Check if --quiet flag is present
            is_quiet = parsed.get("quiet", False)

            # Display daemon mode indicator (unless --quiet flag is set)
            if not is_quiet:
                console.print("🔧 Running in daemon mode", style="blue")

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
            if filters.get("language"):
                # Format multiple values with comma separation
                lang_display = (
                    ", ".join(filters["language"])
                    if isinstance(filters["language"], list)
                    else filters["language"]
                )
                console.print(f"🏷️  Language filter: {lang_display}", style="dim")
            if filters.get("path_filter"):
                # Format multiple values with comma separation
                path_display = (
                    ", ".join(filters["path_filter"])
                    if isinstance(filters["path_filter"], list)
                    else filters["path_filter"]
                )
                console.print(f"📁 Path filter: {path_display}", style="dim")
            console.print(f"📊 Limit: {limit}", style="dim")

            # Build options dict for daemon
            options = {"limit": limit, **filters}

            # Execute query via daemon RPC
            if is_fts and is_semantic:
                # Hybrid search
                response = conn.root.exposed_query_hybrid(
                    str(Path.cwd()), query_text, **options
                )
                # Extract results from response dict
                result = (
                    response.get("results", [])
                    if isinstance(response, dict)
                    else response
                )
                timing_info = None
            elif is_fts:
                # FTS only
                response = conn.root.exposed_query_fts(
                    str(Path.cwd()), query_text, **options
                )
                # Extract results from response dict
                result = (
                    response.get("results", [])
                    if isinstance(response, dict)
                    else response
                )
                timing_info = None
            else:
                # Semantic only
                response = conn.root.exposed_query(
                    str(Path.cwd()), query_text, limit, **filters
                )
                # CRITICAL FIX: Parse response dict with results and timing
                result = response.get("results", [])
                timing_info = response.get("timing", None)

            # Display results with full formatting including timing and quiet flag
            _display_results(result, console, timing_info=timing_info, quiet=is_quiet)

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
            reconcile = "--reconcile" in args
            detect_deletions = "--detect-deletions" in args
            # CRITICAL FIX for Bug #474: Parse temporal indexing flags
            index_commits = "--index-commits" in args
            all_branches = "--all-branches" in args

            # Parse numeric parameters
            batch_size = 50  # default
            files_count = None
            max_commits = None
            since_date = None
            i = 0
            while i < len(args):
                if args[i] == "--batch-size" and i + 1 < len(args):
                    batch_size = int(args[i + 1])
                    i += 2
                elif args[i] == "--files-count-to-process" and i + 1 < len(args):
                    files_count = int(args[i + 1])
                    i += 2
                elif args[i] == "--max-commits" and i + 1 < len(args):
                    max_commits = int(args[i + 1])
                    i += 2
                elif args[i] == "--since-date" and i + 1 < len(args):
                    since_date = args[i + 1]
                    i += 2
                else:
                    i += 1

            # Get daemon config from connection
            from .config import ConfigManager

            try:
                config_manager = ConfigManager.create_with_backtrack(Path.cwd())
                daemon_config = config_manager.get_daemon_config()
            except Exception:
                daemon_config = {
                    "enabled": True,
                    "retry_delays_ms": [100, 500, 1000, 2000],
                }

            # Close the connection before calling delegation (it will create its own)
            conn.close()

            # Delegate to index via daemon with all parameters
            # CRITICAL FIX for Bug #474: Include temporal indexing parameters
            # (mode indicator will be shown inside _index_via_daemon after progress display setup)
            return cli_daemon_delegation._index_via_daemon(
                force_reindex=force_reindex,
                enable_fts=enable_fts,
                daemon_config=daemon_config,
                batch_size=batch_size,
                reconcile=reconcile,
                files_count_to_process=files_count,
                detect_deletions=detect_deletions,
                index_commits=index_commits,
                all_branches=all_branches,
                max_commits=max_commits,
                since_date=since_date,
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
                daemon_config = {
                    "enabled": True,
                    "retry_delays_ms": [100, 500, 1000, 2000],
                }

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
            raise NotImplementedError(
                f"Command '{command}' needs full CLI for rich output"
            )

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
