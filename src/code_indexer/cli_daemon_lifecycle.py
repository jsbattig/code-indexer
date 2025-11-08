"""
Daemon lifecycle commands for CLI.

This module implements commands for controlling daemon lifecycle:
- start: Manually start daemon
- stop: Gracefully stop daemon
- watch-stop: Stop watch mode in daemon
"""

import time
from pathlib import Path
from rich.console import Console
from .config import ConfigManager
from .cli_daemon_delegation import _start_daemon

console = Console()


def start_daemon_command() -> int:
    """
    Start CIDX daemon manually.

    Only available when daemon.enabled: true in config.
    Normally daemon auto-starts on first query, but this allows
    explicit control for debugging or pre-loading.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    daemon_config = config_manager.get_daemon_config()

    if not daemon_config or not daemon_config.get("enabled"):
        console.print("[red]Daemon mode not enabled[/red]")
        console.print("Enable with: cidx config --daemon")
        return 1

    socket_path = config_manager.get_socket_path()

    # Check if already running
    try:
        from rpyc.utils.factory import unix_connect

        conn = unix_connect(str(socket_path))
        # Try to get status to verify it's responsive
        try:
            conn.root.exposed_get_status()
            conn.close()
            console.print("[yellow]Daemon already running[/yellow]")
            console.print(f"  Socket: {socket_path}")
            return 0
        except Exception:
            # Connected but not responsive, close and restart
            conn.close()
    except Exception:
        # Not running, proceed to start
        pass

    # Start daemon
    console.print("Starting daemon...")
    _start_daemon(config_manager.config_path)

    # Wait and verify startup
    time.sleep(1)

    try:
        from rpyc.utils.factory import unix_connect

        conn = unix_connect(str(socket_path))
        _ = conn.root.exposed_get_status()
        conn.close()

        console.print("[green]✓ Daemon started[/green]")
        console.print(f"  Socket: {socket_path}")
        return 0
    except Exception as e:
        console.print("[red]Failed to start daemon[/red]")
        console.print(f"[dim](Error: {e})[/dim]")
        return 1


def stop_daemon_command() -> int:
    """
    Stop CIDX daemon gracefully.

    Gracefully shuts down daemon:
    - Stops any active watch
    - Clears cache
    - Closes connections
    - Exits daemon process

    Returns:
        Exit code (0 = success, 1 = error)
    """
    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    daemon_config = config_manager.get_daemon_config()

    if not daemon_config or not daemon_config.get("enabled"):
        console.print("[yellow]Daemon mode not enabled[/yellow]")
        return 1

    socket_path = config_manager.get_socket_path()

    # Try to connect
    try:
        from rpyc.utils.factory import unix_connect

        conn = unix_connect(str(socket_path))
    except Exception:
        console.print("[yellow]Daemon not running[/yellow]")
        return 0

    # Stop watch if running
    try:
        watch_status = conn.root.exposed_watch_status()
        if watch_status.get("watching"):
            console.print("Stopping watch...")
            conn.root.exposed_watch_stop(str(Path.cwd()))
    except Exception:
        # Watch might not be running or might fail, continue with shutdown
        pass

    # Graceful shutdown
    console.print("Stopping daemon...")
    try:
        conn.root.exposed_shutdown()
    except Exception:
        # Connection closed is expected during shutdown
        pass

    # Wait for shutdown
    time.sleep(0.5)

    # Verify stopped
    try:
        from rpyc.utils.factory import unix_connect

        test_conn = unix_connect(str(socket_path))
        test_conn.close()
        console.print("[red]Failed to stop daemon[/red]")
        return 1
    except Exception:
        # Connection refused = daemon stopped successfully
        console.print("[green]✓ Daemon stopped[/green]")
        return 0


def watch_stop_command() -> int:
    """
    Stop watch mode running in daemon.

    Only available in daemon mode. Use this to stop watch
    without stopping the entire daemon. Queries continue to work.

    Returns:
        Exit code (0 = success, 1 = error)
    """
    config_manager = ConfigManager.create_with_backtrack(Path.cwd())
    daemon_config = config_manager.get_daemon_config()

    if not daemon_config or not daemon_config.get("enabled"):
        console.print("[red]Only available in daemon mode[/red]")
        console.print("Enable with: cidx config --daemon")
        return 1

    socket_path = config_manager.get_socket_path()

    try:
        from rpyc.utils.factory import unix_connect

        conn = unix_connect(str(socket_path))
        stats = conn.root.exposed_watch_stop(str(Path.cwd()))
        conn.close()

        if stats.get("status") == "not_running":
            console.print("[yellow]Watch not running[/yellow]")
            return 1

        console.print("[green]✓ Watch stopped[/green]")
        console.print(f"  Files processed: {stats.get('files_processed', 0)}")
        console.print(f"  Updates applied: {stats.get('updates_applied', 0)}")
        return 0

    except Exception as e:
        console.print("[red]Daemon not running[/red]")
        console.print(f"[dim](Error: {e})[/dim]")
        return 1
