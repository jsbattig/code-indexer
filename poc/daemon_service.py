"""Minimal RPyC daemon service for performance PoC.

This is a Proof of Concept daemon that validates the RPyC architecture
performance improvements. NOT production code.

Key Features:
- Socket binding as atomic lock (no PID files)
- Pre-import heavy modules (Rich, argparse) on startup
- Query caching simulation (5ms cache hit)
- Unix socket at /tmp/cidx-poc-daemon.sock
"""

import socket
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import rpyc
from rpyc.utils.server import ThreadedServer


SOCKET_PATH = "/tmp/cidx-poc-daemon.sock"


class CIDXDaemonService(rpyc.Service):
    """Minimal CIDX daemon service for PoC.

    Exposes query methods via RPyC and caches results in memory.
    """

    def __init__(self):
        super().__init__()
        self.query_cache: Dict[str, Any] = {}
        self._preimport_heavy_modules()

    def _preimport_heavy_modules(self):
        """Pre-import heavy modules to reduce per-query overhead."""
        import argparse  # noqa: F401
        from rich.console import Console  # noqa: F401
        from rich.progress import Progress  # noqa: F401

    def on_connect(self, conn):
        """Called when client connects."""
        print(f"Client connected: {conn}")

    def on_disconnect(self, conn):
        """Called when client disconnects."""
        print(f"Client disconnected: {conn}")

    def exposed_query(
        self,
        query_text: str,
        search_mode: str = "semantic",
        limit: int = 10,
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute query and return results.

        For PoC: Returns cached results (5ms simulation) or simulated results.

        Args:
            query_text: Search query text
            search_mode: One of 'semantic', 'fts', 'hybrid'
            limit: Maximum results to return
            language: Optional language filter

        Returns:
            Dict with 'results', 'count', 'timing_ms' keys
        """
        start_time = time.perf_counter()

        # Create cache key
        cache_key = f"{search_mode}:{query_text}:{limit}:{language}"

        # Check cache
        if cache_key in self.query_cache:
            # Simulate 5ms cache hit
            time.sleep(0.005)
            cached_result: Dict[str, Any] = self.query_cache[cache_key].copy()
            cached_result["cached"] = True
            cached_result["timing_ms"] = (time.perf_counter() - start_time) * 1000
            return cached_result

        # Simulate query processing (not cached)
        # For PoC, return mock results
        results = self._simulate_query(query_text, search_mode, limit, language)

        # Cache results
        self.query_cache[cache_key] = results

        results["cached"] = False
        results["timing_ms"] = (time.perf_counter() - start_time) * 1000
        return results

    def _simulate_query(
        self, query_text: str, search_mode: str, limit: int, language: Optional[str]
    ) -> Dict[str, Any]:
        """Simulate query execution (PoC only).

        In production, this would load HNSW indexes and execute real searches.
        """
        # Simulate different query times based on mode
        if search_mode == "semantic":
            time.sleep(0.02)  # 20ms simulation
        elif search_mode == "fts":
            time.sleep(0.01)  # 10ms simulation
        elif search_mode == "hybrid":
            time.sleep(0.03)  # 30ms simulation

        return {
            "results": [
                {
                    "file": f"/mock/file{i}.py",
                    "score": 0.9 - (i * 0.05),
                    "snippet": f"Mock result {i} for: {query_text}",
                }
                for i in range(min(limit, 5))
            ],
            "count": min(limit, 5),
            "mode": search_mode,
        }

    def exposed_ping(self) -> str:
        """Ping endpoint for RPC overhead measurement."""
        return "pong"

    def exposed_get_stats(self) -> Dict[str, Any]:
        """Get daemon statistics."""
        return {
            "cache_size": len(self.query_cache),
            "cache_keys": list(self.query_cache.keys()),
        }


def start_daemon(socket_path: str = SOCKET_PATH):
    """Start the daemon service.

    Uses socket binding as atomic lock. If socket is already bound,
    another daemon is running and this will exit cleanly.

    Args:
        socket_path: Path to Unix socket

    Raises:
        SystemExit: If socket already bound (daemon running)
    """
    # Clean up stale socket file
    if Path(socket_path).exists():
        # Try to connect to check if daemon is actually running
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(socket_path)
            sock.close()
            # Connection succeeded, daemon is running
            print(f"Daemon already running on {socket_path}", file=sys.stderr)
            sys.exit(1)
        except (ConnectionRefusedError, FileNotFoundError):
            # Stale socket, clean it up
            Path(socket_path).unlink()
            sock.close()

    # Create service
    service = CIDXDaemonService()

    # Create server on Unix socket
    try:
        server = ThreadedServer(
            service,
            socket_path=socket_path,
            protocol_config={
                "allow_public_attrs": True,
                "allow_pickle": True,
            },
        )

        print(f"CIDX daemon started on {socket_path}")
        print("Press Ctrl+C to stop")

        # Start server (blocks)
        server.start()

    except OSError as e:
        if "Address already in use" in str(e):
            print(f"Daemon already running on {socket_path}", file=sys.stderr)
            sys.exit(1)
        raise
    finally:
        # Clean up socket on exit
        if Path(socket_path).exists():
            Path(socket_path).unlink()


if __name__ == "__main__":
    start_daemon()
