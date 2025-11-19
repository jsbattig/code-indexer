"""
Daemon delegation functions for CLI commands.

This module provides helper functions for delegating CLI commands to the daemon
when daemon mode is enabled. It handles:
- Connection to daemon with exponential backoff
- Crash recovery with automatic restart (2 attempts)
- Graceful fallback to standalone mode
- Query delegation (semantic, FTS, hybrid)
- Storage command delegation (clean, clean-data, status)
"""

import sys
import time
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


def _find_config_file() -> Optional[Path]:
    """
    Walk up directory tree looking for .code-indexer/config.json.

    Returns:
        Path to config.json or None if not found
    """
    current = Path.cwd()
    while current != current.parent:
        config_path = current / ".code-indexer" / "config.json"
        if config_path.exists():
            return config_path
        current = current.parent
    return None


def _get_socket_path(config_path: Path) -> Path:
    """
    Calculate socket path from config location.

    Uses ConfigManager.get_socket_path() which generates /tmp/cidx/ paths
    to avoid Unix socket 108-character limit.

    Args:
        config_path: Path to config.json file

    Returns:
        Path to daemon socket file
    """
    from code_indexer.config import ConfigManager
    config_manager = ConfigManager(config_path)
    return config_manager.get_socket_path()


def _connect_to_daemon(
    socket_path: Path, daemon_config: Dict, connection_timeout: float = 2.0
) -> Any:
    """
    Establish RPyC connection to daemon with exponential backoff and timeout.

    ARCHITECTURAL NOTE: This function uses socket-level operations (socket.socket,
    SocketStream, connect_stream) instead of rpyc.utils.factory.unix_connect to enable
    fine-grained timeout control. We need to set a connection timeout to prevent
    indefinite hangs during daemon startup/connection, but allow unlimited timeout
    for long-running RPC operations (queries, indexing).

    Args:
        socket_path: Path to Unix domain socket
        daemon_config: Daemon configuration with retry_delays_ms
        connection_timeout: Connection timeout in seconds (default: 2.0)
                          This 2-second timeout balances responsiveness (fails fast
                          when daemon is truly unavailable) with reliability (allows
                          sufficient time for daemon startup on slower systems).

    Returns:
        RPyC connection object

    Raises:
        ConnectionError: If all retries exhausted
        TimeoutError: If connection times out
    """
    try:
        from rpyc.core.stream import SocketStream
        from rpyc.utils.factory import connect_stream
        import socket as socket_module
    except ImportError:
        raise ImportError(
            "RPyC is required for daemon mode. Install with: pip install rpyc"
        )

    # Get retry delays from config (default: [100, 500, 1000, 2000]ms)
    retry_delays_ms = daemon_config.get("retry_delays_ms", [100, 500, 1000, 2000])
    retry_delays = [d / 1000.0 for d in retry_delays_ms]  # Convert to seconds

    last_error = None
    for attempt, delay in enumerate(retry_delays):
        try:
            # Create socket with connection timeout to prevent indefinite hangs
            sock = socket_module.socket(
                socket_module.AF_UNIX, socket_module.SOCK_STREAM
            )
            sock.settimeout(connection_timeout)

            try:
                # Connect with timeout
                sock.connect(str(socket_path))

                # Reset timeout for RPC operations (allow long-running queries)
                sock.settimeout(None)

                # Create SocketStream and RPyC connection
                stream = SocketStream(sock)
                return connect_stream(
                    stream,
                    config={
                        "allow_public_attrs": True,
                        "sync_request_timeout": None,  # Disable timeout for long operations
                    },
                )
            except Exception:
                # Ensure socket is closed on error
                try:
                    sock.close()
                except Exception:
                    pass
                raise

        except (
            ConnectionRefusedError,
            FileNotFoundError,
            OSError,
            socket_module.timeout,
        ) as e:
            last_error = e
            if attempt < len(retry_delays) - 1:
                time.sleep(delay)
            else:
                # Last attempt failed, convert timeout to TimeoutError for clarity
                if isinstance(e, socket_module.timeout):
                    raise TimeoutError(
                        f"Connection to daemon timed out after {connection_timeout}s"
                    ) from e
                # Re-raise other errors
                raise last_error


def _cleanup_stale_socket(socket_path: Path) -> None:
    """
    Remove stale socket file.

    Args:
        socket_path: Path to socket file to remove
    """
    try:
        socket_path.unlink()
    except (FileNotFoundError, OSError):
        # Socket might not exist or already removed
        pass


def _start_daemon(config_path: Path) -> None:
    """
    Start daemon process as background subprocess.

    Args:
        config_path: Path to config.json for daemon
    """
    # Check if daemon is already running
    socket_path = _get_socket_path(config_path)
    if socket_path.exists():
        try:
            # Try to connect to see if daemon is actually running
            import socket

            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            sock.connect(str(socket_path))
            sock.close()
            # Daemon is running, don't start another
            console.print("[dim]Daemon already running, skipping start[/dim]")
            return
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            # Socket exists but daemon not responding, clean it up
            _cleanup_stale_socket(socket_path)

    daemon_cmd = [
        sys.executable,
        "-m",
        "code_indexer.daemon",
        str(config_path),
    ]

    # Start daemon process detached
    subprocess.Popen(
        daemon_cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # Give daemon time to bind socket
    time.sleep(0.5)


def _display_results(results, query_time: float = 0) -> None:
    """
    Display query results using standalone display logic for UX parity.

    This delegates to cli_daemon_fast._display_results which uses the FULL
    standalone display logic (no truncation, full metadata).

    Args:
        results: Query results (list or dict with "results" key)
        query_time: Query execution time in seconds
    """
    # Import full display function from daemon fast path
    from .cli_daemon_fast import _display_results as fast_display_results

    # Handle both list and dict formats
    if isinstance(results, list):
        result_list = results
    elif isinstance(results, dict):
        result_list = results.get("results", [])
    else:
        console.print("[yellow]No results found[/yellow]")
        return

    if not result_list:
        console.print("[yellow]No results found[/yellow]")
        return

    # Build timing info for display
    timing_info = {"total_ms": query_time * 1000} if query_time > 0 else {}

    # Use full standalone display (FULL content, ALL metadata)
    fast_display_results(result_list, console, timing_info)


def _query_standalone(
    query_text: str, fts: bool = False, semantic: bool = True, limit: int = 10, **kwargs
) -> int:
    """
    Fallback to standalone query execution.

    This imports the full CLI and executes the query locally.
    CRITICAL FIX: Pass standalone=True flag to prevent recursive daemon delegation.

    Args:
        query_text: Query string
        fts: Use FTS search
        semantic: Use semantic search
        limit: Result limit
        **kwargs: Additional query parameters

    Returns:
        Exit code (0 = success)
    """
    # Import full CLI (expensive, but we're in fallback mode)
    from .cli import query as cli_query
    from .config import ConfigManager
    from .mode_detection.command_mode_detector import (
        CommandModeDetector,
        find_project_root,
    )
    import click

    try:
        # Remove daemon-specific kwargs that CLI doesn't accept
        cli_kwargs = {k: v for k, v in kwargs.items() if k not in ["standalone"]}

        # Set default values for missing parameters
        cli_kwargs.setdefault("languages", ())
        cli_kwargs.setdefault("exclude_languages", ())
        cli_kwargs.setdefault("path_filter", None)
        cli_kwargs.setdefault("exclude_paths", ())
        cli_kwargs.setdefault("min_score", None)
        cli_kwargs.setdefault("accuracy", "fast")
        cli_kwargs.setdefault("quiet", False)
        cli_kwargs.setdefault("case_sensitive", False)
        cli_kwargs.setdefault("case_insensitive", False)
        cli_kwargs.setdefault("fuzzy", False)
        cli_kwargs.setdefault("edit_distance", 0)
        cli_kwargs.setdefault("snippet_lines", 5)
        cli_kwargs.setdefault("regex", False)

        # CRITICAL: Add standalone flag to prevent recursive daemon delegation
        cli_kwargs["standalone"] = True

        # Setup context object with mode detection (required by query command)
        project_root = find_project_root(Path.cwd())
        mode_detector = CommandModeDetector(project_root)
        mode = mode_detector.detect_mode()

        # Create context with required obj attributes
        ctx = click.Context(cli_query)
        ctx.obj = {
            "mode": mode,
            "project_root": project_root,
            "standalone": True,  # CRITICAL: Prevent daemon delegation
        }

        # Load config manager if in local mode
        if mode == "local" and project_root:
            try:
                config_manager = ConfigManager.create_with_backtrack(project_root)
                ctx.obj["config_manager"] = config_manager
            except Exception:
                pass  # Config might not exist yet

        # Invoke query command using ctx.invoke()
        with ctx:
            ctx.invoke(
                cli_query,
                query=query_text,
                limit=limit,
                fts=fts,
                semantic=semantic,
                **cli_kwargs,
            )
        return 0
    except Exception as e:
        console.print(f"[red]Query failed: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


def _status_standalone(**kwargs) -> int:
    """
    Fallback to standalone status execution.

    Args:
        **kwargs: Additional status parameters

    Returns:
        Exit code (0 = success)
    """
    from .cli import status as cli_status
    from .mode_detection.command_mode_detector import (
        CommandModeDetector,
        find_project_root,
    )
    import click

    try:
        # Setup context object with mode detection (required by status command)
        project_root = find_project_root(Path.cwd())
        mode_detector = CommandModeDetector(project_root)
        mode = mode_detector.detect_mode()

        # Create a click context with required attributes
        ctx = click.Context(click.Command("status"))
        ctx.obj = {
            "mode": mode,
            "project_root": project_root,
            "standalone": True,  # Prevent daemon delegation
        }

        # Load config manager if in local mode
        if mode == "local" and project_root:
            try:
                from .config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack(project_root)
                ctx.obj["config_manager"] = config_manager
            except Exception:
                pass  # Config might not exist yet

        force_docker = kwargs.get("force_docker", False)
        # Call status function directly (not as a click command)
        with ctx:
            cli_status(ctx, force_docker=force_docker)
        return 0
    except Exception as e:
        console.print(f"[red]Status failed: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


def _query_via_daemon(
    query_text: str,
    daemon_config: Dict,
    fts: bool = False,
    semantic: bool = True,
    limit: int = 10,
    **kwargs,
) -> int:
    """
    Delegate query to daemon with crash recovery.

    Implements 2-attempt restart recovery:
    1. Try to connect and execute
    2. If fails, restart daemon and retry (attempt 1/2)
    3. If fails again, restart daemon and retry (attempt 2/2)
    4. If still fails, fallback to standalone

    Args:
        query_text: Query string
        daemon_config: Daemon configuration
        fts: Use FTS search
        semantic: Use semantic search
        limit: Result limit
        **kwargs: Additional query parameters

    Returns:
        Exit code (0 = success)
    """
    config_path = _find_config_file()
    if not config_path:
        console.print("[yellow]No config found, using standalone mode[/yellow]")
        return _query_standalone(
            query_text, fts=fts, semantic=semantic, limit=limit, **kwargs
        )

    socket_path = _get_socket_path(config_path)

    # Crash recovery: up to 2 restart attempts
    for restart_attempt in range(3):  # Initial + 2 restarts
        conn = None
        try:
            # Connect to daemon
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Determine query type and execute
            start_time = time.perf_counter()

            if fts and semantic:
                # Hybrid search
                result = conn.root.exposed_query_hybrid(
                    str(Path.cwd()), query_text, limit=limit, **kwargs
                )
            elif fts:
                # FTS-only search
                result = conn.root.exposed_query_fts(
                    str(Path.cwd()), query_text, limit=limit, **kwargs
                )
            else:
                # Semantic search
                result = conn.root.exposed_query(
                    str(Path.cwd()), query_text, limit=limit, **kwargs
                )

            query_time = time.perf_counter() - start_time

            # Display results first (while connection is still open)
            _display_results(result, query_time)

            # Close connection after displaying results
            try:
                conn.close()
            except Exception:
                pass  # Connection already closed

            return 0

        except Exception as e:
            # Close connection on error to prevent resource leaks
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

            # Connection or query failed
            if restart_attempt < 2:
                # Still have restart attempts left
                console.print(
                    f"[yellow]⚠️  Daemon connection failed, attempting restart ({restart_attempt + 1}/2)[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")

                # Clean up stale socket before restart
                _cleanup_stale_socket(socket_path)
                _start_daemon(config_path)

                # Wait longer for daemon to fully start
                time.sleep(1.0)
                continue
            else:
                # Exhausted all restart attempts
                console.print(
                    "[yellow]ℹ️  Daemon unavailable after 2 restart attempts, using standalone mode[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")
                console.print("[dim]Tip: Check daemon with 'cidx daemon status'[/dim]")

                return _query_standalone(
                    query_text, fts=fts, semantic=semantic, limit=limit, **kwargs
                )

    # Should never reach here
    return 1


def _clean_via_daemon(**kwargs) -> int:
    """
    Execute clean command via daemon.

    Args:
        **kwargs: Additional clean parameters

    Returns:
        Exit code (0 = success)
    """
    from .config import ConfigManager

    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    socket_path = config_manager.get_socket_path()
    daemon_config = config_manager.get_daemon_config()

    try:
        conn = _connect_to_daemon(socket_path, daemon_config)

        console.print("[yellow]Clearing vectors (via daemon)...[/yellow]")
        result = conn.root.exposed_clean(str(Path.cwd()), **kwargs)
        conn.close()

        console.print("[green]✓ Vectors cleared[/green]")
        console.print(f"  Cache invalidated: {result.get('cache_invalidated', False)}")
        return 0

    except Exception as e:
        console.print(f"[red]Failed to clean via daemon: {e}[/red]")
        console.print("[yellow]Falling back to standalone mode[/yellow]")

        # Fallback to standalone
        from .cli import clean as cli_clean
        import click

        try:
            ctx = click.Context(click.Command("clean"))
            ctx.obj = {"standalone": True}  # Prevent daemon delegation
            force_docker = kwargs.get("force_docker", False)
            cli_clean(ctx, force_docker=force_docker)
            return 0
        except Exception as e2:
            console.print(f"[red]Clean failed: {e2}[/red]")
            return 1


def _clean_data_via_daemon(**kwargs) -> int:
    """
    Execute clean-data command via daemon.

    Args:
        **kwargs: Additional clean-data parameters

    Returns:
        Exit code (0 = success)
    """
    from .config import ConfigManager

    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    socket_path = config_manager.get_socket_path()
    daemon_config = config_manager.get_daemon_config()

    try:
        conn = _connect_to_daemon(socket_path, daemon_config)

        console.print("[yellow]Clearing project data (via daemon)...[/yellow]")
        result = conn.root.exposed_clean_data(str(Path.cwd()), **kwargs)
        conn.close()

        console.print("[green]✓ Project data cleared[/green]")
        console.print(f"  Cache invalidated: {result.get('cache_invalidated', False)}")
        return 0

    except Exception as e:
        console.print(f"[red]Failed to clean data via daemon: {e}[/red]")
        console.print("[yellow]Falling back to standalone mode[/yellow]")

        # Fallback to standalone
        from .cli import clean_data as cli_clean_data
        import click

        try:
            ctx = click.Context(click.Command("clean-data"))
            ctx.obj = {"standalone": True}  # Prevent daemon delegation
            force_docker = kwargs.get("force_docker", False)
            cli_clean_data(ctx, force_docker=force_docker)
            return 0
        except Exception as e2:
            console.print(f"[red]Clean data failed: {e2}[/red]")
            return 1


def _status_via_daemon(**kwargs) -> int:
    """
    Execute status command via daemon.

    Args:
        **kwargs: Additional status parameters

    Returns:
        Exit code (0 = success)
    """
    from .config import ConfigManager

    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    socket_path = config_manager.get_socket_path()
    daemon_config = config_manager.get_daemon_config()

    try:
        conn = _connect_to_daemon(socket_path, daemon_config)
        result = conn.root.exposed_status(str(Path.cwd()))

        # Extract data while connection is still open
        daemon_info = result.get("daemon", {})
        daemon_running = daemon_info.get("running", False)
        daemon_semantic_cached = daemon_info.get("semantic_cached", False)
        daemon_fts_available = daemon_info.get("fts_available", False)
        daemon_watching = daemon_info.get("watching", False)

        storage_info = result.get("storage", {})
        storage_index_size = storage_info.get("index_size", "unknown")

        # Close connection after extracting data
        conn.close()

        # Display daemon status (after connection is closed)
        console.print("[bold]Daemon Status:[/bold]")
        console.print(f"  Running: {daemon_running}")
        console.print(f"  Semantic Cached: {daemon_semantic_cached}")
        console.print(f"  FTS Available: {daemon_fts_available}")
        console.print(f"  Watching: {daemon_watching}")

        # Display storage status
        console.print("\n[bold]Storage Status:[/bold]")
        console.print(f"  Index Size: {storage_index_size}")

        return 0

    except (ConnectionRefusedError, FileNotFoundError, TimeoutError, OSError) as e:
        # Daemon not available - show helpful message and fallback
        console.print(f"[yellow]Daemon not available: {e}[/yellow]")
        console.print("[yellow]Showing local storage status only[/yellow]")

        # Fallback to standalone status
        return _status_standalone(**kwargs)
    except Exception as e:
        # Unexpected error - show warning and fallback
        console.print(f"[yellow]Unexpected error connecting to daemon: {e}[/yellow]")
        console.print("[yellow]Showing local storage status only[/yellow]")

        # Fallback to standalone status
        return _status_standalone(**kwargs)


def _index_standalone(force_reindex: bool = False, **kwargs) -> int:
    """
    Fallback to standalone index execution.

    This imports the full CLI and executes indexing locally without daemon.

    Args:
        force_reindex: Whether to force reindex all files
        **kwargs: Additional indexing parameters

    Returns:
        Exit code (0 = success)
    """
    from .cli import index as cli_index
    from .mode_detection.command_mode_detector import (
        CommandModeDetector,
        find_project_root,
    )
    import click

    try:
        # Filter out daemon-specific kwargs that CLI doesn't understand
        daemon_only_keys = {"daemon_config", "force_full"}
        cli_kwargs = {k: v for k, v in kwargs.items() if k not in daemon_only_keys}

        # Map enable_fts to fts (CLI uses 'fts' parameter)
        if "enable_fts" in cli_kwargs:
            cli_kwargs["fts"] = cli_kwargs.pop("enable_fts")

        # Setup context object with mode detection
        project_root = find_project_root(Path.cwd())
        mode_detector = CommandModeDetector(project_root)
        mode = mode_detector.detect_mode()

        # Create click context
        ctx = click.Context(click.Command("index"))
        ctx.obj = {
            "mode": mode,
            "project_root": project_root,
            "standalone": True,  # Prevent daemon delegation
        }

        # Load config manager if in local mode
        if mode == "local" and project_root:
            try:
                from .config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack(project_root)
                ctx.obj["config_manager"] = config_manager
            except Exception:
                pass  # Config might not exist yet

        # Map force_reindex to clear parameter (CLI uses 'clear' for full reindex)
        # Note: The index command has both --clear and internal force_reindex
        # We pass it as-is since cli.index() accepts force_reindex parameter
        cli_kwargs["clear"] = force_reindex
        cli_kwargs["reconcile"] = False
        cli_kwargs["batch_size"] = cli_kwargs.get("batch_size", 50)
        cli_kwargs["files_count_to_process"] = None
        cli_kwargs["detect_deletions"] = False
        cli_kwargs["rebuild_indexes"] = False
        cli_kwargs["rebuild_index"] = False
        cli_kwargs["fts"] = cli_kwargs.get("fts", False)
        cli_kwargs["rebuild_fts_index"] = False

        # Invoke index command properly via Click context
        result = ctx.invoke(cli_index, **cli_kwargs)
        return int(result) if result is not None else 0
    except Exception as e:
        console.print(f"[red]Index failed: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


def _index_via_daemon(
    force_reindex: bool = False, daemon_config: Optional[Dict] = None, **kwargs
) -> int:
    """
    Delegate indexing to daemon with BLOCKING progress callbacks for UX parity.

    CRITICAL UX FIX: Uses standalone display components (RichLiveProgressManager +
    MultiThreadedProgressManager) for IDENTICAL UX to standalone mode.

    Args:
        force_reindex: Whether to force reindex all files
        daemon_config: Daemon configuration with retry delays
        **kwargs: Additional indexing parameters (enable_fts, etc.)

    Returns:
        Exit code (0 = success)
    """
    config_path = _find_config_file()
    if not config_path:
        console.print("[yellow]No config found, using standalone mode[/yellow]")
        return _index_standalone(force_reindex=force_reindex, **kwargs)

    socket_path = _get_socket_path(config_path)

    # Use default daemon config if not provided
    if daemon_config is None:
        from .config import ConfigManager

        config_manager = ConfigManager.create_with_backtrack(Path.cwd())
        daemon_config = config_manager.get_daemon_config()

    conn = None
    rich_live_manager = None
    progress_manager = None

    # Retry loop with auto-start (EXACTLY like query command)
    for restart_attempt in range(3):
        try:
            # Connect to daemon (will auto-start if needed)
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Import standalone display components (EXACTLY what standalone uses)
            from .progress.progress_display import RichLiveProgressManager
            from .progress import MultiThreadedProgressManager

            # Create progress managers (IDENTICAL to standalone)
            rich_live_manager = RichLiveProgressManager(console=console)
            progress_manager = MultiThreadedProgressManager(
                console=console,
                live_manager=rich_live_manager,
                max_slots=14,  # Default thread count + 2
            )

            # Display mode indicator BEFORE any daemon callbacks
            console.print("🔧 Running in [cyan]daemon mode[/cyan]")

            # Show temporal start message if temporal indexing requested
            if kwargs.get("index_commits", False):
                console.print(
                    "🕒 Starting temporal git history indexing...", style="cyan"
                )
                if kwargs.get("all_branches", False):
                    console.print("   Mode: All branches", style="cyan")
                else:
                    console.print("   Mode: Current branch only", style="cyan")

            # Create callback that feeds progress manager (IDENTICAL to standalone pattern)
            def progress_callback(current, total, file_path, info="", **kwargs):
                """
                Progress callback for daemon indexing with Rich Live display.

                Handles:
                - Setup messages (total=0) -> scrolling at top
                - Progress updates (total>0) -> bottom-pinned progress bar

                Args:
                    current: Current files processed
                    total: Total files to process
                    file_path: Current file being processed
                    info: Progress info string with metrics
                    **kwargs: Additional params (concurrent_files, slot_tracker)
                """
                # DEFENSIVE: Ensure current and total are always integers, never None
                # This prevents "None/None" display and TypeError exceptions
                current = int(current) if current is not None else 0
                total = int(total) if total is not None else 0

                # Setup messages scroll at top (when total=0)
                if total == 0:
                    rich_live_manager.handle_setup_message(info)
                    return

                # RPyC WORKAROUND: Deserialize concurrent_files from JSON to get fresh data
                # RPyC caches proxy objects, causing frozen/stale display. JSON serialization
                # on daemon side + deserialization here ensures we always get current state.
                import json

                concurrent_files_json = kwargs.get("concurrent_files_json", "[]")
                concurrent_files = json.loads(concurrent_files_json)
                slot_tracker = kwargs.get("slot_tracker", None)

                # Bug #475 fix: Extract item_type from kwargs
                item_type = kwargs.get("item_type", "files")

                # Parse progress info for metrics
                try:
                    parts = info.split(" | ")
                    if len(parts) >= 4:
                        # Bug #475 fix: Extract numeric value only (works for both "files/s" AND "commits/s")
                        rate_str = parts[1].strip().split()[0]
                        files_per_second = float(rate_str)

                        kb_str = parts[2].strip().split()[0]
                        kb_per_second = float(kb_str)
                        threads_text = parts[3]
                        active_threads = (
                            int(threads_text.split()[0]) if threads_text.split() else 12
                        )
                    else:
                        files_per_second = 0.0
                        kb_per_second = 0.0
                        active_threads = 12
                except (ValueError, IndexError):
                    files_per_second = 0.0
                    kb_per_second = 0.0
                    active_threads = 12

                # Update progress manager with concurrent files and slot tracker
                # FIX: Now extracts concurrent_files and slot_tracker from kwargs
                # This provides UX parity with standalone mode (shows concurrent file list)
                progress_manager.update_complete_state(
                    current=current,
                    total=total,
                    files_per_second=files_per_second,
                    kb_per_second=kb_per_second,
                    active_threads=active_threads,
                    concurrent_files=concurrent_files,  # Now extracted from kwargs
                    slot_tracker=slot_tracker,  # Now extracted from kwargs
                    info=info,
                    item_type=item_type,  # Bug #475 fix: Pass item_type to show "commits" instead of "files"
                )

                # Get integrated display and update bottom area
                rich_table = progress_manager.get_integrated_display()
                rich_live_manager.async_handle_progress_update(
                    rich_table
                )  # Bug #470 fix - async queue

            # BUG FIX: Add reset_progress_timers method to progress_callback
            # This method is called by HighThroughputProcessor during phase transitions
            # to reset Rich Progress internal timers for accurate time tracking
            def reset_progress_timers():
                """Reset Rich Progress timers for phase transitions."""
                if progress_manager:
                    progress_manager.reset_progress_timers()

            # Attach reset method to callback function (makes it accessible via hasattr check)
            progress_callback.reset_progress_timers = reset_progress_timers  # type: ignore[attr-defined]

            # Map parameters for daemon
            daemon_kwargs = {
                "force_full": force_reindex,
                "enable_fts": kwargs.get("enable_fts", False),
                "batch_size": kwargs.get("batch_size", 50),
                "reconcile_with_database": kwargs.get("reconcile", False),
                "files_count_to_process": kwargs.get("files_count_to_process"),
                "detect_deletions": kwargs.get("detect_deletions", False),
                "index_commits": kwargs.get("index_commits", False),
                "all_branches": kwargs.get("all_branches", False),
                "max_commits": kwargs.get("max_commits"),
                "since_date": kwargs.get("since_date"),
                # rebuild_* flags not supported in daemon mode yet (early-exit paths in local mode)
            }

            # CRITICAL: Start bottom display BEFORE daemon call to enable setup message scrolling
            # This ensures setup messages appear at top (scrolling) before progress bar appears at bottom
            rich_live_manager.start_bottom_display()

            # Execute indexing (BLOCKS until complete, streams progress via callback)
            # RPyC automatically handles callback streaming to client
            result = conn.root.exposed_index_blocking(
                project_path=str(Path.cwd()),
                callback=progress_callback,  # Real-time progress streaming
                **daemon_kwargs,
            )

            # Extract result data FIRST (while connection and proxies still valid)
            status = str(result.get("status", "unknown"))
            message = str(result.get("message", ""))
            stats_dict = dict(result.get("stats", {}))

            # Close connection after extracting data
            conn.close()

            # Stop progress display after connection closed
            if rich_live_manager:
                try:
                    rich_live_manager.stop_display()
                except Exception:
                    pass
            if progress_manager:
                try:
                    progress_manager.stop_progress()
                except Exception:
                    pass

            # Display completion status (IDENTICAL to standalone)
            if status == "completed":
                # Detect temporal vs semantic based on result keys
                is_temporal = (
                    "total_commits" in stats_dict
                    or "approximate_vectors_created" in stats_dict
                )

                cancelled = stats_dict.get("cancelled", False)
                if cancelled:
                    console.print("🛑 Indexing cancelled!", style="yellow")
                    if is_temporal:
                        # Temporal cancellation display
                        console.print(
                            f"   Total commits before cancellation: {stats_dict.get('total_commits', 0)}",
                            style="yellow",
                        )
                        console.print(
                            f"   Files changed: {stats_dict.get('files_processed', 0)}",
                            style="yellow",
                        )
                    else:
                        # Semantic cancellation display
                        console.print(
                            f"📄 Files processed before cancellation: {stats_dict.get('files_processed', 0)}",
                            style="yellow",
                        )
                        console.print(
                            f"📦 Chunks indexed before cancellation: {stats_dict.get('chunks_created', 0)}",
                            style="yellow",
                        )
                    console.print(
                        "💾 Progress saved - you can resume indexing later",
                        style="blue",
                    )
                else:
                    if is_temporal:
                        # Temporal completion display (matches standalone format)
                        console.print(
                            "✅ Temporal indexing completed!", style="green bold"
                        )
                        console.print(
                            f"   Total commits processed: {stats_dict.get('total_commits', 0)}",
                            style="green",
                        )
                        console.print(
                            f"   Files changed: {stats_dict.get('files_processed', 0)}",
                            style="green",
                        )
                        console.print(
                            f"   Vectors created (approx): ~{stats_dict.get('approximate_vectors_created', 0)}",
                            style="green",
                        )
                    else:
                        # Semantic completion display
                        console.print("✅ Indexing complete!", style="green")
                        console.print(
                            f"📄 Files processed: {stats_dict.get('files_processed', 0)}"
                        )
                        console.print(
                            f"📦 Chunks indexed: {stats_dict.get('chunks_created', 0)}"
                        )

                # Only show duration/throughput for semantic indexing
                # Temporal indexing doesn't track duration_seconds yet
                if not is_temporal:
                    duration = stats_dict.get("duration_seconds", 0)
                    console.print(f"⏱️  Duration: {duration:.2f}s")

                    # Calculate throughput
                    if duration > 0:
                        files_per_min = (
                            stats_dict.get("files_processed", 0) / duration
                        ) * 60
                        chunks_per_min = (
                            stats_dict.get("chunks_created", 0) / duration
                        ) * 60
                        console.print(
                            f"🚀 Throughput: {files_per_min:.1f} files/min, {chunks_per_min:.1f} chunks/min"
                        )

                if stats_dict.get("failed_files", 0) > 0:
                    console.print(
                        f"⚠️  Failed files: {stats_dict.get('failed_files', 0)}",
                        style="yellow",
                    )

                # Success - break out of retry loop
                return 0

            elif status == "already_running":
                console.print("[yellow]⚠ Indexing already in progress[/yellow]")
                return 0
            elif status == "error":
                console.print(f"[red]❌ Indexing failed: {message}[/red]")
                return 1
            else:
                console.print(f"[yellow]⚠ Unexpected status: {status}[/yellow]")
                console.print(f"[dim]Message: {message}[/dim]")
                return 1

        except Exception as e:
            # Clean up progress display on error
            if rich_live_manager:
                try:
                    rich_live_manager.stop_display()
                except Exception:
                    pass
            if progress_manager:
                try:
                    progress_manager.stop_progress()
                except Exception:
                    pass

            # Close connection on error
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

            # Retry logic with auto-start (EXACTLY like query command)
            if restart_attempt < 2:
                # Still have restart attempts left
                console.print(
                    f"[yellow]⚠️  Daemon connection failed, attempting restart ({restart_attempt + 1}/2)[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")

                # Clean up stale socket before restart
                _cleanup_stale_socket(socket_path)
                _start_daemon(config_path)

                # Wait longer for daemon to fully start
                time.sleep(1.0)
                continue
            else:
                # Exhausted all restart attempts
                console.print(
                    "[yellow]ℹ️  Daemon unavailable after 2 restart attempts, using standalone mode[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")
                console.print("[dim]Tip: Check daemon with 'cidx daemon status'[/dim]")

                # Clean kwargs to avoid duplicate parameter errors
                clean_kwargs = {
                    k: v
                    for k, v in kwargs.items()
                    if k
                    not in [
                        "enable_fts",
                        "batch_size",
                        "reconcile",
                        "files_count_to_process",
                        "detect_deletions",
                    ]
                }

                return _index_standalone(
                    force_reindex=force_reindex,
                    enable_fts=kwargs.get("enable_fts", False),
                    batch_size=kwargs.get("batch_size", 50),
                    reconcile=kwargs.get("reconcile", False),
                    files_count_to_process=kwargs.get("files_count_to_process"),
                    detect_deletions=kwargs.get("detect_deletions", False),
                    **clean_kwargs,
                )

    # Should never reach here
    return 1


def _watch_standalone(
    debounce: float = 1.0,
    batch_size: int = 50,
    initial_sync: bool = True,
    enable_fts: bool = False,
    **kwargs,
) -> int:
    """
    Fallback to standalone watch execution.

    This imports the full CLI and executes watch locally without daemon.

    Args:
        debounce: Debounce time in seconds
        batch_size: Batch size for indexing
        initial_sync: Whether to do initial sync before watching
        enable_fts: Whether to enable FTS indexing
        **kwargs: Additional watch parameters

    Returns:
        Exit code (0 = success)
    """
    from .cli import watch as cli_watch
    from .mode_detection.command_mode_detector import (
        CommandModeDetector,
        find_project_root,
    )
    import click

    try:
        # Setup context object with mode detection
        project_root = find_project_root(Path.cwd())
        mode_detector = CommandModeDetector(project_root)
        mode = mode_detector.detect_mode()

        # Create click context
        ctx = click.Context(click.Command("watch"))
        ctx.obj = {
            "mode": mode,
            "project_root": project_root,
            "standalone": True,  # Prevent daemon delegation
        }

        # Load config manager if in local mode
        if mode == "local" and project_root:
            try:
                from .config import ConfigManager

                config_manager = ConfigManager.create_with_backtrack(project_root)
                ctx.obj["config_manager"] = config_manager
            except Exception:
                pass  # Config might not exist yet

        # Call watch function directly with mapped parameters
        # CLI watch uses 'fts' parameter, not 'enable_fts'
        with ctx:
            cli_watch(
                ctx,
                debounce=debounce,
                batch_size=batch_size,
                initial_sync=initial_sync,
                fts=enable_fts,
            )
        return 0
    except Exception as e:
        console.print(f"[red]Watch failed: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


def _watch_via_daemon(
    debounce: float = 1.0,
    batch_size: int = 50,
    initial_sync: bool = True,
    enable_fts: bool = False,
    daemon_config: Optional[Dict] = None,
    **kwargs,
) -> int:
    """
    Delegate watch command to daemon.

    Implements watch mode via daemon RPC:
    1. Connects to daemon
    2. Calls exposed_watch_start with parameters
    3. Daemon handles file watching and indexing
    4. Returns immediately, watch runs in background

    Args:
        debounce: Debounce time in seconds for file change detection
        batch_size: Batch size for indexing operations
        initial_sync: Whether to perform initial sync before watching
        enable_fts: Whether to enable FTS indexing
        daemon_config: Daemon configuration with retry delays
        **kwargs: Additional watch parameters

    Returns:
        Exit code (0 = success)
    """
    config_path = _find_config_file()
    if not config_path:
        console.print("[yellow]No config found, using standalone mode[/yellow]")
        return _watch_standalone(
            debounce=debounce,
            batch_size=batch_size,
            initial_sync=initial_sync,
            enable_fts=enable_fts,
            **kwargs,
        )

    socket_path = _get_socket_path(config_path)

    # Use default daemon config if not provided
    if daemon_config is None:
        from .config import ConfigManager

        config_manager = ConfigManager.create_with_backtrack(Path.cwd())
        daemon_config = config_manager.get_daemon_config()

    conn = None
    try:
        # Connect to daemon
        conn = _connect_to_daemon(socket_path, daemon_config)

        # Execute watch via daemon
        result = conn.root.exposed_watch_start(
            project_path=str(Path.cwd()),
            debounce_seconds=debounce,
            batch_size=batch_size,
            initial_sync=initial_sync,
            enable_fts=enable_fts,
        )

        # Extract result data BEFORE closing connection
        # RPyC proxies become invalid after connection closes
        status = result.get("status", "unknown")
        message = result.get("message", "")

        # Close connection AFTER extracting data
        conn.close()

        # Display success message based on status
        if status == "success":
            console.print("[green]✓ Watch mode started in daemon[/green]")
            console.print("[dim]Monitoring file changes in background...[/dim]")
            console.print("[dim]Run 'cidx watch-stop' to stop watching[/dim]")
            return 0
        elif status == "error":
            console.print(f"[yellow]⚠ Watch start failed: {message}[/yellow]")
            return 1
        else:
            console.print(f"[yellow]⚠ Unexpected status: {status}[/yellow]")
            return 1

    except Exception as e:
        # Close connection on error
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        console.print(f"[yellow]Failed to start watch via daemon: {e}[/yellow]")
        console.print("[yellow]Falling back to standalone mode[/yellow]")

        return _watch_standalone(
            debounce=debounce,
            batch_size=batch_size,
            initial_sync=initial_sync,
            enable_fts=enable_fts,
            **kwargs,
        )


def _query_temporal_via_daemon(
    query_text: str,
    time_range: str,
    daemon_config: Dict,
    project_root: Path,
    limit: int = 10,
    languages: Optional[tuple] = None,
    exclude_languages: Optional[tuple] = None,
    path_filter: Optional[tuple] = None,
    exclude_path: Optional[tuple] = None,
    min_score: Optional[float] = None,
    accuracy: str = "balanced",
    chunk_type: Optional[str] = None,
    quiet: bool = False,
) -> int:
    """Delegate temporal query to daemon with crash recovery.

    Implements 2-attempt restart recovery for temporal queries, following
    the IDENTICAL pattern as _query_via_daemon() for HEAD collection queries.

    Args:
        query_text: Query string
        time_range: Time range filter (e.g., "last-7-days", "2024-01-01..2024-12-31")
        daemon_config: Daemon configuration
        project_root: Project root directory
        limit: Result limit
        languages: Language filters (include) as tuple
        exclude_languages: Language filters (exclude) as tuple
        path_filter: Path pattern filters (include) as tuple
        exclude_path: Path pattern filters (exclude) as tuple
        min_score: Minimum similarity score
        accuracy: Accuracy mode (fast/balanced/high)
        chunk_type: Filter by chunk type ("commit_message" or "commit_diff")
        quiet: Suppress non-essential output

    Returns:
        Exit code (0 = success)
    """
    config_path = _find_config_file()
    if not config_path:
        console.print("[yellow]No config found, using standalone mode[/yellow]")
        return 1

    socket_path = _get_socket_path(config_path)

    # Crash recovery: up to 2 restart attempts (IDENTICAL to HEAD query pattern)
    for restart_attempt in range(3):  # Initial + 2 restarts
        conn = None
        try:
            # Connect to daemon
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Execute temporal query via daemon
            result = conn.root.exposed_query_temporal(
                project_path=str(project_root),
                query=query_text,
                time_range=time_range,
                limit=limit,
                languages=list(languages) if languages else None,
                exclude_languages=(
                    list(exclude_languages) if exclude_languages else None
                ),
                path_filter=list(path_filter) if path_filter else None,
                exclude_path=list(exclude_path) if exclude_path else None,
                min_score=min_score or 0.0,
                accuracy=accuracy,
                chunk_type=chunk_type,
            )

            # Check for errors
            if "error" in result:
                console.print(f"[red]❌ {result['error']}[/red]")
                try:
                    conn.close()
                except Exception:
                    pass
                return 1

            # Display results (while connection is still open)
            # Use rich temporal display formatting (same as standalone mode)
            from .utils.temporal_display import display_temporal_results

            display_temporal_results(result, quiet=quiet)

            # Close connection after displaying results
            try:
                conn.close()
            except Exception:
                pass

            return 0

        except Exception as e:
            # Close connection on error
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

            # Connection or query failed
            if restart_attempt < 2:
                # Still have restart attempts left
                console.print(
                    f"[yellow]⚠️  Daemon connection failed, attempting restart ({restart_attempt + 1}/2)[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")

                # Clean up stale socket before restart
                _cleanup_stale_socket(socket_path)
                _start_daemon(config_path)

                # Wait longer for daemon to fully start
                time.sleep(1.0)
                continue
            else:
                # Exhausted all restart attempts - fall back to standalone
                console.print(
                    "[yellow]ℹ️  Daemon unavailable after 2 restart attempts, using standalone mode[/yellow]"
                )
                console.print(f"[dim](Error: {e})[/dim]")
                console.print("[dim]Tip: Check daemon with 'cidx daemon status'[/dim]")
                return 1

    # Should never reach here
    return 1


def rebuild_fts_via_daemon(config_manager, console) -> int:
    """Delegate FTS rebuild to daemon."""
    config_path = config_manager.config_path
    socket_path = _get_socket_path(config_path)
    daemon_config = config_manager.get_daemon_config()

    _start_daemon(config_path)
    conn = _connect_to_daemon(socket_path, daemon_config)

    # Simple callback for progress display
    def progress_callback(current, total, file_path, info=""):
        if total == 0:
            console.print(f"ℹ️  {info}")
        else:
            console.print(f"📄 {current}/{total}: {file_path}")

    result = conn.root.exposed_rebuild_fts_index(
        project_path=str(Path.cwd()),
        callback=progress_callback,
    )

    # Extract data BEFORE closing connection (RPyC proxies become invalid after close)
    status = str(result.get("status", "unknown"))
    error_msg = str(result.get("error", ""))

    conn.close()

    if status == "success":
        console.print("✅ FTS index rebuilt successfully!", style="green")
        return 0
    else:
        console.print(f"❌ Rebuild failed: {error_msg or 'Unknown error'}", style="red")
        return 1


def start_watch_via_daemon(project_root: Path, **kwargs: Any) -> bool:
    """Start watch mode via daemon delegation (Story #472).

    This function enables non-blocking watch mode through the daemon,
    allowing the CLI to return immediately while watch continues in
    the daemon background.

    Args:
        project_root: Project root path
        **kwargs: Additional watch parameters (debounce_seconds, etc.)

    Returns:
        True if delegation succeeded, False if should fall back to standalone
    """
    try:
        from .config import ConfigManager

        # Check if daemon is configured
        config_manager = ConfigManager.create_with_backtrack(project_root)
        config = config_manager.get_config()

        if not getattr(config, "daemon", False):
            logger.debug("Daemon not configured, using standalone watch")
            return False

        # Try to connect to daemon using RPyC
        socket_path = _get_socket_path(config_manager.config_path)
        daemon_config = {"retry_delays_ms": [100, 200, 500]}

        try:
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Check if daemon is running
            ping_result = conn.root.ping()
            if not ping_result or ping_result.get("status") != "ok":
                logger.debug("Daemon not responding, falling back to standalone")
                conn.close()
                return False

            # Start watch via daemon (non-blocking)
            console.print("🚀 Starting watch mode via daemon...", style="blue")
            result = conn.root.watch_start(str(project_root), **kwargs)

            if result.get("status") == "success":
                console.print(
                    "✅ Watch started in daemon (non-blocking mode)", style="green"
                )
                console.print("   Watch continues running in background", style="dim")
                console.print("   Use 'cidx watch-stop' to stop watching", style="dim")
                conn.close()
                return True
            else:
                error = result.get("message", "Unknown error")
                console.print(f"⚠️ Daemon watch start failed: {error}", style="yellow")
                console.print("   Falling back to standalone mode...", style="dim")
                conn.close()
                return False

        except Exception as e:
            logger.debug(f"Failed to connect to daemon: {e}")
            return False

    except Exception as e:
        logger.debug(f"Daemon delegation failed: {e}")
        # Don't print warnings for expected fallback cases
        return False


def stop_watch_via_daemon(project_root: Path) -> Dict[str, Any]:
    """Stop watch mode via daemon delegation (Story #472).

    Args:
        project_root: Project root path

    Returns:
        Result dictionary with status and message
    """
    try:
        from .config import ConfigManager

        config_manager = ConfigManager.create_with_backtrack(project_root)
        socket_path = _get_socket_path(config_manager.config_path)
        daemon_config = {"retry_delays_ms": [100, 200, 500]}

        try:
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Stop watch via daemon
            result = conn.root.watch_stop(str(project_root))
            conn.close()
            return result  # type: ignore[no-any-return]

        except Exception as e:
            return {"status": "error", "message": f"Failed to connect to daemon: {e}"}

    except Exception as e:
        logger.error(f"Failed to stop watch via daemon: {e}")
        return {"status": "error", "message": str(e)}


def get_watch_status_via_daemon(project_root: Path) -> Dict[str, Any]:
    """Get watch status via daemon (Story #472).

    Args:
        project_root: Project root path

    Returns:
        Status dictionary with running state and stats
    """
    try:
        from .config import ConfigManager

        config_manager = ConfigManager.create_with_backtrack(project_root)
        socket_path = _get_socket_path(config_manager.config_path)
        daemon_config = {"retry_delays_ms": [100, 200, 500]}

        try:
            conn = _connect_to_daemon(socket_path, daemon_config)

            # Get watch status via daemon
            result = conn.root.watch_status()
            conn.close()
            return result  # type: ignore[no-any-return]

        except Exception as e:
            return {"running": False, "message": f"Failed to connect to daemon: {e}"}

    except Exception as e:
        logger.error(f"Failed to get watch status via daemon: {e}")
        return {"running": False, "message": str(e)}
