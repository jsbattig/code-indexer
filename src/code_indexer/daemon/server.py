"""Daemon server startup with Unix socket binding.

Provides socket-based atomic lock for single daemon instance per project.
"""

import logging
import signal
import socket
import sys
from pathlib import Path

from rpyc.utils.server import ThreadedServer

from .service import CIDXDaemonService

logger = logging.getLogger(__name__)


def start_daemon(config_path: Path) -> None:
    """Start daemon with socket binding as atomic lock.

    Socket binding provides atomic exclusion - only one daemon can bind
    to a socket at a time. No PID files needed.

    Args:
        config_path: Path to project's .code-indexer/config.json

    Raises:
        SystemExit: If daemon already running or socket binding fails
    """
    # Derive socket path from config directory
    config_dir = config_path.parent
    socket_path = config_dir / "daemon.sock"

    logger.info(f"Starting CIDX daemon for {config_dir}")

    # Clean stale socket if exists
    _clean_stale_socket(socket_path)

    # Setup signal handlers for graceful shutdown
    _setup_signal_handlers(socket_path)

    # Create shared service instance (shared across all connections)
    # This ensures cache and watch state are shared, not per-connection
    shared_service = CIDXDaemonService()

    # Create and start RPyC server with shared service instance
    try:
        server = ThreadedServer(
            shared_service,  # Pass instance, not class
            socket_path=str(socket_path),
            protocol_config={
                "allow_public_attrs": True,
                "allow_pickle": True,
                "sync_request_timeout": 300,  # 5 minute timeout for long operations
            },
        )

        logger.info(f"CIDX daemon listening on {socket_path}")
        print(f"CIDX daemon started on {socket_path}")

        # Blocks here until shutdown
        server.start()

    except OSError as e:
        if "Address already in use" in str(e):
            logger.error(f"Daemon already running on {socket_path}")
            print(f"ERROR: Daemon already running on {socket_path}", file=sys.stderr)
            sys.exit(1)
        raise

    finally:
        # Cleanup socket on exit
        if socket_path.exists():
            socket_path.unlink()
            logger.info(f"Cleaned up socket {socket_path}")


def _clean_stale_socket(socket_path: Path) -> None:
    """Clean stale socket if no daemon is listening.

    Args:
        socket_path: Path to Unix socket

    Raises:
        SystemExit: If daemon is already running
    """
    if not socket_path.exists():
        return

    # Try to connect to see if daemon is actually running
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(str(socket_path))
        sock.close()

        # Connection succeeded - daemon is running
        logger.error(f"Daemon already running on {socket_path}")
        print(f"ERROR: Daemon already running on {socket_path}", file=sys.stderr)
        sys.exit(1)

    except (ConnectionRefusedError, FileNotFoundError):
        # Connection failed - socket is stale, remove it
        logger.info(f"Removing stale socket {socket_path}")
        socket_path.unlink()
        sock.close()


def _setup_signal_handlers(socket_path: Path) -> None:
    """Setup signal handlers for graceful shutdown.

    Args:
        socket_path: Path to Unix socket to clean up
    """

    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down")
        if socket_path.exists():
            socket_path.unlink()
        sys.exit(0)

    # Handle SIGTERM and SIGINT
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
