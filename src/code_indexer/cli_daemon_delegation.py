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
from pathlib import Path
from typing import Optional, Dict, Any
from rich.console import Console

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

    Args:
        config_path: Path to config.json file

    Returns:
        Path to daemon socket file
    """
    return config_path.parent / "daemon.sock"


def _connect_to_daemon(socket_path: Path, daemon_config: Dict) -> Any:
    """
    Establish RPyC connection to daemon with exponential backoff.

    Args:
        socket_path: Path to Unix domain socket
        daemon_config: Daemon configuration with retry_delays_ms

    Returns:
        RPyC connection object

    Raises:
        ConnectionError: If all retries exhausted
    """
    try:
        from rpyc.utils.factory import unix_connect
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
            return unix_connect(str(socket_path))
        except (ConnectionRefusedError, FileNotFoundError) as e:
            last_error = e
            if attempt < len(retry_delays) - 1:
                time.sleep(delay)
            else:
                # Last attempt failed, re-raise
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

    except Exception as e:
        console.print(f"[yellow]Daemon not available: {e}[/yellow]")
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
        daemon_only_keys = {'daemon_config', 'force_full'}
        cli_kwargs = {k: v for k, v in kwargs.items() if k not in daemon_only_keys}

        # Map enable_fts to fts (CLI uses 'fts' parameter)
        if 'enable_fts' in cli_kwargs:
            cli_kwargs['fts'] = cli_kwargs.pop('enable_fts')

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
        cli_kwargs['clear'] = force_reindex
        cli_kwargs['reconcile'] = False
        cli_kwargs['batch_size'] = cli_kwargs.get('batch_size', 50)
        cli_kwargs['files_count_to_process'] = None
        cli_kwargs['detect_deletions'] = False
        cli_kwargs['rebuild_indexes'] = False
        cli_kwargs['rebuild_index'] = False
        cli_kwargs['fts'] = cli_kwargs.get('fts', False)
        cli_kwargs['rebuild_fts_index'] = False

        # Call index function directly
        with ctx:
            cli_index(ctx, **cli_kwargs)
        return 0
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

    CRITICAL UX FIX: This method now BLOCKS until indexing completes,
    displaying a Rich progress bar identical to standalone mode via RPyC callbacks.

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
    try:
        # Connect to daemon
        conn = _connect_to_daemon(socket_path, daemon_config)

        # CRITICAL: Create progress handler for Rich progress bar display
        from .progress.multi_threaded_display import MultiThreadedProgressManager
        from .progress.rich_live_manager import RichLiveManager

        # Initialize progress manager and Rich Live display (IDENTICAL to standalone)
        progress_manager = MultiThreadedProgressManager()
        rich_live_manager = RichLiveManager(progress_manager)

        # Start Rich Live display before indexing
        rich_live_manager.start_display()

        # Create progress callback that updates Rich progress bar
        def progress_callback(current: int, total: int, file_path: Path, info: str = "") -> None:
            """RPyC-compatible progress callback for real-time updates."""
            progress_manager.update_progress(
                current_file=current,
                total_files=total,
                current_file_path=str(file_path),
                info=info,
            )

        # Map parameters for daemon
        daemon_kwargs = {
            'force_full': force_reindex,
            'enable_fts': kwargs.get('enable_fts', False),
            'batch_size': kwargs.get('batch_size', 50),
        }

        # Execute indexing (BLOCKS until complete, streams progress via callback)
        # RPyC automatically handles callback streaming to client
        result = conn.root.exposed_index(
            project_path=str(Path.cwd()),
            callback=progress_callback,  # Real-time progress streaming
            **daemon_kwargs,
        )

        # Stop progress display before showing completion
        progress_manager.stop_progress()
        rich_live_manager.stop_display()

        # Extract result data BEFORE closing connection
        status = result.get("status", "unknown")
        message = result.get("message", "")
        stats_dict = result.get("stats", {})

        # Close connection AFTER extracting data
        conn.close()

        # Display completion status (IDENTICAL to standalone)
        if status == "completed":
            cancelled = stats_dict.get("cancelled", False)
            if cancelled:
                console.print("🛑 Indexing cancelled!", style="yellow")
                console.print(f"📄 Files processed before cancellation: {stats_dict.get('files_processed', 0)}", style="yellow")
                console.print(f"📦 Chunks indexed before cancellation: {stats_dict.get('chunks_created', 0)}", style="yellow")
                console.print("💾 Progress saved - you can resume indexing later", style="blue")
            else:
                console.print("✅ Indexing complete!", style="green")
                console.print(f"📄 Files processed: {stats_dict.get('files_processed', 0)}")
                console.print(f"📦 Chunks indexed: {stats_dict.get('chunks_created', 0)}")

            duration = stats_dict.get("duration_seconds", 0)
            console.print(f"⏱️  Duration: {duration:.2f}s")

            # Calculate throughput
            if duration > 0:
                files_per_min = (stats_dict.get('files_processed', 0) / duration) * 60
                chunks_per_min = (stats_dict.get('chunks_created', 0) / duration) * 60
                console.print(f"🚀 Throughput: {files_per_min:.1f} files/min, {chunks_per_min:.1f} chunks/min")

            if stats_dict.get('failed_files', 0) > 0:
                console.print(f"⚠️  Failed files: {stats_dict.get('failed_files', 0)}", style="yellow")

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
        try:
            progress_manager.stop_progress()
            rich_live_manager.stop_display()
        except Exception:
            pass

        # Close connection on error
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

        console.print(f"[yellow]Failed to index via daemon: {e}[/yellow]")
        console.print("[yellow]Falling back to standalone mode[/yellow]")

        return _index_standalone(force_reindex=force_reindex, **kwargs)


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
